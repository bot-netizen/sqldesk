from unittest import mock

from sqldesk.models import Event, db
from tests import BaseTestCase


class AdminEndpointTestMixin:
    """
    Every admin endpoint answers the same three people the same three ways.

    Worth having on each one rather than once, because the decorator order
    decides it: `@require_super_admin` above `@login_required` checks the
    permission of a user who has not been loaded yet, and a logged-out visitor
    gets 403 instead of being sent to sign in.
    """

    path = None

    def _get(self, user):
        # `org=False`: the admin routes are not org-scoped, so a slug prefix
        # misses them and falls through to the SPA shell -- a 200 of HTML that
        # looks like success and is not.
        return self.make_request("get", self.path, user=user, org=False)

    def test_a_super_admin_may_look(self):
        admin = self.factory.create_admin()
        db.session.commit()

        self.assertEqual(self._get(admin).status_code, 200)

    def test_an_ordinary_user_may_not(self):
        self.assertEqual(self._get(self.factory.user).status_code, 403)

    def test_a_logged_out_visitor_is_asked_to_sign_in(self):
        # 404 rather than 403, and that is the app's own answer for anything
        # under /api/ (see redirect_to_login): a stranger is not told which
        # endpoints exist. What matters here is that it is not 403, which is
        # what the permission check returns when it runs ahead of the login
        # check and inspects a user who was never loaded.
        rv = self._get(False)

        self.assertEqual(rv.status_code, 404)
        self.assertIn("login", rv.json["message"].lower())


class TestOutdatedQueries(AdminEndpointTestMixin, BaseTestCase):
    path = "/api/admin/queries/outdated"

    def test_says_nothing_rather_than_failing_before_the_manager_has_run(self):
        # `sqldesk:status` does not exist until refresh_queries has run once.
        # Reading `last_refresh_at` off it unguarded turned a fresh install's
        # first look at this page into a 500.
        admin = self.factory.create_admin()
        db.session.commit()

        rv = self._get(admin)

        self.assertEqual(rv.status_code, 200)
        self.assertIsNone(rv.json["updated_at"])
        self.assertEqual(rv.json["queries"], [])


class TestRqStatus(AdminEndpointTestMixin, BaseTestCase):
    path = "/api/admin/queries/rq_status"


class TestOverview(AdminEndpointTestMixin, BaseTestCase):
    path = "/api/admin/overview"

    def _overview(self):
        admin = self.factory.create_admin()
        db.session.commit()
        rv = self._get(admin)
        self.assertEqual(rv.status_code, 200)
        return rv.json

    def test_reports_every_section_in_one_read(self):
        # One endpoint on purpose: five would show five different moments.
        overview = self._overview()

        self.assertEqual(
            sorted(overview.keys()),
            ["activity", "limits", "queues", "running", "storage", "workers"],
        )

    def test_reads_the_real_postgres_limits(self):
        limits = self._overview()["limits"]["postgres"]

        self.assertGreater(limits["max"], 0)
        self.assertGreaterEqual(limits["used"], 1)  # this connection, at least
        self.assertLessEqual(limits["used_here"], limits["used"])

    def test_reports_both_redis_connections_separately(self):
        # They can be different servers, and the RQ one fills first.
        redis = self._overview()["limits"]["redis"]

        self.assertEqual(sorted(redis.keys()), ["app", "rq"])
        for side in redis.values():
            self.assertGreater(side["used_memory"], 0)

    def test_reports_what_the_tables_take(self):
        storage = self._overview()["storage"]

        self.assertGreater(storage["database"], 0)
        self.assertGreaterEqual(storage["events"], 0)
        self.assertGreaterEqual(storage["query_results"], 0)

    def test_counts_who_has_been_running_queries(self):
        busy = self.factory.create_user(name="Busy")
        quiet = self.factory.create_user(name="Quiet")
        for _ in range(3):
            self._record_execution(busy)
        self._record_execution(quiet)
        db.session.commit()

        activity = self._overview()["activity"]

        self.assertEqual(activity["executions"], 4)
        by_name = {u["name"]: u["executions"] for u in activity["top_users"]}
        self.assertEqual(by_name["Busy"], 3)
        self.assertEqual(by_name["Quiet"], 1)

    def test_reports_the_cache_hit_ratio(self):
        self._record_execution(self.factory.user, cache="hit")
        self._record_execution(self.factory.user, cache="miss")
        db.session.commit()

        self.assertEqual(self._overview()["activity"]["cache_hit_ratio"], 0.5)

    def test_a_ratio_of_nothing_is_not_zero(self):
        # No executions means the question does not apply, not that every
        # lookup missed.
        self.assertIsNone(self._overview()["activity"]["cache_hit_ratio"])

    def test_counts_only_query_executions(self):
        self._record_execution(self.factory.user)
        db.session.add(
            Event(
                org=self.factory.org,
                user=self.factory.user,
                action="view",
                object_type="dashboard",
            )
        )
        db.session.commit()

        self.assertEqual(self._overview()["activity"]["executions"], 1)

    def _record_execution(self, user, cache="miss"):
        db.session.add(
            Event(
                org=self.factory.org,
                user=user,
                action="execute_query",
                object_type="data_source",
                additional_properties={"cache": cache},
            )
        )


class TestOverviewRunningQueries(BaseTestCase):
    """
    What is running comes from RQ, not from `events`.

    A scheduled refresh never reaches `events` -- it goes through
    `enqueue_query` rather than `run_query` -- and those are exactly the ones
    that run long with nobody watching.
    """

    def _running(self, jobs):
        with mock.patch("sqldesk.monitor.started_job_ids", return_value=["a"]), mock.patch(
            "sqldesk.monitor.fetch_jobs", return_value=jobs
        ):
            from sqldesk.monitor import get_running_queries

            return get_running_queries()

    def test_names_the_query_the_user_and_the_data_source(self):
        query = self.factory.create_query(name="Revenue by region")
        db.session.commit()

        running = self._running(
            [
                {
                    "id": "job-1",
                    "name": "sqldesk.tasks.queries.execution.execute_query",
                    "origin": "queries",
                    "started_at": None,
                    "meta": {
                        "query_id": query.id,
                        "user_id": self.factory.user.id,
                        "data_source_id": self.factory.data_source.id,
                    },
                }
            ]
        )

        self.assertEqual(len(running), 1)
        self.assertEqual(running[0]["query_name"], "Revenue by region")
        self.assertEqual(running[0]["user_name"], self.factory.user.name)
        self.assertEqual(running[0]["data_source"], self.factory.data_source.name)

    def test_leaves_out_jobs_that_are_not_queries(self):
        running = self._running(
            [
                {
                    "id": "job-1",
                    "name": "sqldesk.tasks.general.record_event_task",
                    "origin": "default",
                    "started_at": None,
                    "meta": {},
                }
            ]
        )

        self.assertEqual(running, [])

    def test_a_scheduled_refresh_has_no_user_and_says_so(self):
        running = self._running(
            [
                {
                    "id": "job-1",
                    "name": "sqldesk.tasks.queries.execution.execute_query",
                    "origin": "scheduled_queries",
                    "started_at": None,
                    "meta": {"scheduled": True},
                }
            ]
        )

        self.assertTrue(running[0]["scheduled"])
        self.assertIsNone(running[0]["user_name"])

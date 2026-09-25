import datetime
from unittest import mock

from rq.exceptions import NoSuchJobError

from sqldesk import utils
from sqldesk.models import Event, db
from sqldesk.tasks.queries.maintenance import cleanup_events, cleanup_query_results
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

    def test_an_mcp_run_is_named_as_one(self):
        # An MCP run has a user -- whoever's API key it was -- but nobody is
        # watching it, which is what the admin needs to know before killing it.
        running = self._running(
            [
                {
                    "id": "job-1",
                    "name": "sqldesk.tasks.queries.execution.execute_query",
                    "origin": "queries",
                    "started_at": None,
                    "meta": {"user_id": self.factory.user.id, "mcp": True},
                }
            ]
        )

        self.assertTrue(running[0]["mcp"])
        self.assertEqual(running[0]["user_name"], self.factory.user.name)

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


class TestAdminActions(BaseTestCase):
    """
    The things an admin can do from the page, as opposed to look at.

    Each is recorded: ending someone else's work, or deleting rows, quietly is
    not on.
    """

    def _post(self, path, user):
        return self.make_request("post", path, user=user, org=False)

    def test_only_a_super_admin_may_kill_a_query(self):
        rv = self.make_request("delete", "/api/admin/jobs/anything", user=self.factory.user, org=False)

        self.assertEqual(rv.status_code, 403)

    @mock.patch("sqldesk.handlers.admin.Job")
    def test_killing_a_query_cancels_the_job(self, job_class):
        admin = self.factory.create_admin()
        db.session.commit()
        job = mock.Mock(meta={"query_id": 7, "user_id": 3})
        job_class.fetch.return_value = job

        rv = self.make_request("delete", "/api/admin/jobs/job-1", user=admin, org=False)

        self.assertEqual(rv.status_code, 200)
        job.cancel.assert_called_once()

    @mock.patch("sqldesk.handlers.admin.Job")
    def test_killing_an_unknown_job_is_a_404(self, job_class):
        admin = self.factory.create_admin()
        db.session.commit()
        job_class.fetch.side_effect = NoSuchJobError()

        rv = self.make_request("delete", "/api/admin/jobs/gone", user=admin, org=False)

        self.assertEqual(rv.status_code, 404)

    @mock.patch("sqldesk.handlers.admin.Queue")
    def test_cleanup_enqueues_the_job_that_already_exists(self, queue_class):
        # Not a second implementation of cleaning up: the same task the
        # scheduler runs every five minutes, asked for now.
        admin = self.factory.create_admin()
        db.session.commit()
        queue_class.return_value.enqueue.return_value = mock.Mock(id="job-9")

        rv = self._post("/api/admin/cleanup/query_results", admin)

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["job_id"], "job-9")
        self.assertEqual(queue_class.return_value.enqueue.call_args[0][0], cleanup_query_results)

    @mock.patch("sqldesk.handlers.admin.Queue")
    def test_events_cleanup_enqueues_its_own_task(self, queue_class):
        admin = self.factory.create_admin()
        db.session.commit()
        queue_class.return_value.enqueue.return_value = mock.Mock(id="job-10")

        rv = self._post("/api/admin/cleanup/events", admin)

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(queue_class.return_value.enqueue.call_args[0][0], cleanup_events)

    def test_an_ordinary_user_may_not_clean_up(self):
        for path in ("/api/admin/cleanup/query_results", "/api/admin/cleanup/events"):
            self.assertEqual(self._post(path, self.factory.user).status_code, 403)


class TestEventsCleanup(BaseTestCase):
    def _event(self, age_days):
        return Event(
            org=self.factory.org,
            user=self.factory.user,
            action="execute_query",
            object_type="data_source",
            created_at=utils.utcnow() - datetime.timedelta(days=age_days),
        )

    def test_removes_what_is_older_than_the_cutoff_and_keeps_the_rest(self):
        db.session.add(self._event(age_days=200))
        db.session.add(self._event(age_days=1))
        db.session.commit()

        deleted = cleanup_events()

        self.assertEqual(deleted, 1)
        self.assertEqual(Event.query.count(), 1)

    def test_deletes_nothing_when_everything_is_recent(self):
        db.session.add(self._event(age_days=1))
        db.session.commit()

        self.assertEqual(cleanup_events(), 0)
        self.assertEqual(Event.query.count(), 1)

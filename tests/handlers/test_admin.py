import datetime
import io
import zipfile
from unittest import mock

import yaml
from rq.exceptions import NoSuchJobError

from sqldesk import models, rq_redis_connection, utils
from sqldesk.ai.eval import record_score
from sqldesk.models import Event, db
from sqldesk.tasks import Job
from sqldesk.tasks.catalog import harvest_catalog, harvest_job_id
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


class TestRunningQueries(AdminEndpointTestMixin, BaseTestCase):
    path = "/api/admin/queries/running"

    def test_answers_with_only_what_is_in_flight(self):
        # The point of it being its own endpoint: the page behind it refreshes
        # four times as often as the overview, and must not drag table sizes
        # and an hour of event aggregation along each time.
        admin = self.factory.create_admin()
        db.session.commit()

        rv = self._get(admin)

        self.assertEqual(list(rv.json.keys()), ["running"])
        self.assertIsInstance(rv.json["running"], list)

    def test_reports_the_same_jobs_the_overview_does(self):
        # Two pages showing different answers to "what is running" is worse
        # than one page, so both read the same function.
        admin = self.factory.create_admin()
        db.session.commit()
        job = {"job_id": "abc", "query_id": 1, "user_id": None, "elapsed": 3.0}

        with mock.patch("sqldesk.handlers.admin.get_running_queries", return_value=[job]):
            rv = self._get(admin)

        self.assertEqual(rv.json["running"], [job])


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


class CatalogTestCase(BaseTestCase):
    """
    The catalog only exists where MCP is switched on, so its endpoints answer
    403 where it is not -- for administrators too. Every test below is about
    what somebody may do with a catalog that exists.
    """

    def setUp(self):
        super().setUp()
        feature = mock.patch("sqldesk.settings.FEATURE_AI", True)
        feature.start()
        self.addCleanup(feature.stop)


class TestWhoMayCurateTheCatalog(CatalogTestCase):
    """
    Curating is a feature an administrator hands to a group, not something
    only a super administrator may do: the person who knows what a table is
    for is rarely the person who runs the server.
    """

    def _curator(self, reads=True):
        """A curator who is not an admin; `reads` puts their group on the data source."""
        group = self.factory.create_group(
            name="Curators", permissions=models.Group.DEFAULT_PERMISSIONS + ["manage_catalog"]
        )
        db.session.add(group)
        db.session.commit()
        if reads:
            self.factory.data_source.add_group(group, view_only=True)
            db.session.commit()
        return self.factory.create_user(group_ids=[group.id])

    def _table(self, source=None):
        table = models.CatalogTable(
            org=self.factory.org, data_source_id=(source or self.factory.data_source).id, name="orders"
        )
        db.session.add(table)
        db.session.commit()
        return table

    def test_a_curator_who_is_not_an_admin_may_read_it(self):
        rv = self.make_request("get", "/api/catalog", user=self._curator(), org=False)
        self.assertEqual(200, rv.status_code)

    def test_and_may_describe_a_table(self):
        table = self._table()

        rv = self.make_request(
            "post",
            "/api/catalog/tables/{}".format(table.id),
            data={"description": "One row per order."},
            user=self._curator(),
            org=False,
        )

        self.assertEqual(200, rv.status_code)

    def test_but_only_on_data_sources_their_groups_can_read(self):
        """
        Curation can be granted to a group that is not on every data source.
        Until 0.7.7 such a curator could list another source's tables, export
        the SQL of its verified queries, and write the descriptions its users'
        models are fed.
        """
        table = self._table()
        curator = self._curator(reads=False)

        listed = self.make_request("get", "/api/catalog", user=curator, org=False)
        described = self.make_request(
            "post",
            "/api/catalog/tables/{}".format(table.id),
            data={"description": "Planted."},
            user=curator,
            org=False,
        )
        exported = self.make_request("get", "/api/catalog/export", user=curator, org=False, is_json=False)

        self.assertEqual([], [t["name"] for t in listed.json.get("tables", [])])
        self.assertEqual(404, described.status_code)
        db.session.refresh(table)
        self.assertIsNone(table.description)
        self.assertNotIn(b"orders", exported.data)

    def test_an_admin_sees_every_source(self):
        self._table()
        rv = self.make_request("get", "/api/catalog", user=self.factory.create_admin(), org=False)
        self.assertIn("orders", [t["name"] for t in rv.json["tables"]])

    def test_somebody_without_the_feature_may_not(self):
        rv = self.make_request("get", "/api/catalog", user=self.factory.user, org=False)
        self.assertEqual(403, rv.status_code)

    def test_nor_anybody_when_the_install_has_mcp_switched_off(self):
        curator = self._curator()
        with mock.patch("sqldesk.settings.FEATURE_AI", False):
            self.assertEqual(403, self.make_request("get", "/api/catalog", user=curator, org=False).status_code)
            admin = self.factory.create_admin()
            self.assertEqual(403, self.make_request("get", "/api/catalog", user=admin, org=False).status_code)

    def test_harvesting_is_still_an_admins_call(self):
        # It reads every data source's schema on the worker.
        curator = self._curator()
        rv = self.make_request("post", "/api/catalog/harvest", data={}, user=curator, org=False)
        self.assertEqual(403, rv.status_code)


class TestCatalogReview(CatalogTestCase):
    """
    Describing a table by hand. The ordering matters as much as the writing:
    nobody documents three thousand tables, so the list has to start with the
    ones anyone actually queries.
    """

    def _table(self, name, usage=0, description=None, source=None):
        table = models.CatalogTable(
            org=self.factory.org,
            data_source_id=self.factory.data_source.id,
            name=name,
            usage_count=usage,
            description=description,
            description_source=source,
        )
        db.session.add(table)
        db.session.commit()
        return table

    def test_it_needs_a_super_admin(self):
        self.assertEqual(403, self.make_request("get", "/api/catalog", user=self.factory.user, org=False).status_code)

    def test_most_used_first(self):
        self._table("rare", usage=1)
        self._table("popular", usage=90)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog", user=admin, org=False)

        self.assertEqual(["popular", "rare"], [t["name"] for t in rv.json["tables"]])

    def test_the_worklist_is_the_ones_without_a_sentence(self):
        self._table("described", usage=5, description="Known.", source="engine")
        self._table("bare", usage=4)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog?undescribed=1", user=admin, org=False)

        self.assertEqual(["bare"], [t["name"] for t in rv.json["tables"]])

    def test_writing_one_marks_it_as_a_persons(self):
        table = self._table("orders")
        admin = self.factory.create_admin()

        self.make_request(
            "post",
            "/api/catalog/tables/{}".format(table.id),
            data={"description": "  Orders, excluding the test tenant.  "},
            user=admin,
            org=False,
        )

        db.session.expire_all()
        stored = models.CatalogTable.query.get(table.id)
        self.assertEqual("Orders, excluding the test tenant.", stored.description)
        self.assertEqual("human", stored.description_source)

    def test_clearing_one_lets_the_engine_speak_again(self):
        table = self._table("orders", description="Mine.", source="human")
        admin = self.factory.create_admin()

        self.make_request(
            "post",
            "/api/catalog/tables/{}".format(table.id),
            data={"description": ""},
            user=admin,
            org=False,
        )

        db.session.expire_all()
        stored = models.CatalogTable.query.get(table.id)
        self.assertIsNone(stored.description)
        self.assertIsNone(stored.description_source)

    def test_another_orgs_table_is_not_found(self):
        other = self.factory.create_org()
        table = models.CatalogTable(org=other, data_source_id=self.factory.data_source.id, name="theirs")
        db.session.add(table)
        db.session.commit()
        admin = self.factory.create_admin()

        rv = self.make_request(
            "post",
            "/api/catalog/tables/{}".format(table.id),
            data={"description": "x"},
            user=admin,
            org=False,
        )

        self.assertEqual(404, rv.status_code)


class TestFindingAndHidingTables(CatalogTestCase):
    """
    Search, hide, and the two filters that make a long catalog workable.

    The page is sent the first 200 tables by usage. Until 0.7.3 that was all it
    could ever show: the limit was on the server, so a table past it was not
    merely off the page but unreachable from it.
    """

    def _table(self, name, usage=0, description=None, hidden=False):
        table = models.CatalogTable(
            org=self.factory.org,
            data_source_id=self.factory.data_source.id,
            name=name,
            usage_count=usage,
            description=description,
            description_source="human" if description else None,
            hidden=hidden,
        )
        db.session.add(table)
        return table

    def _get(self, query=""):
        admin = self.factory.create_admin()
        db.session.commit()
        return self.make_request("get", "/api/catalog{}".format(query), user=admin, org=False)

    def test_a_search_finds_a_table_past_the_first_two_hundred(self):
        for n in range(205):
            self._table("metric_{:03d}".format(n), usage=1000 - n)
        self._table("the_one_nobody_could_see", usage=0)

        everything = self._get()
        searched = self._get("?q=nobody_could")

        self.assertEqual(200, len(everything.json["tables"]))
        self.assertNotIn("the_one_nobody_could_see", [t["name"] for t in everything.json["tables"]])
        self.assertEqual(["the_one_nobody_could_see"], [t["name"] for t in searched.json["tables"]])

    def test_and_the_page_is_told_how_many_there_are_beyond_what_it_got(self):
        for n in range(205):
            self._table("metric_{:03d}".format(n))

        rv = self._get()

        self.assertEqual(205, rv.json["total"])
        self.assertEqual(200, rv.json["limit"])

    def test_a_search_reads_descriptions_too(self):
        self._table("t_0193", description="Every refund, one row per refund line.")
        self._table("orders")

        rv = self._get("?q=refund")

        self.assertEqual(["t_0193"], [t["name"] for t in rv.json["tables"]])

    def test_a_search_is_literal_not_a_pattern(self):
        # An underscore is a wildcard to LIKE; to somebody typing order_id it
        # is an underscore.
        self._table("order_id_map")
        self._table("orderXidXmap")

        rv = self._get("?q=order_id")

        self.assertEqual(["order_id_map"], [t["name"] for t in rv.json["tables"]])

    def test_hidden_tables_are_left_out(self):
        self._table("kept")
        self._table("noise", hidden=True)

        rv = self._get()

        self.assertEqual(["kept"], [t["name"] for t in rv.json["tables"]])
        self.assertEqual(1, rv.json["hidden_count"])

    def test_unless_asked_for(self):
        self._table("kept")
        self._table("noise", hidden=True)

        rv = self._get("?hidden=1")

        self.assertEqual({"kept", "noise"}, {t["name"] for t in rv.json["tables"]})
        self.assertTrue({t["name"]: t["hidden"] for t in rv.json["tables"]}["noise"])

    def test_a_search_does_not_reach_hidden_ones_either_unless_asked(self):
        self._table("noise_metric", hidden=True)

        self.assertEqual([], self._get("?q=noise").json["tables"])
        self.assertEqual(["noise_metric"], [t["name"] for t in self._get("?q=noise&hidden=1").json["tables"]])

    def test_only_the_described_ones(self):
        self._table("described", description="Known.")
        self._table("bare")

        rv = self._get("?described=1")

        self.assertEqual(["described"], [t["name"] for t in rv.json["tables"]])

    def test_hiding_one_keeps_its_description(self):
        # The edit used to set the description from whatever body arrived, so
        # hiding a table would have wiped what somebody had written about it.
        table = self._table("orders", description="One row per order.")
        admin = self.factory.create_admin()
        db.session.commit()

        rv = self.make_request(
            "post", "/api/catalog/tables/{}".format(table.id), data={"hidden": True}, user=admin, org=False
        )

        self.assertEqual(200, rv.status_code)
        db.session.refresh(table)
        self.assertTrue(table.hidden)
        self.assertEqual("One row per order.", table.description)
        self.assertEqual("human", table.description_source)

    def test_and_unhiding_it_brings_it_back(self):
        table = self._table("orders", hidden=True)
        admin = self.factory.create_admin()
        db.session.commit()

        self.make_request(
            "post", "/api/catalog/tables/{}".format(table.id), data={"hidden": False}, user=admin, org=False
        )

        self.assertEqual(["orders"], [t["name"] for t in self._get().json["tables"]])


class TestHiddenTablesAreNotOfferedToAModel(CatalogTestCase):
    """Hidden means nobody needs it -- which is true of an agent as much as a person."""

    def setUp(self):
        super().setUp()
        for name, hidden in [("orders", False), ("orders_noise_metric", True)]:
            db.session.add(
                models.CatalogTable(
                    org=self.factory.org,
                    data_source_id=self.factory.data_source.id,
                    name=name,
                    usage_count=10,
                    hidden=hidden,
                )
            )
        db.session.commit()

    def test_retrieval_leaves_them_out(self):
        from sqldesk.ai.catalog.retrieve import find_tables

        found = find_tables(self.factory.org, "orders")

        self.assertEqual(["orders"], [table.name for table in found])

    def test_even_with_no_question_at_all(self):
        from sqldesk.ai.catalog.retrieve import find_tables

        found = find_tables(self.factory.org, "")

        self.assertNotIn("orders_noise_metric", [table.name for table in found])


class TestMeasureReview(CatalogTestCase):
    """
    Approval is the whole point: until somebody sets it, a definition is
    something we noticed rather than something the organisation stands behind.
    """

    def _measure(self, name, usage=0, status=None):
        measure = models.CatalogMeasure(
            org=self.factory.org,
            data_source_id=self.factory.data_source.id,
            table_name="orders",
            name=name,
            kind="sum",
            column_name="amount",
            usage_count=usage,
            status=status or models.MEASURE_PROPOSED,
        )
        db.session.add(measure)
        db.session.commit()
        return measure

    def test_it_needs_a_super_admin(self):
        rv = self.make_request("get", "/api/catalog/measures", user=self.factory.user, org=False)

        self.assertEqual(403, rv.status_code)

    def test_most_written_first(self):
        self._measure("rare", usage=1)
        self._measure("everywhere", usage=40)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/measures", user=admin, org=False)

        self.assertEqual(["everywhere", "rare"], [m["name"] for m in rv.json["measures"]])

    def test_pending_leaves_out_what_is_already_agreed(self):
        self._measure("agreed", usage=9, status=models.MEASURE_APPROVED)
        self._measure("proposed", usage=8)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/measures?pending=1", user=admin, org=False)

        self.assertEqual(["proposed"], [m["name"] for m in rv.json["measures"]])

    def test_approving_one(self):
        measure = self._measure("gross_revenue")
        admin = self.factory.create_admin()

        self.make_request(
            "post",
            "/api/catalog/measures/{}".format(measure.id),
            data={"status": "approved", "description": "Agreed with finance."},
            user=admin,
            org=False,
        )

        db.session.expire_all()
        stored = models.CatalogMeasure.query.get(measure.id)
        self.assertEqual(models.MEASURE_APPROVED, stored.status)
        self.assertEqual("Agreed with finance.", stored.description)

    def test_denying_one(self):
        measure = self._measure("wrong", status=models.MEASURE_APPROVED)
        admin = self.factory.create_admin()

        self.make_request(
            "post",
            "/api/catalog/measures/{}".format(measure.id),
            data={"status": "denied"},
            user=admin,
            org=False,
        )

        db.session.expire_all()
        self.assertEqual(models.MEASURE_DENIED, models.CatalogMeasure.query.get(measure.id).status)

    def test_another_orgs_measure_is_not_found(self):
        other = self.factory.create_org()
        measure = models.CatalogMeasure(
            org=other,
            data_source_id=self.factory.data_source.id,
            table_name="t",
            name="theirs",
            kind="sum",
            column_name="amount",
            usage_count=0,
            status=models.MEASURE_PROPOSED,
        )
        db.session.add(measure)
        db.session.commit()
        admin = self.factory.create_admin()

        rv = self.make_request(
            "post",
            "/api/catalog/measures/{}".format(measure.id),
            data={"status": "approved"},
            user=admin,
            org=False,
        )

        self.assertEqual(404, rv.status_code)

    def test_a_denied_measure_leaves_the_worklist(self):
        self._measure("wrong", usage=5, status=models.MEASURE_DENIED)
        self._measure("still_thinking", usage=4)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/measures?pending=1", user=admin, org=False)

        self.assertEqual(["still_thinking"], [m["name"] for m in rv.json["measures"]])

    def test_a_status_that_is_not_one_of_the_three_is_refused(self):
        measure = self._measure("gross_revenue")
        admin = self.factory.create_admin()

        rv = self.make_request(
            "post",
            "/api/catalog/measures/{}".format(measure.id),
            data={"status": "probably"},
            user=admin,
            org=False,
        )

        self.assertEqual(400, rv.status_code)
        db.session.expire_all()
        self.assertEqual(models.MEASURE_PROPOSED, models.CatalogMeasure.query.get(measure.id).status)


class TestCatalogHarvest(CatalogTestCase):
    """
    Harvesting from the Catalog page rather than waiting for the schedule --
    and, for a data source just added, harvesting only what has nothing in
    the catalog yet instead of re-reading every other source as well.
    """

    def setUp(self):
        super().setUp()
        self.admin = self.factory.create_admin()

    def _catalogued(self, source):
        db.session.add(
            models.CatalogTable(
                org=self.factory.org, data_source_id=source.id, name="orders", harvested_at=db.func.now()
            )
        )
        db.session.commit()

    def _forget_jobs(self, *sources):
        """RQ's Redis is not flushed between tests, and ids restart with the database."""
        for source in sources:
            self.addCleanup(self._delete_job, harvest_job_id(source.id))

    def _delete_job(self, job_id):
        try:
            Job.fetch(job_id, connection=rq_redis_connection).delete()
        except NoSuchJobError:
            pass

    def _harvest(self, body, user=None):
        return self.make_request("post", "/api/catalog/harvest", data=body, user=user or self.admin, org=False)

    def test_it_needs_a_super_admin(self):
        self.assertEqual(403, self._harvest({}, user=self.factory.user).status_code)
        self.assertEqual(
            403, self.make_request("get", "/api/catalog/sources", user=self.factory.user, org=False).status_code
        )

    def test_only_unharvested_leaves_sources_with_a_catalog_alone(self):
        old = self.factory.data_source
        self._catalogued(old)
        new = self.factory.create_data_source(name="Just added")

        with mock.patch.object(harvest_catalog, "delay") as delay:
            rv = self._harvest({"only": "unharvested"})

        self.assertEqual(200, rv.status_code)
        self.assertEqual([new.id], rv.json["queued"])
        self.assertEqual([new.id], [call.args[0] for call in delay.call_args_list])

    def test_left_out_it_harvests_every_source(self):
        self._catalogued(self.factory.data_source)
        new = self.factory.create_data_source(name="Just added")

        with mock.patch.object(harvest_catalog, "delay"):
            rv = self._harvest({})

        self.assertEqual(sorted([self.factory.data_source.id, new.id]), sorted(rv.json["queued"]))

    def test_one_source_can_be_asked_for(self):
        other = self.factory.create_data_source(name="Other")

        with mock.patch.object(harvest_catalog, "delay"):
            rv = self._harvest({"data_source_id": other.id})

        self.assertEqual([other.id], rv.json["queued"])

    def test_another_organizations_source_is_not_found(self):
        theirs = self.factory.create_data_source(name="Theirs", org=self.factory.create_org())

        with mock.patch.object(harvest_catalog, "delay") as delay:
            rv = self._harvest({"data_source_id": theirs.id})

        self.assertEqual(404, rv.status_code)
        self.assertFalse(delay.called)

    def test_a_paused_source_says_why_it_was_skipped(self):
        self.factory.data_source.pause("maintenance")

        with mock.patch.object(harvest_catalog, "delay") as delay:
            rv = self._harvest({"data_source_id": self.factory.data_source.id})

        self.assertEqual([], rv.json["queued"])
        self.assertEqual("paused", rv.json["skipped"][0]["reason"])
        self.assertFalse(delay.called)

    def test_an_unknown_only_is_refused(self):
        self.assertEqual(400, self._harvest({"only": "stale"}).status_code)

    def test_clicking_twice_queues_it_once(self):
        # A real job, not a mock: what is under test is that the job queued
        # the first time is found the second.
        source = self.factory.data_source
        self._forget_jobs(source)

        first = self._harvest({"data_source_id": source.id})
        second = self._harvest({"data_source_id": source.id})

        self.assertEqual([source.id], first.json["queued"])
        self.assertEqual([], second.json["queued"])
        self.assertEqual("already queued", second.json["skipped"][0]["reason"])

    def test_the_sources_say_what_is_held_and_what_is_waiting(self):
        held = self.factory.data_source
        self._catalogued(held)
        waiting = self.factory.create_data_source(name="Waiting")
        self._forget_jobs(waiting)
        self._harvest({"data_source_id": waiting.id})

        rv = self.make_request("get", "/api/catalog/sources", user=self.admin, org=False)

        by_id = {source["id"]: source for source in rv.json["sources"]}
        self.assertEqual(1, by_id[held.id]["tables"])
        self.assertIsNotNone(by_id[held.id]["harvested_at"])
        self.assertIsNone(by_id[held.id]["state"])
        self.assertEqual(0, by_id[waiting.id]["tables"])
        self.assertEqual("queued", by_id[waiting.id]["state"])


class TestCatalogDownload(CatalogTestCase):
    """
    The same files `manage ai export` writes, for somebody with no shell.
    A curation step that requires docker access is one that does not happen.
    """

    def _harvested(self):
        source = self.factory.create_data_source(name="Warehouse")
        table = models.CatalogTable(
            org=self.factory.org,
            data_source_id=source.id,
            name="orders",
            usage_count=3,
            description="One row per order.",
            description_source="human",
        )
        db.session.add(table)
        db.session.commit()
        return source

    def test_it_needs_a_super_admin(self):
        self._harvested()
        rv = self.make_request("get", "/api/catalog/export", user=self.factory.user, org=False)

        self.assertEqual(403, rv.status_code)

    def test_it_returns_a_zip_of_the_same_yaml(self):
        self._harvested()
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/export", user=admin, org=False)

        self.assertEqual(200, rv.status_code)
        archive = zipfile.ZipFile(io.BytesIO(rv.data))
        self.assertIn("warehouse/orders.yml", archive.namelist())
        cube = yaml.safe_load(archive.read("warehouse/orders.yml"))["cubes"][0]
        self.assertEqual("orders", cube["sql_table"])
        self.assertEqual("One row per order.", cube["description"])

    def test_it_arrives_as_a_download_with_a_dated_name(self):
        self._harvested()
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/export", user=admin, org=False)

        self.assertIn("attachment", rv.headers["Content-Disposition"])
        self.assertIn("sqldesk-semantic-", rv.headers["Content-Disposition"])

    def test_one_data_source_can_be_asked_for(self):
        self._harvested()
        other = self.factory.create_data_source(name="Other")
        db.session.add(
            models.CatalogTable(org=self.factory.org, data_source_id=other.id, name="elsewhere", usage_count=1)
        )
        db.session.commit()
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/export?data_source_id={}".format(other.id), user=admin, org=False)

        names = zipfile.ZipFile(io.BytesIO(rv.data)).namelist()
        self.assertEqual(["other/elsewhere.yml"], names)

    def test_a_data_source_that_is_not_yours_is_not_found(self):
        elsewhere = self.factory.create_org()
        theirs = self.factory.create_data_source(name="Theirs", org=elsewhere)
        admin = self.factory.create_admin()

        rv = self.make_request("get", "/api/catalog/export?data_source_id={}".format(theirs.id), user=admin, org=False)

        self.assertEqual(404, rv.status_code)


class TestVerifyingASavedQuery(CatalogTestCase):
    """
    The strongest thing the catalog can offer a model, and the one part of it
    nobody can mine: a person reads the SQL and says this is the right answer.
    Which means the claim is about the SQL they read, and the tests below are
    mostly about what happens when it changes underneath them.
    """

    def _curator(self):
        group = self.factory.create_group(
            name="Curators", permissions=models.Group.DEFAULT_PERMISSIONS + ["manage_catalog"]
        )
        db.session.add(group)
        db.session.commit()
        return self.factory.create_user(group_ids=[group.id, self.factory.default_group.id])

    def _verify(self, query, user=None, **body):
        return self.make_request(
            "post",
            "/api/catalog/queries/{}".format(query.id),
            data=body,
            user=user or self.factory.create_admin(),
            org=False,
        )

    def test_a_curator_may_confirm_one(self):
        query = self.factory.create_query()

        rv = self._verify(query, user=self._curator(), question="What did we take last month?")

        self.assertEqual(200, rv.status_code)
        self.assertTrue(rv.json["verified"])
        self.assertEqual("What did we take last month?", rv.json["question"])

    def test_and_it_records_which_sql_was_read(self):
        query = self.factory.create_query()

        self._verify(query)

        stored = models.CatalogVerifiedQuery.query.filter_by(query_id=query.id).one()
        self.assertEqual(query.query_hash, stored.query_hash)
        self.assertTrue(stored.still_current)

    def test_editing_the_query_afterwards_stops_it_counting(self):
        # The claim was about text that no longer exists. A badge somebody can
        # edit the meaning out of is worse than no badge.
        query = self.factory.create_query(query_text="select 1")
        self._verify(query)

        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        db.session.commit()

        stored = models.CatalogVerifiedQuery.query.filter_by(query_id=query.id).one()
        self.assertFalse(stored.still_current)

    def test_confirming_again_is_how_a_person_re_reads_it(self):
        query = self.factory.create_query(query_text="select 1")
        self._verify(query)
        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        db.session.commit()

        self._verify(query)

        stored = models.CatalogVerifiedQuery.query.filter_by(query_id=query.id).one()
        self.assertTrue(stored.still_current)

    def test_confirming_twice_does_not_make_two_records(self):
        # Verified is a state, not a log.
        query = self.factory.create_query()

        self._verify(query)
        self._verify(query)

        self.assertEqual(1, models.CatalogVerifiedQuery.query.filter_by(query_id=query.id).count())

    def test_withdrawing_it(self):
        query = self.factory.create_query()
        self._verify(query)

        rv = self.make_request(
            "delete", "/api/catalog/queries/{}".format(query.id), user=self.factory.create_admin(), org=False
        )

        self.assertEqual(200, rv.status_code)
        self.assertFalse(rv.json["verified"])
        self.assertEqual(0, models.CatalogVerifiedQuery.query.filter_by(query_id=query.id).count())

    def test_withdrawing_one_that_was_never_confirmed_is_not_an_error(self):
        # Two curators clicking the same button is not a failure.
        query = self.factory.create_query()

        rv = self.make_request(
            "delete", "/api/catalog/queries/{}".format(query.id), user=self.factory.create_admin(), org=False
        )

        self.assertEqual(200, rv.status_code)

    def test_somebody_without_the_feature_may_not(self):
        query = self.factory.create_query()

        rv = self._verify(query, user=self.factory.user)

        self.assertEqual(403, rv.status_code)

    def test_nor_may_a_curator_confirm_sql_they_cannot_read(self):
        # Curating the catalog is not a way into a data source you are not in
        # a group for, and signing an unread document is the thing being
        # prevented.
        other_group = self.factory.create_group(name="Theirs")
        db.session.add(other_group)
        db.session.commit()
        theirs = self.factory.create_data_source(group=other_group, name="theirs")
        query = self.factory.create_query(data_source=theirs)

        rv = self._verify(query, user=self._curator())

        self.assertEqual(403, rv.status_code)

    def test_a_query_in_another_organisation_is_not_found(self):
        other = self.factory.create_org()
        query = self.factory.create_query(org=other, data_source=self.factory.create_data_source(org=other))

        rv = self._verify(query)

        self.assertEqual(404, rv.status_code)

    def test_the_list_says_which_have_drifted(self):
        # The drifted ones are the work: nothing else in the product will ever
        # mention them, so if this page does not show them, re-confirming
        # never happens.
        current = self.factory.create_query(name="Still right", query_text="select 1")
        drifted = self.factory.create_query(name="Edited since", query_text="select 2")
        self._verify(current)
        self._verify(drifted)
        drifted.query_text = "select 3"
        drifted.query_hash = models.utils.gen_query_hash(drifted.query_text)
        db.session.commit()

        rv = self.make_request("get", "/api/catalog/queries", user=self.factory.create_admin(), org=False)

        self.assertEqual(200, rv.status_code)
        state = {row["query_name"]: row["current"] for row in rv.json["queries"]}
        self.assertEqual({"Still right": True, "Edited since": False}, state)

    def test_an_archived_query_drops_off_the_list(self):
        query = self.factory.create_query()
        self._verify(query)
        query.archive()
        db.session.commit()

        rv = self.make_request("get", "/api/catalog/queries", user=self.factory.create_admin(), org=False)

        self.assertEqual([], rv.json["queries"])

    def test_deleting_the_query_takes_the_confirmation_with_it(self):
        query = self.factory.create_query()
        self._verify(query)

        db.session.delete(query)
        db.session.commit()

        self.assertEqual(0, models.CatalogVerifiedQuery.query.count())

    def test_confirming_is_not_editing(self):
        # Assigning the relationship rather than the id marks the query dirty,
        # so the commit bumps `queries.updated_at` -- and then confirming a
        # query makes it jump to the top of every "recently updated" list and
        # its own page says it was edited just now. Found because it also hid
        # a ranking bug: the confirmed query became the most recent one, so an
        # ordering test passed on recency alone.
        query = self.factory.create_query()
        db.session.commit()
        before = db.session.execute("select updated_at from queries where id = :id", {"id": query.id}).scalar()

        self._verify(query)

        after = db.session.execute("select updated_at from queries where id = :id", {"id": query.id}).scalar()
        self.assertEqual(before, after)


class TestTheRetrievalScoreOnThePage(CatalogTestCase):
    def test_nothing_recorded_means_no_score(self):
        # The page shows nothing at all rather than a widget saying "not set
        # up", which is furniture nobody removes.
        rv = self.make_request("get", "/api/catalog/score", user=self.factory.create_admin(), org=False)

        self.assertEqual(200, rv.status_code)
        self.assertIsNone(rv.json["score"])

    def test_a_recorded_score_is_returned(self):
        record_score(
            self.factory.org,
            {"questions": 4, "passed": 3, "score": 0.75, "results": [{"ask": "revenue", "passed": False}]},
        )

        rv = self.make_request("get", "/api/catalog/score", user=self.factory.create_admin(), org=False)

        self.assertEqual(3, rv.json["score"]["passed"])
        self.assertEqual(["revenue"], rv.json["score"]["missed"])

    def test_somebody_without_the_feature_may_not_read_it(self):
        rv = self.make_request("get", "/api/catalog/score", user=self.factory.user, org=False)

        self.assertEqual(403, rv.status_code)


class TestAskingWhetherOneQueryIsConfirmed(TestVerifyingASavedQuery):
    """
    The query page asks this before anyone opens a menu, so it has to answer
    for an unconfirmed query too rather than 404.
    """

    def test_an_unconfirmed_query(self):
        query = self.factory.create_query()

        rv = self.make_request(
            "get", "/api/catalog/queries/{}".format(query.id), user=self.factory.create_admin(), org=False
        )

        self.assertEqual(200, rv.status_code)
        self.assertFalse(rv.json["verified"])

    def test_a_confirmed_one_comes_back_with_who_and_what(self):
        query = self.factory.create_query()
        self._verify(query, question="What did we take?", note="Excludes internal.")

        rv = self.make_request(
            "get", "/api/catalog/queries/{}".format(query.id), user=self.factory.create_admin(), org=False
        )

        self.assertTrue(rv.json["verified"])
        self.assertEqual("What did we take?", rv.json["question"])
        self.assertEqual("Excludes internal.", rv.json["note"])
        self.assertTrue(rv.json["current"])

    def test_and_says_when_the_sql_has_moved_on(self):
        query = self.factory.create_query(query_text="select 1")
        self._verify(query)
        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        db.session.commit()

        rv = self.make_request(
            "get", "/api/catalog/queries/{}".format(query.id), user=self.factory.create_admin(), org=False
        )

        self.assertTrue(rv.json["verified"])
        self.assertFalse(rv.json["current"])

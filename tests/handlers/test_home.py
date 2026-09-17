from tealdash.models import db
from tests import BaseTestCase


class TestHomeSummary(BaseTestCase):
    def summary_for(self, user):
        rv = self.make_request("get", "/api/home/summary", user=user)
        self.assertEqual(rv.status_code, 200)
        return rv.json

    def test_counts_only_what_this_user_made(self):
        mine = self.factory.create_user()
        theirs = self.factory.create_user()

        self.factory.create_query(user=mine)
        self.factory.create_query(user=mine)
        self.factory.create_query(user=theirs)
        self.factory.create_dashboard(user=mine)
        self.factory.create_dashboard(user=theirs)
        db.session.commit()

        counters = self.summary_for(mine)["counters"]

        self.assertEqual(counters["queries"], 2)
        self.assertEqual(counters["dashboards"], 1)

    def test_leaves_out_archived_queries(self):
        user = self.factory.create_user()
        self.factory.create_query(user=user)
        self.factory.create_query(user=user, is_archived=True)
        db.session.commit()

        self.assertEqual(self.summary_for(user)["counters"]["queries"], 1)

    def test_a_schedule_with_nothing_set_is_not_a_schedule(self):
        # Clearing a schedule field by field leaves this behind, and
        # outdated_queries skips it -- so counting it would report a query as
        # scheduled that is never going to run.
        user = self.factory.create_user()
        self.factory.create_query(user=user, schedule={"interval": 300, "time": None, "day_of_week": None})
        self.factory.create_query(user=user, schedule={"interval": None, "time": None, "day_of_week": None})
        self.factory.create_query(user=user, schedule=None)
        db.session.commit()

        self.assertEqual(self.summary_for(user)["counters"]["scheduled_queries"], 1)

    def test_counts_a_crontab_schedule(self):
        user = self.factory.create_user()
        self.factory.create_query(user=user, schedule={"interval": None, "cron": "0 9 * * 1-5"})
        db.session.commit()

        self.assertEqual(self.summary_for(user)["counters"]["scheduled_queries"], 1)

    def test_counts_alerts_this_user_configured(self):
        mine = self.factory.create_user()
        theirs = self.factory.create_user()
        self.factory.create_alert(user=mine)
        self.factory.create_alert(user=theirs)
        db.session.commit()

        self.assertEqual(self.summary_for(mine)["counters"]["alerts"], 1)

    def test_reports_the_size_of_stored_results(self):
        user = self.factory.create_user()
        query = self.factory.create_query(user=user)
        result = self.factory.create_query_result(data={"columns": [], "rows": [{"a": "x" * 5000}]})
        query.latest_query_data = result
        db.session.add(query)
        db.session.commit()

        storage = self.summary_for(user)["counters"]["result_storage_bytes"]

        # pg_column_size reports the stored size, and the data compresses, so
        # the assertion is that the result is accounted for at all rather than
        # that it takes any particular number of bytes.
        self.assertGreater(storage, 0)

    def test_reports_zero_storage_when_nothing_has_run(self):
        user = self.factory.create_user()
        self.factory.create_query(user=user)
        db.session.commit()

        self.assertEqual(self.summary_for(user)["counters"]["result_storage_bytes"], 0)

    def test_lists_scheduled_queries_slowest_first(self):
        user = self.factory.create_user()
        for name, runtime in [("fast", 1.0), ("slowest", 90.0), ("middling", 30.0)]:
            query = self.factory.create_query(user=user, name=name, schedule={"interval": 300})
            query.latest_query_data = self.factory.create_query_result(runtime=runtime)
            db.session.add(query)
        db.session.commit()

        top = self.summary_for(user)["top_scheduled_queries"]

        self.assertEqual([row["name"] for row in top], ["slowest", "middling", "fast"])
        self.assertEqual(top[0]["runtime"], 90.0)

    def test_puts_a_query_that_has_never_run_last(self):
        # No runtime sorts first in a descending order by default, which would
        # put the queries nothing is known about at the top of a list meant to
        # show the slowest.
        user = self.factory.create_user()
        never_run = self.factory.create_query(user=user, name="never run", schedule={"interval": 300})
        ran = self.factory.create_query(user=user, name="ran", schedule={"interval": 300})
        ran.latest_query_data = self.factory.create_query_result(runtime=5.0)
        db.session.add_all([never_run, ran])
        db.session.commit()

        top = self.summary_for(user)["top_scheduled_queries"]

        self.assertEqual([row["name"] for row in top], ["ran", "never run"])
        self.assertIsNone(top[1]["runtime"])

    def test_lists_at_most_ten(self):
        user = self.factory.create_user()
        for i in range(12):
            self.factory.create_query(user=user, name="q{}".format(i), schedule={"interval": 300})
        db.session.commit()

        self.assertEqual(len(self.summary_for(user)["top_scheduled_queries"]), 10)

    def test_names_the_data_source_and_schedule(self):
        user = self.factory.create_user()
        self.factory.create_query(user=user, name="nightly", schedule={"interval": None, "cron": "0 2 * * *"})
        db.session.commit()

        row = self.summary_for(user)["top_scheduled_queries"][0]

        self.assertEqual(row["name"], "nightly")
        self.assertEqual(row["schedule"]["cron"], "0 2 * * *")
        self.assertTrue(row["data_source"])

    def test_unscheduled_queries_are_not_listed(self):
        user = self.factory.create_user()
        self.factory.create_query(user=user, name="ad hoc")
        db.session.commit()

        self.assertEqual(self.summary_for(user)["top_scheduled_queries"], [])

    def test_requires_a_session(self):
        # 404 rather than 401 on purpose: redirect_to_login answers every
        # unauthenticated /api/ request that way so it does not say whether the
        # resource exists. The org slug is part of the path in multi-org mode,
        # which the suite runs in, so it has to be included or the 404 would be
        # about the URL and prove nothing.
        rv = self.client.get("/{}/api/home/summary".format(self.factory.org.slug))

        self.assertEqual(rv.status_code, 404)
        self.assertNotIn("counters", rv.get_data(as_text=True))

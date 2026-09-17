import datetime

from tealdash import models
from tealdash.models import db
from tealdash.utils import utcnow
from tests import BaseTestCase


class TestOutdatedDashboardQueries(BaseTestCase):
    """A dashboard's schedule refreshes the queries behind its widgets.

    Nothing records when a dashboard last refreshed. Each query is measured
    against when it last ran, using the dashboard's expression -- so there is no
    second clock to keep in step with the first.
    """

    def add_widget(self, dashboard, query):
        visualization = self.factory.create_visualization(query_rel=query)
        return self.factory.create_widget(dashboard=dashboard, visualization=visualization)

    def query_last_run(self, hours_ago):
        query = self.factory.create_query()
        query.latest_query_data = self.factory.create_query_result(
            retrieved_at=utcnow() - datetime.timedelta(hours=hours_ago)
        )
        db.session.add(query)
        return query

    def test_refreshes_a_query_when_the_dashboards_slot_has_come_round(self):
        query = self.query_last_run(hours_ago=25)
        dashboard = self.factory.create_dashboard(schedule={"interval": None, "cron": "0 * * * *"})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertIn(query.id, [q.id for q in models.Query.outdated_dashboard_queries()])

    def test_leaves_a_query_alone_inside_the_slot(self):
        query = self.query_last_run(hours_ago=0)
        dashboard = self.factory.create_dashboard(schedule={"interval": None, "cron": "0 3 * * *"})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_ignores_a_dashboard_with_no_schedule(self):
        query = self.query_last_run(hours_ago=25)
        self.add_widget(self.factory.create_dashboard(), query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_ignores_an_archived_dashboard(self):
        query = self.query_last_run(hours_ago=25)
        dashboard = self.factory.create_dashboard(schedule={"cron": "0 * * * *"}, is_archived=True)
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_ignores_an_archived_query(self):
        query = self.query_last_run(hours_ago=25)
        query.is_archived = True
        dashboard = self.factory.create_dashboard(schedule={"cron": "0 * * * *"})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_ignores_a_schedule_with_nothing_set(self):
        query = self.query_last_run(hours_ago=25)
        dashboard = self.factory.create_dashboard(schedule={"interval": None, "cron": None})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_returns_a_query_once_when_it_is_on_two_scheduled_dashboards(self):
        # Otherwise the same query is enqueued twice in a pass, spending the
        # data source's time to get the same answer.
        query = self.query_last_run(hours_ago=25)
        for _ in range(2):
            dashboard = self.factory.create_dashboard(schedule={"cron": "0 * * * *"})
            self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual([q.id for q in models.Query.outdated_dashboard_queries()], [query.id])

    def test_a_textbox_widget_has_no_query_to_refresh(self):
        dashboard = self.factory.create_dashboard(schedule={"cron": "0 * * * *"})
        self.factory.create_widget(dashboard=dashboard, visualization=None, text="just a note")
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])

    def test_disables_a_schedule_it_cannot_read(self):
        # Matching outdated_queries: an expression that cannot be parsed is
        # turned off rather than raising on every pass of the scheduler.
        query = self.query_last_run(hours_ago=25)
        dashboard = self.factory.create_dashboard(schedule={"cron": "not a crontab line"})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])
        self.assertTrue(models.Dashboard.query.get(dashboard.id).schedule["disabled"])

    def test_skips_a_dashboard_whose_schedule_is_disabled(self):
        query = self.query_last_run(hours_ago=25)
        dashboard = self.factory.create_dashboard(schedule={"cron": "0 * * * *", "disabled": True})
        self.add_widget(dashboard, query)
        db.session.commit()

        self.assertEqual(models.Query.outdated_dashboard_queries(), [])


class TestDashboardScheduleApi(BaseTestCase):
    def test_saves_a_crontab_schedule(self):
        dashboard = self.factory.create_dashboard()

        rv = self.make_request(
            "post",
            "/api/dashboards/{}".format(dashboard.id),
            data={"schedule": {"interval": None, "cron": "0 6 * * *"}},
        )

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["schedule"]["cron"], "0 6 * * *")

    def test_rejects_a_crontab_expression_that_cannot_be_read(self):
        dashboard = self.factory.create_dashboard()

        rv = self.make_request(
            "post",
            "/api/dashboards/{}".format(dashboard.id),
            data={"schedule": {"cron": "every morning"}},
        )

        self.assertEqual(rv.status_code, 400)
        self.assertIsNone(models.Dashboard.query.get(dashboard.id).schedule)

    def test_clears_a_schedule(self):
        dashboard = self.factory.create_dashboard(schedule={"cron": "0 6 * * *"})
        db.session.commit()

        rv = self.make_request("post", "/api/dashboards/{}".format(dashboard.id), data={"schedule": None})

        self.assertEqual(rv.status_code, 200)
        self.assertIsNone(rv.json["schedule"])

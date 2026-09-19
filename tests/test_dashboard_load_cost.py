"""
What a dashboard costs to serve, counted in SQL statements.

Showing a dashboard and checking in on a live one both used to walk every
widget lazily -- visualization, query, data source, groups, and the viewer's
permissions once per widget -- so the cost grew with the number of widgets
even though the rows were nearly all the same. These tests hold the cost flat:
what matters is not the exact number but that adding widgets does not add
statements.
"""

from contextlib import contextmanager

from sqlalchemy import event

from sqldesk import models
from tests import BaseTestCase


@contextmanager
def count_statements():
    counter = {"n": 0}

    def before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    engine = models.db.engine
    event.listen(engine, "before_cursor_execute", before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", before)


class DashboardCostTestCase(BaseTestCase):
    def build_dashboard(self, widget_count, shared=1, live=False):
        """A dashboard of `widget_count` widgets, `shared` of them one query."""
        dashboard = self.factory.create_dashboard()
        distinct = widget_count - shared + 1
        for i in range(distinct):
            query = self.factory.create_query(query_text="select {}".format(i))
            for _ in range(shared if i == 0 else 1):
                visualization = self.factory.create_visualization(query_rel=query)
                self.factory.create_widget(dashboard=dashboard, visualization=visualization)
        if live:
            models.db.session.execute(
                models.Dashboard.__table__.update()
                .where(models.Dashboard.id == dashboard.id)
                .values(live={"interval": 30, "paused": False})
            )
        models.db.session.commit()
        models.db.session.expire_all()
        return dashboard


class TestDashboardSerializationCost(DashboardCostTestCase):
    def cost_of_showing(self, widget_count):
        dashboard = self.build_dashboard(widget_count)
        with count_statements() as counter:
            rv = self.make_request("get", "/api/dashboards/{}".format(dashboard.id))
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["widgets"]), widget_count)
        return counter["n"]

    def test_widgets_are_loaded_together(self):
        few = self.cost_of_showing(3)
        many = self.cost_of_showing(15)
        # Five times the widgets, and the statements that fetch them do not
        # multiply: they arrive in one joined load.
        self.assertLessEqual(many - few, 2, "showing a dashboard costs {} then {} statements".format(few, many))

    def test_permissions_are_not_rechecked_per_widget(self):
        # Every widget's query runs through has_access, which reads the
        # viewer's permissions and the data source's groups.
        self.assertLess(self.cost_of_showing(15), 20)


class TestLiveCheckInCost(DashboardCostTestCase):
    def cost_of_checking_in(self, widget_count):
        dashboard = self.build_dashboard(widget_count, live=True)
        url = "/api/dashboards/{}/live/watch".format(dashboard.id)
        # The first check-in also refreshes a dashboard nobody was watching;
        # the repeat is the one that happens every few seconds, for ever.
        self.make_request("post", url, data={"viewer": "probe"})
        with count_statements() as counter:
            rv = self.make_request("post", url, data={"viewer": "probe"})
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json["results"]), widget_count)
        return counter["n"]

    def test_check_in_cost_does_not_grow_with_widgets(self):
        few = self.cost_of_checking_in(3)
        many = self.cost_of_checking_in(15)
        # One result lookup per widget is the real work and still scales; the
        # rest -- widgets, visualizations, queries, groups, permissions --
        # must not.
        self.assertLessEqual(many - few, 14, "checking in costs {} then {} statements".format(few, many))

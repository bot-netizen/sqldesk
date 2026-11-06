"""
Deleting a query or a dashboard outright, rather than hiding it.

Archiving a query already throws away its widgets and its alerts, so
"archived" was never the reversible thing it sounds like -- and people archive
things to get rid of them and then find the archive full. This is the honest
version.

What a destructive path needs tested is not only that it removes things. It is
**what survives**: a result another query is still showing, an event the audit
reads, and a chart that happens to be on three other dashboards.
"""

from sqldesk import models
from sqldesk.models import db
from tests import BaseTestCase


class PermanentDeleteTestCase(BaseTestCase):
    def delete_query(self, query, user=None):
        return self.make_request("delete", "/api/queries/{}/permanent".format(query.id), user=user)

    def delete_dashboard(self, dashboard, user=None):
        return self.make_request("delete", "/api/dashboards/{}/permanent".format(dashboard.id), user=user)


class TestDeletingAQuery(PermanentDeleteTestCase):
    def test_it_goes(self):
        query = self.factory.create_query()
        query_id = query.id

        answer = self.delete_query(query, user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertIsNone(models.Query.query.get(query_id))

    def test_its_visualizations_and_their_widgets_go_with_it(self):
        query = self.factory.create_query()
        visualization = self.factory.create_visualization(query_rel=query)
        widget = self.factory.create_widget(visualization=visualization)
        db.session.commit()
        ids = (visualization.id, widget.id)

        answer = self.delete_query(query, user=self.factory.user)

        self.assertIsNone(models.Visualization.query.get(ids[0]))
        self.assertIsNone(models.Widget.query.get(ids[1]))
        self.assertEqual(1, answer.json["deleted"]["widgets"])

    def test_its_alerts_go_with_it(self):
        query = self.factory.create_query()
        alert = self.factory.create_alert(query_rel=query)
        db.session.commit()
        alert_id = alert.id

        self.delete_query(query, user=self.factory.user)

        self.assertIsNone(models.Alert.query.get(alert_id))

    def test_a_favourite_of_it_goes_too(self):
        """
        Nothing in the database would clear this: a favourite points at an
        object by a type name and an id, with no foreign key. Left behind it
        is a star on somebody's list that opens nothing.
        """
        query = self.factory.create_query()
        favourite = models.Favorite(org_id=self.factory.org.id, object=query, user=self.factory.user)
        db.session.add(favourite)
        db.session.commit()
        favourite_id = favourite.id

        self.delete_query(query, user=self.factory.user)

        # Counted rather than `.get()`: a bulk delete does not expire the
        # session's copy, so `.get()` answers from the identity map and
        # reports a row that is no longer in the database.
        self.assertEqual(0, models.Favorite.query.filter_by(id=favourite_id).count())

    def test_its_version_history_goes_too(self):
        """
        And this is the half that is easy to get wrong: a favourite stores the
        *class* name and a change stores the *table* name. The wrong string
        deletes nothing and says nothing.
        """
        query = self.factory.create_query()
        query.record_changes(self.factory.user)
        db.session.commit()
        self.assertGreater(models.Change.query.filter_by(object_type="queries", object_id=query.id).count(), 0)

        self.delete_query(query, user=self.factory.user)

        self.assertEqual(0, models.Change.query.filter_by(object_type="queries", object_id=query.id).count())

    def test_its_results_stay_because_another_query_may_be_showing_them(self):
        """
        `query_results` is keyed by the SQL and the data source and shared by
        every query that asks the same thing. Deleting them would take rows
        out from under a query nobody touched.
        """
        query = self.factory.create_query()
        result = self.factory.create_query_result()
        query.latest_query_data = result
        db.session.add(query)
        db.session.commit()
        result_id = result.id

        self.delete_query(query, user=self.factory.user)

        self.assertIsNotNone(models.QueryResult.query.get(result_id))

    def test_the_audit_keeps_the_name_it_will_no_longer_be_able_to_look_up(self):
        """
        Recorded *before* the row goes, with the name on it: afterwards there
        is nothing left to look the name up from, and an audit of a month full
        of deleted ids says very little.

        Asserted on the call rather than on the row, because an event is
        written by a queued job -- no worker runs in these tests, so the row
        appears later or not at all.
        """
        from unittest import mock

        query = self.factory.create_query(name="Quarterly rollup")

        with mock.patch("sqldesk.handlers.base.record_event_task") as task:
            self.delete_query(query, user=self.factory.user)

        recorded = [call.args[0] for call in task.delay.call_args_list]
        deletion = [one for one in recorded if one.get("action") == "delete"]
        self.assertEqual(1, len(deletion), recorded)
        self.assertEqual("Quarterly rollup", deletion[0]["name"])
        self.assertEqual("query", deletion[0]["object_type"])


class TestDeletingADashboard(PermanentDeleteTestCase):
    def test_it_goes_and_takes_its_widgets(self):
        dashboard = self.factory.create_dashboard()
        widget = self.factory.create_widget(dashboard=dashboard)
        db.session.commit()
        ids = (dashboard.id, widget.id)

        answer = self.delete_dashboard(dashboard, user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertIsNone(models.Dashboard.query.get(ids[0]))
        self.assertIsNone(models.Widget.query.get(ids[1]))

    def test_the_chart_behind_a_widget_stays(self):
        """
        A widget is a *placement*. The visualization it shows belongs to a
        query that may well be on three other dashboards, and deleting this
        one must not touch it.
        """
        dashboard = self.factory.create_dashboard()
        widget = self.factory.create_widget(dashboard=dashboard)
        db.session.commit()
        visualization_id = widget.visualization_id
        query_id = widget.visualization.query_rel.id

        self.delete_dashboard(dashboard, user=self.factory.user)

        self.assertIsNotNone(models.Visualization.query.get(visualization_id))
        self.assertIsNotNone(models.Query.query.get(query_id))

    def test_a_favourite_of_it_goes(self):
        dashboard = self.factory.create_dashboard()
        favourite = models.Favorite(org_id=self.factory.org.id, object=dashboard, user=self.factory.user)
        db.session.add(favourite)
        db.session.commit()
        favourite_id = favourite.id

        self.delete_dashboard(dashboard, user=self.factory.user)

        self.assertEqual(0, models.Favorite.query.filter_by(id=favourite_id).count())


class TestWhoMayDelete(PermanentDeleteTestCase):
    def test_somebody_who_did_not_make_it_may_not(self):
        query = self.factory.create_query(user=self.factory.create_user())
        db.session.commit()

        answer = self.delete_query(query, user=self.factory.user)

        self.assertEqual(403, answer.status_code)
        self.assertIsNotNone(models.Query.query.get(query.id))

    def test_an_administrator_may(self):
        query = self.factory.create_query(user=self.factory.create_user())
        db.session.commit()
        query_id = query.id

        answer = self.delete_query(query, user=self.factory.create_admin())

        self.assertEqual(200, answer.status_code)
        self.assertIsNone(models.Query.query.get(query_id))

    def test_a_dashboard_somebody_else_made_is_refused(self):
        dashboard = self.factory.create_dashboard(user=self.factory.create_user())
        db.session.commit()

        answer = self.delete_dashboard(dashboard, user=self.factory.user)

        self.assertEqual(403, answer.status_code)
        self.assertIsNotNone(models.Dashboard.query.get(dashboard.id))

    def test_one_from_another_organisation_is_not_found(self):
        other = self.factory.create_org()
        query = self.factory.create_query(org=other, user=self.factory.create_user(org=other))
        db.session.commit()

        answer = self.delete_query(query, user=self.factory.user)

        self.assertEqual(404, answer.status_code)
        self.assertIsNotNone(models.Query.query.get(query.id))

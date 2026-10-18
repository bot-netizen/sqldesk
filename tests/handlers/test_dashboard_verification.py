"""
Verifying a dashboard: who checked it, when, and what they checked.

The same permission as confirming a query in the catalog -- both are somebody
declaring a thing trustworthy for everybody else. And the part that keeps it
honest: a verification that silently outlived the dashboard it vouched for
would be worse than none, so the page is told when the dashboard has changed
since.
"""

from unittest import mock

from sqldesk.models import db
from tests import BaseTestCase


class VerificationTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        feature = mock.patch("sqldesk.settings.FEATURE_AI", True)
        feature.start()
        self.addCleanup(feature.stop)
        self.admin = self.factory.create_admin()
        self.dashboard = self.factory.create_dashboard()
        self.widget = self.factory.create_widget(dashboard=self.dashboard)
        db.session.commit()

    def verify(self, note="Revenue ties out to finance's monthly close.", user=None):
        return self.make_request(
            "post",
            "/api/dashboards/{}/verification".format(self.dashboard.id),
            data={"note": note},
            user=user or self.admin,
        )

    def page(self, user=None):
        return self.make_request("get", "/api/dashboards/{}".format(self.dashboard.id), user=user or self.admin)


class TestVerifying(VerificationTestCase):
    def test_it_records_who_when_and_what(self):
        rv = self.verify()

        self.assertEqual(200, rv.status_code)
        verification = rv.json["verification"]
        self.assertEqual(self.admin.name, verification["by"])
        self.assertEqual("Revenue ties out to finance's monthly close.", verification["note"])
        self.assertIsNotNone(verification["at"])
        self.assertFalse(verification["changed_since"])

    def test_the_dashboard_page_shows_it(self):
        self.verify()

        rv = self.page()

        self.assertEqual(self.admin.name, rv.json["verification"]["by"])
        self.assertTrue(rv.json["can_verify"])

    def test_a_note_is_required(self):
        rv = self.verify(note="   ")

        self.assertEqual(400, rv.status_code)
        self.assertIn("what was checked", rv.json["message"])
        db.session.refresh(self.dashboard)
        self.assertIsNone(self.dashboard.verified_at)

    def test_somebody_who_may_not_curate_may_not_verify(self):
        rv = self.verify(user=self.factory.user)

        self.assertEqual(403, rv.status_code)

    def test_and_is_not_offered_to(self):
        self.assertFalse(self.page(user=self.factory.user).json["can_verify"])

    def test_it_can_be_taken_back(self):
        self.verify()

        rv = self.make_request("delete", "/api/dashboards/{}/verification".format(self.dashboard.id), user=self.admin)

        self.assertEqual(200, rv.status_code)
        self.assertIsNone(self.page().json["verification"])

    def test_a_dashboard_nobody_verified_says_so(self):
        self.assertIsNone(self.page().json["verification"])


class TestItSaysWhenTheDashboardHasChangedSince(VerificationTestCase):
    def test_editing_the_sql_behind_a_chart(self):
        self.verify()
        query = self.widget.visualization.query_rel
        query.query_text = "SELECT 2"
        db.session.commit()

        self.assertTrue(self.page().json["verification"]["changed_since"])

    def test_adding_a_widget(self):
        self.verify()
        self.factory.create_widget(dashboard=self.dashboard)
        db.session.commit()

        self.assertTrue(self.page().json["verification"]["changed_since"])

    def test_removing_one(self):
        self.verify()
        db.session.delete(self.widget)
        db.session.commit()

        self.assertTrue(self.page().json["verification"]["changed_since"])

    def test_but_not_moving_one(self):
        # Layout, which nobody verifies.
        self.verify()
        self.widget.options = {"position": {"col": 3, "row": 4, "sizeX": 2, "sizeY": 2}}
        db.session.commit()

        self.assertFalse(self.page().json["verification"]["changed_since"])

    def test_verifying_again_vouches_for_what_is_there_now(self):
        self.verify()
        self.factory.create_widget(dashboard=self.dashboard)
        db.session.commit()

        self.verify(note="Rechecked with the new panel.")

        self.assertFalse(self.page().json["verification"]["changed_since"])


class TestTheListDoesNotPayForIt(VerificationTestCase):
    def test_a_list_carries_the_verification_without_checking_every_widget(self):
        self.verify()

        rv = self.make_request("get", "/api/dashboards", user=self.admin)

        found = [d for d in rv.json["results"] if d["id"] == self.dashboard.id][0]
        self.assertEqual(self.admin.name, found["verification"]["by"])
        self.assertIsNone(found["verification"]["changed_since"])

from unittest import mock

from sqldesk import models, settings
from sqldesk.models import db
from tests import BaseTestCase


def _rendering_on():
    """Subscriptions are only offered where a renderer is configured."""
    return mock.patch.multiple(
        settings,
        FEATURE_ALERT_SCREENSHOTS=True,
        SCREENSHOT_URL="http://screenshots:3000",
    )


def _half_visible(factory, dashboard):
    """
    A dashboard with one widget everybody can read and one from an HR source,
    and a colleague who can read only the first. `can_see_dashboard` says yes
    for them: one widget's source is theirs.
    """
    hr_group = factory.create_group(name="HR")
    db.session.add(hr_group)
    db.session.commit()
    hr = factory.create_data_source(name="HR", group=hr_group)
    for source in (factory.data_source, hr):
        query = factory.create_query(data_source=source)
        visualization = factory.create_visualization(query_rel=query)
        factory.create_widget(dashboard=dashboard, visualization=visualization)
    colleague = factory.create_user(email="colleague@example.com")
    db.session.commit()
    return colleague


class SubscriptionTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.dashboard = self.factory.create_dashboard()
        db.session.commit()

        # An admin has every feature the install offers, which keeps these
        # tests about the endpoint rather than about §5.
        self.owner = self.factory.create_admin()
        self.schedule = {"interval": 86400, "time": "09:00"}

    def _post(self, data, user=None, dashboard=None):
        return self.make_request(
            "post",
            "/api/dashboards/{}/subscriptions".format((dashboard or self.dashboard).id),
            data=data,
            user=user or self.owner,
        )

    def _subscribe(self, **overrides):
        body = {"schedule": self.schedule, "format": "png", "recipients": [self.owner.id]}
        body.update(overrides)
        return self._post(body)


class TestSubscribing(SubscriptionTestCase):
    def test_it_makes_one(self):
        with _rendering_on():
            rv = self._subscribe()

        self.assertEqual(200, rv.status_code)
        self.assertEqual(self.dashboard.id, rv.json["dashboard_id"])
        self.assertEqual([self.owner.id], [r["id"] for r in rv.json["recipients"]])
        self.assertTrue(rv.json["active"])

    def test_without_a_renderer_there_is_no_such_endpoint(self):
        # Not "500 later, when a worker finds it cannot draw": the feature is
        # not offered, so the door is shut.
        with mock.patch.multiple(settings, FEATURE_ALERT_SCREENSHOTS=False, SCREENSHOT_URL=""):
            rv = self._subscribe()

        self.assertEqual(403, rv.status_code)

    def test_somebody_without_the_feature_cannot(self):
        stranger = self.factory.create_user()
        db.session.commit()

        with _rendering_on():
            rv = self._post(
                {"schedule": self.schedule, "recipients": [stranger.id]},
                user=stranger,
            )

        self.assertEqual(403, rv.status_code)

    def test_a_dashboard_in_another_organization_is_not_found(self):
        elsewhere = self.factory.create_org()
        theirs = self.factory.create_dashboard(org=elsewhere)
        db.session.commit()

        with _rendering_on():
            rv = self._post({"schedule": self.schedule, "recipients": [self.owner.id]}, dashboard=theirs)

        self.assertEqual(404, rv.status_code)


class TestWhoMayBeSentIt(SubscriptionTestCase):
    """
    A subscription puts a dashboard in somebody's hands. Whether the *owner*
    may see it says nothing about whether the recipient may.
    """

    def _outsider(self):
        # A user in a group with no access to the dashboard's data source.
        group = self.factory.create_group(name="Outsiders")
        db.session.add(group)
        db.session.commit()
        user = self.factory.create_user(group_ids=[group.id])
        db.session.commit()
        return user

    def test_somebody_who_cannot_see_it_is_left_out_and_named(self):
        outsider = self._outsider()

        with _rendering_on():
            rv = self._subscribe(recipients=[self.owner.id, outsider.id])

        self.assertEqual(200, rv.status_code)
        self.assertEqual([self.owner.id], [r["id"] for r in rv.json["recipients"]])
        self.assertEqual([outsider.id], [r["id"] for r in rv.json["left_out"]])
        self.assertIn("cannot see this dashboard", rv.json["left_out"][0]["why"])

    def test_somebody_who_cannot_see_every_widget_is_left_out_and_named(self):
        """The picture is drawn as the owner, so it would show them the HR widget the app shows them locked."""
        colleague = _half_visible(self.factory, self.dashboard)

        with _rendering_on():
            rv = self._subscribe(recipients=[self.owner.id, colleague.id])

        self.assertEqual([self.owner.id], [r["id"] for r in rv.json["recipients"]])
        self.assertEqual([colleague.id], [r["id"] for r in rv.json["left_out"]])
        self.assertIn("every widget", rv.json["left_out"][0]["why"])

    def test_a_disabled_account_is_left_out_and_named(self):
        colleague = self.factory.create_admin(email="gone@example.com")
        colleague.disable()
        db.session.commit()

        with _rendering_on():
            rv = self._subscribe(recipients=[self.owner.id, colleague.id])

        self.assertEqual([colleague.id], [r["id"] for r in rv.json["left_out"]])
        self.assertIn("disabled", rv.json["left_out"][0]["why"])

    def test_a_list_of_nobody_who_can_see_it_is_refused(self):
        # Rather than a subscription that exists and mails nobody.
        outsider = self._outsider()

        with _rendering_on():
            rv = self._subscribe(recipients=[outsider.id])

        self.assertEqual(400, rv.status_code)

    def test_somebody_in_another_organization_is_simply_not_a_recipient(self):
        elsewhere = self.factory.create_org()
        stranger = self.factory.create_user(org=elsewhere)
        db.session.commit()

        with _rendering_on():
            rv = self._subscribe(recipients=[self.owner.id, stranger.id])

        self.assertEqual([self.owner.id], [r["id"] for r in rv.json["recipients"]])
        self.assertEqual([], rv.json["left_out"])


class TestWhatIsRefused(SubscriptionTestCase):
    def test_a_dashboard_too_big_to_send(self):
        for _ in range(13):
            visualization = self.factory.create_visualization()
            self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()

        with _rendering_on():
            rv = self._subscribe()

        self.assertEqual(400, rv.status_code)
        self.assertIn("one-page report", rv.json["message"])

    def test_more_often_than_once_an_hour(self):
        with _rendering_on():
            rv = self._subscribe(schedule={"interval": 60})

        self.assertEqual(400, rv.status_code)
        self.assertIn("once an hour", rv.json["message"])

    def test_no_schedule_at_all(self):
        with _rendering_on():
            self.assertEqual(400, self._subscribe(schedule=None).status_code)

    def test_a_day_that_is_not_a_day(self):
        with _rendering_on():
            rv = self._subscribe(schedule={"interval": 604800, "day_of_week": "Blursday"})

        self.assertEqual(400, rv.status_code)

    def test_a_format_that_is_neither_a_picture_nor_a_pdf(self):
        with _rendering_on():
            self.assertEqual(400, self._subscribe(format="fax").status_code)


class TestChangingAndStopping(SubscriptionTestCase):
    def _existing(self):
        with _rendering_on():
            return self._subscribe().json["id"]

    def _update(self, subscription_id, data, user=None):
        return self.make_request(
            "post",
            "/api/subscriptions/{}".format(subscription_id),
            data=data,
            user=user or self.owner,
        )

    def test_the_owner_may_pause_it(self):
        subscription_id = self._existing()

        with _rendering_on():
            rv = self._update(subscription_id, {"active": False})

        self.assertEqual(200, rv.status_code)
        self.assertFalse(rv.json["active"])

    def test_resuming_clears_the_last_error(self):
        # Somebody saying they have dealt with it. Leaving it would leave the
        # page reporting a problem that has gone away.
        subscription_id = self._existing()
        subscription = models.DashboardSubscription.query.get(subscription_id)
        subscription.active = False
        subscription.last_error = "The renderer was not answering."
        db.session.add(subscription)
        db.session.commit()

        with _rendering_on():
            rv = self._update(subscription_id, {"active": True})

        self.assertIsNone(rv.json["last_error"])

    def test_somebody_else_cannot_touch_it(self):
        subscription_id = self._existing()
        other_admin = self.factory.create_admin(email="other@example.com")
        db.session.commit()

        with _rendering_on():
            # An admin may, because an admin may everything.
            self.assertEqual(200, self._update(subscription_id, {"active": False}, user=other_admin).status_code)

    def test_a_stranger_gets_a_404_rather_than_a_403(self):
        # Which subscriptions exist is not something to leak.
        subscription_id = self._existing()
        # Somebody who may send dashboards, but not this one.
        group = self.factory.create_group(name="Senders", permissions=["view_query", "send_dashboards"])
        db.session.add(group)
        db.session.commit()
        sender = self.factory.create_user(group_ids=[group.id])
        db.session.commit()

        with _rendering_on():
            rv = self._update(subscription_id, {"active": False}, user=sender)

        self.assertEqual(404, rv.status_code)

    def test_deleting_it_stops_it(self):
        subscription_id = self._existing()

        with _rendering_on():
            rv = self.make_request("delete", "/api/subscriptions/{}".format(subscription_id), user=self.owner)

        self.assertEqual(200, rv.status_code)
        self.assertIsNone(models.DashboardSubscription.query.get(subscription_id))

    def test_the_dashboard_lists_its_own(self):
        self._existing()

        with _rendering_on():
            rv = self.make_request(
                "get",
                "/api/dashboards/{}/subscriptions".format(self.dashboard.id),
                user=self.owner,
            )

        self.assertEqual(200, rv.status_code)
        self.assertEqual(1, len(rv.json))

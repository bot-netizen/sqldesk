from unittest import mock

from mock import ANY, MagicMock

import sqldesk.tasks.alerts
from sqldesk.models import Alert
from sqldesk.tasks.alerts import check_alerts_for_query, notify_subscriptions
from tests import BaseTestCase


class TestCheckAlertsForQuery(BaseTestCase):
    """
    These replaced `Alert.evaluate` and `notify_subscriptions` by assignment
    and never put them back, so for the rest of the process every alert in
    every later test evaluated to whatever the last of these set -- which is
    why `tests/models/test_alerts.py` passed alone and failed eight ways
    after `tests/tasks` had run. Patched now, so they are restored.
    """

    def evaluates_to(self, state):
        """Make every alert evaluate to `state`, for this test only."""
        patched = mock.patch.object(Alert, "evaluate", return_value=state)
        patched.start()
        self.addCleanup(patched.stop)

    def nothing_is_notified(self):
        """Replace the notifier, for this test only, and hand it back."""
        patched = mock.patch.object(sqldesk.tasks.alerts, "notify_subscriptions")
        notifier = patched.start()
        self.addCleanup(patched.stop)
        return notifier

    def test_notifies_subscribers_when_should(self):
        notify = self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertTrue(notify.called)

    def test_doesnt_notify_when_nothing_changed(self):
        notify = self.nothing_is_notified()
        self.evaluates_to(Alert.OK_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(notify.called)

    def test_doesnt_notify_when_muted(self):
        notify = self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert(options={"muted": True})
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(notify.called)

    def test_and_evaluate_is_the_real_one_again_afterwards(self):
        """
        The guard on the bug above: these tests used to leave a MagicMock on
        the class, and nothing said so until an unrelated file failed.
        """
        self.assertFalse(isinstance(Alert.evaluate, MagicMock))


class TestNotifySubscriptions(BaseTestCase):
    def test_calls_notify_for_subscribers(self):
        subscription = self.factory.create_alert_subscription()
        subscription.notify = MagicMock()
        notify_subscriptions(subscription.alert, Alert.OK_STATE, metadata={"Scheduled": False})
        subscription.notify.assert_called_with(
            subscription.alert,
            subscription.alert.query_rel,
            subscription.user,
            Alert.OK_STATE,
            ANY,
            ANY,
            ANY,
        )

    def test_draws_the_pictures_once_for_everyone(self):
        # Five people on one alert must not mean five runs of the same
        # dashboard.
        first = self.factory.create_alert_subscription()
        second = self.factory.create_alert_subscription(alert=first.alert)
        first.notify = MagicMock()
        second.notify = MagicMock()

        with mock.patch("sqldesk.tasks.alerts.screenshots.for_alert", return_value=[("a.png", b"PNG")]) as draw:
            notify_subscriptions(first.alert, Alert.OK_STATE, metadata={})

        draw.assert_called_once()

    def test_hands_the_pictures_to_the_destination(self):
        subscription = self.factory.create_alert_subscription()
        subscription.notify = MagicMock()

        with mock.patch("sqldesk.tasks.alerts.screenshots.for_alert", return_value=[("a.png", b"PNG")]):
            notify_subscriptions(subscription.alert, Alert.OK_STATE, metadata={"Scheduled": False})

        metadata = subscription.notify.call_args[0][6]
        self.assertEqual(metadata["screenshots"], [("a.png", b"PNG")])
        # And whatever was already in there is still in there.
        self.assertIs(metadata["Scheduled"], False)

    def test_a_broken_renderer_does_not_stop_the_alert(self):
        """
        The guarantee the whole feature hangs on.

        A picture is a nice-to-have; an alert is not. If drawing one could
        stop a notification, this feature would make the product worse at the
        one job it has.
        """
        subscription = self.factory.create_alert_subscription()
        subscription.notify = MagicMock()

        with mock.patch("sqldesk.tasks.alerts.screenshots.for_alert", side_effect=Exception("renderer is down")):
            notify_subscriptions(subscription.alert, Alert.OK_STATE, metadata={})

        self.assertTrue(subscription.notify.called, "the alert must go out even when no picture can be drawn")
        self.assertEqual(subscription.notify.call_args[0][6]["screenshots"], [])

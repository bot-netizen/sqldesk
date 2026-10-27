from unittest import mock

from mock import ANY, MagicMock

import sqldesk.tasks.alerts
from sqldesk import models
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


class TestAnAlertKeepsItsHistory(BaseTestCase):
    """
    The alert row says where it is now and when it last moved. That answers
    "is this firing" and nothing else, so an alert that has gone off four
    times since breakfast looks exactly like one that went off once and
    stayed there -- and which of those is happening is usually the question.
    """

    def evaluates_to(self, state):
        patched = mock.patch.object(Alert, "evaluate", return_value=state)
        patched.start()
        self.addCleanup(patched.stop)

    def nothing_is_notified(self):
        patched = mock.patch.object(sqldesk.tasks.alerts, "notify_subscriptions")
        notifier = patched.start()
        self.addCleanup(patched.stop)
        return notifier

    def fires_of(self, alert):
        return (
            models.AlertFire.query.filter(models.AlertFire.alert_id == alert.id)
            .order_by(models.AlertFire.created_at, models.AlertFire.id)
            .all()
        )

    def test_a_state_change_is_written_down(self):
        self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)
        alert = self.factory.create_alert()

        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        (fire,) = self.fires_of(alert)
        self.assertEqual(Alert.TRIGGERED_STATE, fire.state)
        self.assertTrue(fire.notified)

    def test_firing_four_times_leaves_four_lines(self):
        # The whole point: a counter that says "four times today" needs four
        # rows, not one row updated four times.
        self.nothing_is_notified()
        alert = self.factory.create_alert()

        for state in (Alert.TRIGGERED_STATE, Alert.OK_STATE, Alert.TRIGGERED_STATE, Alert.OK_STATE):
            with mock.patch.object(Alert, "evaluate", return_value=state):
                check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertEqual(
            [Alert.TRIGGERED_STATE, Alert.OK_STATE, Alert.TRIGGERED_STATE, Alert.OK_STATE],
            [f.state for f in self.fires_of(alert)],
        )

    def test_a_state_that_did_not_change_writes_nothing(self):
        self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)
        alert = self.factory.create_alert()

        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertEqual(1, len(self.fires_of(alert)), "a history of a thing that did not happen")

    def test_a_muted_alert_is_recorded_but_marked_unsent(self):
        # It still changed state, and the history should say so. What it must
        # not say is that somebody was told.
        self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)
        alert = self.factory.create_alert(options={"muted": True, "op": "greater than", "value": 1, "column": "foo"})

        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        (fire,) = self.fires_of(alert)
        self.assertEqual(Alert.TRIGGERED_STATE, fire.state)
        self.assertFalse(fire.notified, "nothing was sent, so the history must not claim it was")

    def test_settling_from_unknown_to_ok_is_recorded_but_unsent(self):
        self.nothing_is_notified()
        self.evaluates_to(Alert.OK_STATE)
        alert = self.factory.create_alert()
        alert.state = Alert.UNKNOWN_STATE
        models.db.session.commit()

        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        (fire,) = self.fires_of(alert)
        self.assertEqual(Alert.OK_STATE, fire.state)
        self.assertFalse(fire.notified)

    def test_the_value_it_fired_on_is_kept(self):
        # "It fired" is a fact. "It fired at 412" is the one worth being woken
        # for. Not patching evaluate here, so the real one runs and records.
        self.nothing_is_notified()
        alert = self.factory.create_alert(options={"op": "greater than", "value": 400, "column": "n"})
        query_result = self.factory.create_query_result(data={"columns": [{"name": "n"}], "rows": [{"n": 412}]})
        alert.query_rel.latest_query_data = query_result
        models.db.session.commit()

        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        (fire,) = self.fires_of(alert)
        self.assertEqual(Alert.TRIGGERED_STATE, fire.state)
        self.assertEqual("412", fire.value)

    def test_deleting_an_alert_takes_its_history_with_it(self):
        self.nothing_is_notified()
        self.evaluates_to(Alert.TRIGGERED_STATE)
        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})
        self.assertEqual(1, len(self.fires_of(alert)))

        models.db.session.delete(alert)
        models.db.session.commit()

        self.assertEqual(0, models.AlertFire.query.count())

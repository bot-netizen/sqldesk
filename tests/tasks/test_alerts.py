from mock import ANY, MagicMock

import tealdash.tasks.alerts
from tealdash.models import Alert
from tealdash.tasks.alerts import check_alerts_for_query, notify_subscriptions
from tests import BaseTestCase


class TestCheckAlertsForQuery(BaseTestCase):
    def test_notifies_subscribers_when_should(self):
        tealdash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertTrue(tealdash.tasks.alerts.notify_subscriptions.called)

    def test_doesnt_notify_when_nothing_changed(self):
        tealdash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.OK_STATE)

        alert = self.factory.create_alert()
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(tealdash.tasks.alerts.notify_subscriptions.called)

    def test_doesnt_notify_when_muted(self):
        tealdash.tasks.alerts.notify_subscriptions = MagicMock()
        Alert.evaluate = MagicMock(return_value=Alert.TRIGGERED_STATE)

        alert = self.factory.create_alert(options={"muted": True})
        check_alerts_for_query(alert.query_id, metadata={"Scheduled": False})

        self.assertFalse(tealdash.tasks.alerts.notify_subscriptions.called)


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

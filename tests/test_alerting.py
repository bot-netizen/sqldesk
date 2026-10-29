from unittest import mock

from sqldesk import alerting, models, settings
from tests import BaseTestCase


class AlertingTestCase(BaseTestCase):
    def an_alert(self, column="orders", op="<", value=100, rows=None, **options):
        query = self.factory.create_query()
        result = self.factory.create_query_result(
            data={
                "columns": [{"name": column, "type": "integer"}],
                "rows": rows if rows is not None else [{column: 87}],
            }
        )
        query.latest_query_data = result
        models.db.session.add(query)
        alert = self.factory.create_alert(
            query_rel=query,
            options=dict({"column": column, "op": op, "value": value}, **options),
        )
        models.db.session.commit()
        return alert


class TestSayingTheNumber(AlertingTestCase):
    """
    "Orders just triggered" tells somebody the one thing they already knew
    from the fact that the message arrived.
    """

    def test_the_headline_carries_the_reading_and_the_line_it_crossed(self):
        alert = self.an_alert()

        headline = alerting.headline(alert, "triggered")

        self.assertIn("87", headline)
        self.assertIn("100", headline)

    def test_the_operator_is_read_the_way_somebody_says_it(self):
        for op, word in (("<", "below"), (">", "above"), (">=", "at or above"), ("<=", "at or below")):
            with self.subTest(op=op):
                alert = self.an_alert(op=op)
                self.assertIn(word, alerting.condition(alert))

    def test_an_operator_nobody_has_a_word_for_is_printed_as_written(self):
        alert = self.an_alert(op="~=")

        self.assertIn("~=", alerting.condition(alert))

    def test_a_recovery_says_so_without_pretending_to_be_a_fire(self):
        alert = self.an_alert()

        self.assertIn("normal", alerting.headline(alert, "ok"))

    def test_a_custom_subject_wins_because_somebody_wrote_it(self):
        alert = self.an_alert(custom_subject="Orders are down again")

        self.assertEqual("Orders are down again", alerting.headline(alert, "triggered"))

    def test_a_very_long_value_is_cut_rather_than_filling_the_message(self):
        alert = self.an_alert(value="x" * 200)

        self.assertLessEqual(len(alerting.condition(alert)), alerting.MAX_VALUE + 40)


class TestNothingHereRaises(AlertingTestCase):
    """
    This runs at the moment an alert has something to say, which is the worst
    possible moment for the formatting of a message to be what fails.
    """

    def test_an_alert_with_no_condition_still_gets_a_headline(self):
        alert = self.an_alert()
        alert.options = {}

        self.assertIn(alert.name, alerting.headline(alert, "triggered"))

    def test_a_column_the_result_does_not_have_reads_as_no_value(self):
        alert = self.an_alert(column="orders", rows=[{"something_else": 1}])

        self.assertIsNone(alerting.latest_value(alert))

    def test_an_empty_result_reads_as_no_value(self):
        alert = self.an_alert(rows=[])

        self.assertIsNone(alerting.latest_value(alert))
        self.assertIsNotNone(alerting.headline(alert, "triggered"))

    def test_a_query_with_no_result_at_all_does_not_raise(self):
        alert = self.an_alert()
        alert.query_rel.latest_query_data = None
        models.db.session.commit()

        self.assertIsNone(alerting.latest_value(alert))
        self.assertIsNotNone(alerting.headline(alert, "triggered"))

    def test_a_subject_template_that_blows_up_does_not_take_the_message_with_it(self):
        alert = self.an_alert()
        with mock.patch.object(type(alert), "subject_for", side_effect=RuntimeError("boom")):
            self.assertIsNotNone(alerting.headline(alert, "triggered"))


class TestFlapping(AlertingTestCase):
    def test_more_than_one_fire_is_worth_saying(self):
        self.assertIn("4 times", alerting.how_often(None, 4))

    def test_one_fire_is_not(self):
        # "Fired 1 time in the last 24 hours" is noise on the alert that just
        # fired.
        self.assertIsNone(alerting.how_often(None, 1))

    def test_no_count_says_nothing(self):
        self.assertIsNone(alerting.how_often(None, None))
        self.assertIsNone(alerting.how_often(None, 0))


class TestTheDefaultEmailIsGone(AlertingTestCase):
    """
    Subscribing used to mean being emailed, whether or not anybody asked for
    mail and whether or not the install had a mail server.
    """

    def subscribe_without_a_destination(self):
        alert = self.an_alert()
        subscription = models.AlertSubscription(alert=alert, user=self.factory.user, destination=None)
        models.db.session.add(subscription)
        models.db.session.commit()
        return alert, subscription

    def test_a_subscription_with_no_destination_sends_nothing(self):
        alert, subscription = self.subscribe_without_a_destination()

        with mock.patch("sqldesk.destinations.email.Email.notify") as send:
            subscription.notify(alert, alert.query_rel, self.factory.user, "triggered", None, "http://localhost", {})

        self.assertFalse(send.called)

    def test_the_old_behaviour_can_be_put_back_for_an_install_relying_on_it(self):
        # An alert quietly ceasing to notify on upgrade is a bad way to find
        # out, so the escape hatch exists -- it is just not the default.
        alert, subscription = self.subscribe_without_a_destination()

        with mock.patch.object(settings, "ALERT_EMAIL_FALLBACK", True):
            with mock.patch("sqldesk.destinations.email.Email.notify") as send:
                subscription.notify(
                    alert, alert.query_rel, self.factory.user, "triggered", None, "http://localhost", {}
                )

        self.assertTrue(send.called)

    def test_a_subscription_with_a_destination_is_untouched(self):
        alert = self.an_alert()
        destination = self.factory.create_destination()
        subscription = models.AlertSubscription(alert=alert, user=self.factory.user, destination=destination)
        models.db.session.add(subscription)
        models.db.session.commit()

        with mock.patch.object(type(destination), "notify") as send:
            subscription.notify(alert, alert.query_rel, self.factory.user, "triggered", None, "http://localhost", {})

        self.assertTrue(send.called)

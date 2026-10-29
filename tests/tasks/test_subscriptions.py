import datetime
from unittest import mock

from sqldesk import models, settings
from sqldesk.models import db
from sqldesk.tasks import subscriptions as task
from tests import BaseTestCase


def _rendering_on():
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


class SendingTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.factory.create_admin()
        self.dashboard = self.factory.create_dashboard()
        db.session.commit()

    def _subscription(self, **overrides):
        fields = {
            "org": self.factory.org,
            "dashboard": self.dashboard,
            "user": self.owner,
            "schedule": {"interval": 3600},
            "format": models.DashboardSubscription.PNG,
            "recipient_ids": [self.owner.id],
            "active": True,
        }
        fields.update(overrides)
        subscription = models.DashboardSubscription(**fields)
        db.session.add(subscription)
        db.session.commit()
        return subscription


class TestWhichAreDue(SendingTestCase):
    def test_one_never_sent_is_due_at_once(self):
        subscription = self._subscription()

        self.assertTrue(task._is_due(subscription, datetime.datetime.now(datetime.timezone.utc)))

    def test_one_sent_a_moment_ago_is_not(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        subscription = self._subscription()
        subscription.last_sent_at = now - datetime.timedelta(minutes=1)

        self.assertFalse(task._is_due(subscription, now))

    def test_one_sent_longer_ago_than_its_interval_is(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        subscription = self._subscription()
        subscription.last_sent_at = now - datetime.timedelta(hours=2)

        self.assertTrue(task._is_due(subscription, now))

    def test_nothing_is_queued_where_there_is_no_renderer(self):
        self._subscription()

        with mock.patch.object(task.screenshots, "enabled", return_value=False):
            with mock.patch.object(task.send_subscription, "delay") as delay:
                task.send_due_subscriptions()

        delay.assert_not_called()

    def test_a_paused_one_is_never_queued(self):
        self._subscription(active=False)

        with _rendering_on(), mock.patch.object(task.send_subscription, "delay") as delay:
            task.send_due_subscriptions()

        delay.assert_not_called()

    def test_a_due_one_is_queued_under_its_own_name(self):
        # Named after the subscription so a send already queued is not queued
        # again because this ran while the first was still drawing.
        subscription = self._subscription()

        with _rendering_on(), mock.patch.object(task.send_subscription, "delay") as delay:
            task.send_due_subscriptions()

        delay.assert_called_once_with(subscription.id, job_id="subscription-{}".format(subscription.id))


class TestSending(SendingTestCase):
    def _send(self, subscription, picture=b"PNG"):
        with _rendering_on(), mock.patch.object(task.screenshots, "capture", return_value=picture) as capture:
            with mock.patch.object(task.mail, "send") as send:
                task.send_subscription(subscription.id)
        return capture, send

    def test_it_mails_the_recipients_and_records_the_send(self):
        subscription = self._subscription()

        _, send = self._send(subscription)

        self.assertEqual(1, send.call_count)
        message = send.call_args[0][0]
        self.assertEqual([self.owner.email], message.recipients)
        self.assertIn(self.dashboard.name, message.subject)
        self.assertIsNotNone(subscription.last_sent_at)
        self.assertIsNone(subscription.last_error)

    def test_a_recipient_who_cannot_see_every_widget_is_not_sent_it(self):
        """Asked at each send: their access, or the dashboard, may have changed since they were added."""
        colleague = _half_visible(self.factory, self.dashboard)
        subscription = self._subscription(recipient_ids=[self.owner.id, colleague.id])

        _, send = self._send(subscription)

        self.assertEqual([[self.owner.email]], [call[0][0].recipients for call in send.call_args_list])
        self.assertIsNotNone(subscription.last_sent_at)
        self.assertIn(colleague.name, subscription.last_error)

    def test_a_dashboard_with_a_query_that_never_ran_is_still_sent(self):
        """
        It failed at "how old are the numbers" -- `Query.retrieved_at` assumed
        a result -- and the subscription recorded that the mail server would
        not take it, then tried again every minute.
        """
        never_ran = self.factory.create_query()
        visualization = self.factory.create_visualization(query_rel=never_ran)
        self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()
        subscription = self._subscription()

        _, send = self._send(subscription)

        self.assertEqual(1, send.call_count)
        self.assertIsNone(subscription.last_error)
        self.assertIn("have not been refreshed", send.call_args[0][0].html)

    def test_a_picture_goes_inline_so_it_is_seen(self):
        subscription = self._subscription(format=models.DashboardSubscription.PNG)

        _, send = self._send(subscription)

        attachment = send.call_args[0][0].attachments[0]
        self.assertEqual("image/png", attachment.content_type)
        self.assertEqual("inline", attachment.disposition)
        self.assertIn("cid:sqldesk-dashboard", send.call_args[0][0].html)

    def test_a_pdf_is_attached_rather_than_shown(self):
        subscription = self._subscription(format=models.DashboardSubscription.PDF)

        capture, send = self._send(subscription, picture=b"%PDF-")

        self.assertEqual("pdf", capture.call_args[1]["fmt"])
        attachment = send.call_args[0][0].attachments[0]
        self.assertEqual("application/pdf", attachment.content_type)
        self.assertTrue(attachment.filename.endswith(".pdf"))

    def test_the_email_says_how_old_the_numbers_are(self):
        # A subscription sends stored results. Somebody reading Tuesday's
        # figures on Thursday should be told, not left to assume.
        query = self.factory.create_query(latest_query_data=self.factory.create_query_result())
        visualization = self.factory.create_visualization(query_rel=query)
        self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()
        subscription = self._subscription()

        _, send = self._send(subscription)

        self.assertIn("Numbers as of", send.call_args[0][0].html)

    def test_and_says_so_when_there_are_none(self):
        # A dashboard whose queries have never run. Silence here would read
        # as "these are current".
        subscription = self._subscription()

        _, send = self._send(subscription)

        self.assertIn("have not been refreshed", send.call_args[0][0].html)


class TestWhenItCannotBeSent(SendingTestCase):
    """
    None of these raise. The subscription records why on itself -- the owner
    sees it on the dashboard -- and the other nineteen still go out.
    """

    def _attempt(self, subscription, **patches):
        with _rendering_on():
            with mock.patch.object(task.screenshots, "capture", **patches) as capture:
                with mock.patch.object(task.mail, "send") as send:
                    task.send_subscription(subscription.id)
        return capture, send

    def test_a_renderer_that_cannot_draw_it(self):
        subscription = self._subscription()

        _, send = self._attempt(subscription, return_value=None)

        send.assert_not_called()
        self.assertIn("could not draw", subscription.last_error)
        self.assertIsNone(subscription.last_sent_at)

    def test_a_dashboard_that_has_grown_too_big_since(self):
        subscription = self._subscription()
        for _ in range(13):
            visualization = self.factory.create_visualization()
            self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()

        _, send = self._attempt(subscription, return_value=b"PNG")

        send.assert_not_called()
        self.assertIn("one-page report", subscription.last_error)

    def test_an_owner_who_has_lost_sight_of_it(self):
        subscription = self._subscription()

        with _rendering_on():
            with mock.patch.object(task.screenshots, "may_see_dashboard", return_value=False):
                with mock.patch.object(task.mail, "send") as send:
                    task.send_subscription(subscription.id)

        send.assert_not_called()
        self.assertIn("can no longer see", subscription.last_error)

    def test_a_disabled_owner(self):
        subscription = self._subscription()
        self.owner.disable()
        db.session.commit()

        _, send = self._attempt(subscription, return_value=b"PNG")

        send.assert_not_called()
        self.assertIn("gone", subscription.last_error)

    def test_a_paused_subscription_is_simply_not_sent(self):
        subscription = self._subscription(active=False)

        _, send = self._attempt(subscription, return_value=b"PNG")

        send.assert_not_called()
        # And no error recorded: pausing is not a fault.
        self.assertIsNone(subscription.last_error)

    def test_a_mail_server_that_will_not_take_it(self):
        subscription = self._subscription()

        with _rendering_on():
            with mock.patch.object(task.screenshots, "capture", return_value=b"PNG"):
                with mock.patch.object(task.mail, "send", side_effect=Exception("no route to host")):
                    task.send_subscription(subscription.id)

        self.assertIn("mail server", subscription.last_error)
        self.assertIsNone(subscription.last_sent_at)

    def test_a_send_that_works_clears_an_earlier_problem(self):
        subscription = self._subscription()
        subscription.last_error = "The renderer could not draw this dashboard."
        db.session.add(subscription)
        db.session.commit()

        self._attempt(subscription, return_value=b"PNG")

        self.assertIsNone(subscription.last_error)

    def test_a_subscription_deleted_between_queueing_and_sending(self):
        subscription = self._subscription()
        subscription_id = subscription.id
        db.session.delete(subscription)
        db.session.commit()

        with _rendering_on(), mock.patch.object(task.mail, "send") as send:
            task.send_subscription(subscription_id)  # must not raise

        send.assert_not_called()


class TestAFailedSendBacksOff(SendingTestCase):
    """
    A failed send left `last_sent_at` alone, so it was due again a minute
    later: a refused address meant everybody before it got the dashboard every
    minute, and a broken renderer drew it every minute, all day.
    """

    def test_it_waits_longer_after_each_failure(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        subscription = self._subscription(failures=2, last_attempt_at=now)

        self.assertFalse(task._is_due(subscription, now + datetime.timedelta(minutes=3)))
        self.assertTrue(task._is_due(subscription, now + datetime.timedelta(minutes=5)))

    def test_and_never_more_than_an_hour(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        subscription = self._subscription(failures=20, last_attempt_at=now)

        self.assertTrue(task._is_due(subscription, now + datetime.timedelta(minutes=61)))

    def test_one_refused_address_does_not_resend_to_the_others(self):
        colleague = self.factory.create_admin(email="colleague@example.com")
        db.session.commit()
        subscription = self._subscription(recipient_ids=[self.owner.id, colleague.id])

        def refuse_the_colleague(message):
            if colleague.email in message.recipients:
                raise RuntimeError("550 no such mailbox")

        with _rendering_on(), mock.patch.object(task.screenshots, "capture", return_value=b"PNG"):
            with mock.patch.object(task.mail, "send", side_effect=refuse_the_colleague) as send:
                task.send_subscription(subscription.id)
                # And the next minute's run finds it already sent.
                task.send_subscription(subscription.id)

        self.assertEqual(2, send.call_count)
        self.assertIsNotNone(subscription.last_sent_at)
        self.assertEqual(0, subscription.failures)
        self.assertIn(colleague.name, subscription.last_error)

    def test_a_send_nobody_received_counts_as_a_failure(self):
        subscription = self._subscription()

        with _rendering_on(), mock.patch.object(task.screenshots, "capture", return_value=b"PNG"):
            with mock.patch.object(task.mail, "send", side_effect=RuntimeError("down")):
                task.send_subscription(subscription.id)

        self.assertIsNone(subscription.last_sent_at)
        self.assertEqual(1, subscription.failures)
        self.assertIsNotNone(subscription.last_attempt_at)

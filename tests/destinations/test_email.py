from unittest import mock

from sqldesk.destinations.email import Email
from tests import BaseTestCase


class TestEmailAttachments(BaseTestCase):
    """
    The pictures an alert was told to attach, arriving in the email.

    Inline by content-id rather than as attachments, because an attachment is
    a thing nobody opens and the point of this feature is that you see the
    chart without leaving your inbox.
    """

    def _notify(self, metadata, custom_body=None):
        # The default body template renders the result that fired the alert,
        # so the query needs one.
        result = self.factory.create_query_result(
            data={"rows": [{"value": 1}], "columns": [{"name": "value", "type": "INTEGER"}]}
        )
        query = self.factory.create_query(latest_query_data_id=result.id)
        alert = self.factory.create_alert(
            query_rel=query,
            options={"selector": "first", "op": "equals", "column": "value", "value": "1"},
        )
        if custom_body is not None:
            alert.options = dict(alert.options or {}, custom_body=custom_body)

        options = {"addresses": "someone@example.com"}
        with mock.patch("sqldesk.destinations.email.mail") as mail:
            Email(options).notify(
                alert=alert,
                query=alert.query_rel,
                user=self.factory.user,
                new_state="triggered",
                app=None,
                host="http://localhost",
                metadata=metadata,
                options=options,
            )

        self.assertTrue(mail.send.called, "the alert should have been sent")
        message = mail.send.call_args[0][0]

        # Serialised, not just inspected. A mocked mailer never builds the
        # MIME message, so a malformed attachment header sails through every
        # assertion below and then raises on the first real send -- which is
        # exactly what happened: flask_mail iterates `attachment.headers` as
        # (key, value) pairs and a dict blew up on unpack.
        message.as_bytes()

        return message

    def test_carries_each_picture(self):
        message = self._notify({"screenshots": [("a.png", b"PNG-A"), ("b.png", b"PNG-B")]})

        self.assertEqual(len(message.attachments), 2)
        self.assertEqual([a.filename for a in message.attachments], ["a.png", "b.png"])
        self.assertEqual(message.attachments[0].content_type, "image/png")

    def test_shows_them_in_the_body(self):
        message = self._notify({"screenshots": [("a.png", b"PNG-A")]})

        # Referenced by the content-id the attachment was given, or the image
        # is carried and never displayed.
        self.assertIn("cid:sqldesk-attachment-0", message.html)

    def test_sends_nothing_extra_when_there_are_no_pictures(self):
        message = self._notify({})

        self.assertEqual(message.attachments, [])

    def test_leaves_a_custom_body_alone(self):
        # Somebody who wrote their own body wrote all of it. Appending to it
        # is not ours to do.
        message = self._notify({"screenshots": [("a.png", b"PNG-A")]}, custom_body="Just this.")

        self.assertEqual(message.html, "Just this.")
        self.assertEqual(message.attachments, [])

    def test_an_alert_still_sends_when_the_metadata_is_empty(self):
        # Every other destination is handed the same metadata; email must not
        # be the one that falls over when a caller passes nothing.
        message = self._notify(None)

        self.assertEqual(message.attachments, [])

    def test_the_message_survives_being_turned_into_an_email(self):
        """
        The check the mocked mailer cannot make.

        Everything else here inspects the Message object. This one builds the
        MIME bytes the SMTP server would actually receive, which is where a
        malformed attachment header shows up.
        """
        message = self._notify({"screenshots": [("a.png", b"PNG-A")]})
        raw = message.as_bytes()

        self.assertIn(b"Content-ID: <sqldesk-attachment-0>", raw)
        self.assertIn(b"image/png", raw)
        self.assertIn(b"inline", raw)

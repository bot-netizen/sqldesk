import logging

from flask_mail import Message

from sqldesk import mail, settings
from sqldesk.destinations import BaseDestination, register


class Email(BaseDestination):
    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "addresses": {"type": "string"},
                "subject_template": {
                    "type": "string",
                    "default": settings.ALERTS_DEFAULT_MAIL_SUBJECT_TEMPLATE,
                    "title": "Subject Template",
                },
            },
            "required": ["addresses"],
            "extra_options": ["subject_template"],
        }

    @classmethod
    def icon(cls):
        return "fa-envelope"

    def notify(self, alert, query, user, new_state, app, host, metadata, options):
        recipients = [email for email in options.get("addresses", "").split(",") if email]

        if not recipients:
            logging.warning("No emails given. Skipping send.")

        if alert.custom_body:
            html = alert.custom_body
        else:
            with open(settings.SQLDESK_ALERTS_DEFAULT_MAIL_BODY_TEMPLATE_FILE, "r") as f:
                html = alert.render_template(f.read())
        logging.debug("Notifying: %s", recipients)

        try:
            state = new_state.upper()
            if alert.custom_subject:
                subject = alert.custom_subject
            else:
                subject_template = options.get("subject_template", settings.ALERTS_DEFAULT_MAIL_SUBJECT_TEMPLATE)
                subject = subject_template.format(alert_name=alert.name, state=state)

            message = Message(recipients=recipients, subject=subject, html=html)

            # Pictures of whatever the alert was told to attach, drawn once
            # for the whole notification in tasks/alerts.py. Inline by
            # content-id and appended to the body, so they are seen rather
            # than sitting as attachments nobody opens. A custom body is left
            # exactly as written -- it is not ours to append to.
            images = (metadata or {}).get("screenshots") or []
            if images and not alert.custom_body:
                parts = []
                for index, (filename, png) in enumerate(images):
                    cid = f"sqldesk-attachment-{index}"
                    message.attach(
                        filename,
                        "image/png",
                        png,
                        disposition="inline",
                        headers={"Content-ID": f"<{cid}>"},
                    )
                    parts.append(f'<div style="margin-top:16px"><img src="cid:{cid}" style="max-width:100%"></div>')
                message.html = html + "".join(parts)

            mail.send(message)
        except Exception:
            logging.exception("Mail send error.")


register(Email)

"""
An alert to a Slack incoming webhook.

The simplest destination there is: paste a URL, get a message. It cannot
upload a file, so an alert on a chart arrives without the chart -- `slack_app`
is the one that carries pictures, and both exist on purpose.

What this one can do, and did not, is say the number. A message reading
"Orders just triggered" tells somebody the one thing they already knew from
the fact that it arrived; *orders fell to 87 and the line is 100* is what
they were woken for. The wording is shared with the app destination in
`sqldesk/alerting.py` so the two do not drift.
"""

import logging

import requests

from sqldesk import alerting
from sqldesk.destinations import BaseDestination, register
from sqldesk.utils import json_dumps

logger = logging.getLogger(__name__)

#: Slack renders a left-hand bar in this colour. Red for a threshold crossed,
#: green for one that cleared -- the state is readable before the words are.
TRIGGERED = "#c0392b"
RECOVERED = "#27ae60"

#: Slack truncates a section past this, and an alert has no business being
#: near it.
MAX_TEXT = 2800


class Slack(BaseDestination):
    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "title": "Slack Webhook URL"},
            },
            "secret": ["url"],
        }

    @classmethod
    def icon(cls):
        return "fa-slack"

    def notify(self, alert, query, user, new_state, app, host, metadata, options):
        url = (options or {}).get("url")
        if not url:
            logger.warning("alert %s has a Slack destination with no webhook URL", alert.id)
            return

        triggered = new_state == "triggered"
        payload = {
            # Blocks inside an attachment rather than either alone: blocks are
            # what Slack renders properly now, and the attachment is the only
            # thing that still draws the coloured bar down the side.
            "attachments": [
                {
                    "color": TRIGGERED if triggered else RECOVERED,
                    "blocks": self._blocks(alert, query, new_state, host, metadata),
                    # What a notification preview and a screen reader get.
                    "fallback": alerting.headline(alert, new_state),
                }
            ]
        }

        try:
            response = requests.post(url, data=json_dumps(payload).encode("utf-8"), timeout=5.0)
            if response.status_code != 200:
                # The body, because Slack puts the reason there -- "invalid_payload"
                # and "channel_not_found" need different fixes and the status code
                # is 400 for both.
                logger.error(
                    "alert %s could not be sent to Slack: %s %s",
                    alert.id,
                    response.status_code,
                    (response.text or "")[:200],
                )
        except Exception:
            logger.exception("alert %s could not be sent to Slack", alert.id)

    def _blocks(self, alert, query, new_state, host, metadata):
        headline = alerting.headline(alert, new_state)
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*{}*".format(headline[:MAX_TEXT])}}]

        body = ""
        try:
            # Unescaped, and rendered once. Slack is not HTML, so a result
            # containing `&` should arrive as `&` rather than `&amp;` -- and
            # filling a template in is a query result read and a render, not
            # something to do twice to find out whether it is empty.
            body = alert.body_for(escape=False) or ""
        except Exception:
            logger.warning("could not render the body for alert %s", alert.id, exc_info=True)
        if body:
            # Exactly as written. A custom body is not ours to append to.
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body[:MAX_TEXT]}})

        # The small print: how often it has gone off, and whether anybody has
        # muted it. Context rather than a section, so it reads as a footnote.
        notes = []
        often = alerting.how_often(alert, (metadata or {}).get("fires_24h"))
        if often:
            notes.append("Fired {}".format(often))
        if getattr(alert, "muted", False):
            notes.append("This alert is muted, so nobody else was told")
        links = alerting.links(alert, query, host)
        if links:
            notes.append(links)
        if notes:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(notes)[:MAX_TEXT]}]})

        # A webhook cannot upload, so say the picture exists rather than
        # dropping it silently -- an alert about a chart arriving with no
        # chart and no explanation reads as the alert being broken.
        if (metadata or {}).get("screenshots"):
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                "A picture was drawn for this alert. A webhook cannot carry one — "
                                "the Slack (app) destination can."
                            ),
                        }
                    ],
                }
            )

        return blocks


register(Slack)

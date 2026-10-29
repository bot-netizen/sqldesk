"""
An alert to Slack through the app, which can carry the picture.

The existing Slack destination posts to an incoming webhook. A webhook cannot
upload a file, so an alert sent that way says a threshold was crossed and shows
nothing -- which for an alert on a chart is most of the information missing.
This one posts as the app installed under Settings → Slack, so it can upload
the pictures the alert was told to attach and put them in the message.

Both exist on purpose. A webhook needs nothing set up beyond a URL and works
where nobody wants to install an app; this needs the app and gives you the
picture. Replacing the webhook one would break every alert already using it for
a feature not everybody wants.

What it does **not** do is take a token of its own. The token is the
organisation's, entered once by an administrator and stored encrypted; a
destination that carried its own would mean a bot token in a form field on a
page anybody with alert permissions can reach.
"""

import logging

from sqldesk import alerting, models, slack
from sqldesk.destinations import BaseDestination, register

logger = logging.getLogger(__name__)

#: Slack's own limit on a message's text block is 3000 characters; a line about
#: an alert has no business being near it.
MAX_TEXT = 1500


class SlackApp(BaseDestination):
    @classmethod
    def name(cls):
        return "Slack (app)"

    @classmethod
    def type(cls):
        return "slack_app"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "title": "Channel",
                    "info": "Its name or its id. For a private channel, invite the app to it first.",
                },
            },
            "required": ["channel"],
        }

    @classmethod
    def icon(cls):
        return "fa-slack"

    def notify(self, alert, query, user, new_state, app, host, metadata, options):
        workspace = models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == query.org_id).first()
        if workspace is None:
            # Said once, with what to do. An alert firing into nothing every
            # five minutes is worse than one that never fired.
            logger.warning(
                "alert %s uses Slack (app) but no workspace is connected; "
                "an administrator adds the app's token under Settings -> Slack",
                alert.id,
            )
            return

        channel = (options.get("channel") or "").strip()
        if not channel:
            logger.warning("alert %s has a Slack (app) destination with no channel", alert.id)
            return

        text = self._text(alert, query, new_state, host, metadata)
        file_ids, problems = self._upload(workspace, metadata)

        _posted, error = slack.post(
            workspace.bot_token,
            channel,
            text,
            file_id=file_ids[0] if file_ids else None,
            footer="; ".join(problems) if problems else None,
            button={"text": "Open query", "url": "{}/queries/{}".format(host, query.id)},
        )
        if error:
            workspace.last_error = error
            models.db.session.commit()
            logger.warning("alert %s could not be sent to Slack: %s", alert.id, error)
            return
        if workspace.last_error:
            workspace.last_error = None
            models.db.session.commit()

        # Anything past the first picture, as its own message. A Slack message
        # carries one image block, and an alert told to attach three dashboards
        # should send three rather than silently send one.
        for file_id in file_ids[1:]:
            slack.post(workspace.bot_token, channel, "", file_id=file_id)

    def _text(self, alert, query, new_state, host, metadata=None):
        # The headline carries the number now -- "Orders: 87, below 100"
        # rather than "Orders just triggered", which says only what the
        # arrival of the message already said. Shared with the webhook
        # destination so the two do not drift.
        lines = ["*{}*".format(alerting.headline(alert, new_state))]

        body = alert.body_for(escape=False)
        if body:
            # Exactly as written. A custom body is not ours to append to.
            lines.append(body[:MAX_TEXT])

        notes = []
        often = alerting.how_often(alert, (metadata or {}).get("fires_24h"))
        if often:
            notes.append("Fired {}".format(often))
        if alert.muted:
            notes.append("muted, so nobody else was told")
        notes.append(alerting.links(alert, query, host) or "")
        lines.append(" \u00b7 ".join(one for one in notes if one))
        return "\n".join(lines)

    def _upload(self, workspace, metadata):
        """
        The pictures, uploaded. Returns `(file_ids, problems)`.

        A picture that will not upload must not stop the alert: the threshold
        was still crossed, and somebody still needs to know. What goes in the
        message instead is a line saying the picture is missing, because an
        alert about a chart arriving with no chart and no explanation reads as
        the alert being broken.
        """
        images = (metadata or {}).get("screenshots") or []
        file_ids, problems = [], []
        for picture in images:
            file_id, error = slack.upload(workspace.bot_token, picture["filename"], picture["image"])
            if error:
                logger.warning("could not upload %s to Slack: %s", picture["filename"], error)
                problems.append("{} could not be attached".format(picture.get("title") or picture["filename"]))
                continue
            file_ids.append(file_id)
        return file_ids, problems


register(SlackApp)

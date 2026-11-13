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
        """
        Post the alert, with its first picture inside the message and any
        others shared into the channel after it.

        Returns `{ok, detail}` for the alert's history, which is where "it
        fired but nothing arrived" gets its answer: posted, posted with a
        picture missing, or not posted and why.
        """
        workspace = models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == query.org_id).first()
        if workspace is None:
            # Said once, with what to do. An alert firing into nothing every
            # five minutes is worse than one that never fired.
            logger.warning(
                "alert %s uses Slack (app) but no workspace is connected; "
                "an administrator adds the app's token under Settings -> Slack",
                alert.id,
            )
            return {
                "ok": False,
                "detail": "Slack is not set up: an administrator adds the app under Settings -> Slack.",
            }

        channel = (options.get("channel") or "").strip()
        if not channel:
            logger.warning("alert %s has a Slack (app) destination with no channel", alert.id)
            return {"ok": False, "detail": "This Slack destination has no channel."}

        pictures = (metadata or {}).get("screenshots") or []
        logger.info("slack: alert %s (%s) to %s, with %s picture(s)", alert.id, new_state, channel, len(pictures))
        text = self._text(alert, query, new_state, host, metadata)
        token = workspace.bot_token

        # The first picture goes inside the message; uploaded on its own,
        # unshared, so the message can carry it. A picture that will not
        # upload must not stop the alert -- the threshold was still crossed --
        # so it becomes a line in the message saying it is missing instead.
        problems = []
        file_id = None
        if pictures:
            file_id, error = slack.upload(token, pictures[0]["filename"], pictures[0]["image"])
            if error:
                logger.warning("could not upload %s to Slack: %s", pictures[0]["filename"], error)
                problems.append(self._missing(pictures[0]))

        # No button to an address nobody in the channel could open, such as
        # localhost -- see `slack.public_link`.
        link = slack.public_link("{}/queries/{}".format(host, query.id))
        if link is None:
            logger.info("slack: no button on alert %s: %s is not an address people in Slack can open", alert.id, host)
        button = {"text": "Open query", "url": link} if link else None
        footer = "; ".join(problems) if problems else None

        _posted, code, error = slack.post_message(token, channel, text, file_id=file_id, footer=footer, button=button)
        as_files = False
        if error and code in slack.LAYOUT_REFUSALS and file_id:
            # Slack would not take the message around the picture. The alert
            # still goes -- words and button, no image block -- and the
            # picture follows it as a file, so it is not lost to the layout.
            logger.warning(
                "slack: %s refused alert %s's layout (%s); sending the words, then the pictures as files",
                channel,
                alert.id,
                code,
            )
            _posted, code, error = slack.post_message(token, channel, text, footer=footer, button=button)
            as_files = not error

        if error:
            workspace.last_error = error
            models.db.session.commit()
            logger.warning("alert %s could not be sent to Slack: %s", alert.id, error)
            return {"ok": False, "detail": error}
        logger.info("slack: alert %s sent to %s", alert.id, channel)
        if workspace.last_error:
            workspace.last_error = None
            models.db.session.commit()

        # Every picture the message did not carry, shared into the channel
        # with its own title. A Slack message carries one image block, and an
        # alert told to attach three dashboards should deliver three. (Each
        # used to go as a message of its own with no words, which Slack
        # refuses: a section's text cannot be empty.)
        attached = 1 if file_id and not as_files else 0
        following = pictures if as_files else pictures[1:]
        for picture in following:
            _shared, share_error = slack.upload(
                token, picture["filename"], picture["image"], channel=channel, comment=picture.get("title")
            )
            if share_error:
                logger.warning("could not share %s into %s: %s", picture["filename"], channel, share_error)
                problems.append(self._missing(picture))
            else:
                attached += 1

        detail = "Posted to {}".format(channel)
        if pictures:
            detail += " with {} of {} picture{}{}".format(
                attached, len(pictures), "" if len(pictures) == 1 else "s", ", as files" if as_files else ""
            )
        if problems:
            detail += " -- " + "; ".join(problems)
        return {"ok": True, "detail": detail}

    @staticmethod
    def _missing(picture):
        return "{} could not be attached".format(picture.get("title") or picture["filename"])

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


register(SlackApp)

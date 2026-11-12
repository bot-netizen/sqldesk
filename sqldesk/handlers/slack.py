"""
Settings → Slack, and sending a dashboard to a channel.

Two audiences in one file, with two different permission checks. An
administrator installs the app and pastes its token, once. Anybody with
`send_dashboards` picks a channel and sends. Keeping them together is
deliberate: the send has to know what the setup stored, and splitting them
would mean two modules importing each other.
"""

import logging

from flask import request
from flask_restful import abort

from sqldesk import features, models, one_page, screenshots, slack
from sqldesk.destinations import get_configuration_schema_for_destination_type
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import can_see_dashboard, require_admin
from sqldesk.utils import utcnow
from sqldesk.utils.configuration import ConfigurationContainer

logger = logging.getLogger(__name__)

#: A line somebody types above the picture. Long enough for a sentence of
#: context, short enough that the message is still mostly the dashboard.
MAX_MESSAGE = 1000


def _workspace(org, required=True):
    found = models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == org.id).first()
    if found is None and required:
        abort(400, message="Slack is not set up. An administrator adds the app's token under Settings.")
    return found


class SlackSettingsResource(BaseResource):
    """
    What is installed, and a token to replace it with.

    The token is never sent back, not even partially. A bot token posts as the
    app in every channel the app is in and does not expire, so there is no
    version of showing it that is worth the risk -- the page says which
    workspace it belongs to, which is the question somebody actually has.
    """

    @require_admin
    def get(self):
        found = _workspace(self.current_org, required=False)
        if found is None:
            return {"configured": False}
        return {
            "configured": True,
            "team_name": found.team_name,
            "app_name": found.app_name,
            "installed_by": found.installed_by.name if found.installed_by else None,
            "installed_at": found.created_at,
            "working": found.working,
            "last_error": found.last_error,
            "last_checked_at": found.last_checked_at,
        }

    @require_admin
    def post(self):
        body = request.get_json(silent=True) or {}
        token = (body.get("bot_token") or "").strip()
        if not token:
            abort(400, message="Paste the Slack app's bot token.")

        # Checked against Slack before it is stored, so a wrong token is
        # refused while somebody is still looking at the field rather than the
        # first time a dashboard fails to send.
        who, error = slack.check(token)
        if error:
            abort(400, message=error)

        found = _workspace(self.current_org, required=False)
        if found is None:
            found = models.SlackWorkspace(org=self.current_org)
            models.db.session.add(found)
        found.bot_token = token
        found.team_name = who.get("team")
        found.app_name = who.get("app")
        found.installed_by = self.current_user
        found.last_error = None
        found.last_checked_at = utcnow()
        models.db.session.commit()

        self.record_event({"action": "configure", "object_type": "slack"})
        return {"configured": True, "team_name": found.team_name, "app_name": found.app_name, "working": True}

    @require_admin
    def delete(self):
        found = _workspace(self.current_org, required=False)
        if found is not None:
            models.db.session.delete(found)
            models.db.session.commit()
        self.record_event({"action": "disconnect", "object_type": "slack"})
        return {"configured": False}


def _may_pick_channels(user):
    """
    Whether somebody may see which channels the app is in.

    Whoever may send a dashboard, and whoever works with alerts -- an alert's
    Slack channel is picked from the same list. Not everybody: a private
    channel's name can say more than its owners meant to.
    """
    return features.can(user, features.SEND_DASHBOARDS) or user.has_permission("list_alerts")


class SlackChannelsResource(BaseResource):
    """
    The channels the app is in.

    Asked by the Send dialog, the subscription dialog and an alert's
    destinations rather than typed by hand, so a typo cannot produce a
    message that goes nowhere -- and only the channels the app has been added
    to, because those are the only ones it can post to.

    The app's name travels with them, so an empty list can say what to type
    in Slack to fix it.
    """

    def get(self):
        if not _may_pick_channels(self.current_user):
            abort(403, message="You may not send to Slack.")
        found = _workspace(self.current_org)
        channels, error = slack.channels(found.bot_token)
        if error:
            _remember(found, error)
            abort(400, message=error)
        _remember(found, None)
        return {"channels": channels, "app_name": found.app_name}


class SlackAlertDestinationResource(BaseResource):
    """
    An alert destination for a Slack channel, made by picking the channel.

    An alert is sent to destinations, and until now a Slack (app) destination
    was something an administrator made under Alert Destinations by typing a
    channel's name. Somebody setting up an alert who wanted it in #ops had to
    ask for one, or find the one somebody had made, by name, among the rest.

    Picking a channel from the alert asks here for its destination: the one
    that already posts there if there is one, so twenty alerts to #ops share a
    destination rather than make twenty, and a new one otherwise. Open to
    whoever works with alerts and not only administrators, because what it
    makes can do nothing an administrator has not already allowed -- it posts
    as the app the administrator installed, to a channel somebody invited the
    app into.
    """

    def post(self):
        if not _may_pick_channels(self.current_user):
            abort(403, message="You may not send to Slack.")
        body = request.get_json(silent=True) or {}
        channel_id = (body.get("channel") or "").strip()
        if not channel_id:
            abort(400, message="Pick a channel.")

        workspace = _workspace(self.current_org)
        channel, error = slack.find_channel(workspace.bot_token, channel_id)
        if error:
            abort(400, message=error)

        for destination in models.NotificationDestination.all(self.current_org):
            if destination.type == "slack_app" and (destination.options or {}).get("channel") == channel_id:
                return destination.to_dict()

        name = "Slack #{}".format(channel["name"])
        taken = {d.name for d in models.NotificationDestination.all(self.current_org)}
        if name in taken:
            # Somebody already named a destination this -- a webhook to the
            # same channel, say. The id keeps the two apart without renaming
            # theirs.
            name = "{} ({})".format(name, channel_id)

        schema = get_configuration_schema_for_destination_type("slack_app")
        destination = models.NotificationDestination(
            org=self.current_org,
            name=name,
            type="slack_app",
            options=ConfigurationContainer({"channel": channel_id}, schema),
            user=self.current_user,
        )
        models.db.session.add(destination)
        models.db.session.commit()
        self.record_event({"action": "create", "object_id": destination.id, "object_type": "destination"})
        return destination.to_dict()


def _remember(workspace, error):
    """
    Keep the last thing Slack said.

    A revoked token looks exactly like a working one from here until something
    is sent, so the settings page needs somewhere to read the failure from
    other than a worker's log.
    """
    workspace.last_error = error
    workspace.last_checked_at = utcnow()
    models.db.session.commit()


class DashboardSlackShareResource(BaseResource):
    def post(self, dashboard_id):
        """
        Draw the dashboard, upload it, and post it with a button.

        Done while the caller waits, rather than on a worker. Somebody has just
        pressed Send and the thing they need to know is whether it arrived --
        on a queue, a revoked token or an archived channel becomes a log line
        nobody reads. It costs a web worker for a few seconds, which is what an
        explicit button press is allowed to cost.
        """
        if not features.can(self.current_user, features.SEND_DASHBOARDS):
            abort(403, message="You may not send dashboards.")

        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        # Sending a dashboard's contents to a channel is at least as much
        # access as opening it, so it is the same check subscribing uses.
        if not can_see_dashboard(dashboard.id, self.current_org, self.current_user):
            abort(403, message="You cannot see that dashboard.")

        body = request.get_json(silent=True) or {}
        channel = (body.get("channel") or "").strip()
        if not channel:
            abort(400, message="Pick a channel.")
        message = (body.get("text") or "").strip()[:MAX_MESSAGE]

        # Before anything is drawn or sent, because the answer does not depend
        # on either and a person should not wait eight seconds to be told no.
        too_big = one_page.too_big_to_send(dashboard.widgets)
        if too_big:
            abort(400, message=too_big)

        workspace = _workspace(self.current_org)
        picture, error = self._draw(dashboard)
        if error:
            abort(400, message=error)

        sender = self.current_user.name
        text = (
            "{}\n\n_{} shared *{}*_".format(message, sender, dashboard.name)
            if message
            else ("*{}*, shared by {}".format(dashboard.name, sender))
        )
        posted, error = slack.post_dashboard(
            workspace.bot_token,
            channel,
            "{}.png".format(dashboard.slug),
            picture,
            text,
            link=slack.dashboard_link(self.current_org, dashboard),
            footer=slack.as_of(dashboard),
        )
        if error:
            _remember(workspace, error)
            abort(400, message=error)

        _remember(workspace, None)
        self.record_event({"action": "share_slack", "object_id": dashboard.id, "object_type": "dashboard"})
        return {"sent": True, "channel": posted["channel"]}

    def _draw(self, dashboard):
        """
        A PNG of the dashboard as this person sees it.

        The same render pass §1 built: minted for them, for this dashboard
        alone, withdrawn as soon as the renderer answers. Nothing is made
        public to take a picture of it.
        """
        # No check that a renderer exists: `send_dashboards` is not granted at
        # all without one (see features.py), so somebody who reaches this line
        # has one. A branch for it would be unreachable code, which is code
        # nobody has run.
        picture = screenshots.capture(screenshots.DASHBOARD, dashboard, self.current_user)
        if not picture:
            # `capture` folds every failure into None, because to an alert they
            # all mean "send it without a picture". Here they mean "do not
            # send", so the message says what to look at.
            return None, "Could not draw the dashboard. The renderer's log will say why."
        return picture, None

"""
Who gets a dashboard mailed to them, or which Slack channel it is posted to,
and when.

Everything here needs the `send_dashboards` feature, which an install only
offers where a renderer is configured -- there is nothing to send without a
picture.

Two rules run at save time rather than at send time, because both are
somebody's mistake and both are cheaper to say now than to discover in twenty
inboxes a week later:

- the dashboard has to be small enough to send as one page, and
- a recipient has to be able to see the dashboard. One who cannot is left off
  and named in the reply, rather than silently dropped or silently mailed
  something they have no right to.

A Slack channel is the third: it has to be one the app is in, asked of Slack
when the subscription is saved, because a channel the app is not in refuses
every post and the first anybody would hear of it is a dashboard that never
arrives.
"""

from flask import request
from flask_restful import abort

from sqldesk import features, models, one_page, slack
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.models import db
from sqldesk.permissions import (
    can_see_dashboard,
    require_feature,
    sees_all_of_dashboard,
)
from sqldesk.serializers import serialize_dashboard_subscription

#: The shapes a schedule may take, which are the ones a query's schedule
#: already takes -- so the two are described the same way in the interface.
MIN_INTERVAL = 3600


#: Moved to sqldesk.permissions, where sharing to Slack asks the same question.
_visible = can_see_dashboard


def _check_schedule(schedule):
    if not isinstance(schedule, dict):
        return "A subscription needs a schedule."

    interval = schedule.get("interval")
    if not isinstance(interval, int) or interval < MIN_INTERVAL:
        return "A subscription sends at most once an hour."

    day = schedule.get("day_of_week")
    if day is not None and day not in (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ):
        return "{!r} is not a day of the week.".format(day)

    return None


def _slack_channel(org, channel_id):
    """The channel with this id, if the app is in it, or why not."""
    workspace = models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == org.id).first()
    if workspace is None:
        return None, "Slack is not set up. An administrator adds the app's token under Settings."
    return slack.find_channel(workspace.bot_token, channel_id)


def _sort_recipients(ids, dashboard, org):
    """
    Who may be sent this dashboard, and who may not.

    Checked against each person's own access rather than the owner's: a
    subscription is a way to put a dashboard in somebody's hands, and the
    owner being allowed to look at it says nothing about whether they are.
    """
    allowed, refused = [], []
    for user in models.User.query.filter(models.User.id.in_(ids or []), models.User.org_id == org.id):
        if user.is_disabled:
            refused.append({"id": user.id, "name": user.name, "why": "That account is disabled."})
        elif not _visible(dashboard.id, org, user):
            refused.append({"id": user.id, "name": user.name, "why": "They cannot see this dashboard."})
        elif not sees_all_of_dashboard(dashboard, user):
            # The picture is drawn as the owner, so it would show them widgets
            # the app shows them as locked.
            refused.append(
                {"id": user.id, "name": user.name, "why": "They cannot see every widget on this dashboard."}
            )
        else:
            allowed.append(user.id)
    return allowed, refused


class DashboardSendableResource(BaseResource):
    def get(self, dashboard_id):
        """
        Whether this dashboard fits on one page, and what to change if not.

        Asked by the Send to Slack and subscription dialogs as they open, so
        the answer arrives before somebody has picked a channel or a list of
        people -- not as the reply to pressing Send.
        """
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        if not _visible(dashboard.id, self.current_org, self.current_user):
            abort(404, message="Dashboard not found.")
        return one_page.size_check(dashboard.widgets)


class DashboardSubscriptionListResource(BaseResource):
    @require_feature(features.SEND_DASHBOARDS)
    def get(self, dashboard_id):
        """Every subscription to this dashboard."""
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        if not _visible(dashboard.id, self.current_org, self.current_user):
            abort(404, message="Dashboard not found.")

        return [
            serialize_dashboard_subscription(s) for s in models.DashboardSubscription.for_dashboard(dashboard).all()
        ]

    @require_feature(features.SEND_DASHBOARDS)
    def post(self, dashboard_id):
        """
        Subscribe some people to this dashboard.

        :<json object schedule: when to send -- the shape a query's schedule has
        :<json string format: `png` or `pdf`
        :<json array recipients: user ids, never addresses
        :<json string slack_channel: a Slack channel's id, instead of recipients
        """
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        if not _visible(dashboard.id, self.current_org, self.current_user):
            abort(404, message="Dashboard not found.")

        body = request.get_json(force=True, silent=True) or {}

        too_big = one_page.too_big_to_send(dashboard.widgets)
        if too_big:
            abort(400, message=too_big)

        problem = _check_schedule(body.get("schedule"))
        if problem:
            abort(400, message=problem)

        fmt = body.get("format", models.DashboardSubscription.PNG)
        if fmt not in models.DashboardSubscription.FORMATS:
            abort(400, message="A subscription is sent as a picture or a PDF.")

        channel = None
        channel_id = (body.get("slack_channel") or "").strip()
        if channel_id:
            channel, problem = _slack_channel(self.current_org, channel_id)
            if problem:
                abort(400, message=problem)
            # A channel shows a picture in the conversation; a PDF arrives as
            # a file to download, which is not what somebody watching a
            # dashboard every hour wants to open.
            fmt = models.DashboardSubscription.PNG
            allowed, refused = [], []
        else:
            allowed, refused = _sort_recipients(body.get("recipients"), dashboard, self.current_org)
            if not allowed:
                abort(400, message="Nobody on that list can see this dashboard.")

        subscription = models.DashboardSubscription(
            org=self.current_org,
            dashboard=dashboard,
            user=self.current_user,
            schedule=body["schedule"],
            format=fmt,
            recipient_ids=allowed,
            slack_channel=channel["id"] if channel else None,
            slack_channel_name=channel["name"] if channel else None,
        )
        db.session.add(subscription)
        db.session.commit()

        self.record_event({"action": "subscribe", "object_id": dashboard.id, "object_type": "dashboard"})

        # The refusals travel with the thing that was made, so the owner is
        # told who was left off at the moment they would wonder.
        return dict(serialize_dashboard_subscription(subscription), left_out=refused)


class DashboardSubscriptionResource(BaseResource):
    def _mine_or_404(self, subscription_id):
        subscription = get_object_or_404(
            models.DashboardSubscription.get_by_id_and_org, subscription_id, self.current_org
        )
        # The owner or an admin. A subscription can mail a dashboard to
        # twenty people; who may change it is not a question to be casual
        # about.
        if subscription.user_id != self.current_user.id and not self.current_user.has_permission("admin"):
            abort(404, message="Subscription not found.")
        return subscription

    @require_feature(features.SEND_DASHBOARDS)
    def post(self, subscription_id):
        """Change a subscription's schedule, format, recipients, or pause it."""
        subscription = self._mine_or_404(subscription_id)
        body = request.get_json(force=True, silent=True) or {}
        refused = []

        if "schedule" in body:
            problem = _check_schedule(body["schedule"])
            if problem:
                abort(400, message=problem)
            subscription.schedule = body["schedule"]

        if "format" in body:
            if body["format"] not in models.DashboardSubscription.FORMATS:
                abort(400, message="A subscription is sent as a picture or a PDF.")
            if subscription.slack_channel and body["format"] != models.DashboardSubscription.PNG:
                abort(400, message="A Slack channel is sent a picture.")
            subscription.format = body["format"]

        if body.get("slack_channel") and subscription.slack_channel:
            channel, problem = _slack_channel(self.current_org, body["slack_channel"].strip())
            if problem:
                abort(400, message=problem)
            subscription.slack_channel = channel["id"]
            subscription.slack_channel_name = channel["name"]

        if "recipients" in body and not subscription.slack_channel:
            allowed, refused = _sort_recipients(body["recipients"], subscription.dashboard, self.current_org)
            if not allowed:
                abort(400, message="Nobody on that list can see this dashboard.")
            subscription.recipient_ids = allowed

        if "active" in body:
            subscription.active = bool(body["active"])
            if subscription.active:
                # Resuming is somebody saying they have dealt with it.
                subscription.last_error = None

        db.session.add(subscription)
        db.session.commit()

        return dict(serialize_dashboard_subscription(subscription), left_out=refused)

    @require_feature(features.SEND_DASHBOARDS)
    def delete(self, subscription_id):
        """Stop sending, and forget it."""
        subscription = self._mine_or_404(subscription_id)
        dashboard_id = subscription.dashboard_id

        db.session.delete(subscription)
        db.session.commit()

        self.record_event({"action": "unsubscribe", "object_id": dashboard_id, "object_type": "dashboard"})

from flask import request
from flask_restful import abort
from funcy import project

from sqldesk import models, utils
from sqldesk.handlers.base import (
    BaseResource,
    get_object_or_404,
    require_fields,
)
from sqldesk.permissions import (
    require_access,
    require_admin_or_owner,
    require_permission,
    view_only,
)
from sqldesk.serializers import serialize_alert
from sqldesk.tasks.alerts import (
    notify_subscriptions,
    should_notify,
)


def require_access_to_attachments(options, user, org):
    """
    The pictures an alert attaches are of queries and dashboards, rendered
    with the query's own key -- so attaching one is reading it, and takes the
    same access as opening it.
    """
    for attachment in (options or {}).get("attachments") or []:
        kind, object_id = attachment.get("type"), attachment.get("id")
        if kind == "query":
            query = get_object_or_404(models.Query.get_by_id_and_org, object_id, org)
            require_access(query, user, view_only)
        elif kind == "dashboard":
            dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, object_id, org)
            if not user.has_permission("admin") and not can_see_dashboard(dashboard, user, org):
                abort(403, message="You cannot see that dashboard.")
        else:
            abort(400, message="An attachment is a query or a dashboard.")


def can_see_dashboard(dashboard, user, org):
    """Visible by the dashboard list's own rule, which is the rule everywhere else."""
    return models.Dashboard.all(org, user.group_ids, user.id).filter(models.Dashboard.id == dashboard.id).count() > 0


class AlertResource(BaseResource):
    def get(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)
        self.record_event({"action": "view", "object_id": alert.id, "object_type": "alert"})
        # Somebody has opened this one, which is where the history is worth a
        # query. The list gets a count instead.
        fires = models.Alert.fire_counts([alert.id])
        return serialize_alert(alert, fires_24h=fires.get(alert.id, 0), with_history=True)

    def post(self, alert_id):
        req = request.get_json(True)
        params = project(req, ("options", "name", "query_id", "rearm"))
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        if "query_id" in params:
            # Pointing the alert at another query is the same decision as
            # creating it on that query: the alert's checks and its emails
            # then carry that query's rows.
            query = get_object_or_404(models.Query.get_by_id_and_org, params.pop("query_id"), self.current_org)
            require_access(query, self.current_user, view_only)
            refuse_a_stream(query)
            params["query_rel"] = query
        if "options" in params:
            require_access_to_attachments(params["options"], self.current_user, self.current_org)

        self.update_model(alert, params)
        models.db.session.commit()

        self.record_event({"action": "edit", "object_id": alert.id, "object_type": "alert"})

        return serialize_alert(alert)

    def delete(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user_id)
        models.db.session.delete(alert)
        models.db.session.commit()


class AlertEvaluateResource(BaseResource):
    def post(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        new_state = alert.evaluate()
        if should_notify(alert, new_state):
            alert.state = new_state
            alert.last_triggered_at = utils.utcnow()
            models.db.session.commit()

        notify_subscriptions(alert, new_state, {})
        self.record_event({"action": "evaluate", "object_id": alert.id, "object_type": "alert"})


class AlertMuteResource(BaseResource):
    def post(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        alert.options["muted"] = True
        models.db.session.commit()

        self.record_event({"action": "mute", "object_id": alert.id, "object_type": "alert"})

    def delete(self, alert_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        require_admin_or_owner(alert.user.id)

        alert.options["muted"] = False
        models.db.session.commit()

        self.record_event({"action": "unmute", "object_id": alert.id, "object_type": "alert"})


def refuse_a_stream(query):
    """
    An alert cannot watch a stream.

    An alert is checked when its query's new result is stored, and a stream
    stores no result -- its window exists only while somebody is watching it,
    and at three in the morning nobody is. An alert on one would be an alert
    that never fires, which is worse than one that cannot be made: a person who
    is told no goes and builds something that works.
    """
    source = query.data_source
    if source is not None and source.streams_only:
        abort(
            400,
            message=(
                "An alert cannot watch a stream. A stream is consumed only while somebody is "
                "looking at it and stores no result for an alert to check."
            ),
        )


class AlertListResource(BaseResource):
    def post(self):
        req = request.get_json(True)
        require_fields(req, ("options", "name", "query_id"))

        query = get_object_or_404(models.Query.get_by_id_and_org, req["query_id"], self.current_org)
        require_access(query, self.current_user, view_only)
        refuse_a_stream(query)
        require_access_to_attachments(req["options"], self.current_user, self.current_org)

        alert = models.Alert(
            name=req["name"],
            query_rel=query,
            user=self.current_user,
            rearm=req.get("rearm"),
            options=req["options"],
        )

        models.db.session.add(alert)
        models.db.session.flush()
        models.db.session.commit()

        self.record_event({"action": "create", "object_id": alert.id, "object_type": "alert"})

        return serialize_alert(alert)

    @require_permission("list_alerts")
    def get(self):
        self.record_event({"action": "list", "object_type": "alert"})
        alerts = list(models.Alert.all(group_ids=self.current_user.group_ids))
        # One grouped query for every row's count, rather than one per row.
        # An alert that went off six times reads very differently from one
        # that went off once and stayed there, and the list is where somebody
        # finds that out.
        fires = models.Alert.fire_counts([alert.id for alert in alerts])
        return [serialize_alert(alert, fires_24h=fires.get(alert.id, 0)) for alert in alerts]


class AlertSubscriptionListResource(BaseResource):
    def post(self, alert_id):
        req = request.get_json(True)

        alert = models.Alert.get_by_id_and_org(alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)
        kwargs = {"alert": alert, "user": self.current_user}

        if "destination_id" in req:
            destination = models.NotificationDestination.get_by_id_and_org(req["destination_id"], self.current_org)
            kwargs["destination"] = destination

        subscription = models.AlertSubscription(**kwargs)
        models.db.session.add(subscription)
        models.db.session.commit()

        self.record_event(
            {
                "action": "subscribe",
                "object_id": alert_id,
                "object_type": "alert",
                "destination": req.get("destination_id"),
            }
        )

        d = subscription.to_dict()
        return d

    def get(self, alert_id):
        alert = models.Alert.get_by_id_and_org(alert_id, self.current_org)
        require_access(alert, self.current_user, view_only)

        subscriptions = models.AlertSubscription.all(alert_id)
        return [s.to_dict() for s in subscriptions]


class AlertSubscriptionResource(BaseResource):
    def delete(self, alert_id, subscriber_id):
        alert = get_object_or_404(models.Alert.get_by_id_and_org, alert_id, self.current_org)
        subscription = models.AlertSubscription.query.filter(
            models.AlertSubscription.id == subscriber_id, models.AlertSubscription.alert_id == alert.id
        ).first()
        if subscription is None:
            abort(404)
        require_admin_or_owner(subscription.user.id)
        models.db.session.delete(subscription)
        models.db.session.commit()

        self.record_event({"action": "unsubscribe", "object_id": alert_id, "object_type": "alert"})

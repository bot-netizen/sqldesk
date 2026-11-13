import datetime
import logging

from flask import current_app

from sqldesk import models, screenshots, settings, utils
from sqldesk.worker import get_job_logger, job

logger = get_job_logger(__name__)

#: How much of a destination's own explanation the history keeps.
MAX_DETAIL = 300


class _Problems(logging.Handler):
    """
    What a destination logged as a problem while it was sending.

    Destinations do not say whether they delivered: every one of them catches
    its own failures and logs them -- most with `logging.exception` on the
    root logger -- and returns nothing either way. Listening for the warnings
    and errors logged while one is sending is how the history learns that a
    webhook answered 500 without touching fourteen destinations to make them
    report it. One that knows better says so itself (see `_deliver`).
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        if record.name == "root" or record.name.startswith("sqldesk"):
            try:
                self.messages.append(record.getMessage())
            except Exception:
                self.messages.append(str(record.msg))


def _deliver(subscription, alert, new_state, host, metadata):
    """
    Send one subscription's notification and say what happened:
    `{destination, type, ok, detail}`.

    A destination may return that dict itself -- Slack (app) does, because it
    knows the difference between "posted, with a picture missing" and "not
    posted". Otherwise: raising is a failure, logging a warning or error while
    sending is a failure with that line as its reason, and neither is taken to
    mean it went.
    """
    destination = subscription.destination
    if destination is not None:
        name, kind = destination.name, destination.type
    else:
        name, kind = "Email to {}".format(subscription.user.email), "email"
        if not settings.ALERT_EMAIL_FALLBACK:
            return {
                "destination": name,
                "type": kind,
                "ok": False,
                "detail": "This subscription has no destination, so nothing was sent.",
            }

    problems = _Problems()
    root = logging.getLogger()
    root.addHandler(problems)
    try:
        result = subscription.notify(alert, alert.query_rel, subscription.user, new_state, current_app, host, metadata)
    except Exception as error:
        logger.exception("Error with processing destination")
        return {
            "destination": name,
            "type": kind,
            "ok": False,
            "detail": "{}: {}".format(error.__class__.__name__, error)[:MAX_DETAIL],
        }
    finally:
        root.removeHandler(problems)

    if isinstance(result, dict) and "ok" in result:
        detail = result.get("detail")
        return {
            "destination": name,
            "type": kind,
            "ok": bool(result["ok"]),
            "detail": detail[:MAX_DETAIL] if detail else None,
        }
    if problems.messages:
        return {"destination": name, "type": kind, "ok": False, "detail": problems.messages[-1][:MAX_DETAIL]}
    return {"destination": name, "type": kind, "ok": True, "detail": None}


def notify_subscriptions(alert, new_state, metadata):
    host = utils.base_url(alert.query_rel.org)

    # Drawn once for the whole notification rather than once per subscriber:
    # five people on one alert should not mean five runs of the same
    # dashboard. Carried in `metadata`, which already reaches every
    # destination untouched, so no destination signature has to change --
    # and the eleven that cannot use an image never learn it is there.
    #
    # Caught broadly, and that is deliberate rather than lazy: a picture is a
    # nice-to-have and an alert is not, so there is no failure here worth
    # losing a notification over. `screenshots` guards the expected ones; this
    # is for the unexpected.
    metadata = dict(metadata or {})
    try:
        metadata["screenshots"] = screenshots.for_alert(alert)
    except Exception:
        logger.exception("Could not draw the attachments for alert %s; sending without them.", alert.id)
        metadata["screenshots"] = []

    # How often this has gone off lately, carried the same way the pictures
    # are. Four fires and four recoveries in an afternoon is a different
    # problem from one fire that stayed, and a single message cannot tell them
    # apart -- the count is what makes flapping visible at the moment somebody
    # is reading about it. Never worth losing a notification over.
    try:
        metadata["fires_24h"] = models.Alert.fire_counts([alert.id]).get(alert.id, 0)
    except Exception:
        logger.exception("Could not count recent fires for alert %s; sending without the count.", alert.id)

    deliveries = []
    for subscription in alert.subscriptions:
        delivery = _deliver(subscription, alert, new_state, host, metadata)
        deliveries.append(delivery)
        logger.info(
            "Alert %s to %s: %s%s",
            alert.id,
            delivery["destination"],
            "sent" if delivery["ok"] else "NOT sent",
            " -- " + delivery["detail"] if delivery["detail"] else "",
        )
    return deliveries


def should_notify(alert, new_state):
    passed_rearm_threshold = False
    if alert.rearm and alert.last_triggered_at:
        passed_rearm_threshold = alert.last_triggered_at + datetime.timedelta(seconds=alert.rearm) < utils.utcnow()

    return new_state != alert.state or (alert.state == models.Alert.TRIGGERED_STATE and passed_rearm_threshold)


@job("default", timeout=300)
def check_alerts_for_query(query_id, metadata):
    logger.debug("Checking query %d for alerts", query_id)

    query = models.Query.query.get(query_id)

    for alert in query.alerts:
        logger.info("Checking alert (%d) of query %d.", alert.id, query_id)
        new_state = alert.evaluate()

        if should_notify(alert, new_state):
            logger.info("Alert %d new state: %s", alert.id, new_state)
            old_state = alert.state

            # Whether anything will be sent, decided before the row is written
            # rather than after: the two silent cases below are `continue`s,
            # and a history that recorded them as notifications would have
            # people looking for messages nobody sent.
            settling = old_state == models.Alert.UNKNOWN_STATE and new_state == models.Alert.OK_STATE
            will_notify = not settling and not alert.muted

            alert.state = new_state
            alert.last_triggered_at = utils.utcnow()
            # `evaluated_value` is set by `evaluate` above. Absent when it is
            # patched, which is how most of the tests drive this.
            value = getattr(alert, "evaluated_value", None)
            fire = models.AlertFire(
                alert=alert,
                state=new_state,
                value=None if value is None else str(value)[:255],
                notified=will_notify,
            )
            models.db.session.add(fire)
            models.db.session.commit()

            if settling:
                logger.debug("Skipping notification (previous state was unknown and now it's ok).")
                continue

            if alert.muted:
                logger.debug("Skipping notification (alert muted).")
                continue

            # What each destination did, kept on the event, so the alert's page
            # can say "Slack #ops: not in channel" rather than leave somebody
            # wondering why nothing arrived.
            fire.deliveries = notify_subscriptions(alert, new_state, metadata)
            models.db.session.add(fire)
            models.db.session.commit()

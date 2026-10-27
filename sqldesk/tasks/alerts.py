import datetime

from flask import current_app

from sqldesk import models, screenshots, utils
from sqldesk.worker import get_job_logger, job

logger = get_job_logger(__name__)


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

    for subscription in alert.subscriptions:
        try:
            subscription.notify(alert, alert.query_rel, subscription.user, new_state, current_app, host, metadata)
        except Exception:
            logger.exception("Error with processing destination")


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
            models.db.session.add(
                models.AlertFire(
                    alert=alert,
                    state=new_state,
                    value=None if value is None else str(value)[:255],
                    notified=will_notify,
                )
            )
            models.db.session.commit()

            if settling:
                logger.debug("Skipping notification (previous state was unknown and now it's ok).")
                continue

            if alert.muted:
                logger.debug("Skipping notification (alert muted).")
                continue

            notify_subscriptions(alert, new_state, metadata)

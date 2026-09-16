import requests
from flask_mail import Message

from tealdash import mail, models, settings
from tealdash.models import users
from tealdash.query_runner import NotSupported
from tealdash.tasks.worker import Queue
from tealdash.version_check import run_version_check
from tealdash.worker import get_job_logger, job

logger = get_job_logger(__name__)


@job("default")
def record_event(raw_event):
    event = models.Event.record(raw_event)
    models.db.session.commit()

    for hook in settings.EVENT_REPORTING_WEBHOOKS:
        logger.debug("Forwarding event to: %s", hook)
        try:
            # The schema URI names the payload format for whatever is on the
            # other end. It changed with the rename, so a receiver matching on
            # the old one needs updating -- the `data` object itself is
            # unchanged.
            data = {
                "schema": "iglu:dev.tealdash.webhooks/event/jsonschema/1-0-0",
                "data": event.to_dict(),
            }
            response = requests.post(hook, json=data)
            if response.status_code != 200:
                logger.error("Failed posting to %s: %s", hook, response.content)
        except Exception:
            logger.exception("Failed posting to %s", hook)


def version_check():
    run_version_check()


@job("default")
def subscribe(form):
    logger.info(
        "Subscribing to: [security notifications=%s], [newsletter=%s]",
        form["security_notifications"],
        form["newsletter"],
    )
    # Upstream POSTed the admin's name and email to its own servers here.
    # Tealdash has no such service, and an operator setting up a self-hosted
    # install has every reason to expect their details stay on their own box --
    # so the preference is recorded in the log and goes no further.
    logger.info("Subscription preferences recorded locally; nothing was sent off-box.")


@job("emails")
def send_mail(to, subject, html, text):
    try:
        message = Message(recipients=to, subject=subject, html=html, body=text)

        mail.send(message)
    except Exception:
        logger.exception("Failed sending message: %s", message.subject)


@job("queries", timeout=30, ttl=90)
def test_connection(data_source_id):
    try:
        data_source = models.DataSource.get_by_id(data_source_id)
        data_source.query_runner.test_connection()
    except Exception as e:
        return e
    else:
        return True


@job("schemas", queue_class=Queue, at_front=True, timeout=settings.SCHEMAS_REFRESH_TIMEOUT, ttl=90)
def get_schema(data_source_id, refresh):
    try:
        data_source = models.DataSource.get_by_id(data_source_id)
        return data_source.get_schema(refresh)
    except NotSupported:
        return {
            "error": {
                "code": 1,
                "message": "Data source type does not support retrieving schema",
            }
        }
    except Exception as e:
        return {"error": {"code": 2, "message": "Error retrieving schema", "details": str(e)}}


def sync_user_details():
    users.sync_last_active_at()

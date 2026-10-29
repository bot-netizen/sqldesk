"""
Sending a dashboard to the people who asked for it.

Two jobs. One runs every minute and asks which subscriptions are due; the
other sends one of them. Separate because a send draws a page in a browser and
mails several people, which is seconds of work, and the minute-by-minute job
has to stay quick enough to be run every minute.

What is sent is the latest **stored** results, and the email says how old they
are. Refreshing every query first would turn a subscription into a warehouse
bill nobody asked for; an owner who wants fresh numbers gives the queries a
schedule.

Nothing here raises at the caller. A subscription that cannot be sent records
why on itself -- the owner sees it on the dashboard -- and the next one is
tried. One broken dashboard must not stop the other nineteen going out.
"""

import datetime
import logging

from flask_mail import Message

from sqldesk import mail, models, one_page, screenshots, unsubscribe
from sqldesk.models import db
from sqldesk.permissions import sees_all_of_dashboard
from sqldesk.utils import base_url
from sqldesk.worker import job

logger = logging.getLogger(__name__)

#: How a subscription's picture is announced in the email.
FORMATS = {
    models.DashboardSubscription.PNG: ("image/png", "png"),
    models.DashboardSubscription.PDF: ("application/pdf", "pdf"),
}


def _is_due(subscription, now):
    """
    Whether this subscription's slot has come round.

    The same question `refresh_queries` asks of a query, answered by the same
    function, because the schedule is the same shape.
    """
    if subscription.failures and subscription.last_attempt_at:
        # 2, 4, 8 ... minutes after a failed try, never more than an hour.
        wait = datetime.timedelta(minutes=min(2**subscription.failures, MAX_BACKOFF_MINUTES))
        if now < subscription.last_attempt_at + wait:
            return False
    schedule = subscription.schedule or {}
    return models.should_schedule_next(
        subscription.last_sent_at,
        now,
        schedule.get("interval"),
        schedule.get("time"),
        schedule.get("day_of_week"),
    )


#: The longest a subscription that keeps failing waits between tries.
MAX_BACKOFF_MINUTES = 60


def _record_problem(subscription, message):
    subscription.last_error = message
    subscription.failures = (subscription.failures or 0) + 1
    db.session.add(subscription)
    db.session.commit()
    logger.warning("Subscription %s: %s", subscription.id, message)


@job("periodic", timeout=60)
def send_due_subscriptions():
    """Put every subscription whose slot has come round on the emails queue."""
    if not screenshots.enabled():
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    due = [s.id for s in models.DashboardSubscription.query.filter_by(active=True) if _is_due(s, now)]

    for subscription_id in due:
        # One job per subscription, named after it: a send already queued is
        # not queued twice because this ran again while the first was still
        # drawing.
        send_subscription.delay(subscription_id, job_id="subscription-{}".format(subscription_id))

    if due:
        logger.info("Queued %s dashboard subscriptions.", len(due))


@job("emails", timeout=300)
def send_subscription(subscription_id):
    """Draw one dashboard and mail it to the people on the subscription."""
    subscription = models.DashboardSubscription.query.get(subscription_id)
    if subscription is None or not subscription.active:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    # Asked again here, because the job id does not stop a second copy being
    # queued while the first waits behind other mail: the second then finds
    # the first already sent it, and goes.
    if not _is_due(subscription, now):
        return
    subscription.last_attempt_at = now
    db.session.add(subscription)
    db.session.commit()

    dashboard = subscription.dashboard
    owner = subscription.user

    if dashboard is None or owner is None or owner.is_disabled:
        _record_problem(subscription, "The dashboard or its owner has gone.")
        return

    # Asked again, because a dashboard grows after somebody subscribes to it.
    too_big = one_page.too_big_to_send(dashboard.widgets)
    if too_big:
        _record_problem(subscription, too_big)
        return

    # And because access changes: the owner is whose sight of it this is.
    if not screenshots.may_see_dashboard(dashboard, owner):
        _record_problem(subscription, "{} can no longer see this dashboard.".format(owner.name))
        return

    recipients = [user for user in subscription.recipients() if not user.is_disabled]
    recipients = [user for user in recipients if screenshots.may_see_dashboard(dashboard, user)]
    # The picture is drawn as the owner. Somebody who cannot read every data
    # source on the dashboard would be shown widgets the app shows them as
    # locked, so they are left out -- asked again at each send, because both
    # the dashboard and people's access change after somebody subscribes.
    left_out = [user for user in recipients if not sees_all_of_dashboard(dashboard, user)]
    recipients = [user for user in recipients if user not in left_out]
    if not recipients:
        _record_problem(subscription, "Nobody on this subscription can see the dashboard any more.")
        return

    picture = screenshots.capture(screenshots.DASHBOARD, dashboard, owner, fmt=subscription.format)
    if picture is None:
        _record_problem(subscription, "The renderer could not draw this dashboard.")
        return

    # One at a time, each on its own: the first refused address used to stop
    # the loop, so the people before it were mailed again on every retry.
    refused = []
    for recipient in recipients:
        try:
            _mail(subscription, dashboard, recipient, picture)
        except Exception:
            logger.exception("Could not mail subscription %s to user %s.", subscription_id, recipient.id)
            refused.append(recipient)
    if len(refused) == len(recipients):
        _record_problem(subscription, "The mail server would not take it.")
        return

    notes = []
    if left_out:
        notes.append(
            "Not sent to {}: they cannot see every widget on this dashboard.".format(
                ", ".join(user.name for user in left_out)
            )
        )
    if refused:
        notes.append("The mail server would not take it for {}.".format(", ".join(user.name for user in refused)))
    subscription.last_sent_at = datetime.datetime.now(datetime.timezone.utc)
    subscription.failures = 0
    subscription.last_error = " ".join(notes) or None
    db.session.add(subscription)
    db.session.commit()


def _freshness(dashboard):
    """
    How old the numbers are, in words.

    Said in the email because a subscription sends stored results: somebody
    reading Tuesday's figures on Thursday should be told, not left to assume.
    """
    times = [w.visualization.query_rel.retrieved_at for w in dashboard.widgets if w.visualization]
    times = [t for t in times if t]
    if not times:
        return "These numbers have not been refreshed."
    oldest = min(times)
    return "Numbers as of {}.".format(oldest.strftime("%d %b %Y, %H:%M UTC"))


BODY = (
    '<div style="font:14px/1.5 sans-serif;color:#34302b">'
    '<div style="font-size:18px;font-weight:600">{name}</div>'
    '<div style="color:#6f6b66;margin:4px 0 16px">{freshness}</div>'
    "{picture}"
    '<div style="margin-top:20px;color:#6f6b66;font-size:12px">'
    'Sent because {owner} subscribed you. <a href="{link}">Open it in SQLDesk</a>. '
    '<a href="{unsubscribe}">Unsubscribe</a>.'
    "</div></div>"
)


def _mail(subscription, dashboard, recipient, picture):
    """
    One message, to one person.

    One each rather than one to everybody, because the unsubscribe link is
    theirs alone -- a shared link would let anyone on the subscription remove
    anyone else. It also keeps the recipients from seeing each other's
    addresses, which a dashboard subscription has no business revealing.
    """
    mime_type, extension = FORMATS[subscription.format]
    filename = "{}.{}".format(dashboard.name.replace("/", "-")[:60] or "dashboard", extension)
    base = base_url(dashboard.org).rstrip("/")
    link = "{}/dashboards/{}".format(base, dashboard.id)
    unsubscribe_link = unsubscribe.link_for(subscription, recipient, base)

    message = Message(
        recipients=[recipient.email],
        # The dashboard's name is what the reader is looking for in a list of
        # subject lines; anything before it is noise.
        subject=dashboard.name,
        # What a mail client's own Unsubscribe button uses. `One-Click` is
        # RFC 8058: the client POSTs to the address and expects it to work
        # without the reader visiting a page.
        extra_headers={
            "List-Unsubscribe": "<{}>".format(unsubscribe_link),
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )

    if subscription.format == models.DashboardSubscription.PNG:
        # Inline, so it is seen rather than sitting as an attachment nobody
        # opens. The `alt` is the dashboard's name: many clients block images
        # by default, and an unlabelled one that does not load is a blank box.
        cid = "sqldesk-dashboard"
        message.attach(
            filename,
            mime_type,
            picture,
            disposition="inline",
            # A list of pairs, not a dict: flask_mail unpacks each header as
            # a pair, and a dict hands it bare strings. See the same note in
            # destinations/email.py, where it reached a real send.
            headers=[("Content-ID", "<{}>".format(cid))],
        )
        rendered_picture = '<img src="cid:{}" alt="{}" style="max-width:100%;border:1px solid #e8e5e1">'.format(
            cid, dashboard.name
        )
    else:
        message.attach(filename, mime_type, picture)
        rendered_picture = '<div style="color:#6f6b66">Attached: {}</div>'.format(filename)

    message.html = BODY.format(
        name=dashboard.name,
        freshness=_freshness(dashboard),
        picture=rendered_picture,
        owner=subscription.user.name,
        link=link,
        unsubscribe=unsubscribe_link,
    )

    mail.send(message)

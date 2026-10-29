"""
The clock on uploaded files.

Three steps, cheapest and most reversible first:

1. **Unload** a file nothing has queried for three days. No view is created
   for it, so every query on that data source stops paying for its schema
   inference. The file is untouched and the next query naming it brings it
   back. Nobody is told, because nothing was lost.
2. **Warn** the uploader a day before expiry, with a button that keeps the
   file. This is the step that makes step 3 acceptable.
3. **Delete** what was warned about and not kept.

The ordering is the policy. An upload is the only copy of itself, so the only
deletion that happens without a person involved is one that was announced in a
mail somebody could act on -- and if the mail could not be sent, the file is
not deleted.
"""

import datetime
import logging

from flask import render_template
from flask_mail import Message

from sqldesk import mail, models, redis_connection, settings, uploads
from sqldesk.utils import base_url, utcnow
from sqldesk.worker import job

logger = logging.getLogger(__name__)


@job("default", timeout=600)
def manage_uploads():
    """Run the three steps. Scheduled hourly; each one decides for itself."""
    unloaded = unload_idle_uploads()
    warned = warn_about_expiring_uploads()
    deleted = delete_expired_uploads()
    if unloaded or warned or deleted:
        logger.info(
            "task=manage_uploads unloaded=%s warned=%s deleted=%s",
            unloaded,
            warned,
            deleted,
        )
    return {"unloaded": unloaded, "warned": warned, "deleted": deleted}


def unload_idle_uploads():
    """
    Stop registering files nothing has queried lately.

    Dated from the last query, or from the upload where there has never been
    one: a file uploaded four days ago and never read is exactly the case this
    is for.
    """
    if settings.UPLOAD_UNLOAD_AFTER_DAYS <= 0:
        return 0

    cutoff = utcnow() - datetime.timedelta(days=settings.UPLOAD_UNLOAD_AFTER_DAYS)
    idle = models.UploadedFile.query.filter(
        models.UploadedFile.unloaded_at.is_(None),
        models.db.or_(
            models.db.and_(
                models.UploadedFile.last_queried_at.is_(None),
                models.UploadedFile.created_at < cutoff,
            ),
            models.UploadedFile.last_queried_at < cutoff,
        ),
    ).all()

    for upload in idle:
        upload.unloaded_at = utcnow()
    if idle:
        models.db.session.commit()
        # Each data source's cached schema named the unloaded views, and a
        # schema browser offering a table that is no longer registered is
        # worse than one that is a few minutes behind.
        _forget_schemas(idle)
    return len(idle)


def warn_about_expiring_uploads():
    """
    Mail each uploader once about the files of theirs that go tomorrow.

    One mail per person rather than per file: somebody who uploaded nine CSVs
    on Tuesday gets one message with nine buttons, not nine messages. The
    warning is marked as sent only when the mail actually went, so a mail
    outage delays the deletion rather than silently skipping the warning.
    """
    if settings.UPLOAD_LIFETIME_DAYS <= 0:
        return 0

    deadline = utcnow() + uploads.WARN_WITHIN
    due = models.UploadedFile.query.filter(
        models.UploadedFile.expires_at.isnot(None),
        models.UploadedFile.expires_at <= deadline,
        models.UploadedFile.expiry_warning_sent_at.is_(None),
    ).all()

    by_person = {}
    for upload in due:
        if upload.created_by is None or not upload.created_by.email:
            # Nobody to tell. Marked as warned so it is not reconsidered every
            # hour, and deliberately *not* deleted: see `delete_expired_uploads`.
            upload.expiry_warning_sent_at = utcnow()
            continue
        by_person.setdefault(upload.created_by, []).append(upload)

    sent = 0
    for person, their_uploads in by_person.items():
        if _tell(person, their_uploads):
            now = utcnow()
            for upload in their_uploads:
                upload.expiry_warning_sent_at = now
            sent += len(their_uploads)

    models.db.session.commit()
    return sent


def send_mail(to, subject, html, text):
    """
    Send now, and raise if it does not go.

    Not `sqldesk.tasks.general.send_mail`, which catches every error and logs
    it: called from here it returned normally when the mail server refused,
    `_tell` took that for a warning sent, and the file was deleted the next
    day with nobody told. This module's one promise depends on knowing.
    """
    mail.send(Message(recipients=to, subject=subject, html=html, body=text))


def _tell(person, their_uploads):
    """One mail. Returns whether it went."""
    files = [
        {
            "name": upload.display_name or upload.filename,
            "size": uploads._readable(upload.size or 0),
            "last_queried": upload.last_queried_at.date().isoformat() if upload.last_queried_at else None,
            "keep_link": uploads.keep_link(upload),
        }
        for upload in their_uploads
    ]
    context = {"files": files, "base_url": base_url(their_uploads[0].org)}
    subject = (
        "A file you uploaded to SQLDesk expires tomorrow"
        if len(files) == 1
        else "{} files you uploaded to SQLDesk expire tomorrow".format(len(files))
    )
    try:
        send_mail(
            [person.email],
            subject,
            render_template("emails/upload_expiring.html", **context),
            render_template("emails/upload_expiring.txt", **context),
        )
        return True
    except Exception:
        # Not marked as warned, so it is tried again next hour and the file is
        # not deleted meanwhile.
        logger.exception("could not warn %s about expiring uploads", person.id)
        return False


def delete_expired_uploads():
    """
    Delete what has expired and was warned about.

    The `expiry_warning_sent_at` condition is the rule, not an optimisation:
    without it a mail outage would turn into silent deletion of the only copy
    of somebody's data, which is the one outcome this whole module exists to
    prevent. A file whose uploader has no address is warned-marked but still
    never deleted without somebody having had the chance -- which in that case
    means an administrator deleting it from the storage page.
    """
    if settings.UPLOAD_LIFETIME_DAYS <= 0:
        return 0

    now = utcnow()
    # A full day after the warning went, however late it went. A file already
    # past expiry when it was first warned about -- after a mail outage, a
    # scheduler that was down, an install that switched the lifecycle on --
    # used to be warned and deleted in the same run.
    warned_before = now - uploads.WARN_WITHIN
    expired = [
        upload
        for upload in models.UploadedFile.query.filter(
            models.UploadedFile.expires_at.isnot(None),
            models.UploadedFile.expires_at <= now,
            models.UploadedFile.expiry_warning_sent_at.isnot(None),
            models.UploadedFile.expiry_warning_sent_at <= warned_before,
        ).all()
        if upload.created_by is not None and upload.created_by.email
    ]

    sources = {upload.data_source for upload in expired if upload.data_source}
    for upload in expired:
        logger.info(
            "task=delete_expired_upload id=%s file=%s size=%s last_queried=%s",
            upload.id,
            upload.filename,
            upload.size,
            upload.last_queried_at,
        )
        upload.delete()
    if sources:
        _forget_schemas_for_sources(sources)
    return len(expired)


def _forget_schemas(upload_rows):
    _forget_schemas_for_sources({upload.data_source for upload in upload_rows if upload.data_source})


def _forget_schemas_for_sources(sources):
    for source in sources:
        try:
            redis_connection.delete(source._schema_key)
        except Exception:
            logger.warning("could not clear the cached schema for data source %s", source.id, exc_info=True)

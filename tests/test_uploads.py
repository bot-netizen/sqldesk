"""
The clock on uploaded files.

The one rule everything here serves: an uploaded file is the only copy of
itself. A warehouse answer can be fetched again and a stream window is a
window, but nobody can re-create a CSV somebody dragged in six months ago and
has since deleted from their laptop. So it expires on a clock people can see
and stop, and the only deletion that happens without a person involved is one
that was announced in a mail they could have acted on.
"""

import datetime
import io
import os
import tempfile
import unittest
from unittest import mock

from sqldesk import models, settings, uploads
from sqldesk.models import db
from sqldesk.tasks.uploads import (
    delete_expired_uploads,
    unload_idle_uploads,
    warn_about_expiring_uploads,
)
from tests import BaseTestCase, authenticate_request


class _WithNoDeclaredLength:
    """
    The live request, but claiming no content length.

    A real chunked upload sends none, and werkzeug's test client cannot send
    one: it writes a Content-Length for every multipart body. So the condition
    is produced here rather than over the wire. Everything other than the
    length is the real request -- this is a wrapper, not a stub.
    """

    content_length = None

    def __getattr__(self, name):
        from flask import request as live

        return getattr(live, name)


class UploadTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.source = self.factory.create_data_source(name="Files", type="duckdb", options={"dbpath": ":memory:"})

    def upload(self, name="sales.csv", size=1024, user=None, days_old=0, **fields):
        """A row with a real file behind it, so deletion has something to do."""
        row = models.UploadedFile(
            org=self.factory.org,
            data_source=self.source,
            filename=name,
            stored_filename=name,
            size=size,
            created_by=user if user is not None else self.factory.user,
            expires_at=models.UploadedFile.default_expiry(),
            **fields,
        )
        db.session.add(row)
        db.session.flush()
        os.makedirs(row.directory, exist_ok=True)
        with open(row.path, "w") as handle:
            handle.write("x\n1\n")
        if days_old:
            row.created_at = models.utcnow() - datetime.timedelta(days=days_old)
        db.session.commit()
        return row


class TestWhenAnUploadExpires(UploadTestCase):
    def test_a_new_one_is_given_seven_days(self):
        with mock.patch("sqldesk.settings.UPLOAD_LIFETIME_DAYS", 7):
            row = self.upload()

        self.assertEqual(7, row.expires_in_days)

    def test_an_install_with_the_clock_off_keeps_everything(self):
        with mock.patch("sqldesk.settings.UPLOAD_LIFETIME_DAYS", 0):
            row = self.upload()

        self.assertIsNone(row.expires_at)
        self.assertTrue(row.kept)
        self.assertIsNone(row.expires_in_days)

    def test_keeping_it_clears_the_clock_and_says_who(self):
        row = self.upload()

        row.keep(self.factory.user)
        db.session.commit()

        self.assertTrue(row.kept)
        self.assertEqual(self.factory.user, row.kept_by)
        self.assertIsNotNone(row.kept_at)

    def test_and_clears_a_warning_already_sent(self):
        # So that putting it back on the clock later warns again rather than
        # deleting it on the next pass.
        row = self.upload(expiry_warning_sent_at=models.utcnow())

        row.keep(self.factory.user)

        self.assertIsNone(row.expiry_warning_sent_at)


class TestUnloadingWhatNobodyQueries(UploadTestCase):
    def test_a_file_unqueried_since_it_arrived_is_unloaded(self):
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 3):
            row = self.upload(days_old=4)

            self.assertEqual(1, unload_idle_uploads())

        self.assertIsNotNone(row.unloaded_at)

    def test_a_fresh_one_is_left_alone(self):
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 3):
            row = self.upload(days_old=1)

            unload_idle_uploads()

        self.assertIsNone(row.unloaded_at)

    def test_nor_is_one_queried_yesterday(self):
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 3):
            row = self.upload(days_old=40)
            row.last_queried_at = models.utcnow() - datetime.timedelta(days=1)
            db.session.commit()

            unload_idle_uploads()

        self.assertIsNone(row.unloaded_at)

    def test_with_the_step_switched_off_nothing_is_unloaded(self):
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 0):
            row = self.upload(days_old=400)

            self.assertEqual(0, unload_idle_uploads())

        self.assertIsNone(row.unloaded_at)

    def test_unloading_leaves_the_file_where_it_is(self):
        # It is reversible. The next query that names it brings it back, and
        # nobody is told because nothing was lost.
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 3):
            row = self.upload(days_old=10)
            path = row.path

            unload_idle_uploads()

        self.assertTrue(os.path.exists(path))

    def test_it_forgets_the_data_sources_cached_schema(self):
        # The cached schema named the view. Offering a table that is no longer
        # registered is worse than a schema a few minutes behind.
        with mock.patch("sqldesk.settings.UPLOAD_UNLOAD_AFTER_DAYS", 3):
            self.upload(days_old=10)
            with mock.patch("sqldesk.tasks.uploads.redis_connection") as redis:
                unload_idle_uploads()

        redis.delete.assert_called_once_with(self.source._schema_key)


class TestNotingThatAQueryUsedAFile(UploadTestCase):
    def test_a_query_naming_the_view_records_it(self):
        row = self.upload(name="sales.csv")

        uploads.note_queried(self.source, "select count(*) from sales")

        self.assertIsNotNone(row.last_queried_at)

    def test_a_query_naming_something_else_does_not(self):
        row = self.upload(name="sales.csv")

        uploads.note_queried(self.source, "select 1")

        self.assertIsNone(row.last_queried_at)

    def test_the_name_is_matched_as_a_whole_word(self):
        # Otherwise `sales` in a string literal or a column name marks the file
        # as used, and nothing is ever unloaded.
        row = self.upload(name="sales.csv")

        uploads.note_queried(self.source, "select 'wholesales' as label")

        self.assertIsNone(row.last_queried_at)

    def test_it_brings_an_unloaded_file_back(self):
        row = self.upload(name="sales.csv", unloaded_at=models.utcnow())

        uploads.note_queried(self.source, "select * from sales")

        self.assertIsNone(row.unloaded_at)

    def test_a_dashboard_refreshing_every_minute_does_not_write_every_minute(self):
        # One UPDATE per widget per minute on a read-only page is the kind of
        # cost that is invisible until it is the whole database.
        row = self.upload(name="sales.csv")
        uploads.note_queried(self.source, "select * from sales")
        first = row.last_queried_at

        uploads.note_queried(self.source, "select * from sales")

        self.assertEqual(first, row.last_queried_at)

    def test_but_an_hour_later_it_does(self):
        row = self.upload(name="sales.csv")
        row.last_queried_at = models.utcnow() - datetime.timedelta(hours=2)
        db.session.commit()
        before = row.last_queried_at

        uploads.note_queried(self.source, "select * from sales")

        self.assertGreater(row.last_queried_at, before)


class TestWarningBeforeDeleting(UploadTestCase):
    def expiring_tomorrow(self, **fields):
        row = self.upload(**fields)
        row.expires_at = models.utcnow() + datetime.timedelta(hours=20)
        db.session.commit()
        return row

    def test_the_uploader_is_mailed(self):
        row = self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            self.assertEqual(1, warn_about_expiring_uploads())

        self.assertEqual([self.factory.user.email], send.call_args[0][0])
        self.assertIsNotNone(row.expiry_warning_sent_at)

    def test_the_mail_carries_a_link_that_keeps_it(self):
        row = self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        html = send.call_args[0][2]
        self.assertIn(uploads.keep_token(row), html)
        self.assertIn("only copy", html)

    def test_and_says_whether_it_was_ever_queried(self):
        # The one fact that decides whether to keep it.
        self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        self.assertIn("Never queried", send.call_args[0][2])

    def test_one_mail_per_person_however_many_files(self):
        self.expiring_tomorrow(name="a.csv")
        self.expiring_tomorrow(name="b.csv")
        self.expiring_tomorrow(name="c.csv")

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        self.assertEqual(1, send.call_count)
        self.assertIn("3 files", send.call_args[0][1])

    def test_and_one_each_for_two_people(self):
        other = self.factory.create_user()
        self.expiring_tomorrow(name="a.csv")
        self.expiring_tomorrow(name="b.csv", user=other)

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        self.assertEqual(2, send.call_count)

    def test_nobody_is_warned_twice(self):
        self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()
            warn_about_expiring_uploads()

        self.assertEqual(1, send.call_count)

    def test_a_file_a_week_away_is_not_warned_about(self):
        # A week's notice about a file somebody uploaded on Tuesday is a mail
        # nobody reads.
        row = self.upload()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        self.assertEqual(0, send.call_count)
        self.assertIsNone(row.expiry_warning_sent_at)

    def test_a_kept_file_is_never_warned_about(self):
        row = self.expiring_tomorrow()
        row.keep(self.factory.user)
        db.session.commit()

        with mock.patch("sqldesk.tasks.uploads.send_mail") as send:
            warn_about_expiring_uploads()

        self.assertEqual(0, send.call_count)

    def test_a_failed_send_is_tried_again_rather_than_marked_done(self):
        # Otherwise a mail outage turns into silent deletion.
        row = self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.send_mail", side_effect=RuntimeError("no mail")):
            self.assertEqual(0, warn_about_expiring_uploads())

        self.assertIsNone(row.expiry_warning_sent_at)

    def test_a_mail_server_that_refuses_it_is_not_a_warning_either(self):
        """
        Through the real send, not a mock of it. The shared mail job catches
        every error, so a refused send returned normally, counted as a warning,
        and the file was deleted the next day with nobody told.
        """
        import smtplib

        row = self.expiring_tomorrow()

        with mock.patch("sqldesk.tasks.uploads.mail.send", side_effect=smtplib.SMTPException("refused")):
            self.assertEqual(0, warn_about_expiring_uploads())

        self.assertIsNone(row.expiry_warning_sent_at)


class TestDeleting(UploadTestCase):
    def expired_and_warned(self, **fields):
        row = self.upload(**fields)
        row.expires_at = models.utcnow() - datetime.timedelta(minutes=1)
        row.expiry_warning_sent_at = models.utcnow() - datetime.timedelta(days=1)
        db.session.commit()
        return row

    def test_an_expired_warned_file_goes(self):
        row = self.expired_and_warned()
        path = row.path

        self.assertEqual(1, delete_expired_uploads())

        self.assertFalse(os.path.exists(path))
        self.assertEqual(0, models.UploadedFile.query.count())

    def test_an_expired_file_nobody_was_warned_about_stays(self):
        # The rule, not an optimisation: without it a mail outage silently
        # deletes the only copy of somebody's data.
        row = self.upload()
        row.expires_at = models.utcnow() - datetime.timedelta(days=5)
        db.session.commit()

        self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))

    def test_a_file_whose_uploader_has_no_address_is_never_deleted(self):
        # Nobody could have been warned, so nobody gets to lose the file to a
        # timer. An administrator removes it from the storage page.
        row = self.expired_and_warned()
        row.created_by = None
        db.session.commit()

        self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))

    def test_a_kept_file_is_never_deleted(self):
        row = self.expired_and_warned()
        row.keep(self.factory.user)
        db.session.commit()

        self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))

    def test_nor_is_one_that_was_warned_about_and_then_kept(self):
        # Built by hand, because `keep()` also clears the warning flag and so
        # no route reaches this state today -- which meant the "has an expiry
        # at all" condition could be deleted with every test still passing.
        # Kept as a check rather than a comment: a future path that keeps a
        # file without clearing the flag must not then delete it, and the cost
        # of being wrong here is somebody's only copy.
        row = self.upload()
        row.expires_at = None
        row.expiry_warning_sent_at = models.utcnow() - datetime.timedelta(days=1)
        db.session.commit()

        self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))

    def test_one_not_yet_expired_is_left(self):
        row = self.upload(expiry_warning_sent_at=models.utcnow())

        self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))

    def test_a_file_warned_about_late_is_kept_a_day_after_the_warning(self):
        """
        Already past expiry when first warned -- after a mail outage, a
        scheduler that was down, an install that turned the lifecycle on. It
        used to be warned and deleted in the same run.
        """
        from sqldesk.tasks.uploads import manage_uploads

        row = self.upload()
        row.expires_at = models.utcnow() - datetime.timedelta(days=3)
        db.session.commit()

        with mock.patch("sqldesk.tasks.uploads.mail.send"):
            result = manage_uploads()

        self.assertEqual((1, 0), (result["warned"], result["deleted"]))
        self.assertTrue(os.path.exists(row.path))

        row.expiry_warning_sent_at = models.utcnow() - datetime.timedelta(days=1, minutes=1)
        db.session.commit()
        self.assertEqual(1, delete_expired_uploads())

    def test_with_the_clock_off_nothing_is_deleted(self):
        row = self.expired_and_warned()

        with mock.patch("sqldesk.settings.UPLOAD_LIFETIME_DAYS", 0):
            self.assertEqual(0, delete_expired_uploads())

        self.assertTrue(os.path.exists(row.path))


class TestTheQuota(UploadTestCase):
    def test_under_the_ceiling_is_fine(self):
        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            self.assertIsNone(uploads.why_this_would_not_fit(self.factory.org, 1024))

    def test_over_it_says_so_with_the_figures(self):
        self.upload(size=9 * 1024 * 1024)

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            problem = uploads.why_this_would_not_fit(self.factory.org, 5 * 1024 * 1024)

        self.assertIn("10", problem)
        self.assertIn("9.0 MB is in use", problem)

    def test_and_counts_the_files_nobody_has_queried(self):
        # Deleting those is almost always the answer, and nothing else in the
        # product would tell somebody they exist.
        self.upload(size=9 * 1024 * 1024, name="a.csv", days_old=60)
        self.upload(size=1024, name="b.csv", days_old=60)

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            problem = uploads.why_this_would_not_fit(self.factory.org, 5 * 1024 * 1024)

        self.assertIn("2 uploads have not been queried in a month", problem)

    def test_a_file_last_queried_months_ago_counts_as_idle(self):
        # The case the count is for. Testing only the recently-queried file
        # left the "queried, but long ago" half untested, and it could be
        # deleted with everything still passing.
        self.upload(
            size=9 * 1024 * 1024,
            name="a.csv",
            days_old=60,
            last_queried_at=models.utcnow() - datetime.timedelta(days=45),
        )

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            problem = uploads.why_this_would_not_fit(self.factory.org, 5 * 1024 * 1024)

        self.assertIn("one upload has not been queried in a month", problem)

    def test_a_recently_queried_file_is_not_counted_as_idle(self):
        self.upload(size=9 * 1024 * 1024, name="a.csv", days_old=60, last_queried_at=models.utcnow())

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            problem = uploads.why_this_would_not_fit(self.factory.org, 5 * 1024 * 1024)

        self.assertNotIn("not been queried", problem)

    def test_with_no_ceiling_nothing_is_refused(self):
        self.upload(size=50 * 1024 * 1024)

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 0):
            self.assertIsNone(uploads.why_this_would_not_fit(self.factory.org, 10 * 1024 * 1024))

    def test_another_organisations_files_do_not_count_against_ours(self):
        other = self.factory.create_org()
        theirs = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        db.session.add(
            models.UploadedFile(
                org=other, data_source=theirs, filename="big.csv", stored_filename="big.csv", size=9 * 1024 * 1024
            )
        )
        db.session.commit()

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            self.assertIsNone(uploads.why_this_would_not_fit(self.factory.org, 5 * 1024 * 1024))


class TestTheKeepPage(UploadTestCase):
    def _curator(self):
        group = self.factory.create_group(
            name="Keepers", permissions=models.Group.DEFAULT_PERMISSIONS + ["keep_uploads"]
        )
        db.session.add(group)
        db.session.commit()
        return self.factory.create_user(group_ids=[group.id, self.factory.default_group.id])

    def path_for(self, row):
        return "/{}/uploads/keep/{}".format(self.factory.org.slug, uploads.keep_token(row))

    def test_somebody_who_may_keep_sees_the_button(self):
        row = self.upload()
        authenticate_request(self.client, self._curator())

        page = self.client.get(self.path_for(row))

        self.assertEqual(200, page.status_code)
        self.assertIn("Keep this file", page.data.decode("utf-8"))

    def test_and_pressing_it_keeps_the_file(self):
        row = self.upload()
        authenticate_request(self.client, self._curator())

        page = self.client.post(self.path_for(row))

        self.assertEqual(200, page.status_code)
        self.assertTrue(models.UploadedFile.query.get(row.id).kept)

    def test_a_get_never_keeps_anything(self):
        # Mail clients and scanners fetch links before anybody reads them.
        row = self.upload()
        authenticate_request(self.client, self._curator())

        self.client.get(self.path_for(row))

        self.assertFalse(models.UploadedFile.query.get(row.id).kept)

    def test_somebody_without_the_permission_is_told_who_to_ask(self):
        row = self.upload()
        authenticate_request(self.client, self.factory.user)

        page = self.client.get(self.path_for(row))

        self.assertEqual(403, page.status_code)
        self.assertIn("administrator grants", page.data.decode("utf-8"))
        self.assertFalse(models.UploadedFile.query.get(row.id).kept)

    def test_nor_can_they_keep_it_by_posting(self):
        row = self.upload()
        authenticate_request(self.client, self.factory.user)

        self.client.post(self.path_for(row))

        self.assertFalse(models.UploadedFile.query.get(row.id).kept)

    def test_a_tampered_token_says_the_file_is_gone(self):
        authenticate_request(self.client, self._curator())

        page = self.client.get("/{}/uploads/keep/not-a-real-token".format(self.factory.org.slug))

        self.assertEqual(404, page.status_code)
        self.assertIn("no longer here", page.data.decode("utf-8"))

    def test_so_does_a_token_for_a_file_that_has_been_deleted(self):
        row = self.upload()
        token_path = self.path_for(row)
        row.delete()
        authenticate_request(self.client, self._curator())

        page = self.client.get(token_path)

        self.assertEqual(404, page.status_code)

    def test_another_organisations_file_is_not_reachable(self):
        other = self.factory.create_org()
        theirs = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        row = models.UploadedFile(
            org=other, data_source=theirs, filename="theirs.csv", stored_filename="theirs.csv", size=10
        )
        db.session.add(row)
        db.session.commit()
        authenticate_request(self.client, self._curator())

        page = self.client.get("/{}/uploads/keep/{}".format(self.factory.org.slug, uploads.keep_token(row)))

        self.assertEqual(404, page.status_code)

    def test_a_file_already_kept_says_so(self):
        row = self.upload()
        row.keep(self.factory.user)
        db.session.commit()
        authenticate_request(self.client, self._curator())

        page = self.client.get(self.path_for(row))

        self.assertIn("Already kept", page.data.decode("utf-8"))

    def test_signing_in_is_required(self):
        row = self.upload()

        page = self.client.get(self.path_for(row))

        self.assertIn(page.status_code, (302, 401))


class TestUploadingThroughTheApi(UploadTestCase):
    def post_file(self, content=b"x\n1\n", name="new.csv", user=None):
        return self.make_request(
            "post",
            "/api/data_sources/{}/uploads".format(self.source.id),
            user=user or self.factory.create_admin(),
            data={"file": (io.BytesIO(content), name)},
            is_json=False,
        )

    def test_a_new_upload_is_given_an_expiry(self):
        with mock.patch("sqldesk.settings.UPLOAD_LIFETIME_DAYS", 7):
            response = self.post_file()

        self.assertEqual(200, response.status_code)
        self.assertEqual(7, response.json["expires_in_days"])
        self.assertFalse(response.json["kept"])

    def test_an_upload_past_the_quota_is_refused_with_the_numbers(self):
        self.upload(size=9 * 1024 * 1024)

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            response = self.post_file(content=b"y" * (2 * 1024 * 1024))

        self.assertEqual(413, response.status_code)
        self.assertIn("is in use", response.json["message"])

    def test_it_is_checked_again_on_what_actually_arrived(self):
        """
        Content-length is a claim, and a chunked upload does not make one.

        The first check reads the declared length and refuses before any bytes
        are written, which is what makes an over-quota upload cheap. It cannot
        be the only check: with `Transfer-Encoding: chunked` there is no
        declared length at all, and the test client always sets one -- so the
        second check was being written and never exercised.
        """
        self.upload(size=9 * 1024 * 1024)

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            with mock.patch("sqldesk.handlers.uploads.request", _WithNoDeclaredLength()):
                response = self.post_file(content=b"y" * (2 * 1024 * 1024), name="late.csv")

        self.assertEqual(413, response.status_code)
        self.assertIn("is in use", response.json["message"])

    def test_and_nothing_is_left_on_the_disk(self):
        # The row is rolled back, so a file left behind would be unreachable
        # bytes that nothing ever counts or cleans up.
        self.upload(size=9 * 1024 * 1024)
        before = set(os.listdir(os.path.join(self.root, str(self.factory.org.id), str(self.source.id))))

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            self.post_file(content=b"y" * (2 * 1024 * 1024))

        after = set(os.listdir(os.path.join(self.root, str(self.factory.org.id), str(self.source.id))))
        self.assertEqual(before, after)

    def test_the_list_says_when_each_one_goes(self):
        self.upload()

        response = self.make_request(
            "get",
            "/api/data_sources/{}/uploads".format(self.source.id),
            user=self.factory.create_admin(),
        )

        self.assertIsNotNone(response.json[0]["expires_at"])
        self.assertIn("last_queried_at", response.json[0])
        self.assertIn("unloaded", response.json[0])


class TestKeepingOneThroughTheApi(UploadTestCase):
    def _keeper(self):
        group = self.factory.create_group(
            name="Keepers", permissions=models.Group.DEFAULT_PERMISSIONS + ["keep_uploads"]
        )
        db.session.add(group)
        db.session.commit()
        return self.factory.create_user(group_ids=[group.id, self.factory.default_group.id])

    def keep(self, row, user=None, method="post"):
        return self.make_request(
            method,
            "/api/data_sources/{}/uploads/{}/keep".format(self.source.id, row.id),
            user=user or self._keeper(),
        )

    def test_somebody_with_the_permission_may(self):
        row = self.upload()

        response = self.keep(row)

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json["kept"])
        self.assertIsNone(response.json["expires_at"])

    def test_and_the_answer_says_who_did(self):
        row = self.upload()
        keeper = self._keeper()

        response = self.keep(row, user=keeper)

        self.assertEqual(keeper.name, response.json["kept_by"])

    def test_somebody_without_it_may_not(self):
        row = self.upload()

        response = self.keep(row, user=self.factory.user)

        self.assertEqual(403, response.status_code)
        self.assertFalse(models.UploadedFile.query.get(row.id).kept)

    def test_it_can_be_put_back_on_the_clock(self):
        row = self.upload()
        keeper = self._keeper()
        self.keep(row, user=keeper)

        response = self.keep(row, user=keeper, method="delete")

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["kept"])
        self.assertIsNotNone(response.json["expires_at"])

    def test_an_upload_on_another_data_source_is_not_found(self):
        other = self.factory.create_data_source(name="Other files", type="duckdb")
        row = self.upload()

        response = self.make_request(
            "post",
            "/api/data_sources/{}/uploads/{}/keep".format(other.id, row.id),
            user=self._keeper(),
        )

        self.assertEqual(404, response.status_code)


class TestTheStoragePage(UploadTestCase):
    """
    None of this was visible anywhere. On 2026-09-28 the development disk
    reached 100% and took Postgres with it, and the only way to find out why
    was to look at the filesystem.
    """

    def storage(self, user=None):
        return self.make_request("get", "/api/admin/storage", user=user or self.factory.create_admin(), org=False)

    def test_it_adds_up_what_is_held(self):
        self.upload(name="a.csv", size=3 * 1024 * 1024)
        self.upload(name="b.csv", size=1024 * 1024)

        response = self.storage()

        self.assertEqual(4 * 1024 * 1024, response.json["uploads"]["bytes"])
        self.assertEqual(2, response.json["uploads"]["files"])

    def test_broken_down_by_data_source_biggest_first(self):
        small = self.factory.create_data_source(name="Small", type="duckdb")
        self.upload(name="big.csv", size=9 * 1024 * 1024)
        row = self.upload(name="small.csv", size=1024)
        row.data_source = small
        db.session.commit()

        listed = self.storage().json["uploads"]["by_data_source"]

        self.assertEqual(["Files", "Small"], [entry["data_source_name"] for entry in listed])

    def test_each_file_says_when_it_goes_and_when_it_was_last_read(self):
        self.upload(last_queried_at=models.utcnow())

        files = self.storage().json["uploads"]["by_data_source"][0]["uploads"]

        self.assertIsNotNone(files[0]["expires_at"])
        self.assertIsNotNone(files[0]["last_queried_at"])

    def test_it_reports_the_ceiling_and_the_policy(self):
        self.upload()

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 10):
            response = self.storage()

        self.assertEqual(10 * 1024 * 1024, response.json["uploads"]["quota_bytes"])
        self.assertEqual(settings.UPLOAD_LIFETIME_DAYS, response.json["uploads"]["lifetime_days"])

    def test_no_ceiling_is_reported_as_none_rather_than_zero(self):
        # So the page can say "no limit" instead of drawing a bar at 0%.
        self.upload()

        with mock.patch("sqldesk.settings.UPLOAD_QUOTA_MB", 0):
            self.assertIsNone(self.storage().json["uploads"]["quota_bytes"])

    def test_the_borrowed_half_is_listed_apart(self):
        # A cached result can be fetched again and an upload cannot, so showing
        # them as one number is how somebody ends up afraid to delete a result.
        response = self.storage()

        self.assertIn("results", response.json)

    def test_another_organisations_files_are_not_counted(self):
        other = self.factory.create_org()
        theirs = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        db.session.add(
            models.UploadedFile(
                org=other, data_source=theirs, filename="t.csv", stored_filename="t.csv", size=5 * 1024 * 1024
            )
        )
        db.session.commit()
        self.upload(size=1024)

        response = self.storage()

        self.assertEqual(1024, response.json["uploads"]["bytes"])
        # And in the breakdown, which is computed separately -- asserting only
        # on the total left the per-source filter untested.
        self.assertEqual(
            ["Files"], [entry["data_source_name"] for entry in response.json["uploads"]["by_data_source"]]
        )
        self.assertEqual(1, response.json["uploads"]["files"])

    def test_somebody_who_is_not_an_administrator_may_not_look(self):
        self.assertEqual(403, self.storage(user=self.factory.user).status_code)


class TestWhatTheChartSays(BaseTestCase):
    """
    The Helm chart is a shipped artifact, and two of these settings decide
    whether somebody loses data or sends a token in the clear.

    Read out of `values.yaml` and `_helpers.tpl` as text rather than rendered
    with helm, because helm is not in the container the suite runs in -- a test
    that skips itself wherever it actually runs is not a test. `helm lint` and
    `helm template` cover the rendering; what is checked here is the pair of
    things text can check and a human reading two files cannot: that a default
    has not drifted, and that every environment variable the chart sets is one
    the application reads.
    """

    def values(self):
        import yaml

        return yaml.safe_load(open("charts/sqldesk/values.yaml"))

    def test_the_upload_lifecycle_is_on_by_default(self):
        lifecycle = self.values()["uploads"]["lifecycle"]

        self.assertEqual(7, lifecycle["lifetimeDays"])
        self.assertEqual(3, lifecycle["unloadAfterDays"])
        self.assertEqual(5120, lifecycle["quotaMb"])

    def test_the_quota_fits_inside_the_volume_the_chart_asks_for(self):
        # Otherwise the disk fills before the quota is reached, and what
        # somebody sees is a disk error rather than a sentence they can act on.
        values = self.values()
        size = values["uploads"]["size"]
        self.assertTrue(size.endswith("Gi"), size)
        self.assertLessEqual(values["uploads"]["lifecycle"]["quotaMb"], int(size[:-2]) * 1024)

    def test_oauth_is_on_by_default_and_http_is_not(self):
        oauth = self.values()["mcp"]["oauth"]

        self.assertTrue(oauth["enabled"])
        self.assertFalse(oauth["allowHttp"])

    def test_every_setting_the_chart_names_is_one_the_application_reads(self):
        """
        A typo in an environment variable's name in the chart is silent: the
        pod starts, the setting keeps its default, and the feature is quietly
        off. Nothing else would catch it.
        """
        import re

        template = open("charts/sqldesk/templates/_helpers.tpl").read()
        settings_source = open("sqldesk/settings/__init__.py").read()
        for name in sorted(set(re.findall(r"SQLDESK_[A-Z0-9_]+", template))):
            self.assertIn(
                '"{}"'.format(name),
                settings_source,
                "{} is set by the chart and read by nothing".format(name),
            )


class TestAnUploadWhoseFileIsGone(BaseTestCase):
    """
    A record with no file behind it.

    It should not happen -- deleting an upload deletes both -- but it does when
    the volume holding uploads is replaced underneath an install, and then
    every page goes on reporting the upload as though it were there. The
    symptom is a data source whose schema is silently empty: no table to query,
    nothing for the catalog to harvest, and no page saying why.
    """

    def upload(self, stored_filename="orders.parquet"):
        source = self.factory.create_data_source(name="Files", type="duckdb")
        return models.UploadedFile(
            org=self.factory.org,
            data_source=source,
            filename="orders.parquet",
            stored_filename=stored_filename,
            content_type="application/octet-stream",
            size=1008,
        )

    def test_it_is_reported_as_missing(self):
        # `path` is built from the upload root, the org and the data source, so
        # a row with nothing written under it has no file.
        self.assertTrue(self.upload().to_dict()["missing"])

    def test_and_one_that_is_there_is_not(self):
        row = self.upload()
        os.makedirs(row.directory, exist_ok=True)
        with open(row.path, "wb") as handle:
            handle.write(b"x")
        self.addCleanup(os.remove, row.path)

        self.assertFalse(row.to_dict()["missing"])


class TestEveryPodOnTheUploadsVolumeSharesANode(unittest.TestCase):
    """
    A ReadWriteOnce volume mounts on one node. Every pod that mounts the uploads
    volume therefore has to land on that node, or it waits forever on a
    Multi-Attach error -- which minikube, being one node, can never show.

    0.7.3 pinned the workers to the server but not the server to itself, so a
    second server replica could land elsewhere, and a rolling update with one
    replica could deadlock: the new pod unable to mount until the old one let
    go, the old one kept until the new was ready. The stream worker mounted the
    volume with no affinity at all.

    Read as text, like the other chart checks here, because helm is not in the
    container this suite runs in.
    """

    def template(self, name):
        return open("charts/sqldesk/templates/{}".format(name)).read()

    def deployment(self, text, component):
        start = text.index("app.kubernetes.io/component: {}".format(component))
        following = text.find("kind: Deployment", start)
        return text[start : following if following != -1 else len(text)]

    def test_the_server_is_pinned_to_its_own_node(self):
        self.assertIn('include "sqldesk.uploadsAffinity"', self.template("server.yaml"))

    def test_so_is_every_worker_that_mounts_the_volume(self):
        workers = self.template("worker.yaml")
        for component in ("worker", "mcp-worker", "stream-worker"):
            block = self.deployment(workers, component)
            if "sqldesk.uploadsMount" in block:
                self.assertIn('include "sqldesk.uploadsAffinity"', block, component)

    def test_the_affinity_names_the_server(self):
        helper = open("charts/sqldesk/templates/_helpers.tpl").read()
        start = helper.index('define "sqldesk.uploadsAffinity"')
        body = helper[start : helper.index("{{- end -}}", start)]
        self.assertIn("app.kubernetes.io/component: server", body)
        self.assertIn('eq .Values.uploads.accessMode "ReadWriteOnce"', body)

from unittest import mock

from sqlalchemy import event

from sqldesk import models
from sqldesk.models import db
from sqldesk.tasks.general import record_event
from sqldesk.tasks.schedule import periodic_job_definitions
from tests import BaseTestCase


class TestEvents(BaseTestCase):
    def test_a_crafted_event_does_not_break_the_admin_page(self):
        # A client may post any event. One shaped like an execution but
        # without its `query` raised KeyError when an admin listed events,
        # and the page was gone for good.
        db.session.add(
            models.Event(
                org=self.factory.org,
                user=self.factory.user,
                action="execute_query",
                object_type="data_source",
                object_id=1,
                additional_properties={},
            )
        )
        db.session.commit()

        listed = self.make_request("get", "/api/events", user=self.factory.create_admin())

        self.assertEqual(200, listed.status_code)

    def test_posting_events_is_a_list_or_nothing(self):
        posted = self.make_request(
            "post", "/api/events", data=[{"action": "view", "object_type": "page", "object_id": "x"}]
        )
        self.assertEqual(200, posted.status_code)
        self.assertEqual(400, self.make_request("post", "/api/events", data={"action": "view"}).status_code)


class TestAPagesEventsCostOneJob(BaseTestCase):
    """
    The browser batches what happened in the last second and posts it in one
    request. Each event then became a job of its own: a dashboard of thirty
    widgets queued about seventy-five jobs, each with a round trip to Redis, a
    worker pick-up and a transaction, for seventy-five small inserts.
    """

    def _post(self, events):
        with mock.patch("sqldesk.handlers.base.record_event_task") as task:
            response = self.make_request("post", "/api/events", data=events)
        return response, task

    def test_a_page_of_events_is_one_job(self):
        response, task = self._post(
            [{"action": "view", "object_type": "widget", "object_id": index} for index in range(30)]
        )

        self.assertEqual(200, response.status_code)
        task.delay.assert_called_once()
        self.assertEqual(30, len(task.delay.call_args[0][0]))

    def test_each_one_still_says_who_did_it_and_when(self):
        _response, task = self._post([{"action": "view", "object_type": "page", "object_id": "home"}])

        sent = task.delay.call_args[0][0][0]
        self.assertEqual(self.factory.user.id, sent["user_id"])
        self.assertEqual(self.factory.org.id, sent["org_id"])
        self.assertIn("timestamp", sent)

    def test_an_absurd_list_is_refused_rather_than_queued(self):
        # No limit at all, from an endpoint any signed-in session may post to.
        response, task = self._post([{"action": "view", "object_type": "page", "object_id": "x"}] * 500)

        self.assertEqual(400, response.status_code)
        task.delay.assert_not_called()

    def test_a_list_with_nothing_usable_in_it_queues_nothing(self):
        response, task = self._post(["not an event"])

        self.assertEqual(200, response.status_code)
        task.delay.assert_not_called()

    def test_five_events_are_written_in_one_transaction(self):
        # The ids first: the factory creates its org and user lazily, and
        # commits when it does, which would be counted below.
        org_id, user_id = self.factory.org.id, self.factory.user.id
        commits = []

        def committed(_session):
            commits.append(1)

        event.listen(db.session, "after_commit", committed)
        try:
            record_event(
                [
                    {
                        "org_id": org_id,
                        "user_id": user_id,
                        "action": "view",
                        "object_type": "page",
                        "object_id": index,
                        "timestamp": 1_700_000_000,
                    }
                    for index in range(5)
                ]
            )
        finally:
            event.remove(db.session, "after_commit", committed)

        self.assertEqual(5, models.Event.query.filter(models.Event.object_type == "page").count())
        # Five events used to arrive as five jobs and so five transactions.
        self.assertEqual(1, len(commits))

    def test_one_malformed_event_does_not_cost_the_others(self):
        record_event(
            [
                {"action": "view"},  # no org, no type: nonsense
                {
                    "org_id": self.factory.org.id,
                    "user_id": self.factory.user.id,
                    "action": "view",
                    "object_type": "page",
                    "object_id": "home",
                    "timestamp": 1_700_000_000,
                },
            ]
        )

        self.assertEqual(1, models.Event.query.filter(models.Event.object_type == "page").count())

    def test_a_single_event_is_still_accepted(self):
        # Every call inside the server passes one, and a job already on the
        # queue at upgrade time carries one.
        record_event(
            {
                "org_id": self.factory.org.id,
                "user_id": self.factory.user.id,
                "action": "view",
                "object_type": "dashboard",
                "object_id": 3,
                "timestamp": 1_700_000_000,
            }
        )

        self.assertEqual(1, models.Event.query.filter(models.Event.object_type == "dashboard").count())


class TestTheEventsCleanupIsActuallyScheduled(BaseTestCase):
    """
    The events table grows faster than any other -- a row per execution, each
    holding the query text -- and the cleanup for it was written, tested,
    settable, and never put on the schedule, so nothing ever pruned it.
    """

    def test_it_is_on_the_schedule(self):
        names = [job["func"].__name__ for job in periodic_job_definitions()]

        self.assertIn("cleanup_events", names)

    def test_and_is_left_off_where_the_age_says_keep_everything(self):
        with mock.patch("sqldesk.settings.EVENTS_CLEANUP_MAX_AGE", 0):
            names = [job["func"].__name__ for job in periodic_job_definitions()]

        self.assertNotIn("cleanup_events", names)

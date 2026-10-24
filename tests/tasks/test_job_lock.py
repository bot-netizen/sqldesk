"""
The lock that stops the same query running twice at once.

A dashboard of widgets asks for the same query repeatedly, within
milliseconds; the lock is what makes the second request join the job already
running instead of starting its own. Releasing it wrongly is worse than not
having it, because the extra run is against somebody's warehouse.
"""

from unittest import mock

from sqldesk import redis_connection
from sqldesk.tasks.queries.execution import _job_lock_id, _unlock
from tests import BaseTestCase


class TestReleasingTheLock(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.key = _job_lock_id("abc", 1)

    def test_a_job_releases_its_own_lock(self):
        redis_connection.set(self.key, "job-1")

        _unlock("abc", 1, "job-1")

        self.assertIsNone(redis_connection.get(self.key))

    def test_but_not_one_a_newer_job_has_taken(self):
        # The first job finishes just after a second has taken the lock. A
        # plain delete here released the second job's lock, so the next
        # request started a third run of the same query while the second was
        # still going.
        redis_connection.set(self.key, "job-2")

        _unlock("abc", 1, "job-1")

        self.assertEqual("job-2", redis_connection.get(self.key))

    def test_a_caller_that_does_not_know_its_job_still_clears_it(self):
        redis_connection.set(self.key, "job-2")

        _unlock("abc", 1)

        self.assertIsNone(redis_connection.get(self.key))

    def test_a_redis_without_scripting_leaves_the_lock_rather_than_dropping_it(self):
        # A stale lock is cleared by enqueue_query, which checks whether the
        # job it names is still alive. Dropping somebody else's is not.
        import redis as redis_module

        redis_connection.set(self.key, "job-1")
        with mock.patch.object(
            redis_connection, "eval", side_effect=redis_module.ResponseError("unknown command EVAL")
        ):
            _unlock("abc", 1, "job-1")

        self.assertEqual("job-1", redis_connection.get(self.key))

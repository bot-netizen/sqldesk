"""
Where one consuming job leaves off, for the job that takes over.

Every job used to seek to the end when it started, so each hand-over dropped
whatever arrived between two jobs -- and starting from the beginning would have
replayed the whole topic at every one.
"""

from sqldesk import redis_connection
from sqldesk.streams import handover
from tests import BaseTestCase


class TestHandingOver(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(lambda: redis_connection.delete(handover._key(7)))

    def test_what_one_job_leaves_the_next_one_takes(self):
        handover.give(7, {0: 120, 1: 45})

        self.assertEqual({0: 120, 1: 45}, handover.take(7))

    def test_only_once(self):
        # A second job taking the same positions would read the same events
        # twice -- and a later cold start must not inherit them either.
        handover.give(7, {0: 120})
        handover.take(7)

        self.assertEqual({}, handover.take(7))

    def test_a_cold_start_finds_nothing(self):
        self.assertEqual({}, handover.take(7))

    def test_nothing_to_hand_over_writes_nothing(self):
        self.assertFalse(handover.give(7, {}))
        self.assertIsNone(redis_connection.get(handover._key(7)))

    def test_it_does_not_outlive_a_successor_that_never_came(self):
        handover.give(7, {0: 120})

        ttl = redis_connection.ttl(handover._key(7))
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, handover.SECONDS)

    def test_rubbish_in_redis_is_a_cold_start_not_a_crash(self):
        redis_connection.set(handover._key(7), "not json")

        self.assertEqual({}, handover.take(7))

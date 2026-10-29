from unittest import mock

from sqldesk import pools, settings
from tests import BaseTestCase


class PoolTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.clear)
        self.clear()

    def clear(self):
        from sqldesk import redis_connection

        for key in redis_connection.keys("pool:*"):
            redis_connection.delete(key)


class TestWhichPoolADataSourceDrawsFrom(PoolTestCase):
    """
    A pool is named so that two data sources can be one machine.

    `prod-readonly` and `prod-analytics` are separate rows here and the same
    warehouse. Keying the budget to the data source caps each of them and
    hands the machine twice what it was promised.
    """

    def test_a_data_source_gets_a_pool_of_its_own_by_default(self):
        source = self.factory.create_data_source()

        self.assertEqual("ds:{}".format(source.id), pools.pool_for(source))

    def test_two_sources_naming_one_pool_share_it(self):
        warehouse = self.factory.create_data_source()
        reporting = self.factory.create_data_source()
        warehouse.options["query_pool"] = "snowflake"
        reporting.options["query_pool"] = "snowflake"

        self.assertEqual(pools.pool_for(warehouse), pools.pool_for(reporting))

    def test_a_blank_or_missing_name_falls_back_to_its_own(self):
        source = self.factory.create_data_source()

        for value in (None, "", "   ", 7, []):
            with self.subTest(value=value):
                source.options["query_pool"] = value
                self.assertEqual("ds:{}".format(source.id), pools.pool_for(source))


class TestWhatAPoolIsWorth(PoolTestCase):
    def test_nothing_configured_is_unlimited(self):
        # The default on purpose: upgrading must not cap an install that has
        # run a nightly batch of thirty refreshes for a year.
        source = self.factory.create_data_source()

        self.assertEqual(pools.NO_LIMIT, pools.budget(pools.pool_for(source), source))

    def test_a_named_pool_is_configured_in_one_place(self):
        with mock.patch.object(settings, "QUERY_POOLS", {"snowflake": 8}):
            self.assertEqual(8, pools.budget("snowflake"))

    def test_a_source_can_size_the_pool_it_made_for_itself(self):
        source = self.factory.create_data_source()
        source.options["query_slots"] = 3

        self.assertEqual(3, pools.budget(pools.pool_for(source), source))

    def test_a_source_cannot_resize_a_pool_it_only_shares(self):
        # Otherwise one source quietly changes a budget another relies on.
        source = self.factory.create_data_source()
        source.options["query_pool"] = "snowflake"
        source.options["query_slots"] = 99

        with mock.patch.object(settings, "QUERY_POOLS", {"snowflake": 8}):
            self.assertEqual(8, pools.budget("snowflake", source))

    def test_nor_when_nothing_else_has_configured_that_shared_pool(self):
        # The case the test above misses: with no named setting to answer
        # first, a source's own number must still not reach a pool it merely
        # shares -- or the last source edited silently sets the budget for
        # every other source on that warehouse.
        source = self.factory.create_data_source()
        source.options["query_pool"] = "snowflake"
        source.options["query_slots"] = 99

        with mock.patch.object(settings, "QUERY_POOLS", {}):
            self.assertEqual(settings.QUERY_SLOTS_DEFAULT, pools.budget("snowflake", source))

    def test_the_named_setting_wins_over_the_sources_own(self):
        source = self.factory.create_data_source()
        source.options["query_slots"] = 99

        with mock.patch.object(settings, "QUERY_POOLS", {"ds:{}".format(source.id): 2}):
            self.assertEqual(2, pools.budget(pools.pool_for(source), source))

    def test_an_unreadable_size_falls_back_rather_than_raising(self):
        source = self.factory.create_data_source()

        for value in ("eight", None, [], {}):
            with self.subTest(value=value):
                source.options["query_slots"] = value
                self.assertEqual(
                    settings.QUERY_SLOTS_DEFAULT,
                    pools.budget(pools.pool_for(source), source),
                )

    def test_a_negative_size_is_unlimited_rather_than_a_blocked_source(self):
        source = self.factory.create_data_source()
        source.options["query_slots"] = -4

        self.assertEqual(pools.NO_LIMIT, pools.budget(pools.pool_for(source), source))


class TestTakingRoom(PoolTestCase):
    def test_up_to_the_budget_gets_in(self):
        for i in range(3):
            self.assertIsNone(pools.acquire("warehouse", "job-{}".format(i), limit=3))

        self.assertEqual(3, pools.in_use("warehouse"))

    def test_the_one_past_it_is_refused(self):
        for i in range(3):
            pools.acquire("warehouse", "job-{}".format(i), limit=3)

        self.assertIsNotNone(pools.acquire("warehouse", "job-4", limit=3))

    def test_a_refusal_is_a_sentence_somebody_can_act_on(self):
        pools.acquire("warehouse", "job-1", limit=1)

        message = pools.acquire("warehouse", "job-2", limit=1)

        # The numbers and the name, because "it is busy" is not actionable.
        self.assertIn("warehouse", message)
        self.assertIn("1", message)

    def test_an_unlimited_pool_never_refuses(self):
        for i in range(50):
            self.assertIsNone(pools.acquire("warehouse", "job-{}".format(i), limit=pools.NO_LIMIT))

    def test_releasing_makes_room_for_the_next(self):
        pools.acquire("warehouse", "job-1", limit=1)
        self.assertIsNotNone(pools.acquire("warehouse", "job-2", limit=1))

        pools.release("warehouse", "job-1")

        self.assertIsNone(pools.acquire("warehouse", "job-2", limit=1))

    def test_pools_do_not_see_each_other(self):
        pools.acquire("warehouse", "job-1", limit=1)

        self.assertIsNone(pools.acquire("reporting", "job-2", limit=1))

    def test_asking_twice_under_one_holder_takes_one_slot(self):
        # A retried job must not consume a second slot while its first is
        # still counted.
        self.assertIsNone(pools.acquire("warehouse", "job-1", limit=1))
        self.assertIsNone(pools.acquire("warehouse", "job-1", limit=1))

        self.assertEqual(1, pools.in_use("warehouse"))


class TestWeight(PoolTestCase):
    """
    A four-terabyte scan and a four-gigabyte one are not the same load.

    Nothing estimates cost yet, so everything weighs one today. The mechanism
    carries weight from the start because it is cheaper than retrofitting it.
    """

    def test_a_heavy_request_takes_more_than_one_slot(self):
        self.assertIsNone(pools.acquire("warehouse", "big", weight=3, limit=4))

        self.assertEqual(3, pools.in_use("warehouse"))

    def test_a_request_that_would_not_fit_is_refused_even_with_room_for_one(self):
        pools.acquire("warehouse", "small", weight=1, limit=4)

        # Two slots free, a request for three.
        self.assertIsNotNone(pools.acquire("warehouse", "big", weight=3, limit=3))

    def test_what_is_already_held_is_counted_by_weight_and_not_by_holder(self):
        # One holder occupying three of four slots. Counting holders instead
        # of weight reads this as "one in use" and lets the next two in on top
        # of a warehouse already carrying three.
        pools.acquire("warehouse", "big", weight=3, limit=4)

        self.assertIsNotNone(pools.acquire("warehouse", "another", weight=2, limit=4))
        self.assertIsNone(pools.acquire("warehouse", "small", weight=1, limit=4))

    def test_a_weight_below_one_still_counts_as_one(self):
        for weight in (0, -5):
            with self.subTest(weight=weight):
                self.clear()
                pools.acquire("warehouse", "job", weight=weight, limit=2)
                self.assertEqual(1, pools.in_use("warehouse"))

    def test_a_request_exactly_filling_the_pool_gets_in(self):
        self.assertIsNone(pools.acquire("warehouse", "big", weight=4, limit=4))


class TestAHolderExpiresOnItsOwn(PoolTestCase):
    """
    Nothing may depend on a worker surviving long enough to release its slot.

    A killed process, a drained node and an OOM all have to end with the slot
    free, or one bad day permanently shrinks a pool.
    """

    def test_an_expired_holder_stops_counting(self):
        pools.acquire("warehouse", "died", limit=1, ttl=10, now=1000)

        self.assertEqual(0, pools.in_use("warehouse", now=1100))

    def test_and_its_room_is_given_to_somebody_else(self):
        pools.acquire("warehouse", "died", limit=1, ttl=10, now=1000)

        self.assertIsNone(pools.acquire("warehouse", "next", limit=1, now=1100))

    def test_a_live_holder_is_not_collected_early(self):
        pools.acquire("warehouse", "running", limit=1, ttl=100, now=1000)

        self.assertEqual(1, pools.in_use("warehouse", now=1050))

    def test_renewing_pushes_the_expiry_out(self):
        pools.acquire("warehouse", "slow", limit=1, ttl=100, now=1000)
        pools.renew("warehouse", "slow", now=1050)

        # Without the renewal it would have gone at 1100.
        self.assertEqual(1, pools.in_use("warehouse", now=1120))

    def test_renewing_keeps_the_weight_it_was_given(self):
        pools.acquire("warehouse", "big", weight=3, limit=4, ttl=100, now=1000)
        pools.renew("warehouse", "big", now=1050)

        self.assertEqual(3, pools.in_use("warehouse", now=1060))

    def test_renewing_something_gone_does_not_bring_it_back(self):
        # A renewal racing a release must not resurrect the slot.
        pools.renew("warehouse", "never-existed")

        self.assertEqual(0, pools.in_use("warehouse"))

    def test_an_unreadable_entry_is_dropped_rather_than_counted_for_ever(self):
        from sqldesk import redis_connection

        redis_connection.hset("pool:warehouse", "corrupt", "not-a-number")

        self.assertEqual(0, pools.in_use("warehouse"))
        self.assertIsNone(pools.acquire("warehouse", "next", limit=1))


class TestRedisBeingUnreachable(PoolTestCase):
    """
    The ceiling is a safety feature, and a safety feature that takes the
    application down with it when its store blinks is worse than none.
    """

    def test_a_pool_that_cannot_be_read_does_not_raise(self):
        with mock.patch("sqldesk.pools.redis_connection") as redis:
            redis.hgetall.side_effect = RuntimeError("redis is away")

            self.assertEqual({}, pools.held("warehouse"))

    def test_a_slot_that_cannot_be_written_does_not_raise(self):
        with mock.patch("sqldesk.pools.redis_connection") as redis:
            redis.set.return_value = True
            redis.hgetall.return_value = {}
            redis.hset.side_effect = RuntimeError("redis is away")

            self.assertIsNone(pools.acquire("warehouse", "job", limit=4))

    def test_a_lock_that_cannot_be_taken_refuses_rather_than_over_admitting(self):
        # Refusing is the safe direction: letting everybody through because
        # the lock is unavailable is a ceiling that does not cap.
        with mock.patch("sqldesk.pools.redis_connection") as redis:
            redis.set.side_effect = RuntimeError("redis is away")

            self.assertIsNotNone(pools.acquire("warehouse", "job", limit=4))


class TestThePoolIsNotTheWorkerCount(PoolTestCase):
    """
    The requirement, in Iqbal's words: a cap "irrespective of workers we
    have". These assert the property rather than the implementation.
    """

    def test_many_independent_callers_share_one_ceiling(self):
        # Stands in for workers in different processes on different nodes:
        # nothing is shared between them but Redis.
        got = [pools.acquire("warehouse", "worker-{}".format(i), limit=3) for i in range(10)]

        self.assertEqual(3, len([one for one in got if one is None]))
        self.assertEqual(7, len([one for one in got if one is not None]))

    def test_the_ceiling_does_not_move_when_callers_come_and_go(self):
        for i in range(3):
            pools.acquire("warehouse", "first-wave-{}".format(i), limit=3)
        for i in range(3):
            pools.release("warehouse", "first-wave-{}".format(i))

        got = [pools.acquire("warehouse", "second-wave-{}".format(i), limit=3) for i in range(10)]

        self.assertEqual(3, len([one for one in got if one is None]))

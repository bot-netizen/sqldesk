from unittest import mock

from sqldesk import models, pools, settings
from sqldesk.tasks.queries.execution import execute_query
from tests import BaseTestCase


def a_job(*args, **kwargs):
    """
    A stand-in for the RQ job the executor expects.

    `_log_progress` reads `self.job.id` on every state change, so the executor
    has never been runnable outside a worker. The same shape the existing
    executor tests use.
    """
    job = mock.Mock()
    job.id = "job-under-test"
    job.is_cancelled = False
    return job


class QueryPoolTestCase(BaseTestCase):
    """
    The pool as the execution path sees it.

    `tests/test_pools.py` covers the mechanism; this covers the wiring -- that
    a query takes a slot before it reaches the data source, gives it back
    afterwards, and refuses with something readable when there is no room.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(self.clear)
        self.clear()
        job = mock.patch("sqldesk.tasks.queries.execution.get_current_job", side_effect=a_job)
        job.start()
        self.addCleanup(job.stop)
        self.source = self.factory.create_data_source()
        models.db.session.commit()
        self.pool = pools.pool_for(self.source)

    def clear(self):
        from sqldesk import redis_connection

        for key in redis_connection.keys("pool:*"):
            redis_connection.delete(key)

    def run_with(self, runner, query="SELECT 1", **settings_overrides):
        """
        The real entry point, which is where a refusal becomes a returned
        error rather than an exception -- the shape the rest of the system
        already handles.
        """
        overrides = {"QUERY_SLOT_WAIT_SECONDS": 0}
        overrides.update(settings_overrides)
        for key, value in overrides.items():
            one = mock.patch.object(settings, key, value)
            one.start()
            self.addCleanup(one.stop)
        with mock.patch.object(type(self.source), "query_runner", runner):
            return execute_query(query, self.source.id, {}, user_id=self.factory.user.id)


def a_runner(data='{"columns":[],"rows":[]}', error=None):
    runner = mock.MagicMock()
    runner.run_query.return_value = (data, error)
    runner.annotate_query.side_effect = lambda q, m: q
    return runner


class TestAQueryTakesASlot(QueryPoolTestCase):
    def test_an_unlimited_pool_runs_the_query_and_records_nothing(self):
        runner = a_runner()

        self.run_with(runner)

        self.assertTrue(runner.run_query.called)
        self.assertEqual(0, pools.in_use(self.pool))

    def test_a_slot_is_given_back_once_the_result_is_stored(self):
        self.source.options["query_slots"] = 1
        models.db.session.commit()

        self.run_with(a_runner())

        self.assertEqual(0, pools.in_use(self.pool))

    def test_a_full_pool_refuses_before_the_data_source_is_touched(self):
        # The point of the whole feature: the warehouse is not asked.
        self.source.options["query_slots"] = 1
        models.db.session.commit()
        pools.acquire(self.pool, "somebody-else", limit=1)
        runner = a_runner()

        result = self.run_with(runner)

        self.assertFalse(runner.run_query.called)
        self.assertIn("slots", str(result))

    def test_a_refusal_names_the_pool_and_the_numbers(self):
        self.source.options["query_slots"] = 2
        models.db.session.commit()
        for i in range(2):
            pools.acquire(self.pool, "other-{}".format(i), limit=2)

        result = self.run_with(a_runner())

        self.assertIn(self.pool, str(result))
        self.assertIn("2", str(result))

    def test_a_query_that_fails_still_gives_its_slot_back(self):
        # Otherwise one broken query permanently shrinks the pool.
        self.source.options["query_slots"] = 1
        models.db.session.commit()

        self.run_with(a_runner(data=None, error="syntax error"))

        self.assertEqual(0, pools.in_use(self.pool))

    def test_a_query_whose_runner_raises_still_gives_its_slot_back(self):
        self.source.options["query_slots"] = 1
        models.db.session.commit()
        runner = a_runner()
        runner.run_query.side_effect = RuntimeError("connection reset")

        self.run_with(runner)

        self.assertEqual(0, pools.in_use(self.pool))


class TestTwoSourcesOneWarehouse(QueryPoolTestCase):
    """
    The case that made the pool named rather than per-source.
    """

    def test_sources_sharing_a_pool_share_its_ceiling(self):
        other = self.factory.create_data_source()
        self.source.options["query_pool"] = "snowflake"
        other.options["query_pool"] = "snowflake"
        models.db.session.commit()
        runner = a_runner()

        with mock.patch.object(settings, "QUERY_POOLS", {"snowflake": 1}):
            pools.acquire("snowflake", "a-query-on-the-other-source", limit=1)
            result = self.run_with(runner)

        # The other source filled the machine; this one is told so.
        self.assertFalse(runner.run_query.called)
        self.assertIn("snowflake", str(result))

    def test_sources_on_separate_pools_do_not_block_each_other(self):
        other = self.factory.create_data_source()
        models.db.session.commit()
        self.source.options["query_slots"] = 1
        models.db.session.commit()
        pools.acquire(pools.pool_for(other), "busy", limit=1)
        runner = a_runner()

        self.run_with(runner)

        self.assertTrue(runner.run_query.called)

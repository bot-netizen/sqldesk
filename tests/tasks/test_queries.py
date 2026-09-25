from mock import Mock, patch
from rq import Connection
from rq.exceptions import NoSuchJobError

from sqldesk import models, redis_connection, rq_redis_connection
from sqldesk.query_runner.pg import PostgreSQL
from sqldesk.tasks import Job
from sqldesk.tasks.queries.execution import (
    QueryExecutionError,
    _job_lock_id,
    enqueue_query,
    execute_query,
)
from sqldesk.utils import gen_query_hash
from tests import BaseTestCase


def fetch_job(*args, **kwargs):
    if any(args):
        job_id = args[0] if isinstance(args[0], str) else args[0].id
    else:
        job_id = create_job().id

    result = Mock()
    result.id = job_id
    result.is_cancelled = False

    return result


def create_job(*args, **kwargs):
    return Job(connection=rq_redis_connection)


@patch("sqldesk.tasks.queries.execution.Job.fetch", side_effect=fetch_job)
@patch("sqldesk.tasks.queries.execution.Queue.enqueue", side_effect=create_job)
class TestEnqueueTask(BaseTestCase):
    def test_multiple_enqueue_of_same_query(self, enqueue, _):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

        self.assertEqual(1, enqueue.call_count)

    def test_the_job_meta_says_when_a_run_came_from_mcp(self, enqueue, _):
        # The admin's list of running queries is built from this meta. If the
        # flag does not survive the hop into it, a query a model asked for is
        # indistinguishable from one a person is sitting waiting for.
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                metadata={"Username": "Arik", "mcp": True},
            )

        self.assertTrue(enqueue.call_args[1]["meta"]["mcp"])

    def test_the_job_meta_says_when_a_run_did_not(self, enqueue, _):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                metadata={"Username": "Arik"},
            )

        self.assertFalse(enqueue.call_args[1]["meta"]["mcp"])

    def test_multiple_enqueue_of_expired_job(self, enqueue, fetch_job):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

            # "expire" the previous job
            fetch_job.side_effect = NoSuchJobError

            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

        self.assertEqual(2, enqueue.call_count)

    def test_reenqueue_during_job_cancellation(self, enqueue, my_fetch_job):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

            # "cancel" the previous job
            def cancel_job(*args, **kwargs):
                job = fetch_job(*args, **kwargs)
                job.is_cancelled = True
                return job

            my_fetch_job.side_effect = cancel_job

            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

        self.assertEqual(2, enqueue.call_count)

    @patch("sqldesk.settings.dynamic_settings.query_time_limit", return_value=60)
    def test_limits_query_time(self, _, enqueue, __):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                query,
                {"Username": "Arik", "query_id": query.id},
            )

        _, kwargs = enqueue.call_args
        self.assertEqual(60, kwargs.get("job_timeout"))

    def test_multiple_enqueue_of_different_query(self, enqueue, _):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Arik", "query_id": query.id},
            )
            enqueue_query(
                query.query_text + "2",
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Arik", "query_id": query.id},
            )
            enqueue_query(
                query.query_text + "3",
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Arik", "query_id": query.id},
            )

        self.assertEqual(3, enqueue.call_count)


@patch("sqldesk.tasks.queries.execution.get_current_job", side_effect=fetch_job)
class QueryExecutorTests(BaseTestCase):
    def test_success(self, _):
        """
        ``execute_query`` invokes the query runner and stores a query result.
        """
        with patch.object(PostgreSQL, "run_query") as qr:
            query_result_data = {"columns": [], "rows": []}
            qr.return_value = (query_result_data, None)
            result_id = execute_query("SELECT 1, 2", self.factory.data_source.id, {})
            self.assertEqual(1, qr.call_count)
            result = models.QueryResult.query.get(result_id)
            self.assertEqual(result.data, query_result_data)

    def test_success_scheduled(self, _):
        """
        Scheduled queries remember their latest results.
        """
        q = self.factory.create_query(query_text="SELECT 1, 2", schedule={"interval": 300})
        with patch.object(PostgreSQL, "run_query") as qr:
            qr.return_value = (
                {
                    "columns": [
                        {"name": "_col0", "friendly_name": "_col0", "type": "integer"},
                        {"name": "_col1", "friendly_name": "_col1", "type": "integer"},
                    ],
                    "rows": [{"_col0": 1, "_col1": 2}],
                },
                None,
            )
            result_id = execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
            )
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 0)
            result = models.QueryResult.query.get(result_id)
            self.assertEqual(q.latest_query_data, result)

    def test_failure_scheduled(self, _):
        """
        Scheduled queries that fail have their failure recorded.
        """
        q = self.factory.create_query(query_text="SELECT 1, 2", schedule={"interval": 300})
        with patch.object(PostgreSQL, "run_query") as qr:
            qr.side_effect = ValueError("broken")

            result = execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
            )
            self.assertTrue(isinstance(result, QueryExecutionError))
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 1)

            result = execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
            )
            self.assertTrue(isinstance(result, QueryExecutionError))
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 2)

    def test_success_after_failure(self, _):
        """
        Query execution success resets the failure counter.
        """
        q = self.factory.create_query(query_text="SELECT 1, 2", schedule={"interval": 300})
        with patch.object(PostgreSQL, "run_query") as qr:
            qr.side_effect = ValueError("broken")
            result = execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
            )
            self.assertTrue(isinstance(result, QueryExecutionError))
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 1)

        with patch.object(PostgreSQL, "run_query") as qr:
            qr.return_value = (
                {
                    "columns": [
                        {"name": "_col0", "friendly_name": "_col0", "type": "integer"},
                        {"name": "_col1", "friendly_name": "_col1", "type": "integer"},
                    ],
                    "rows": [{"_col0": 1, "_col1": 2}],
                },
                None,
            )
            execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
            )
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 0)

    def test_adhoc_success_after_scheduled_failure(self, _):
        """
        Query execution success resets the failure counter, even if it runs as an adhoc query.
        """
        q = self.factory.create_query(query_text="SELECT 1, 2", schedule={"interval": 300})
        with patch.object(PostgreSQL, "run_query") as qr:
            qr.side_effect = ValueError("broken")
            result = execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                scheduled_query_id=q.id,
                user_id=self.factory.user.id,
            )
            self.assertTrue(isinstance(result, QueryExecutionError))
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 1)

        with patch.object(PostgreSQL, "run_query") as qr:
            qr.return_value = (
                {
                    "columns": [
                        {"name": "_col0", "friendly_name": "_col0", "type": "integer"},
                        {"name": "_col1", "friendly_name": "_col1", "type": "integer"},
                    ],
                    "rows": [{"_col0": 1, "_col1": 2}],
                },
                None,
            )
            execute_query(
                "SELECT 1, 2",
                self.factory.data_source.id,
                {"query_id": q.id},
                user_id=self.factory.user.id,
            )
            q = models.Query.get_by_id(q.id)
            self.assertEqual(q.schedule_failures, 0)


@patch("sqldesk.tasks.queries.execution.get_current_job", side_effect=fetch_job)
class QueryLockTests(BaseTestCase):
    """
    The Redis lock on (data source, query hash) is what makes a second request
    for the same query join the job already running instead of starting its
    own.

    It used to be released the moment the query returned, which left a window
    between the data coming back and the result row being written. A sibling
    arriving in that window found no job to join -- and, because widgets ask
    with ``max_age`` 0, no stored result to fall back on either -- so it ran
    the whole query again. These pin the window shut.
    """

    def setUp(self):
        super().setUp()
        self.query_text = "SELECT 1"
        self.key = _job_lock_id(gen_query_hash(self.query_text), self.factory.data_source.id)
        redis_connection.delete(self.key)

    def tearDown(self):
        redis_connection.delete(self.key)
        super().tearDown()

    def run_with_lock_held(self, run_query_returns):
        """Execute a query with the lock in place, noting when it is released."""
        redis_connection.set(self.key, "a-job-id")
        seen = {}
        real_store = models.QueryResult.store_result.__func__

        def watching_store(cls, *args, **kwargs):
            seen["locked_while_storing"] = bool(redis_connection.exists(self.key))
            return real_store(cls, *args, **kwargs)

        with patch.object(PostgreSQL, "run_query") as qr:
            qr.return_value = run_query_returns
            with patch.object(models.QueryResult, "store_result", classmethod(watching_store)):
                # execute_query catches QueryExecutionError and hands it back
                # as the result rather than raising, so a failure arrives here
                # as a value.
                seen["outcome"] = execute_query(self.query_text, self.factory.data_source.id, {})
        seen["locked_after"] = bool(redis_connection.exists(self.key))
        return seen

    def test_the_lock_is_still_held_while_the_result_is_written(self, _):
        seen = self.run_with_lock_held(({"columns": [], "rows": []}, None))

        # The moment that used to be unguarded.
        self.assertTrue(
            seen["locked_while_storing"],
            "a second request arriving while the row is written would start its own execution",
        )
        self.assertIsNotNone(models.QueryResult.query.get(seen["outcome"]))

    def test_the_lock_is_released_once_the_result_exists(self, _):
        seen = self.run_with_lock_held(({"columns": [], "rows": []}, None))

        # Held for longer, but not held open: the next request for this query
        # should start a fresh job rather than wait on a finished one.
        self.assertFalse(seen["locked_after"], "the lock outlived the job that owned it")

    def test_a_failed_query_still_gives_the_lock_back(self, _):
        # Nothing is stored on this path, so without the release in `finally`
        # every later request for this query would be handed a dead job id
        # until the lock expired on its own.
        seen = self.run_with_lock_held((None, "it went wrong"))

        self.assertIsInstance(seen["outcome"], QueryExecutionError)
        self.assertFalse(seen["locked_after"], "a failed query left its lock behind")

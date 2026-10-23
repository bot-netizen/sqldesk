from mock import call, patch
from rq import Connection
from rq.job import JobStatus

from sqldesk import rq_redis_connection
from sqldesk.tasks import Queue, Worker
from sqldesk.tasks.queries.execution import enqueue_query
from sqldesk.worker import default_queues, job
from tests import BaseTestCase


@patch("statsd.StatsClient.incr")
class TestWorkerMetrics(BaseTestCase):
    def tearDown(self):
        with Connection(rq_redis_connection):
            for queue_name in default_queues:
                Queue(queue_name).empty()

    def test_worker_records_success_metrics(self, incr):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Patrick", "query_id": query.id},
            )

            Worker(["queries"]).work(max_jobs=1)

        calls = [
            call("rq.jobs.running.queries"),
            call("rq.jobs.started.queries"),
            call("rq.jobs.running.queries", -1, 1),
            call("rq.jobs.finished.queries"),
        ]
        incr.assert_has_calls(calls)

    @patch("rq.Worker.execute_job")
    def test_worker_records_failure_metrics(self, _, incr):
        """
        Force superclass execute_job to do nothing and set status to JobStatus.Failed to simulate query failure
        """
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            job = enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Patrick", "query_id": query.id},
            )
            job.set_status(JobStatus.FAILED)

            Worker(["queries"]).work(max_jobs=1)

        calls = [
            call("rq.jobs.running.queries"),
            call("rq.jobs.started.queries"),
            call("rq.jobs.running.queries", -1, 1),
            call("rq.jobs.failed.queries"),
        ]
        incr.assert_has_calls(calls)


@patch("statsd.StatsClient.incr")
class TestQueueMetrics(BaseTestCase):
    def tearDown(self):
        with Connection(rq_redis_connection):
            for queue_name in default_queues:
                Queue(queue_name).empty()

    def test_enqueue_query_records_created_metric(self, incr):
        query = self.factory.create_query()

        with Connection(rq_redis_connection):
            enqueue_query(
                query.query_text,
                query.data_source,
                query.user_id,
                False,
                None,
                {"Username": "Patrick", "query_id": query.id},
            )

        incr.assert_called_with("rq.jobs.created.queries")

    def test_job_delay_records_created_metric(self, incr):
        @job("default", timeout=300)
        def foo():
            pass

        foo.delay()
        incr.assert_called_with("rq.jobs.created.default")


class TestStoppingAWorker(BaseTestCase):
    """
    A deploy, a scale-down or a node drain sends the worker SIGTERM. RQ's
    HerokuWorker then gave the running job 6 seconds before raising in it, so
    every rolling update failed every running query -- while supervisord's 290
    seconds, the pod's 300 and the docs all promised five minutes.
    """

    def tearDown(self):
        from sqldesk.tasks import worker

        worker._shutdown.clear()
        super().tearDown()

    def test_a_running_job_is_given_most_of_the_grace_period(self):
        from sqldesk import settings

        self.assertEqual(settings.WORKER_SHUTDOWN_SECONDS, Worker.imminent_shutdown_delay)
        self.assertGreater(Worker.imminent_shutdown_delay, 200)
        # Inside supervisord's stopwaitsecs, so the job ends on its own terms.
        self.assertLess(Worker.imminent_shutdown_delay, 290)

    def test_and_a_job_that_can_stop_early_is_told(self):
        import signal

        from sqldesk.tasks import worker

        horse = Worker([], connection=rq_redis_connection)
        self.assertFalse(worker.shutting_down())

        with patch.object(signal, "alarm"), patch.object(signal, "signal"):
            horse.request_stop_sigrtmin(signal.SIGRTMIN, None)

        self.assertTrue(worker.shutting_down())

"""
A job RQ still calls queued that no queue holds will never run.

Found on minikube: a worker replaced under a query that had just been
submitted took the job off its queue and stopped before starting it. The page
polled "waiting" for a job nothing would ever run, and the same query run
again joined that job through its lock instead of starting one.
"""
import datetime

from mock import Mock, patch
from rq import Connection
from rq.job import JobStatus

from sqldesk import models, redis_connection, rq_redis_connection
from sqldesk.query_runner.pg import PostgreSQL
from sqldesk.serializers import LOST, WORKER_GONE, serialize_job
from sqldesk.tasks.queries.execution import (
    QueryExecutionError,
    _job_lock_id,
    enqueue_query,
    execute_query,
)
from sqldesk.tasks.worker import Job, Queue
from sqldesk.utils import gen_query_hash
from tests import BaseTestCase


def a_query():
    return "SELECT 1"


class LostJobTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.queue = Queue("lost_job_checks", connection=rq_redis_connection)
        self.queue.empty()

    def queued(self, seconds_ago=60):
        job = self.queue.enqueue(a_query)
        job.enqueued_at = job.enqueued_at - datetime.timedelta(seconds=seconds_ago)
        job.save()
        return Job.fetch(job.id, connection=rq_redis_connection)

    def taken_off_the_queue(self, job):
        # What a worker does first, before it marks the job started.
        rq_redis_connection.lrem(self.queue.key, 0, job.id)
        return Job.fetch(job.id, connection=rq_redis_connection)


class TestAJobIsLost(LostJobTestCase):
    def test_when_it_is_queued_on_no_queue(self):
        self.assertTrue(self.taken_off_the_queue(self.queued()).is_lost)

    def test_not_while_it_waits_on_its_queue(self):
        self.assertFalse(self.queued().is_lost)

    def test_not_in_the_moment_a_worker_takes_it(self):
        self.assertFalse(self.taken_off_the_queue(self.queued(seconds_ago=1)).is_lost)

    def test_not_once_it_has_started(self):
        job = self.taken_off_the_queue(self.queued())
        job.set_status(JobStatus.STARTED)

        self.assertFalse(Job.fetch(job.id, connection=rq_redis_connection).is_lost)


class TestAStartedJobWhoseWorkerIsGone(LostJobTestCase):
    def started_on(self, worker_name, alive):
        job = self.taken_off_the_queue(self.queued())
        job.worker_name = worker_name
        job.save()
        job.set_status(JobStatus.STARTED)
        key = "rq:worker:" + worker_name
        if alive:
            rq_redis_connection.set(key, "1", ex=60)
        else:
            rq_redis_connection.delete(key)
        return Job.fetch(job.id, connection=rq_redis_connection)

    def test_is_orphaned(self):
        self.assertTrue(self.started_on("gone-worker", alive=False).is_orphaned)

    def test_not_while_its_worker_is_there(self):
        self.assertFalse(self.started_on("live-worker", alive=True).is_orphaned)

    def test_the_page_is_told_and_need_not_wait_for_the_time_limit(self):
        reply = serialize_job(self.started_on("gone-worker", alive=False))["job"]

        self.assertEqual(reply["status"], 4)
        self.assertEqual(reply["error"], WORKER_GONE)

    def test_running_it_again_starts_it_again(self):
        data_source = self.factory.data_source
        orphan = self.started_on("gone-worker", alive=False)
        redis_connection.set(_job_lock_id(gen_query_hash("SELECT 3"), data_source.id), orphan.id)

        with Connection(rq_redis_connection):
            job = enqueue_query("SELECT 3", data_source, self.factory.user.id)

        self.assertNotEqual(job.id, orphan.id)


class TestTheQueryPageIsTold(LostJobTestCase):
    def test_a_lost_job_has_failed_and_says_why(self):
        reply = serialize_job(self.taken_off_the_queue(self.queued()))["job"]

        self.assertEqual(reply["status"], 4)
        self.assertEqual(reply["error"], LOST)

    def test_a_waiting_job_is_still_waiting(self):
        reply = serialize_job(self.queued())["job"]

        self.assertEqual(reply["status"], 1)
        self.assertEqual(reply["error"], "")


class TestRunningItAgain(LostJobTestCase):
    def test_starts_a_new_job_instead_of_joining_the_lost_one(self):
        data_source = self.factory.data_source
        lost = self.taken_off_the_queue(self.queued())
        # The lock is in SQLDesk's Redis, not RQ's.
        redis_connection.set(_job_lock_id(gen_query_hash("SELECT 2"), data_source.id), lost.id)

        with Connection(rq_redis_connection):
            job = enqueue_query("SELECT 2", data_source, self.factory.user.id)

        self.assertNotEqual(job.id, lost.id)
        self.assertEqual(job.get_status(), JobStatus.QUEUED)


class TestAFailureKeepsItsOwnWords(BaseTestCase):
    def test_even_when_the_rollback_after_it_fails(self):
        # A connection that died under the query made the rollback raise, and
        # the page got SQLAlchemy's "Background on this error" line instead.
        with patch.object(PostgreSQL, "run_query", return_value=(None, "Trino said no")), patch.object(
            models.db.session, "rollback", side_effect=Exception("server closed the connection unexpectedly")
        ), patch("sqldesk.tasks.queries.execution.get_current_job", return_value=Mock(id="job-1", is_cancelled=False)):
            outcome = execute_query("SELECT 1", self.factory.data_source.id, {})

        self.assertIsInstance(outcome, QueryExecutionError)
        self.assertEqual(str(outcome), "Trino said no")

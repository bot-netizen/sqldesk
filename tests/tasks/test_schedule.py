from unittest import TestCase

from mock import patch
from rq import Connection

from sqldesk import rq_redis_connection
from sqldesk.tasks import Queue, Worker
from sqldesk.tasks.schedule import (
    reschedule_missing_periodic_jobs,
    rq_scheduler,
    schedule_periodic_jobs,
)


def tick():
    # A periodic job the worker can import by name.
    return "ticked"


class TestSchedule(TestCase):
    def setUp(self):
        for job in rq_scheduler.get_jobs():
            rq_scheduler.cancel(job)
            job.delete()

    def test_schedules_a_new_job(self):
        def foo():
            pass

        schedule_periodic_jobs([{"func": foo, "interval": 60}])

        jobs = [job for job in rq_scheduler.get_jobs()]

        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].func_name.endswith("foo"))
        self.assertEqual(jobs[0].meta["interval"], 60)

    def test_doesnt_reschedule_an_existing_job(self):
        def foo():
            pass

        schedule_periodic_jobs([{"func": foo, "interval": 60}])
        with patch("sqldesk.tasks.rq_scheduler.schedule") as schedule:
            schedule_periodic_jobs([{"func": foo, "interval": 60}])
            schedule.assert_not_called()

    def test_reschedules_a_modified_job(self):
        def foo():
            pass

        schedule_periodic_jobs([{"func": foo, "interval": 60}])
        schedule_periodic_jobs([{"func": foo, "interval": 120}])

        jobs = [job for job in rq_scheduler.get_jobs()]

        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].func_name.endswith("foo"))
        self.assertEqual(jobs[0].meta["interval"], 120)

    def test_removes_jobs_that_are_no_longer_defined(self):
        def foo():
            pass

        def bar():
            pass

        schedule_periodic_jobs([{"func": foo, "interval": 60}, {"func": bar, "interval": 90}])
        schedule_periodic_jobs([{"func": foo, "interval": 60}])

        jobs = [job for job in rq_scheduler.get_jobs()]

        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].func_name.endswith("foo"))
        self.assertEqual(jobs[0].meta["interval"], 60)


class TestPeriodicJobsStayScheduled(TestCase):
    """
    rq-scheduler drops a job for good when its record in Redis is gone. That
    happened to every short periodic job whenever the host slept longer than
    the job's result TTL, and live dashboards stopped until the scheduler was
    restarted (issue #1).
    """

    def setUp(self):
        for job in rq_scheduler.get_jobs():
            rq_scheduler.cancel(job)
            job.delete()
        with Connection(rq_redis_connection):
            Queue("periodic").empty()
        rq_scheduler._periodic_checked_at = None

    def definitions(self):
        return [{"func": tick, "interval": 10}]

    def test_puts_back_a_job_whose_record_has_gone(self):
        schedule_periodic_jobs(self.definitions())
        (job,) = rq_scheduler.get_jobs()

        # What Redis does to an expired record while the host is asleep.
        rq_redis_connection.delete(job.key)

        with patch("sqldesk.tasks.schedule.periodic_job_definitions", side_effect=self.definitions):
            rq_scheduler.enqueue_jobs()

        self.assertIn(job.id, rq_scheduler)
        self.assertTrue(rq_redis_connection.exists(job.key))

    def test_leaves_a_scheduled_job_alone(self):
        schedule_periodic_jobs(self.definitions())

        with patch("sqldesk.tasks.schedule.periodic_job_definitions", side_effect=self.definitions):
            rq_scheduler.enqueue_jobs()
            missing = reschedule_missing_periodic_jobs()

        self.assertEqual(missing, [])
        self.assertEqual(len(list(rq_scheduler.get_jobs())), 1)

    def test_a_finished_run_keeps_its_record(self):
        schedule_periodic_jobs(self.definitions())
        (job,) = rq_scheduler.get_jobs()

        with patch("sqldesk.tasks.schedule.periodic_job_definitions", side_effect=self.definitions):
            rq_scheduler.enqueue_jobs()
        with Connection(rq_redis_connection):
            Worker(["periodic"]).work(max_jobs=1)

        self.assertEqual(job.fetch(job.id, connection=rq_redis_connection).get_status(), "finished")
        # -1: no expiry. It was 60 seconds for live dashboards.
        self.assertEqual(rq_redis_connection.ttl(job.key), -1)


class TestSchedulerMetrics(TestCase):
    def setUp(self):
        for job in rq_scheduler.get_jobs():
            rq_scheduler.cancel(job)
            job.delete()

    def test_scheduler_enqueue_job_metric(self):
        def foo():
            pass

        schedule_periodic_jobs([{"func": foo, "interval": 60}])

        with patch("statsd.StatsClient.incr") as incr:
            rq_scheduler.enqueue_jobs()
            incr.assert_called_once_with("rq.jobs.created.periodic")

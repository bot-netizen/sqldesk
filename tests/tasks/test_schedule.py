from datetime import timedelta
from unittest import TestCase

from mock import patch
from rq import Connection

from sqldesk import rq_redis_connection, settings
from sqldesk.tasks import Queue, Worker
from sqldesk.tasks.schedule import (
    HEARTBEAT_KEY,
    HEARTBEAT_TTL,
    periodic_job_definitions,
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


class TestHowOftenSchemasAreRefreshed(TestCase):
    """
    Reading every schema on every pass is the most expensive periodic job here
    -- minutes of work against a warehouse with thousands of tables -- and the
    only reason it is affordable is that the interval is somebody's to set.

    A hardcoded interval would pass every other test in this file.
    """

    def _interval_of(self, func_name):
        for definition in periodic_job_definitions():
            if definition["func"].__name__ == func_name:
                return definition["interval"]
        self.fail("{} is not scheduled at all".format(func_name))

    def test_the_interval_is_the_configured_one(self):
        with patch("sqldesk.settings.SCHEMAS_REFRESH_SCHEDULE", 180):
            self.assertEqual(timedelta(minutes=180), self._interval_of("refresh_schemas"))

        with patch("sqldesk.settings.SCHEMAS_REFRESH_SCHEDULE", 15):
            self.assertEqual(timedelta(minutes=15), self._interval_of("refresh_schemas"))

    def test_the_default_is_not_a_few_minutes(self):
        # The number itself is somebody's to tune; what is pinned is that the
        # shipped default is not the half-hourly one it used to be, which on an
        # install with a few large sources meant the schemas queue was rarely
        # idle. An hour is the floor, not a recommendation.
        self.assertGreaterEqual(settings.SCHEMAS_REFRESH_SCHEDULE, 60)

    def test_schemas_are_not_read_as_often_as_queries_are_run(self):
        # The pairing is the point: refresh_queries has to be frequent because
        # it decides what runs, and this does not.
        schemas = self._interval_of("refresh_schemas")
        queries = self._interval_of("refresh_queries")
        as_seconds = queries if isinstance(queries, int) else queries.total_seconds()

        self.assertGreater(schemas.total_seconds(), as_seconds)


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


class TestTheSchedulerSaysItIsAlive(TestCase):
    """
    Something outside the process has to be able to tell a scheduler that is
    looping from one that is merely running, because Kubernetes cannot: the
    process stays up either way and no scheduled query runs.
    """

    def setUp(self):
        rq_redis_connection.delete(HEARTBEAT_KEY)

    def tearDown(self):
        rq_redis_connection.delete(HEARTBEAT_KEY)

    def test_a_pass_round_the_loop_records_a_heartbeat(self):
        rq_scheduler.heartbeat()

        self.assertTrue(rq_redis_connection.exists(HEARTBEAT_KEY))
        ttl = rq_redis_connection.ttl(HEARTBEAT_KEY)
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, HEARTBEAT_TTL)

    def test_a_heartbeat_that_has_already_expired_comes_back(self):
        # The whole reason this is not rq-scheduler's own heartbeat, which is
        # an EXPIRE: EXPIRE on a key that has gone does nothing, so one slow
        # pass would lose the signal for the life of the process while the
        # scheduler carried on working.
        rq_scheduler.heartbeat()
        rq_redis_connection.delete(HEARTBEAT_KEY)

        rq_scheduler.heartbeat()

        self.assertTrue(rq_redis_connection.exists(HEARTBEAT_KEY))

    def test_it_stops_being_true_once_the_scheduler_stops(self):
        rq_scheduler.heartbeat()
        # What Redis does for us after HEARTBEAT_TTL with nobody writing it.
        rq_redis_connection.delete(HEARTBEAT_KEY)

        self.assertFalse(rq_redis_connection.exists(HEARTBEAT_KEY))

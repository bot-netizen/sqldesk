import hashlib
import json
import logging
import time
from datetime import datetime, timedelta

from rq.job import Job
from rq_scheduler import Scheduler

from sqldesk import rq_redis_connection, settings
from sqldesk.live import refresh_live_dashboards
from sqldesk.tasks.catalog import harvest_catalogs
from sqldesk.tasks.failure_report import send_aggregated_errors
from sqldesk.tasks.general import sync_user_details, version_check
from sqldesk.tasks.queries import (
    cleanup_query_results,
    empty_schedules,
    refresh_queries,
    refresh_schemas,
    remove_ghost_locks,
)
from sqldesk.tasks.worker import Queue

logger = logging.getLogger(__name__)


class StatsdRecordingScheduler(Scheduler):
    """
    RQ Scheduler Mixin that uses SQLDesk's custom RQ Queue class to increment/modify metrics via Statsd.

    It also keeps the periodic jobs on the schedule. rq-scheduler drops a
    scheduled job for good when it finds the job's record in Redis gone, and
    the jobs were only ever scheduled when this process started -- so one lost
    record stopped that job until somebody restarted the scheduler.
    """

    queue_class = Queue

    # Seconds between checks that every periodic job is still scheduled. The
    # check is a handful of ZSCOREs; recovery waits at most this long.
    periodic_check_interval = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._periodic_checked_at = None

    def enqueue_jobs(self):
        # After enqueueing, so a job dropped by this very pass is put back now.
        jobs = super().enqueue_jobs()
        now = time.monotonic()
        if self._periodic_checked_at is None or now - self._periodic_checked_at >= self.periodic_check_interval:
            self._periodic_checked_at = now
            try:
                reschedule_missing_periodic_jobs()
            except Exception:  # never let the check stop the scheduler itself
                logger.exception("Could not check the periodic jobs are scheduled.")
        return jobs


rq_scheduler = StatsdRecordingScheduler(connection=rq_redis_connection, queue_name="periodic", interval=5)


def job_id(kwargs):
    metadata = kwargs.copy()
    metadata["func"] = metadata["func"].__name__

    return hashlib.sha1(json.dumps(metadata, sort_keys=True).encode()).hexdigest()


def prep(kwargs):
    interval = kwargs["interval"]
    if isinstance(interval, timedelta):
        interval = int(interval.total_seconds())

    kwargs["interval"] = interval
    # A periodic job reuses one record for every run, and rq-scheduler drops the
    # job for good if that record is ever missing. With a result TTL, Redis
    # deleted it whenever the next run came later than the TTL -- which is what
    # happens when a laptop sleeps or Docker's VM is paused: live dashboards,
    # with a 60-second TTL, stopped after the first nap. -1 keeps it.
    kwargs["result_ttl"] = -1

    return kwargs


def schedule(kwargs):
    rq_scheduler.schedule(scheduled_time=datetime.utcnow(), id=job_id(kwargs), **kwargs)


def periodic_job_definitions():
    jobs = [
        {"func": refresh_queries, "timeout": 600, "interval": 30},
        # Live dashboards: every 10 seconds, so a 30-second dashboard is on time.
        # Does nothing for a dashboard nobody is watching.
        {"func": refresh_live_dashboards, "timeout": 60, "interval": 10},
        {"func": remove_ghost_locks, "interval": timedelta(minutes=1)},
        {"func": empty_schedules, "interval": timedelta(minutes=60)},
        {
            "func": refresh_schemas,
            "interval": timedelta(minutes=settings.SCHEMAS_REFRESH_SCHEDULE),
        },
        {"func": sync_user_details, "timeout": 60, "interval": timedelta(minutes=1)},
        {
            "func": send_aggregated_errors,
            "interval": timedelta(minutes=settings.SEND_FAILURE_EMAIL_INTERVAL),
        },
    ]

    # The catalog the MCP context tools read. Off unless the feature is on,
    # and off entirely at 0 for anyone who would rather run it themselves.
    if settings.FEATURE_AI and settings.CATALOG_HARVEST_SCHEDULE > 0:
        jobs.append(
            {
                "func": harvest_catalogs,
                "interval": timedelta(hours=settings.CATALOG_HARVEST_SCHEDULE),
            }
        )

    if settings.VERSION_CHECK:
        jobs.append({"func": version_check, "interval": timedelta(days=1)})

    if settings.QUERY_RESULTS_CLEANUP_ENABLED:
        jobs.append({"func": cleanup_query_results, "interval": timedelta(minutes=5)})

    # Add your own custom periodic jobs in your dynamic_settings module.
    jobs.extend(settings.dynamic_settings.periodic_jobs() or [])

    return jobs


def schedule_periodic_jobs(jobs):
    job_definitions = [prep(job) for job in jobs]

    jobs_to_clean_up = Job.fetch_many(
        set([job.id for job in rq_scheduler.get_jobs()]) - set([job_id(job) for job in job_definitions]),
        rq_redis_connection,
    )

    jobs_to_schedule = [job for job in job_definitions if job_id(job) not in rq_scheduler]

    for job in jobs_to_clean_up:
        logger.info("Removing %s (%s) from schedule.", job.id, job.func_name)
        rq_scheduler.cancel(job)
        job.delete()

    for job in jobs_to_schedule:
        logger.info(
            "Scheduling %s (%s) with interval %s.",
            job_id(job),
            job["func"].__name__,
            job.get("interval"),
        )
        schedule(job)


def reschedule_missing_periodic_jobs(jobs=None):
    """
    Schedule again any periodic job that has fallen off the schedule, and
    return the ones that had. Unlike schedule_periodic_jobs, removes nothing:
    it runs inside the scheduler's loop, where the definitions cannot have
    changed.
    """
    job_definitions = [prep(job) for job in (periodic_job_definitions() if jobs is None else jobs)]
    missing = [job for job in job_definitions if job_id(job) not in rq_scheduler]
    for job in missing:
        logger.warning(
            "Periodic job %s (%s) had fallen off the schedule; scheduling it again.",
            job_id(job),
            job["func"].__name__,
        )
        schedule(job)
    return missing

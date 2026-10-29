import signal
import threading
import time

import redis
from rq import get_current_job
from rq.exceptions import NoSuchJobError
from rq.job import JobStatus
from rq.timeouts import JobTimeoutException

from sqldesk import models, pools, redis_connection, settings, uploads
from sqldesk.query_runner import InterruptException
from sqldesk.tasks.alerts import check_alerts_for_query
from sqldesk.tasks.failure_report import track_failure
from sqldesk.tasks.worker import Job, Queue
from sqldesk.utils import gen_query_hash, utcnow
from sqldesk.worker import get_job_logger

logger = get_job_logger(__name__)
TIMEOUT_MESSAGE = "Query exceeded SQLDesk query execution time limit."


def _job_lock_id(query_hash, data_source_id):
    return "query_hash_job:%s:%s" % (data_source_id, query_hash)


#: Delete the lock only if it still names this job.
#:
#: `DELETE` on its own dropped whatever was there, so a finishing job released
#: the lock a *newer* job had already taken -- and the next request for that
#: query started a third run of it, against the data source, while the second
#: was still going. Two executions of the same query is what the lock exists
#: to prevent, and the race is likeliest exactly when it matters: the same
#: query asked for repeatedly, by a dashboard full of widgets.
_UNLOCK_IF_MINE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _unlock(query_hash, data_source_id, job_id=None):
    """Release the lock, unless another job has taken it since."""
    key = _job_lock_id(query_hash, data_source_id)
    if job_id is None:
        # Nothing to compare against: the old behaviour, for a caller that
        # does not know which job it is.
        redis_connection.delete(key)
        return
    try:
        redis_connection.eval(_UNLOCK_IF_MINE, 1, key, job_id)
    except redis.ResponseError:
        # A Redis with scripting turned off. Dropping the lock is worse than
        # leaving it: a stale lock is cleared by enqueue_query, which checks
        # whether the job it names is still alive.
        logger.warning("Could not release the lock for %s with a script.", query_hash, exc_info=True)


def enqueue_query(query, data_source, user_id, is_api_key=False, scheduled_query=None, metadata={}, queue_name=None):
    query_hash = gen_query_hash(query)
    logger.info("Inserting job for %s with metadata=%s", query_hash, metadata)
    try_count = 0
    job = None

    while try_count < 5:
        try_count += 1

        pipe = redis_connection.pipeline()
        try:
            pipe.watch(_job_lock_id(query_hash, data_source.id))
            job_id = pipe.get(_job_lock_id(query_hash, data_source.id))
            if job_id:
                logger.info("[%s] Found existing job: %s", query_hash, job_id)
                job_complete = None
                job_cancelled = None

                try:
                    job = Job.fetch(job_id)
                    job_exists = True
                    status = job.get_status()
                    job_complete = status in [JobStatus.FINISHED, JobStatus.FAILED]
                    job_cancelled = job.is_cancelled

                    if job_complete:
                        message = "job found is complete (%s)" % status
                    elif job_cancelled:
                        message = "job found has been cancelled"
                except NoSuchJobError:
                    message = "job found has expired"
                    job_exists = False

                lock_is_irrelevant = job_complete or job_cancelled or not job_exists

                if lock_is_irrelevant:
                    logger.info("[%s] %s, removing lock", query_hash, message)
                    redis_connection.delete(_job_lock_id(query_hash, data_source.id))
                    job = None

            if not job:
                pipe.multi()

                # A caller may name the queue itself -- live dashboards run on
                # the scheduled queue without being scheduled queries, which
                # would otherwise mean failure emails to the query's owner and
                # a growing backoff on its own schedule.
                if scheduled_query:
                    queue_name = queue_name or data_source.scheduled_queue_name
                    scheduled_query_id = scheduled_query.id
                else:
                    queue_name = queue_name or data_source.queue_name
                    scheduled_query_id = None

                time_limit = settings.dynamic_settings.query_time_limit(scheduled_query, user_id, data_source.org_id)
                metadata["Queue"] = queue_name

                queue = Queue(queue_name)
                enqueue_kwargs = {
                    "user_id": user_id,
                    "scheduled_query_id": scheduled_query_id,
                    "is_api_key": is_api_key,
                    "job_timeout": time_limit,
                    "failure_ttl": settings.JOB_DEFAULT_FAILURE_TTL,
                    "meta": {
                        "data_source_id": data_source.id,
                        "org_id": data_source.org_id,
                        "scheduled": scheduled_query_id is not None,
                        "query_id": metadata.get("query_id"),
                        "user_id": user_id,
                        # Where the run came from. The admin's list of running
                        # queries is built from this meta, so without it a
                        # query a model asked for looks exactly like one a
                        # person ran, and "who is causing this" has no answer.
                        "mcp": bool(metadata.get("mcp")),
                    },
                }

                if not scheduled_query:
                    enqueue_kwargs["result_ttl"] = settings.JOB_RESULT_TTL

                job = queue.enqueue(execute_query, query, data_source.id, metadata, **enqueue_kwargs)

                logger.info("[%s] Created new job: %s", query_hash, job.id)
                pipe.set(
                    _job_lock_id(query_hash, data_source.id),
                    job.id,
                    settings.JOB_EXPIRY_TIME,
                )
                pipe.execute()
            break

        except redis.WatchError:
            continue
        finally:
            pipe.reset()

    if not job:
        logger.error("[Manager][%s] Failed adding job for query.", query_hash)

    return job


def signal_handler(*args):
    raise InterruptException


class QueryExecutionError(Exception):
    pass


def _resolve_user(user_id, is_api_key, query_id):
    if user_id is not None:
        if is_api_key:
            api_key = user_id
            if query_id is not None:
                q = models.Query.get_by_id(query_id)
            else:
                q = models.Query.by_api_key(api_key)

            return models.ApiUser(api_key, q.org, q.groups)
        else:
            return models.User.get_by_id(user_id)
    else:
        return None


def _shape_of(data):
    """
    How big the result is, for the log line, in rows and columns.

    This used to be the result's size in bytes, measured by walking every
    object in it and keeping the id of each one in a set: on a 200,000-row
    result that was 1.9 seconds of a 2.3-second write, spent entirely on one
    line of logging. Rows and columns answer the question people actually
    bring to that line -- "was this a big result" -- and cost two lookups.
    """
    if not isinstance(data, dict):
        return "unknown"
    rows = data.get("rows")
    columns = data.get("columns")
    try:
        return "{} rows x {} columns".format(len(rows), len(columns))
    except TypeError:
        return "unknown"


class QueryExecutor:
    def __init__(self, query, data_source_id, user_id, is_api_key, metadata, is_scheduled_query):
        self.job = get_current_job()
        self.query = query
        self.data_source_id = data_source_id
        self.metadata = metadata
        self.data_source = self._load_data_source()
        self.query_id = metadata.get("query_id")
        self.user = _resolve_user(user_id, is_api_key, metadata.get("query_id"))
        self.query_model = (
            models.Query.query.get(self.query_id)
            if self.query_id and self.query_id != "adhoc"
            else None
        )  # fmt: skip

        # Close DB connection to prevent holding a connection for a long time while the query is executing.
        models.db.session.close()
        self.query_hash = gen_query_hash(self.query)
        # Resolved once: `run` releases in a finally that must not depend on
        # the data source still being loadable by then.
        self.pool = pools.pool_for(self.data_source)
        self.is_scheduled_query = is_scheduled_query
        if self.is_scheduled_query:
            # Load existing tracker or create a new one if the job was created before code update:
            models.scheduled_queries_executions.update(self.query_model.id)

    def run(self):
        signal.signal(signal.SIGINT, signal_handler)
        started_at = time.time()

        logger.debug("Executing query:\n%s", self.query)
        self._log_progress("executing_query")

        query_runner = self.data_source.query_runner
        annotated_query = self._annotate_query(query_runner)

        # Which uploaded files this query reads. Recorded here rather than in
        # the runner because the runner has no session to write with, and
        # before the query rather than after so a query that times out still
        # counts as somebody needing the file. Never fatal: a file whose "last
        # queried" is a minute stale is not worth failing a query over.
        try:
            uploads.note_queried(self.data_source, self.query)
        except Exception:
            logger.warning("could not record which uploads this query reads", exc_info=True)

        # Room on the pool this data source draws from, before any work is
        # sent to it. Here rather than at enqueue because a job waiting in a
        # queue must not hold a slot -- the ceiling is on what the resource is
        # *doing*, not on what is addressed to it.
        refusal = self._take_a_slot()
        if refusal:
            return self._refuse(refusal)

        # A slot expires on its own so that a killed worker frees it. That
        # means a query running longer than the TTL would drop the slot it is
        # still using, and the pool would admit somebody on top of it -- so
        # the slot is renewed from a thread for as long as the query runs.
        keep_slot = self._renew_in_background()
        try:
            data, error = query_runner.run_query(annotated_query, self.user)
        except Exception as e:
            if isinstance(e, JobTimeoutException):
                error = TIMEOUT_MESSAGE
            else:
                error = str(e)

            data = None
            logger.warning("Unexpected error while running query:", exc_info=1)

        finally:
            keep_slot.set()

        run_time = time.time() - started_at

        logger.info(
            "job=execute_query query_hash=%s ds_id=%d data=%s error=[%s]",
            self.query_hash,
            self.data_source_id,
            data and _shape_of(data),
            error,
        )

        try:
            if error is not None and data is None:
                result = QueryExecutionError(error)
                if self.is_scheduled_query:
                    self.query_model = models.db.session.merge(self.query_model, load=False)
                    track_failure(self.query_model, error)
                raise result
            else:
                if self.query_model and self.query_model.schedule_failures > 0:
                    self.query_model = models.db.session.merge(self.query_model, load=False)
                    self.query_model.schedule_failures = 0
                    self.query_model.skip_updated_at = True
                    models.db.session.add(self.query_model)

                query_result = models.QueryResult.store_result(
                    self.data_source.org_id,
                    self.data_source,
                    self.query_hash,
                    self.query,
                    data,
                    run_time,
                    utcnow(),
                )

                updated_query_ids = models.Query.update_latest_result(query_result)

                models.db.session.commit()  # make sure that alert sees the latest query result
                self._log_progress("checking_alerts")
                for query_id in updated_query_ids:
                    check_alerts_for_query.delay(query_id, self.metadata)
                self._log_progress("finished")

                result = query_result.id
                models.db.session.commit()
                return result
        finally:
            # Released only once the result row is committed, not as soon as the
            # data comes back. The lock is what makes a second request for the
            # same query join the job already running instead of starting its
            # own -- and between the query returning and the row being written
            # there was nothing for that second request to find. Widgets ask
            # with max_age 0, so there is no stored result to fall back on
            # either, and the sibling ran the whole query again.
            #
            # Safe on the failure path too: a lock left behind by a job that
            # died is cleared by enqueue_query, which drops any lock whose job
            # has finished, failed or expired.
            #
            # And only if the lock is still this job's: a plain delete here
            # released a lock a newer job had taken, so the next request for
            # the same query started a third run of it while the second was
            # still going.
            _unlock(self.query_hash, self.data_source.id, self.job.id if self.job else None)
            # The pool entry would expire on its own; giving it back now means
            # the next query in the queue starts immediately rather than when
            # a timer says so.
            pools.release(self.pool, self._slot_holder())

    def _slot_holder(self):
        """
        What occupies the slot.

        The job id, so a retried job that is still counted re-acquires its own
        entry instead of taking a second one -- and so an entry left behind by
        a process that died can be read back to something.
        """
        return self.job.id if self.job else "adhoc:{}".format(self.query_hash)

    def _take_a_slot(self):
        """
        Wait briefly for room on the pool, then give up and say so.

        A worker blocked on a semaphore is a worker doing nothing, so the wait
        is deliberately short. Contention means the resource is busy, and
        telling somebody that in a few seconds beats holding a process for a
        minute to discover it.

        Returns None once there is room, or the sentence to show.
        """
        limit = pools.budget(self.pool, self.data_source)
        if limit == pools.NO_LIMIT:
            return None

        deadline = time.time() + settings.QUERY_SLOT_WAIT_SECONDS
        refusal = None
        while True:
            refusal = pools.acquire(
                self.pool,
                self._slot_holder(),
                weight=1,
                owner=str(self.metadata.get("Username") or ""),
                limit=limit,
            )
            if refusal is None:
                return None
            if time.time() >= deadline:
                return refusal
            time.sleep(0.25)

    def _renew_in_background(self):
        """
        Hold this query's slot for as long as the query runs.

        Returns the event that stops it. A daemon thread because it must never
        be the reason a worker will not exit: if the process is going down the
        slot expiring on its own is exactly the right outcome.
        """
        stop = threading.Event()
        if pools.budget(self.pool, self.data_source) == pools.NO_LIMIT:
            stop.set()
            return stop

        # A third of the lifetime, so two renewals have to be missed before a
        # slot is lost.
        every = max(1, settings.QUERY_SLOT_TTL_SECONDS // 3)
        pool, holder = self.pool, self._slot_holder()

        def renew():
            while not stop.wait(every):
                try:
                    pools.renew(pool, holder)
                except Exception:
                    logger.warning("could not renew the slot for %s", holder, exc_info=True)

        threading.Thread(target=renew, name="pool-renew", daemon=True).start()
        return stop

    def _refuse(self, message):
        """
        Turn a full pool into the same shape as any other query failure.

        A refusal is not an exception in the code's sense -- nothing went
        wrong -- but it has to reach the person who asked, and the only route
        from here to a screen is the error a failed query carries.
        """
        logger.info(
            "job=execute_query state=refused pool=%s query_hash=%s ds_id=%d",
            self.pool,
            self.query_hash,
            self.data_source_id,
        )
        self._log_progress("refused")
        if self.is_scheduled_query:
            # The next tick will try again; what matters is that the failure
            # is recorded as the queue being full rather than the query being
            # broken.
            self.query_model = models.db.session.merge(self.query_model, load=False)
            track_failure(self.query_model, message)
            models.db.session.commit()
        raise QueryExecutionError(message)

    def _annotate_query(self, query_runner):
        self.metadata["Job ID"] = self.job.id
        self.metadata["Query Hash"] = self.query_hash
        self.metadata["Scheduled"] = self.is_scheduled_query

        return query_runner.annotate_query(self.query, self.metadata)

    def _log_progress(self, state):
        logger.info(
            "job=execute_query state=%s query_hash=%s type=%s ds_id=%d "
            "job_id=%s queue=%s query_id=%s username=%s",  # fmt: skip
            state,
            self.query_hash,
            self.data_source.type,
            self.data_source.id,
            self.job.id,
            self.metadata.get("Queue", "unknown"),
            self.metadata.get("query_id", "unknown"),
            self.metadata.get("Username", "unknown"),
        )

    def _load_data_source(self):
        logger.info("job=execute_query state=load_ds ds_id=%d", self.data_source_id)
        return models.DataSource.query.get(self.data_source_id)


# user_id is added last as a keyword argument for backward compatability -- to support executing previously submitted
# jobs before the upgrade to this version.
def execute_query(
    query,
    data_source_id,
    metadata,
    user_id=None,
    scheduled_query_id=None,
    is_api_key=False,
):
    try:
        return QueryExecutor(
            query,
            data_source_id,
            user_id,
            is_api_key,
            metadata,
            scheduled_query_id is not None,
        ).run()
    except QueryExecutionError as e:
        models.db.session.rollback()
        return e

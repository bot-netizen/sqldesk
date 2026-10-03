"""
The jobs that run streams: one consumer per active stream, and the rollup.

A consumer is not like any other job here. Every other task has an end -- run
this query, send this email, harvest this catalog -- and a consumer runs until
nobody is watching. So it is given a deadline, it checks on every flush whether
it should still be running, and when its deadline arrives it **hands over to a
successor it enqueues itself**. The supervisor only starts streams that have no
consumer at all.

The hand-over is not decoration. With the supervisor as the only starter, a
five-minute job on a one-minute tick leaves up to a minute of the topic
unconsumed after every job -- on a window measured in minutes, a visible hole in
the chart.

A job that ends every few minutes and immediately replaces itself is still much
simpler than a daemon: it recovers from a broker that went away, a worker that
was restarted and a topic that was deleted without any of that being written
out. What it costs is one line of hand-over and a lock.
"""

import datetime
import logging
import os

from sqldesk import models, redis_connection, settings
from sqldesk.streams import activity, rollup, slots, watching
from sqldesk.streams.consumer import Broker, consume
from sqldesk.streams.consumer import _security as security
from sqldesk.streams.store import RECEIVED, Store
from sqldesk.utils import utcnow
from sqldesk.worker import job

logger = logging.getLogger(__name__)

#: How long one consumer job holds a worker before handing over. Not a limit on
#: how long a stream is consumed -- the successor starts at once -- but on how
#: long a single job can be stuck before RQ reclaims it, and how often the
#: queue gets a look in.
CONSUMER_MINUTES = 5

#: A stream is consumed by one worker at a time. Longer than the job itself, so
#: a crashed worker's stream is not picked up while its consumer group
#: membership is still timing out at the broker -- and short enough that a
#: crashed worker's stream is picked up at all. A clean hand-over releases it
#: explicitly and does not wait for this.
LOCK_SECONDS = CONSUMER_MINUTES * 60 + 60


def _lock_key(stream_id):
    return "stream:consuming:{}".format(stream_id)


@job("periodic", timeout=60)
def supervise_streams():
    """
    Start a consumer for every active stream that has none.

    Once a minute, and it is the *starter* rather than the keeper: a running
    consumer re-enqueues itself when its own time is up, so the supervisor's
    job is only to pick up streams that have no consumer at all -- one somebody
    has just looked at, or one whose worker died.

    Nothing here stops a consumer. A consumer stops itself when its stream goes
    quiet, which it notices on its own flush; a supervisor that killed jobs
    would have to decide what a half-written flush means.
    """
    if not settings.STREAM_ACTIVE_MINUTES:
        return 0

    started = 0
    for stream in activity.active_streams():
        if _being_consumed(stream.id):
            continue
        if watching.state(stream) != watching.RUNNING:
            # Seen recently but nobody watching now: paused, and a paused
            # stream keeps its window and starts nothing.
            continue
        refused = slots.acquire(stream.id, owner=stream.started_by_id)
        if refused:
            # Said on the stream so the page can explain it. A person looking
            # at an empty chart deserves "all the slots are in use" rather than
            # silence.
            if stream.last_error != refused:
                stream.last_error = refused
                models.db.session.commit()
            continue
        if stream.last_error and "slot" in stream.last_error:
            stream.last_error = None
            models.db.session.commit()
        consume_stream.delay(stream.id)
        started += 1
    if started:
        logger.info("task=supervise_streams started=%s", started)
    return started


def _being_consumed(stream_id):
    """
    Whether a consumer already holds this stream.

    A cheap read, not the claim: the claim is atomic and happens inside the job,
    because the job is also what re-enqueues itself and nothing outside it knows
    when that happens. This only stops the supervisor queueing a second job a
    second one would refuse anyway.
    """
    try:
        return bool(redis_connection.exists(_lock_key(stream_id)))
    except Exception:
        # Say yes, so nothing is queued. A stream that is not consumed is an
        # empty chart somebody notices; a flood of jobs that all refuse is a
        # queue nobody can read.
        logger.warning("could not ask whether stream %s is consumed", stream_id, exc_info=True)
        return True


def _claim(stream_id):
    """
    Whether this process may consume this stream.

    Redis `SET NX`, which is the whole of it: two consumers on one stream would
    both write to the same DuckDB file and both count the same events, and the
    window would be wrong in a way nobody could see.
    """
    try:
        return bool(redis_connection.set(_lock_key(stream_id), "1", ex=LOCK_SECONDS, nx=True))
    except Exception:
        # Without Redis there is no safe answer, so the safe answer is no: a
        # stream that is not consumed is an empty chart, and two consumers on
        # one file is a corrupted window.
        logger.warning("could not claim stream %s", stream_id, exc_info=True)
        return False


@job("streams", timeout=CONSUMER_MINUTES * 60 + 30)
def consume_stream(stream_id):
    """
    Consume one stream until it goes quiet or the job's time is up.

    Its own queue, because this holds a worker for minutes at a time and would
    otherwise sit in front of the queries people are waiting for.
    """
    stream = models.Stream.query.get(stream_id)
    if stream is None:
        return
    if not _claim(stream_id):
        # Another worker has it. Claimed here rather than by the supervisor
        # because this job also re-enqueues itself, and nothing outside it
        # knows when that happens.
        return

    deadline = utcnow().timestamp() + CONSUMER_MINUTES * 60
    carry_on = False

    def should_continue():
        # Re-read rather than trusting the row we loaded: whether anybody is
        # watching changes while this runs, which is the entire point.
        models.db.session.refresh(stream)
        if utcnow().timestamp() >= deadline:
            return False
        if watching.state(stream) != watching.RUNNING:
            return False
        # Renewed here rather than on a timer of its own: this is called on
        # every flush, which is exactly as often as the slot needs holding.
        slots.renew(stream.id)
        return True

    if not should_continue():
        _release(stream_id)
        return

    broker = Broker(
        brokers=stream.data_source.options.get("brokers"),
        topic=stream.topic,
        group="sqldesk-stream-{}".format(stream.id),
        options=security(stream.data_source.options),
    )
    try:
        stream.last_error = None
        models.db.session.commit()
        consume(stream, broker, should_continue)
    except Exception as error:
        # Kept where the stream's page can read it. A consumer that stopped with
        # an error and a consumer that stopped because nobody is watching look
        # identical on a chart, and only one of them is a problem.
        logger.exception("task=consume_stream state=error stream=%s", stream_id)
        stream.last_error = "The consumer stopped: {}".format(error)
        models.db.session.commit()
    else:
        # Its own time is up rather than its stream going quiet, so hand over to
        # a successor at once. Waiting for the supervisor's next minute would
        # leave up to a minute of the topic unconsumed after every job, which on
        # a window measured in minutes is a visible hole in the chart.
        carry_on = watching.state(stream) == watching.RUNNING
    finally:
        _release(stream_id)
        if carry_on:
            consume_stream.delay(stream_id)
        else:
            # Nothing is going to renew it, and leaving it to expire would hold
            # a slot for two minutes after the stream stopped.
            slots.release(stream_id)


def _release(stream_id):
    try:
        redis_connection.delete(_lock_key(stream_id))
    except Exception:
        # It expires on its own; the only cost is a minute's delay before the
        # stream is picked up again.
        logger.warning("could not release stream %s", stream_id, exc_info=True)


@job("periodic", timeout=300)
def roll_up_streams():
    """
    Turn the last minute of every stream into buckets, and drop old ones.

    Once a minute, over rows that had to be stored anyway: the aggregation was
    measured at seven milliseconds over 200,000 rows, so this is not where the
    time goes. What it buys is a question about this morning having an answer
    after the raw window has moved on.
    """
    rolled = 0
    for stream in models.Stream.query.filter(models.Stream.measures.isnot(None)):
        try:
            rolled += _roll_up_one(stream)
        except Exception:
            # One stream's rollup failing is not worth the others'.
            logger.exception("task=roll_up_streams state=error stream=%s", stream.id)
    removed = _drop_old_rollups()
    if rolled or removed:
        logger.info("task=roll_up_streams rolled=%s removed=%s", rolled, removed)
    return rolled


def _roll_up_one(stream):
    group_by = list(stream.group_by or [])
    measures = list(stream.measures or [])
    if not measures:
        return 0

    # A reader too: the rollup aggregates what the consumer has written and
    # writes its buckets to Postgres, so taking the window's write lock would
    # only stall the consumer that fills it.
    store = Store(stream.store_path(), read_only=True)
    try:
        problem = rollup.check(group_by, measures, store.columns())
        if problem:
            # Said on the page rather than only in a log: the person who can
            # fix a rollup definition is the person looking at the stream.
            stream.last_error = problem
            models.db.session.commit()
            return 0

        # Every finished minute the window still holds that has no buckets
        # yet -- not simply "the last minute".
        #
        # This used to roll up `now() - 1 minute` and nothing else, which meant
        # a run that arrived late lost that minute for good: by the time it
        # ran, the minute it would have read was two minutes back and nothing
        # ever went looking for it again. The task is scheduled once a minute,
        # so one busy worker was enough to leave a hole in the history. It was
        # also why the test for this was intermittent -- the clock crossing a
        # boundary mid-test is the same event as a late run.
        #
        # The minute in progress is still skipped: a bucket written while its
        # minute is filling is wrong until it is rewritten, and nothing
        # rewrites it.
        wanted = _minutes_to_roll(store, stream)
        rows = []
        described = []
        for minute in wanted:
            sql = rollup.minute_sql(
                group_by,
                measures,
                RECEIVED,
                _literal(minute),
                _literal(minute + MINUTE),
            )
            described = [row[0] for row in store.connection.execute("DESCRIBE {}".format(sql)).fetchall()]
            rows.extend(store.connection.execute(sql).fetchall())
    finally:
        store.close()

    written = 0
    for row in rows:
        values = dict(zip(described, row))
        minute = values.pop("minute")
        is_other = bool(values.pop("is_other", False))
        if minute >= _this_minute():
            # The minute in progress; see above.
            continue
        key = {column: values.pop(column, None) for column in group_by}
        existing = models.StreamRollup.query.filter(
            models.StreamRollup.stream_id == stream.id,
            models.StreamRollup.minute == minute,
            models.StreamRollup.group_key == key,
        ).first()
        if existing is None:
            existing = models.StreamRollup(stream_id=stream.id, minute=minute, group_key=key)
            models.db.session.add(existing)
            written += 1
        existing.is_other = is_other
        existing.values = {name: _plain(value) for name, value in values.items()}
        existing.sample_rate = stream.sample_rate or 1
    models.db.session.commit()
    return written


#: How far back a late run will catch up. The window can hold a long stretch of
#: a quiet topic, and re-reading all of it every minute would be work nobody
#: asked for; a quarter of an hour covers a worker that was busy without
#: turning this into a sweep.
CATCHUP_MINUTES = 15

MINUTE = datetime.timedelta(minutes=1)


def _literal(moment):
    """
    A moment as DuckDB will read it back.

    Rendered from a value DuckDB itself returned, so the round trip is
    self-consistent -- `_received_at` is created from `now()` and is therefore
    timestamptz, and the bounds have to be the same.
    """
    return "TIMESTAMPTZ '{}'".format(moment.isoformat())


def _minutes_to_roll(store, stream):
    """
    The finished minutes this stream has events for and no buckets for.

    Asked of the store rather than worked out from the clock: what is missing
    is a fact about the two stores, not about what time it is now.
    """
    found = store.connection.execute(
        "SELECT DISTINCT date_trunc('minute', {received}) AS minute FROM events "
        "WHERE {received} < date_trunc('minute', now()) "
        "ORDER BY 1 DESC LIMIT {limit}".format(received=RECEIVED, limit=CATCHUP_MINUTES)
    ).fetchall()
    minutes = sorted(row[0] for row in found)
    if not minutes:
        return []

    already = {
        row[0]
        for row in models.db.session.query(models.StreamRollup.minute)
        .filter(
            models.StreamRollup.stream_id == stream.id,
            models.StreamRollup.minute >= minutes[0],
        )
        .distinct()
    }
    return [minute for minute in minutes if minute not in already]


def _this_minute():
    now = utcnow()
    return now.replace(second=0, microsecond=0)


def _plain(value):
    """A number JSONB can hold. DuckDB hands back decimals for some aggregates."""
    if value is None:
        return None
    try:
        return int(value) if float(value).is_integer() else float(value)
    except (TypeError, ValueError):
        return str(value)


def _drop_old_rollups():
    if settings.STREAM_ROLLUP_HOURS <= 0:
        return 0
    cutoff = utcnow() - datetime.timedelta(hours=settings.STREAM_ROLLUP_HOURS)
    removed = models.StreamRollup.query.filter(models.StreamRollup.minute < cutoff).delete()
    if removed:
        models.db.session.commit()
    return removed


@job("periodic", timeout=120)
def drop_cold_windows():
    """
    Delete the window of every stream that has gone cold.

    A paused stream keeps its window so that coming back resumes in seconds. A
    cold one -- nobody for ten minutes -- does not: the disk is worth more than
    a window of events nobody is going to look at, and starting again is a
    deliberate act anyway, which is what the button says.

    Counted down to nothing on the row as well as removed from the disk, so the
    page does not go on reporting rows in a window that is not there.
    """
    dropped = 0
    for stream in models.Stream.query.filter(models.Stream.pinned.is_(False)):
        if watching.state(stream) != watching.COLD:
            continue
        path = stream.store_path()
        if not os.path.exists(path):
            continue
        if _being_consumed(stream.id):
            # Between the state going cold and the consumer noticing. It will
            # be cold again on the next tick.
            continue
        try:
            os.remove(path)
        except OSError:
            logger.warning("could not drop the window for stream %s", stream.id, exc_info=True)
            continue
        stream.rows = 0
        stream.malformed = 0
        stream.observed_rate = 0
        models.db.session.commit()
        dropped += 1
    if dropped:
        logger.info("task=drop_cold_windows dropped=%s", dropped)
    return dropped

from datetime import datetime, timedelta, timezone

from funcy import flatten
from rq import Queue, Worker
from rq.job import Job
from rq.registry import StartedJobRegistry
from sqlalchemy import desc, func

from sqldesk import __version__, redis_connection, rq_redis_connection, settings
from sqldesk.models import (
    Dashboard,
    DataSource,
    Event,
    Query,
    QueryResult,
    User,
    Widget,
    db,
)


def get_redis_status():
    info = redis_connection.info()
    return {
        "redis_used_memory": info["used_memory"],
        "redis_used_memory_human": info["used_memory_human"],
    }


def get_object_counts():
    status = {}
    status["queries_count"] = Query.query.count()
    if settings.FEATURE_SHOW_QUERY_RESULTS_COUNT:
        status["query_results_count"] = QueryResult.query.count()
        status["unused_query_results_count"] = QueryResult.unused(settings.QUERY_RESULTS_CLEANUP_MAX_AGE).count()
    status["dashboards_count"] = Dashboard.query.count()
    status["widgets_count"] = Widget.query.count()
    return status


def get_queues_status():
    return {queue.name: {"size": len(queue)} for queue in Queue.all(connection=rq_redis_connection)}


def get_db_sizes():
    database_metrics = []
    queries = [
        [
            "Query Results Size",
            "select pg_total_relation_size('query_results') as size from (select 1) as a",
        ],
        ["SQLDesk DB Size", "select pg_database_size(current_database()) as size"],
    ]
    for query_name, query in queries:
        result = db.session.execute(query).first()
        database_metrics.append([query_name, result[0]])

    return database_metrics


def get_status():
    status = {"version": __version__, "workers": []}
    status.update(get_redis_status())
    status.update(get_object_counts())
    status["manager"] = redis_connection.hgetall("sqldesk:status")
    status["manager"]["queues"] = get_queues_status()
    status["database_metrics"] = {}
    status["database_metrics"]["metrics"] = get_db_sizes()

    return status


def rq_job_ids():
    queues = Queue.all(connection=rq_redis_connection)

    started_jobs = [StartedJobRegistry(queue=q).get_job_ids() for q in queues]
    queued_jobs = [q.job_ids for q in queues]

    return flatten(started_jobs + queued_jobs)


def fetch_jobs(job_ids):
    return [
        {
            "id": job.id,
            "name": job.func_name,
            "origin": job.origin,
            "enqueued_at": job.enqueued_at,
            "started_at": job.started_at,
            "meta": job.meta,
        }
        for job in Job.fetch_many(job_ids, connection=rq_redis_connection)
        if job is not None
    ]


def rq_queues():
    return {
        q.name: {
            "name": q.name,
            "started": fetch_jobs(StartedJobRegistry(queue=q).get_job_ids()),
            "queued": len(q.job_ids),
        }
        # `connection=` matters: RQ_REDIS_URL can point somewhere other than
        # REDIS_URL, and without it this reads whatever connection rq happens
        # to have as its default -- which is the app's, where there are no
        # queues at all. `rq_job_ids` above has always passed it; these two did
        # not, so the RQ Status page went blank on exactly the split-Redis
        # setups that need watching most.
        for q in sorted(Queue.all(connection=rq_redis_connection), key=lambda q: q.name)
    }


def describe_job(job):
    return "{} ({})".format(job.id, job.func_name.split(".").pop()) if job else None


def rq_workers():
    return [
        {
            "name": w.name,
            "hostname": w.hostname,
            "pid": w.pid,
            "queues": ", ".join([q.name for q in w.queues]),
            "state": w.state,
            "last_heartbeat": w.last_heartbeat,
            "birth_date": w.birth_date,
            "current_job": describe_job(w.get_current_job()),
            "successful_jobs": w.successful_job_count,
            "failed_jobs": w.failed_job_count,
            "total_working_time": w.total_working_time,
        }
        for w in Worker.all(connection=rq_redis_connection)
    ]


def rq_status():
    return {"queues": rq_queues(), "workers": rq_workers()}


# ---------------------------------------------------------------- overview --
#
# What an admin wants to know while the thing is merely slow: what is running,
# who is asking for the most, and what are we about to run out of. Everything
# below is read at the moment it is asked for -- nothing is accumulated, so
# none of it can be a second source of truth that drifts.

EXECUTE_QUERY = "sqldesk.tasks.queries.execution.execute_query"

#: Above this fraction of a limit, say so.
PRESSURE_WARNING = 0.75


def started_job_ids():
    return flatten([StartedJobRegistry(queue=q).get_job_ids() for q in Queue.all(connection=rq_redis_connection)])


def _elapsed_seconds(started_at):
    """Seconds since an RQ timestamp, which is naive UTC."""
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())


def _names(model, ids):
    if not ids:
        return {}
    return dict(db.session.query(model.id, model.name).filter(model.id.in_(ids)).all())


def get_running_queries():
    """
    The queries executing right now, oldest first.

    From RQ rather than from `events`, and deliberately: a scheduled refresh
    never reaches `events` at all (it goes through `enqueue_query`, not
    `run_query`), and those are exactly the ones that run long unattended.
    `enqueue_query` stamps each job's meta with the query, user and data
    source, so the names cost three lookups however many jobs there are.
    """
    jobs = [job for job in fetch_jobs(started_job_ids()) if job.get("name") == EXECUTE_QUERY]

    metas = [job.get("meta") or {} for job in jobs]
    queries = _names(Query, {m.get("query_id") for m in metas if m.get("query_id")})
    users = _names(User, {m.get("user_id") for m in metas if m.get("user_id")})
    sources = _names(DataSource, {m.get("data_source_id") for m in metas if m.get("data_source_id")})

    running = []
    for job in jobs:
        meta = job.get("meta") or {}
        running.append(
            {
                "job_id": job["id"],
                "queue": job.get("origin"),
                "query_id": meta.get("query_id"),
                "query_name": queries.get(meta.get("query_id")),
                "user_id": meta.get("user_id"),
                # Scheduled refreshes have no user, which is worth showing as
                # what it is rather than as a blank.
                "user_name": users.get(meta.get("user_id")),
                "data_source": sources.get(meta.get("data_source_id")),
                "scheduled": bool(meta.get("scheduled")),
                "mcp": bool(meta.get("mcp")),
                "started_at": job.get("started_at"),
                "elapsed": _elapsed_seconds(job.get("started_at")),
            }
        )

    return sorted(running, key=lambda r: r["elapsed"] or 0, reverse=True)


def get_postgres_limits():
    row = db.session.execute(
        """
        select (select count(*) from pg_stat_activity) as used,
               (select count(*) from pg_stat_activity where datname = current_database()) as used_here,
               current_setting('max_connections')::int as max
        """
    ).first()
    return {"used": row[0], "used_here": row[1], "max": row[2]}


def _redis_limits(connection):
    memory = connection.info("memory")
    clients = connection.info("clients")
    # maxmemory is 0 when none is configured, which is not a limit of zero.
    maxmemory = memory.get("maxmemory") or None
    return {
        "used_memory": memory.get("used_memory"),
        "max_memory": maxmemory,
        "clients": clients.get("connected_clients"),
    }


def get_redis_limits():
    """
    Both connections, because they can be different servers.

    Reporting one number for "Redis" would be wrong on any split setup, and
    the RQ side is the one that fills up first.
    """
    return {"app": _redis_limits(redis_connection), "rq": _redis_limits(rq_redis_connection)}


def get_storage():
    rows = db.session.execute(
        """
        select pg_database_size(current_database()) as database,
               pg_total_relation_size('query_results') as query_results,
               pg_total_relation_size('events') as events
        """
    ).first()
    return {"database": rows[0], "query_results": rows[1], "events": rows[2]}


def get_activity(org_id, minutes=60):
    """
    Who has been asking, and how often, over the last `minutes`.

    Read from `events`, so this covers what people ran and not what the
    scheduler ran -- see `get_running_queries`. The two answer different
    questions and the page says so rather than adding them together.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    executions = Event.query.filter(
        Event.org_id == org_id,
        Event.action == "execute_query",
        Event.created_at >= since,
    )

    counted = func.count().label("executions")
    top_users = (
        db.session.query(User.id, User.name, counted)
        .select_from(Event)
        .join(User, User.id == Event.user_id)
        .filter(
            Event.org_id == org_id,
            Event.action == "execute_query",
            Event.created_at >= since,
        )
        .group_by(User.id, User.name)
        .order_by(desc(counted))
        .limit(10)
        .all()
    )

    minute = func.date_trunc("minute", Event.created_at).label("minute")
    per_minute = (
        db.session.query(minute, func.count())
        .filter(
            Event.org_id == org_id,
            Event.action == "execute_query",
            Event.created_at >= since,
        )
        .group_by(minute)
        .order_by(minute)
        .all()
    )

    total = executions.count()
    cached = executions.filter(Event.additional_properties["cache"].astext == "hit").count()

    return {
        "window_minutes": minutes,
        "executions": total,
        # None rather than 0 when nothing ran: a ratio of no executions is not
        # a cache that is missing everything.
        "cache_hit_ratio": (cached / total) if total else None,
        "top_users": [{"id": uid, "name": name, "executions": n} for uid, name, n in top_users],
        "per_minute": [[at.isoformat(), n] for at, n in per_minute],
    }


def get_overview(org_id):
    queues = rq_queues()
    workers = rq_workers()
    return {
        "running": get_running_queries(),
        "queues": {name: {"queued": q["queued"], "started": len(q["started"])} for name, q in queues.items()},
        "workers": {
            "total": len(workers),
            "busy": len([w for w in workers if w["state"] == "busy"]),
        },
        "limits": {"postgres": get_postgres_limits(), "redis": get_redis_limits()},
        "storage": get_storage(),
        "activity": get_activity(org_id),
    }

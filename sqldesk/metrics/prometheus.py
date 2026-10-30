"""
What SQLDesk is about to run out of, in the format a cluster already scrapes.

StatsD is what SQLDesk has emitted since the fork, and it is the wrong shape
for most deployments now: it pushes, which means something has to be listening,
and almost nothing in a Kubernetes cluster is. Prometheus pulls.

**Written by hand rather than with a client library, and that is a decision
rather than an omission.** Everything worth reporting here is a *gauge read at
the moment of the scrape* -- how deep a queue is, how many workers are busy,
how much of a pool is held, how many database connections are checked out. None
of it is accumulated in this process, so none of it needs the library's shared
registry. And the library's registry is precisely the part that does not work
here: under gunicorn each worker has its own, so a counter kept in one is
invisible to the scrape that lands on another, and the multiprocess mode that
fixes it needs a shared directory and a collector nobody would guess was
there. Reading the real numbers out of Redis and SQLAlchemy at scrape time
sidesteps all of it, and adds no dependency.

The exposition format itself is four lines of string formatting, and the
`TYPE`/`HELP` comments matter more than the machinery: a metric nobody can
interpret is a metric nobody acts on.
"""

import logging

from sqldesk import redis_connection, settings

logger = logging.getLogger(__name__)

#: Everything here is prefixed, so a dashboard built on it keeps working when
#: somebody scrapes two installs into the same Prometheus.
PREFIX = "sqldesk"


def enabled():
    """
    Off unless a token is set.

    Not merely about secrecy, though pool and queue names do carry a data
    source's name. An endpoint that exists but refuses is one more thing to
    explain in a port scan; one that is simply not mounted is not.
    """
    return bool(settings.METRICS_TOKEN)


def authorised(header):
    given = header or ""
    if not given.startswith("Bearer "):
        return False
    # `hmac.compare_digest` rather than `==`: the comparison is against a
    # secret, and the answer's timing should not describe how much of it was
    # right.
    import hmac

    return hmac.compare_digest(given[len("Bearer ") :], settings.METRICS_TOKEN)


def _escape(value):
    """A label value, as the exposition format wants it."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(labels):
    if not labels:
        return ""
    return "{" + ",".join('{}="{}"'.format(name, _escape(value)) for name, value in sorted(labels.items())) + "}"


class Metrics:
    """
    The exposition, grouped by metric family.

    Grouped rather than appended in call order, which is what a first draft
    does and what the format forbids: every sample of a family has to arrive
    together, under one TYPE. Collecting per queue naturally interleaves them
    -- depth, started, depth, started -- and a strict parser rejects the
    second group as a duplicate family.
    """

    def __init__(self):
        self._families = {}
        self._order = []

    def add(self, name, value, labels=None, kind="gauge", help_text=""):
        full = "{}_{}".format(PREFIX, name)
        if full not in self._families:
            self._families[full] = {"kind": kind, "help": help_text, "samples": []}
            self._order.append(full)
        family = self._families[full]
        # The first declaration wins its help text, so a later call adding
        # another series does not have to repeat it.
        if help_text and not family["help"]:
            family["help"] = help_text
        family["samples"].append("{}{} {}".format(full, _labels(labels), _number(value)))

    def render(self):
        lines = []
        for full in self._order:
            family = self._families[full]
            if family["help"]:
                lines.append("# HELP {} {}".format(full, family["help"]))
            lines.append("# TYPE {} {}".format(full, family["kind"]))
            lines.extend(family["samples"])
        return "\n".join(lines) + "\n"


def _number(value):
    """Prometheus wants a float; `1` and `1.0` both read, `True` does not."""
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return "0.0"


def collect():
    """
    Every number, read now.

    Each source is wrapped on its own: Redis being unreachable should cost the
    queue metrics and nothing else, because a scrape that returns half the
    truth is far more useful during an incident than one that returns an error
    page.
    """
    out = Metrics()
    out.add("up", 1, kind="gauge", help_text="1 when this instance answered the scrape.")
    for collector in (_queues, _workers, _query_pools, _stream_slots, _database):
        try:
            collector(out)
        except Exception:
            logger.warning("could not collect %s", collector.__name__, exc_info=True)
    return out.render()


def _queues(out):
    """
    How much work is waiting, which is the first thing to look at when SQLDesk
    feels slow and the warehouse is fine.
    """
    from sqldesk import monitor

    for name, queue in monitor.rq_queues().items():
        out.add(
            "queue_depth",
            queue["queued"],
            {"queue": name},
            help_text="Jobs waiting in this queue.",
        )
        out.add(
            "queue_started",
            len(queue["started"] or []),
            {"queue": name},
            help_text="Jobs this queue has handed to a worker and not yet finished.",
        )


def _workers(out):
    """
    Saturation: how many workers there are, and how many are busy right now.

    The ratio is the number that matters. Queue depth alone cannot tell a
    cluster that is keeping up from one that has no workers at all.
    """
    from sqldesk import monitor

    workers = monitor.rq_workers()
    by_state = {}
    succeeded = failed = 0
    for worker in workers:
        state = (worker.get("state") or "unknown").lower()
        by_state[state] = by_state.get(state, 0) + 1
        succeeded += worker.get("successful_jobs") or 0
        failed += worker.get("failed_jobs") or 0

    out.add("workers", len(workers), help_text="Workers currently registered.")
    for state, count in sorted(by_state.items()):
        out.add("workers_in_state", count, {"state": state}, help_text="Workers in each state.")
    # Counters, not gauges: they only go up, and they reset when a worker is
    # replaced -- which is what `rate()` is built to cope with.
    out.add(
        "worker_jobs_succeeded_total",
        succeeded,
        kind="counter",
        help_text="Jobs finished successfully, summed over the workers alive now.",
    )
    out.add(
        "worker_jobs_failed_total",
        failed,
        kind="counter",
        help_text="Jobs that failed, summed over the workers alive now.",
    )


def _query_pools(out):
    """
    How much of each warehouse's budget is held.

    Enumerated from Redis rather than from the data sources, so a pool shared
    by two sources is one series -- which is what the budget actually is.
    """
    from sqldesk import pools

    for key in redis_connection.scan_iter("{}*".format(pools.KEY_PREFIX), count=200):
        name = key.decode() if isinstance(key, bytes) else key
        pool = name[len(pools.KEY_PREFIX) :]
        limit = pools.budget(pool)
        out.add(
            "query_pool_in_use",
            pools.in_use(pool),
            {"pool": pool},
            help_text="Slots held in this pool right now.",
        )
        # NO_LIMIT reported as 0 would read as "no room at all", which is the
        # opposite of what it means, so an unlimited pool simply has no limit
        # series and a dashboard's ratio has no denominator for it.
        if limit and limit > 0:
            out.add(
                "query_pool_limit",
                limit,
                {"pool": pool},
                help_text="Slots this pool allows.",
            )


def _stream_slots(out):
    """Consumers running, against the ceiling. A slot is a topic, not a viewer."""
    if not settings.STREAMS_ENABLED:
        return
    from sqldesk.streams import slots

    out.add("stream_slots_in_use", len(slots.held()), help_text="Topics being consumed right now.")
    out.add("stream_slots_limit", settings.STREAM_MAX_CONCURRENT, help_text="Topics that may be consumed at once.")


def _database(out):
    """
    Connections checked out of the pool, which is the thing most likely to
    fall over and the thing nothing here could see until now.

    A SQLAlchemy pool is per process, so a scrape describes the process that
    answered it. That is worth stating rather than hiding: with several web
    workers the useful view is the maximum across them, and a reading of
    `checked_out == size + overflow` on any one of them is the one to act on.
    """
    from sqldesk.models import db

    pool = db.engine.pool
    for name, reader, help_text in (
        ("db_connections_in_use", "checkedout", "Connections checked out of the pool right now."),
        ("db_connections_idle", "checkedin", "Connections sitting idle in the pool."),
        ("db_pool_size", "size", "Connections the pool keeps."),
    ):
        read = getattr(pool, reader, None)
        if callable(read):
            out.add(name, read(), help_text="{} In the process that answered.".format(help_text))

    # The ceiling, so a dashboard has something to divide by. Not
    # `pool.overflow()`, which is where the first version of this went wrong:
    # SQLAlchemy starts that counter at *minus the pool size* and counts up, so
    # a healthy install reports `-4` and anybody reading it has to know that to
    # make sense of it. Size plus the overflow allowance is the number that
    # means what it says: the most connections this process will ever hold.
    size, allowance = getattr(pool, "size", None), getattr(pool, "_max_overflow", None)
    if callable(size) and isinstance(allowance, int):
        out.add(
            "db_pool_limit",
            size() + max(0, allowance),
            help_text="The most connections this process will open. In the process that answered.",
        )

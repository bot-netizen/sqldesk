"""
How much work a resource may be given at once, whatever the workers are doing.

Concurrency here has always been an accident of deployment: `WORKERS_COUNT`
processes times however many replicas happen to be running is how many queries
execute at once, and the only way to change what a warehouse is subjected to
is to change the deployment. An autoscaler moving replicas while a query runs
changes it again without anybody asking.

A pool is a ceiling that does not move when the workers do. It lives in Redis,
which every worker already shares, and is checked at the moment work begins.

**A pool is named, and a data source points at one.** The first draft of this
keyed the budget to the data source, which cannot express the case it most
needs to: `prod-readonly` and `prod-analytics` are two rows here and one
machine. Cap each at eight and the machine is handed sixteen. Every data
source gets a pool of its own by default, so nothing needs configuring; two
sources share a budget by naming the same pool.

A pool need not be a database. A rate-limited HTTP connector is the same kind
of scarce, and so is anything else somebody decides to protect.

**A request may weigh more than one slot.** A four-terabyte scan and a
four-gigabyte one are not the same load, and counting both as "one query"
makes a ceiling that is either far too loose or far too tight. Nothing
estimates cost yet, so everything weighs one today -- the weight is here
because the mechanism is cheaper to build with it than to retrofit around it.

This is `streams/slots.py` generalised, and it keeps that module's two good
properties:

**A holder expires on its own**, and is renewed while the work runs. Nothing
depends on a worker surviving long enough to give its slot back -- a killed
process, a drained node, an OOM all end the same way, with the slot free
shortly after.

**The count is taken under a short lock**, because "is there room" is asked by
several processes at once and a count that two of them pass simultaneously is
a ceiling that does not cap.
"""

import logging
import time

from sqldesk import redis_connection, settings

logger = logging.getLogger(__name__)

#: One Redis hash per pool. Kept separate rather than one hash for everything
#: so that reading a busy pool does not read every other pool with it.
KEY_PREFIX = "pool:"
LOCK_PREFIX = "pool:lock:"

#: The lock spans one read and one write. A second is generous; what it is
#: really for is making sure a process that dies holding it does not stop
#: everybody else acquiring for ever.
LOCK_SECONDS = 1

#: How long to wait for the lock before giving up. A refusal says "try again";
#: blocking longer than this is worse than refusing.
LOCK_WAIT_SECONDS = 2

#: Unlimited. The default, so that upgrading does not suddenly cap an install
#: that has been running a nightly batch of thirty refreshes for a year.
NO_LIMIT = 0

#: What each kind of work may take of a pool, as `(floor, ceiling)` percentages.
#:
#: The floor is reserved: other work may borrow it while it is idle and must
#: give it back the moment it is wanted. The ceiling is the most this kind may
#: hold even when the pool is otherwise empty.
#:
#: Both halves are load-bearing. Floors without borrowing waste the warehouse
#: -- a reserved slot nobody is using is money burning. Borrowing without
#: floors lets whatever is busiest take everything, and the dashboard somebody
#: is presenting from stalls behind a refresh storm.
#:
#: **`mcp`'s floor of zero is the point of the whole table.** An agent may use
#: capacity that is idle and may never take the last slot. There is no way to
#: say that with queues and worker counts, and it is the rule that matters
#: more every month.
#:
#: The design named `alerts` as a kind of its own. It is not one here, and
#: deliberately: an alert does not run a query, it evaluates after one has
#: run, and the query behind it is a scheduled refresh like any other. A share
#: that never matches anything is worse than no share.
#:
#: **Order is priority**, most important first, and it decides whose floor is
#: held back from whom. A floor can only be kept by refusing somebody, because
#: nothing here preempts a query that is already running -- so holding
#: capacity back from *every* kind would idle a pool to protect work that may
#: never arrive. Instead a kind must leave room for the floors above it and
#: may borrow freely from the ones below: interactive work can fill the pool,
#: and an agent must leave everyone else's floor alone. That is the asymmetry
#: the feature exists for -- the floors protect people from agents, not agents
#: from people.
SHARES = {
    "interactive": (50, 100),
    "scheduled": (25, 50),
    "notebook": (10, 50),
    "mcp": (0, 25),
}

#: What work that named no kind counts as. Interactive, because a person is
#: the thing most likely to be waiting for it.
DEFAULT_FEATURE = "interactive"


def shares(feature):
    """This kind's `(floor, ceiling)` percentages, or the default's."""
    configured = settings.QUERY_POOL_SHARES or SHARES
    return configured.get(feature) or configured.get(DEFAULT_FEATURE) or (0, 100)


def _slots(percent, limit):
    """A percentage of a pool, rounded down -- a floor must not over-promise."""
    return (percent * limit) // 100


def _key(pool):
    return "{}{}".format(KEY_PREFIX, pool)


class _Lock:
    def __init__(self, pool):
        self.key = "{}{}".format(LOCK_PREFIX, pool)
        self.held = False

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                if redis_connection.set(self.key, "1", ex=LOCK_SECONDS, nx=True):
                    self.held = True
                    return self
            except Exception:
                logger.warning("could not reach Redis for the pool lock", exc_info=True)
                return self
            time.sleep(0.02)
        return self

    def __exit__(self, *_):
        if self.held:
            try:
                redis_connection.delete(self.key)
            except Exception:
                logger.warning("could not release the pool lock", exc_info=True)
        return False


def _text(value):
    return value.decode("utf-8") if isinstance(value, bytes) else value


def pool_for(data_source):
    """
    The pool this data source draws from.

    Its own by default, which makes the out-of-the-box behaviour a per-source
    ceiling. Naming a pool explicitly is how two sources on one warehouse come
    to share a budget.
    """
    named = (data_source.options or {}).get("query_pool")
    if isinstance(named, str) and named.strip():
        return named.strip()
    return "ds:{}".format(data_source.id)


def budget(pool, data_source=None):
    """
    How many slots this pool has, or `NO_LIMIT`.

    Looked up by name first, so a shared pool is configured in one place.
    A data source's own setting applies only to the pool it made for itself --
    otherwise one source could quietly resize a budget another is relying on.
    """
    configured = settings.QUERY_POOLS.get(pool)
    if configured is not None:
        return configured

    if data_source is not None and pool == "ds:{}".format(data_source.id):
        own = (data_source.options or {}).get("query_slots")
        try:
            if own is not None:
                return max(NO_LIMIT, int(own))
        except (TypeError, ValueError):
            logger.warning("data source %s has an unreadable query_slots", data_source.id)

    return settings.QUERY_SLOTS_DEFAULT


def held(pool, now=None):
    """
    `{holder: (weight, feature, owner)}` for everything occupying this pool.

    Expired entries are dropped as they are read rather than by a sweeper: the
    only moment the answer has to be right is when somebody is asking, and
    that is the moment this runs.
    """
    now = now or time.time()
    try:
        raw = redis_connection.hgetall(_key(pool)) or {}
    except Exception:
        logger.warning("could not read pool %s", pool, exc_info=True)
        return {}

    live, stale = {}, []
    for key, value in raw.items():
        holder = _text(key)
        parts = _text(value).split(":", 3)
        try:
            expires, weight = float(parts[0]), int(parts[1])
            if expires > now:
                feature = (parts[2] if len(parts) > 2 else "") or DEFAULT_FEATURE
                live[holder] = (weight, feature, (parts[3] if len(parts) > 3 else "") or None)
            else:
                stale.append(holder)
        except (IndexError, TypeError, ValueError):
            stale.append(holder)

    if stale:
        try:
            redis_connection.hdel(_key(pool), *stale)
        except Exception:
            logger.warning("could not drop expired holders from pool %s", pool, exc_info=True)
    return live


def in_use(pool, now=None):
    """Total weight held, which is what a budget is measured against."""
    return sum(entry[0] for entry in held(pool, now).values())


def in_use_by(pool, now=None):
    """`{feature: weight}` -- what each kind of work is holding."""
    counted = {}
    for weight, feature, _ in held(pool, now).values():
        counted[feature] = counted.get(feature, 0) + weight
    return counted


def room_for(feature, taken, limit):
    """
    How much of this pool this kind of work may take right now.

    Everything other kinds are *entitled to* is subtracted first -- what they
    hold, or their floor, whichever is larger. That is what makes a floor a
    promise rather than a suggestion: capacity reserved for interactive work
    stays reserved while an agent is borrowing the rest of the pool, so the
    moment somebody opens a dashboard there is room for it.

    Then the kind's own ceiling applies, which is what stops the pool being
    emptied by whatever happens to be busiest.
    """
    table = settings.QUERY_POOL_SHARES or SHARES
    order = list(table)
    mine = taken.get(feature, 0)
    above = order.index(feature) if feature in order else len(order)

    # What is held by everything, plus the unused floor of anything that
    # outranks this kind. Work below it in the order is not reserved against:
    # its floor is borrowable, because nothing here can take a slot back from
    # a query already running and a floor held for work that never arrives is
    # a pool idling for nothing.
    held_by_others = sum(w for f, w in taken.items() if f != feature)
    reserved_above = 0
    for other in order[:above]:
        floor, _ = shares(other)
        reserved_above += max(0, _slots(floor, limit) - taken.get(other, 0))

    _, ceiling = shares(feature)
    by_ceiling = _slots(ceiling, limit) - mine
    by_pool = limit - held_by_others - mine - reserved_above
    return max(0, min(by_ceiling, by_pool))


def acquire(pool, holder, weight=1, owner=None, limit=None, ttl=None, now=None, feature=None):
    """
    Take room in this pool, or say why there is none.

    Returns None on success and a sentence on refusal -- a sentence because
    somebody reads it. "All 8 slots on warehouse are in use" tells a person
    what to do next; `False` does not.

    Re-acquiring under a holder already present is free and refreshes it. That
    makes the call idempotent, so a retried job does not consume a second slot
    while its first is still counted.
    """
    now = now or time.time()
    weight = max(1, int(weight))
    limit = budget(pool) if limit is None else limit
    ttl = ttl or settings.QUERY_SLOT_TTL_SECONDS
    feature = feature or DEFAULT_FEATURE

    if limit == NO_LIMIT:
        _write(pool, holder, weight, feature, owner, ttl, now)
        return None

    with _Lock(pool) as lock:
        if not lock.held:
            return "Could not check the limit on {} just now. Try again.".format(pool)

        entries = held(pool, now)
        if holder in entries:
            _write(pool, holder, weight, feature, owner, ttl, now)
            return None

        taken = {}
        for w, f, _ in entries.values():
            taken[f] = taken.get(f, 0) + w
        used = sum(taken.values())

        if weight > room_for(feature, taken, limit):
            # Named numbers, because "it is busy" is not something anybody can
            # act on and this message reaches a person. The kind is named too,
            # because being refused at 3 of 8 only makes sense once you know
            # the rest is reserved for something else.
            return "{} of {} slots on {} are in use, and {} work may take no more. Try again shortly.".format(
                used, limit, pool, feature
            )

        _write(pool, holder, weight, feature, owner, ttl, now)
        return None


def renew(pool, holder, now=None):
    """Keep a holder alive while its work is still running."""
    current = held(pool, now).get(holder)
    if current is None:
        return
    weight, feature, owner = current
    _write(pool, holder, weight, feature, owner, settings.QUERY_SLOT_TTL_SECONDS, now or time.time())


def _write(pool, holder, weight, feature, owner, ttl, now):
    try:
        redis_connection.hset(
            _key(pool),
            str(holder),
            "{}:{}:{}:{}".format(now + ttl, weight, feature or DEFAULT_FEATURE, owner or ""),
        )
    except Exception:
        logger.warning("could not record %s in pool %s", holder, pool, exc_info=True)


def release(pool, holder):
    try:
        redis_connection.hdel(_key(pool), str(holder))
    except Exception:
        logger.warning("could not release %s from pool %s", holder, pool, exc_info=True)

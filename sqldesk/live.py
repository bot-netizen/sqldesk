"""
Live dashboards: the server runs a dashboard's queries on an interval, once
for everyone watching, instead of every open tab re-running them on a timer.

Three rules make that cheap and safe:

- **Only while watched.** Viewers check in every few seconds while their tab
  is visible; a dashboard nobody has checked in to for WATCH_WINDOW seconds is
  not refreshed. A hidden tab stops checking in, and says it has left.
- **Viewers cannot add load.** A live dashboard shows no refresh button and
  locks its parameters to their saved values, so every viewer asks for the
  same results the server is producing.
- **Turning it on is a permission.** Admins have it; other groups can be
  granted MANAGE_LIVE_PERMISSION. Watching needs only ordinary access.

State lives in `dashboards.live`; who is watching lives in Redis, because a
database write per viewer per check-in would be the wrong kind of cost.
"""

import logging
import time

from sqldesk import models, redis_connection
from sqldesk.models.parameterized_query import (
    InvalidParameterError,
    QueryDetachedFromDataSourceError,
)
from sqldesk.utils import gen_query_hash, utcnow

logger = logging.getLogger(__name__)

MANAGE_LIVE_PERMISSION = "manage_live_dashboards"

# Seconds between server-side refreshes a dashboard can be set to.
LIVE_INTERVALS = (30, 60, 120, 300)

# A viewer who has not checked in for this long is no longer watching.
# Viewers check in every CHECK_IN_SECONDS, so this allows two misses.
CHECK_IN_SECONDS = 15
WATCH_WINDOW = 45

# A result counts as fresh this many seconds before the interval is up, so a
# 30-second dashboard refreshes every ~30 seconds rather than every ~40 once
# the scheduler's own 10-second tick is added.
FRESHNESS_SLACK = 5


def can_manage_live(user):
    return user.has_permission("admin") or user.has_permission(MANAGE_LIVE_PERMISSION)


def live_settings(dashboard):
    """The dashboard's live settings, or None when it is not live."""
    live = dashboard.live
    if not live or not isinstance(live, dict):
        return None
    interval = live.get("interval")
    if interval not in LIVE_INTERVALS:
        return None
    return live


def is_running(dashboard):
    live = live_settings(dashboard)
    return bool(live) and not live.get("paused") and not dashboard.is_archived


# -- Who is watching -----------------------------------------------------------


def _watchers_key(dashboard_id):
    return "sqldesk:live:watchers:{}".format(dashboard_id)


def check_in(dashboard_id, viewer_id, now=None):
    now = now if now is not None else time.time()
    key = _watchers_key(dashboard_id)
    pipe = redis_connection.pipeline()
    pipe.zadd(key, {viewer_id: now})
    # The set outlives its members by a little, then goes away on its own.
    pipe.expire(key, WATCH_WINDOW * 2)
    pipe.execute()


def leave(dashboard_id, viewer_id):
    redis_connection.zrem(_watchers_key(dashboard_id), viewer_id)


def watcher_count(dashboard_id, now=None):
    now = now if now is not None else time.time()
    key = _watchers_key(dashboard_id)
    redis_connection.zremrangebyscore(key, "-inf", now - WATCH_WINDOW)
    return redis_connection.zcard(key)


def is_watched(dashboard_id, now=None):
    return watcher_count(dashboard_id, now) > 0


# -- What each widget runs -----------------------------------------------------


def widget_query_text(widget):
    """
    The query a widget shows, with its parameters as a live dashboard locks
    them: the query's saved values, overridden by any value fixed on the
    widget itself. Values from a viewer's URL play no part -- that is the
    point of locking them.

    Returns (query, text), or None for a text box or a widget that cannot be
    resolved.
    """
    visualization = widget.visualization
    if visualization is None:
        return None
    query = visualization.query_rel
    if query is None or query.data_source is None:
        return None

    values = {p["name"]: p.get("value") for p in query.parameters}
    mappings = (widget.options or {}).get("parameterMappings") or {}
    for name, mapping in mappings.items():
        if isinstance(mapping, dict) and mapping.get("type") == "static-value" and name in values:
            values[name] = mapping.get("value")

    try:
        text = query.parameterized.apply(values).query if values else query.query_text
    except (InvalidParameterError, QueryDetachedFromDataSourceError) as e:
        logger.info("Live dashboard widget %s cannot resolve its parameters: %s", widget.id, e)
        return None

    should_limit = (query.options or {}).get("apply_auto_limit", False)
    text = query.data_source.query_runner.apply_auto_limit(text, should_limit)
    return query, text


def latest_results(dashboard, user=None):
    """
    {widget id: id of the newest result for what it shows}, for widgets the
    user may see. A viewer compares these with what it has and reloads only
    the widgets whose result changed.
    """
    from sqldesk.permissions import has_access, view_only

    results = {}
    for widget in dashboard.loaded_widgets():
        if widget.visualization_id is None:
            continue
        resolved = widget_query_text(widget)
        if resolved is None:
            continue
        query, text = resolved
        if user is not None and not has_access(query, user, view_only):
            continue
        latest = models.QueryResult.get_latest(query.data_source, text, max_age=-1)
        results[str(widget.id)] = latest.id if latest else None
    return results


# -- The periodic job ----------------------------------------------------------


def _skip(query):
    if query.org.is_disabled:
        return "its organization is disabled"
    if query.data_source.paused:
        return "its data source is paused"
    return None


def _attempt_key(data_source_id, query_hash):
    return "sqldesk:live:attempted:{}:{}".format(data_source_id, query_hash)


def claim_attempt(data_source, text, interval, now=None):
    """
    Whether this refresh is ours to make, marking it as made if so.

    A run that succeeds leaves a result behind and the freshness check below
    is enough. A run that *fails* leaves nothing, so the freshness check finds
    nothing every time and the ten-second scheduler asks again on every tick:
    thirty times the interval on a five-minute dashboard, for ever, against a
    data source that is already unhappy.

    The mark expires after exactly as long as a result would stay fresh, so a
    failing query is retried at the dashboard's interval like a working one,
    and the two clocks cannot drift apart. It is keyed by query text rather
    than by widget, so two widgets showing the same query ask once between
    them.
    """
    key = _attempt_key(data_source.id, gen_query_hash(text))
    ttl = max(int(interval - FRESHNESS_SLACK), 1)
    now = now if now is not None else time.time()
    return bool(redis_connection.set(key, now, ex=ttl, nx=True))


def forget_attempts(dashboard):
    """
    Drop the marks for a dashboard's queries, so a refresh asked for by hand
    -- going live, changing the interval, resuming -- happens now rather than
    waiting out the last one.
    """
    keys = []
    for widget in dashboard.loaded_widgets():
        resolved = widget_query_text(widget)
        if resolved is None:
            continue
        query, text = resolved
        keys.append(_attempt_key(query.data_source_id, gen_query_hash(text)))
    if keys:
        redis_connection.delete(*keys)


def refresh_dashboard(dashboard):
    """
    Enqueue each of a running live dashboard's widget queries whose newest
    result is older than its interval, and return their query ids.

    Queries already running are not stacked: enqueue_query hands back the job
    already in flight for the same text.
    """
    from sqldesk.tasks.queries.execution import enqueue_query

    if not is_running(dashboard):
        return []

    enqueued = []
    interval = dashboard.live["interval"]
    for widget in dashboard.loaded_widgets():
        resolved = widget_query_text(widget)
        if resolved is None:
            continue
        query, text = resolved
        reason = _skip(query)
        if reason:
            logger.debug("Live dashboard %s skips query %s because %s", dashboard.id, query.id, reason)
            continue
        fresh = models.QueryResult.get_latest(query.data_source, text, max_age=interval - FRESHNESS_SLACK)
        if fresh:
            continue
        if not claim_attempt(query.data_source, text, interval):
            continue
        try:
            enqueue_query(
                text,
                query.data_source,
                dashboard.user_id,
                metadata={
                    "query_id": query.id,
                    "dashboard_id": dashboard.id,
                    "Username": "Live dashboard {}".format(dashboard.id),
                },
                # The server runs these, not a person waiting on a result, so
                # they belong beside scheduled refreshes rather than competing
                # with queries somebody is sitting in front of.
                queue_name=query.data_source.scheduled_queue_name,
            )
            enqueued.append(query.id)
        except Exception:  # one bad query must not stop the others
            logger.exception("Live dashboard %s could not enqueue query %s", dashboard.id, query.id)
    return enqueued


def refresh_live_dashboards():
    """
    Refresh every running live dashboard somebody is watching. Scheduled by
    the periodic scheduler every 10 seconds; costs one query and one Redis
    round trip per live dashboard when nothing is due.
    """
    enqueued = []
    now = time.time()
    dashboards = models.Dashboard.query.filter(
        models.Dashboard.live.isnot(None), models.Dashboard.is_archived.is_(False)
    )
    for dashboard in dashboards:
        if is_running(dashboard) and is_watched(dashboard.id, now):
            enqueued.extend(refresh_dashboard(dashboard))

    if enqueued:
        logger.info("Live dashboards enqueued %d queries: %s", len(enqueued), enqueued)
    return enqueued


def describe(dashboard):
    """The live settings as the API shows them, or None."""
    live = live_settings(dashboard)
    if not live:
        return None
    return {
        "interval": live["interval"],
        "paused": bool(live.get("paused")),
        "paused_by": live.get("paused_by"),
        "paused_at": live.get("paused_at"),
        "check_in_seconds": CHECK_IN_SECONDS,
    }


def pause_record(user):
    return {"paused": True, "paused_by": {"id": user.id, "name": user.name}, "paused_at": utcnow().isoformat()}

from flask_login import current_user, login_required
from sqlalchemy import func, or_

from sqldesk import models
from sqldesk.authentication import current_org
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, org_scoped_rule

TOP_SCHEDULED_LIMIT = 10


def _my_queries():
    return models.Query.query.filter(
        models.Query.user_id == current_user.id,
        models.Query.org_id == current_org.id,
        models.Query.is_archived.is_(False),
    )


def _is_scheduled():
    """Whether a query's schedule actually schedules anything.

    A query can carry a schedule dict with every field empty -- the UI writes
    one when a schedule is cleared field by field rather than set to null -- and
    outdated_queries skips those. Counting them would report queries as
    scheduled that will never run. ->> returns SQL NULL for a JSON null as well
    as for a missing key, so one test covers both.
    """
    return or_(
        models.Query.schedule["interval"].astext.isnot(None),
        models.Query.schedule["cron"].astext.isnot(None),
    )


def _result_storage_bytes():
    """On-disk size of the cached results belonging to this user's queries.

    Only each query's current result is counted, reached through
    latest_query_data_id. Older results for the same query are still in the
    table until the cleanup job takes them, but they are not what the query
    holds now, and counting them would make the number jump around with the
    cleanup schedule rather than with anything the user did.

    pg_column_size reports the stored size, so compression is already accounted
    for -- this is space on disk, not the length of the JSON.
    """
    return (
        models.db.session.query(func.coalesce(func.sum(func.pg_column_size(models.QueryResult.data)), 0))
        .select_from(models.QueryResult)
        .join(models.Query, models.Query.latest_query_data_id == models.QueryResult.id)
        .filter(
            models.Query.user_id == current_user.id,
            models.Query.org_id == current_org.id,
            models.Query.is_archived.is_(False),
        )
        .scalar()
    )


def _top_scheduled_queries():
    """The user's scheduled queries, slowest first.

    Slowest rather than most recent: a scheduled query nobody watches is where
    runtime quietly grows, and this is the list worth looking down.
    """
    rows = (
        models.db.session.query(
            models.Query.id,
            models.Query.name,
            models.Query.schedule,
            models.DataSource.name.label("data_source"),
            models.QueryResult.runtime,
            models.QueryResult.retrieved_at,
            func.pg_column_size(models.QueryResult.data).label("result_bytes"),
        )
        .select_from(models.Query)
        .outerjoin(models.DataSource, models.DataSource.id == models.Query.data_source_id)
        .outerjoin(models.QueryResult, models.QueryResult.id == models.Query.latest_query_data_id)
        .filter(
            models.Query.user_id == current_user.id,
            models.Query.org_id == current_org.id,
            models.Query.is_archived.is_(False),
            _is_scheduled(),
        )
        # A query that has never run has no runtime. It belongs at the end of a
        # slowest-first list, not the start, which is where NULL sorts by default.
        .order_by(models.QueryResult.runtime.desc().nullslast())
        .limit(TOP_SCHEDULED_LIMIT)
        .all()
    )

    return [
        {
            "id": row.id,
            "name": row.name,
            "schedule": row.schedule,
            "data_source": row.data_source,
            "runtime": row.runtime,
            "retrieved_at": row.retrieved_at,
            "result_bytes": row.result_bytes,
        }
        for row in rows
    ]


@routes.route(org_scoped_rule("/api/home/summary"), methods=["GET"])
@login_required
def home_summary(org_slug=None):
    """What the home page shows: counts of the things this user made.

    Scoped to the current user rather than the organization. The org-wide
    figures are what /api/organization/status reports, and they answer a
    different question.
    """
    counters = {
        "queries": _my_queries().count(),
        "dashboards": models.Dashboard.query.filter(
            models.Dashboard.user_id == current_user.id,
            models.Dashboard.org_id == current_org.id,
            models.Dashboard.is_archived.is_(False),
        ).count(),
        "scheduled_queries": _my_queries().filter(_is_scheduled()).count(),
        "alerts": models.Alert.query.filter(models.Alert.user_id == current_user.id).count(),
        "result_storage_bytes": _result_storage_bytes(),
    }

    return json_response(
        {
            "counters": counters,
            "top_scheduled_queries": _top_scheduled_queries(),
        }
    )

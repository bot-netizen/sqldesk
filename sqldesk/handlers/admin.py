from flask_login import current_user, login_required

from sqldesk import models, redis_connection
from sqldesk.authentication import current_org
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, record_event
from sqldesk.monitor import get_overview, rq_status
from sqldesk.permissions import require_super_admin
from sqldesk.serializers import QuerySerializer
from sqldesk.utils import json_loads


@routes.route("/api/admin/queries/outdated", methods=["GET"])
@login_required
@require_super_admin
def outdated_queries():
    manager_status = redis_connection.hgetall("sqldesk:status")
    query_ids = json_loads(manager_status.get("query_ids", "[]"))
    if query_ids:
        outdated_queries = (
            models.Query.query.outerjoin(models.QueryResult)
            .filter(models.Query.id.in_(query_ids))
            .order_by(models.Query.created_at.desc())
        )
    else:
        outdated_queries = []

    record_event(
        current_org,
        current_user._get_current_object(),
        {
            "action": "list",
            "object_type": "outdated_queries",
        },
    )

    response = {
        "queries": QuerySerializer(outdated_queries, with_stats=True, with_last_modified_by=False).serialize(),
        # `.get`, because the key does not exist until `refresh_queries` has
        # run once. A fresh install asking this page a question got a KeyError
        # and a 500 rather than an empty list.
        "updated_at": manager_status.get("last_refresh_at"),
    }
    return json_response(response)


@routes.route("/api/admin/queries/rq_status", methods=["GET"])
@login_required
@require_super_admin
def queries_rq_status():
    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "list", "object_type": "rq_status"},
    )

    return json_response(rq_status())


@routes.route("/api/admin/overview", methods=["GET"])
@login_required
@require_super_admin
def admin_overview():
    """
    One read of everything an admin needs while the instance is slow.

    Deliberately one endpoint rather than five: the page shows a single moment,
    and five calls would show five, which is how a dashboard ends up
    contradicting itself.
    """
    return json_response(get_overview(current_org.id))

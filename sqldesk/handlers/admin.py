from flask_login import current_user, login_required

from sqldesk import models, redis_connection
from sqldesk.authentication import current_org
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, record_event
from sqldesk.monitor import rq_status
from sqldesk.permissions import require_super_admin
from sqldesk.serializers import QuerySerializer
from sqldesk.utils import json_loads


@routes.route("/api/admin/queries/outdated", methods=["GET"])
@require_super_admin
@login_required
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
        "updated_at": manager_status["last_refresh_at"],
    }
    return json_response(response)


@routes.route("/api/admin/queries/rq_status", methods=["GET"])
@require_super_admin
@login_required
def queries_rq_status():
    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "list", "object_type": "rq_status"},
    )

    return json_response(rq_status())

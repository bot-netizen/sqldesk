from flask_login import current_user, login_required
from flask_restful import abort
from rq.exceptions import NoSuchJobError

from sqldesk import models, redis_connection, rq_redis_connection
from sqldesk.authentication import current_org
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, record_event
from sqldesk.monitor import get_overview, rq_status
from sqldesk.permissions import require_super_admin
from sqldesk.serializers import QuerySerializer
from sqldesk.tasks import Job, Queue
from sqldesk.tasks.queries.maintenance import cleanup_events, cleanup_query_results
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


@routes.route("/api/admin/jobs/<job_id>", methods=["DELETE"])
@login_required
@require_super_admin
def kill_running_query(job_id):
    """
    Stop a query an admin has decided is not worth waiting for.

    Deliberately separate from `/api/jobs/<id>`, which only lets people cancel
    their own. This is the one place a query belonging to somebody else -- or
    to the scheduler, which belongs to nobody -- can be stopped, and it is
    recorded, because ending someone else's work quietly is not on.
    """
    try:
        job = Job.fetch(job_id, connection=rq_redis_connection)
    except NoSuchJobError:
        abort(404, message="Unknown job id.")

    meta = job.meta or {}
    job.cancel()

    record_event(
        current_org,
        current_user._get_current_object(),
        {
            "action": "cancel",
            "object_type": "job",
            "object_id": job_id,
            "query_id": meta.get("query_id"),
            "belonged_to": meta.get("user_id"),
        },
    )

    return json_response({"job_id": job_id})


@routes.route("/api/admin/cleanup/query_results", methods=["POST"])
@login_required
@require_super_admin
def run_query_results_cleanup():
    """
    Run the stored-result cleanup now rather than waiting for its slot.

    It is already scheduled every five minutes; this is for when it has been
    falling behind its per-run cap and somebody is watching the table grow.
    """
    job = Queue("periodic", connection=rq_redis_connection).enqueue(cleanup_query_results)

    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "cleanup", "object_type": "query_results"},
    )

    return json_response({"job_id": job.id})


@routes.route("/api/admin/cleanup/events", methods=["POST"])
@login_required
@require_super_admin
def run_events_cleanup():
    """
    Drop old rows from `events`.

    Every execution writes one, carrying the full query text, so this is the
    table that grows fastest and the one nobody thinks to look at.
    """
    job = Queue("periodic", connection=rq_redis_connection).enqueue(cleanup_events)

    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "cleanup", "object_type": "events"},
    )

    return json_response({"job_id": job.id})

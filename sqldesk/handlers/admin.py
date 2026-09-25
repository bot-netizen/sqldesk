import datetime
import io
import zipfile

from flask import request, send_file
from flask_login import current_user, login_required
from flask_restful import abort
from rq.exceptions import NoSuchJobError

from sqldesk import models, redis_connection, rq_redis_connection
from sqldesk.ai.catalog.semantic import catalog_documents
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


@routes.route("/api/admin/catalog", methods=["GET"])
@login_required
@require_super_admin
def catalog_tables():
    """
    The catalog, for reviewing and describing it.

    Ordered by usage, because that is the order the work is worth doing in:
    nobody documents three thousand tables, and the twenty anyone actually
    queries are most of the value. `undescribed=1` narrows it to the ones
    still missing a sentence, which turns an impossible job into a list with
    an end.
    """
    source_id = request.args.get("data_source_id", type=int)
    tables = models.CatalogTable.query.filter(models.CatalogTable.org == current_org)
    if source_id:
        tables = tables.filter(models.CatalogTable.data_source_id == source_id)
    if request.args.get("undescribed"):
        tables = tables.filter(models.CatalogTable.description.is_(None))

    tables = tables.order_by(models.CatalogTable.usage_count.desc().nullslast()).limit(200).all()

    # One query for every table's column count rather than one per table.
    counts = dict(
        models.db.session.query(models.CatalogColumn.catalog_table_id, models.db.func.count())
        .filter(models.CatalogColumn.catalog_table_id.in_([t.id for t in tables] or [0]))
        .group_by(models.CatalogColumn.catalog_table_id)
        .all()
    )

    return json_response(
        {
            "tables": [
                {
                    "id": table.id,
                    "name": table.name,
                    "data_source_id": table.data_source_id,
                    "usage_count": table.usage_count,
                    "description": table.description,
                    "description_source": table.description_source,
                    "column_count": counts.get(table.id, 0),
                    "card": table.card,
                    "harvested_at": table.harvested_at,
                }
                for table in tables
            ]
        }
    )


@routes.route("/api/admin/catalog/tables/<int:table_id>", methods=["POST"])
@login_required
@require_super_admin
def describe_catalog_table(table_id):
    """
    Write a description by hand.

    Marked "human", which is what stops the next scheduled harvest replacing
    it with whatever the warehouse does or does not say.
    """
    table = models.CatalogTable.query.filter(
        models.CatalogTable.id == table_id, models.CatalogTable.org == current_org
    ).first()
    if table is None:
        abort(404)

    description = (request.get_json(force=True) or {}).get("description")
    description = (description or "").strip() or None
    table.description = description
    # Cleared by a person is still a decision by a person -- but with nothing
    # to protect, the source goes back to unset so the engine may fill it.
    table.description_source = "human" if description else None
    models.db.session.commit()

    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "describe", "object_id": table_id, "object_type": "catalog_table"},
    )

    return json_response(
        {"id": table.id, "description": table.description, "description_source": table.description_source}
    )


@routes.route("/api/admin/catalog/measures", methods=["GET"])
@login_required
@require_super_admin
def catalog_measures():
    """
    Metrics mined from saved SQL, most-written first.

    A definition four teams wrote independently is a different proposition
    from one somebody tried once, which is what the count is for.
    """
    source_id = request.args.get("data_source_id", type=int)
    measures = models.CatalogMeasure.query.filter(models.CatalogMeasure.org == current_org)
    if source_id:
        measures = measures.filter(models.CatalogMeasure.data_source_id == source_id)
    if request.args.get("pending"):
        # Proposals only. A measure somebody denied has been looked at, and
        # putting it back on the worklist every night is how a worklist stops
        # being read.
        measures = measures.filter(models.CatalogMeasure.status == models.MEASURE_PROPOSED)

    measures = measures.order_by(models.CatalogMeasure.usage_count.desc().nullslast()).limit(200).all()

    return json_response(
        {
            "measures": [
                {
                    "id": measure.id,
                    "table_name": measure.table_name,
                    "name": measure.name,
                    "kind": measure.kind,
                    "column_name": measure.column_name,
                    "usage_count": measure.usage_count,
                    "status": measure.status,
                    "description": measure.description,
                }
                for measure in measures
            ]
        }
    )


@routes.route("/api/admin/catalog/measures/<int:measure_id>", methods=["POST"])
@login_required
@require_super_admin
def review_catalog_measure(measure_id):
    """
    Agree a proposed metric, deny it, or write what it means.

    Approval is the whole point: until somebody sets it, the definition is
    something we noticed rather than something the organisation stands
    behind, and only the latter belongs in front of a model. Denial matters
    for a duller reason -- a proposal nobody can reject is one that comes
    back every night until the list stops being read.
    """
    measure = models.CatalogMeasure.query.filter(
        models.CatalogMeasure.id == measure_id, models.CatalogMeasure.org == current_org
    ).first()
    if measure is None:
        abort(404)

    body = request.get_json(force=True) or {}
    if "status" in body:
        if body["status"] not in models.MEASURE_STATUSES:
            abort(400, message="status must be one of {}.".format(", ".join(models.MEASURE_STATUSES)))
        measure.status = body["status"]
    if "description" in body:
        measure.description = (body["description"] or "").strip() or None
    models.db.session.commit()

    record_event(
        current_org,
        current_user._get_current_object(),
        {
            "action": measure.status,
            "object_id": measure_id,
            "object_type": "catalog_measure",
        },
    )

    return json_response({"id": measure.id, "status": measure.status, "description": measure.description})


@routes.route("/api/admin/catalog/export", methods=["GET"])
@login_required
@require_super_admin
def download_catalog():
    """
    The semantic layer as a zip, for people who do not have a shell.

    `manage ai export` writes the same files into a mounted directory, which
    suits a deploy pipeline. It does not suit the person actually writing the
    descriptions, who may have no access to the container at all -- and a
    curation step that requires docker is one that does not happen.

    Built in memory: the whole thing is a few kilobytes of YAML per table,
    and writing it to disk first would mean cleaning it up afterwards.
    """
    source = None
    source_id = request.args.get("data_source_id", type=int)
    if source_id:
        source = models.DataSource.query.filter(
            models.DataSource.id == source_id, models.DataSource.org == current_org
        ).first()
        if source is None:
            abort(404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, text in catalog_documents(current_org, data_source=source):
            archive.writestr(path, text)
    buffer.seek(0)

    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "export", "object_type": "catalog"},
    )

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="sqldesk-semantic-{}.zip".format(datetime.datetime.now().strftime("%Y-%m-%d")),
    )

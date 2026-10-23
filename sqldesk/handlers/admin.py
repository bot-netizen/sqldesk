import datetime
import io
import zipfile

from flask import request, send_file
from flask_login import current_user, login_required
from flask_restful import abort
from rq.exceptions import NoSuchJobError

from sqldesk import features, models, redis_connection, rq_redis_connection, settings
from sqldesk import uploads as sqldesk_uploads
from sqldesk.ai.catalog.freshness import in_days, stale_sources
from sqldesk.ai.catalog.semantic import catalog_documents
from sqldesk.authentication import current_org
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, record_event
from sqldesk.monitor import get_db_sizes, get_overview, get_running_queries, rq_status
from sqldesk.permissions import (
    has_access,
    require_access,
    require_feature,
    require_super_admin,
    view_only,
)
from sqldesk.serializers import QuerySerializer
from sqldesk.tasks import Job, Queue
from sqldesk.tasks.catalog import enqueue_harvest, harvest_states
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


@routes.route("/api/admin/queries/running", methods=["GET"])
@login_required
@require_super_admin
def admin_running_queries():
    """
    Only what the workers have in flight.

    Its own endpoint rather than a slice of the overview, because the page that
    shows this is read while somebody is waiting for a query to end, and it
    refreshes four times as often as the overview does. The overview also
    measures table sizes and aggregates an hour of events; doing that every few
    seconds to find out whether one job is still running would make the page
    part of the problem it is there to diagnose.
    """
    return json_response({"running": get_running_queries()})


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


@routes.route("/api/admin/storage", methods=["GET"])
@login_required
@require_super_admin
def storage_overview():
    """
    What SQLDesk is holding, per data source, and what happens to it when.

    None of this was visible anywhere. On 2026-09-28 the development disk
    reached 100% and took Postgres with it, and the only way to find out why
    was to look at the filesystem -- which is exactly the situation a product
    that stores files for people should not put anybody in.

    Borrowed and owned data are listed apart, because the policies are
    different and conflating them is how somebody ends up afraid to delete a
    cached query result. A result can be fetched again; an upload cannot.
    """
    uploads_by_source = {}
    for upload in models.UploadedFile.query.filter(models.UploadedFile.org_id == current_org.id).order_by(
        models.UploadedFile.size.desc()
    ):
        uploads_by_source.setdefault(upload.data_source_id, []).append(upload)

    names = dict(
        models.db.session.query(models.DataSource.id, models.DataSource.name).filter(
            models.DataSource.org == current_org
        )
    )

    sources = []
    for source_id, rows in uploads_by_source.items():
        sources.append(
            {
                "data_source_id": source_id,
                "data_source_name": names.get(source_id) or "a deleted data source",
                "files": len(rows),
                "bytes": sum(row.size or 0 for row in rows),
                "uploads": [row.to_dict() for row in rows[:200]],
            }
        )
    sources.sort(key=lambda entry: -entry["bytes"])

    held = sqldesk_uploads.bytes_held(current_org)
    ceiling = sqldesk_uploads.quota_bytes()
    return json_response(
        {
            "uploads": {
                "bytes": held,
                "quota_bytes": ceiling or None,
                "files": sum(entry["files"] for entry in sources),
                "lifetime_days": settings.UPLOAD_LIFETIME_DAYS,
                "unload_after_days": settings.UPLOAD_UNLOAD_AFTER_DAYS,
                "by_data_source": sources,
            },
            # The borrowed half, from the numbers the status page already
            # gathers, so the two are not computed two different ways.
            "results": get_db_sizes(),
        }
    )


#: How many tables the catalog page is sent at once. A search runs over all of
#: them; this only bounds how many come back.
LIMIT = 200


def _curatable_source_ids():
    """
    The data sources whose catalog this person may see and change.

    Every one for an administrator, who can manage every data source anyway.
    For anybody else, only those their groups can read: the curation feature
    can be granted to a group that is not in every data source's groups, and
    until 0.7.7 such a curator could list another source's tables and
    columns, download the SQL of its verified queries, and write the
    descriptions its users' models are then fed.
    """
    user = current_user._get_current_object()
    sources = models.DataSource.query.filter(models.DataSource.org == current_org).all()
    if user.has_permission("admin"):
        return [source.id for source in sources]
    return [source.id for source in sources if has_access(source, user, view_only)]


def _curatable_or_404(data_source_id):
    if data_source_id not in _curatable_source_ids():
        abort(404)


@routes.route("/api/catalog", methods=["GET"])
@login_required
@require_feature(features.MANAGE_CATALOG)
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
    tables = models.CatalogTable.query.filter(
        models.CatalogTable.org == current_org,
        models.CatalogTable.data_source_id.in_(_curatable_source_ids() or [0]),
    )
    if source_id:
        tables = tables.filter(models.CatalogTable.data_source_id == source_id)

    # Counted before the hidden filter, so the page can say how many are
    # hidden while they are not being shown.
    hidden_count = tables.filter(models.CatalogTable.hidden.is_(True)).count()
    if not request.args.get("hidden"):
        tables = tables.filter(models.CatalogTable.hidden.is_(False))

    if request.args.get("undescribed"):
        tables = tables.filter(models.CatalogTable.description.is_(None))
    elif request.args.get("described"):
        tables = tables.filter(models.CatalogTable.description.isnot(None))

    # On the server, over every table. The page shows the first 200 by usage,
    # and a search that only looked at those 200 would never find the 201st
    # -- which is the table somebody is searching for, because it is the one
    # they could not see.
    search = (request.args.get("q") or "").strip()
    if search:
        pattern = "%{}%".format(search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"))
        tables = tables.filter(
            models.db.or_(
                models.CatalogTable.name.ilike(pattern, escape="\\"),
                models.CatalogTable.description.ilike(pattern, escape="\\"),
            )
        )

    total = tables.count()
    tables = (
        tables.order_by(models.CatalogTable.usage_count.desc().nullslast(), models.CatalogTable.name)
        .limit(LIMIT)
        .all()
    )

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
                    "hidden": table.hidden,
                }
                for table in tables
            ],
            # So the page can say "200 of 1,432" rather than look complete.
            "total": total,
            "limit": LIMIT,
            "hidden_count": hidden_count,
        }
    )


@routes.route("/api/catalog/sources", methods=["GET"])
@login_required
@require_super_admin
def catalog_sources():
    """
    Every data source, with what the catalog holds for it: how many tables,
    when it was last harvested, and whether a harvest is waiting or running.
    A source with no tables has never been harvested -- or its schema came
    back empty, which is worth harvesting again anyway.
    """
    sources = models.DataSource.query.filter(models.DataSource.org == current_org).order_by(models.DataSource.name)
    sources = sources.all()
    held = dict(
        (row[0], (row[1], row[2]))
        for row in models.db.session.query(
            models.CatalogTable.data_source_id,
            models.db.func.count(),
            models.db.func.max(models.CatalogTable.harvested_at),
        )
        .filter(models.CatalogTable.org == current_org)
        .group_by(models.CatalogTable.data_source_id)
    )
    states = harvest_states(source.id for source in sources)
    # Which of them are old enough to matter, by the one policy -- rather than
    # leaving the page to invent a threshold of its own from the timestamps.
    stale = stale_sources(current_org, [source.id for source in sources])

    return json_response(
        {
            "sources": [
                {
                    "id": source.id,
                    "name": source.name,
                    "type": source.type,
                    "paused": bool(source.paused),
                    "tables": held.get(source.id, (0, None))[0],
                    "harvested_at": held.get(source.id, (0, None))[1],
                    "state": states.get(source.id),
                    "stale_for": in_days(stale[source.id]) if source.id in stale else None,
                }
                for source in sources
            ]
        }
    )


@routes.route("/api/catalog/harvest", methods=["POST"])
@login_required
@require_super_admin
def harvest_catalog_now():
    """
    Harvest now rather than at the next scheduled run.

    `{"data_source_id": 3}` harvests one source; `{"only": "unharvested"}`
    only the sources with nothing in the catalog yet, which is what a new
    data source needs without re-reading every other one; `{}` all of them.
    Each source is its own job on the `schemas` queue, as on the schedule.
    """
    body = request.get_json(silent=True) or {}
    sources = models.DataSource.query.filter(models.DataSource.org == current_org)

    source_id = body.get("data_source_id")
    if source_id is not None:
        sources = sources.filter(models.DataSource.id == source_id)
    elif body.get("only") == "unharvested":
        # NOT IN over a list holding a NULL matches nothing at all, so the
        # NULLs go before the list is used.
        harvested = models.db.session.query(models.CatalogTable.data_source_id).filter(
            models.CatalogTable.org == current_org, models.CatalogTable.data_source_id.isnot(None)
        )
        sources = sources.filter(~models.DataSource.id.in_(harvested.subquery()))
    elif body.get("only") is not None:
        abort(400, message='`only` can be "unharvested", or left out for every data source.')

    sources = sources.all()
    if source_id is not None and not sources:
        abort(404, message="No such data source.")

    queued, skipped = [], []
    for source in sources:
        reason = enqueue_harvest(source)
        if reason:
            skipped.append({"id": source.id, "name": source.name, "reason": reason})
        else:
            queued.append(source.id)

    record_event(
        current_org,
        current_user._get_current_object(),
        {
            "action": "harvest",
            "object_type": "catalog",
            "object_id": source_id,
            "queued": queued,
            "only": body.get("only"),
        },
    )

    return json_response({"queued": queued, "skipped": skipped})


@routes.route("/api/catalog/tables/<int:table_id>", methods=["POST"])
@login_required
@require_feature(features.MANAGE_CATALOG)
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
    _curatable_or_404(table.data_source_id)

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400, message="A JSON object is expected.")

    # Only what was sent. This used to set the description from whatever body
    # arrived, so a request carrying anything else -- hiding a table, say --
    # would have wiped a description somebody had written.
    if "description" in body:
        description = (body.get("description") or "").strip() or None
        table.description = description
        # Cleared by a person is still a decision by a person -- but with
        # nothing to protect, the source goes back to unset so the engine may
        # fill it.
        table.description_source = "human" if description else None
    if "hidden" in body:
        table.hidden = bool(body["hidden"])
    models.db.session.commit()

    record_event(
        current_org,
        current_user._get_current_object(),
        {
            "action": "hide" if body.get("hidden") else "describe",
            "object_id": table_id,
            "object_type": "catalog_table",
        },
    )

    return json_response(
        {
            "id": table.id,
            "description": table.description,
            "description_source": table.description_source,
            "hidden": table.hidden,
        }
    )


@routes.route("/api/catalog/measures", methods=["GET"])
@login_required
@require_feature(features.MANAGE_CATALOG)
def catalog_measures():
    """
    Metrics mined from saved SQL, most-written first.

    A definition four teams wrote independently is a different proposition
    from one somebody tried once, which is what the count is for.
    """
    source_id = request.args.get("data_source_id", type=int)
    measures = models.CatalogMeasure.query.filter(
        models.CatalogMeasure.org == current_org,
        models.CatalogMeasure.data_source_id.in_(_curatable_source_ids() or [0]),
    )
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


@routes.route("/api/catalog/measures/<int:measure_id>", methods=["POST"])
@login_required
@require_feature(features.MANAGE_CATALOG)
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
    _curatable_or_404(measure.data_source_id)

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400, message="A JSON object is expected.")
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


@routes.route("/api/catalog/queries", methods=["GET"])
@login_required
@require_feature(features.MANAGE_CATALOG)
def catalog_verified_queries():
    """
    The queries somebody has confirmed, and the ones that have drifted.

    Both in one list, because the drifted ones are the work: a verification
    whose query has since been edited is a claim nobody currently stands
    behind, it is hidden from every model until a person looks again, and
    nothing else in the product will ever mention it. If this page does not
    show it, re-confirming never happens.
    """
    rows = (
        models.CatalogVerifiedQuery.query.join(models.Query, models.Query.id == models.CatalogVerifiedQuery.query_id)
        .filter(
            models.CatalogVerifiedQuery.org == current_org,
            models.Query.data_source_id.in_(_curatable_source_ids() or [0]),
        )
        .order_by(models.CatalogVerifiedQuery.verified_at.desc())
        .limit(200)
        .all()
    )

    listed = []
    for row in rows:
        query = row.query_rel
        if query is None or query.is_archived:
            continue
        listed.append(
            {
                "id": row.id,
                "query_id": row.query_id,
                "query_name": query.name,
                "data_source_id": query.data_source_id,
                "question": row.question,
                "note": row.note,
                "verified_by": row.verified_by.name if row.verified_by else None,
                "verified_at": row.verified_at,
                # The whole reason this endpoint exists rather than a flag on
                # the query serializer.
                "current": row.still_current,
            }
        )
    return json_response({"queries": listed})


@routes.route("/api/catalog/queries/<int:query_id>", methods=["GET", "POST", "DELETE"])
@login_required
@require_feature(features.MANAGE_CATALOG)
def verify_catalog_query(query_id):
    """
    Confirm a saved query as the right answer to a question, or withdraw it.

    The hash of the SQL is recorded with the confirmation, so the claim is
    about the text the curator read. Re-confirming an edited query is the
    same call again -- it rewrites the hash, which is the person saying they
    have read the new version.
    """
    query = models.Query.query.filter(models.Query.id == query_id, models.Query.org == current_org).first()
    if query is None:
        abort(404)
    # Curating the catalog is not a way to read a data source you are not in
    # a group for, and confirming SQL you cannot see would be a signature on
    # an unread document.
    require_access(query, current_user._get_current_object(), view_only)

    existing = models.CatalogVerifiedQuery.query.filter(
        models.CatalogVerifiedQuery.query_id == query.id,
        models.CatalogVerifiedQuery.org == current_org,
    ).first()

    if request.method == "GET":
        # Asked by the query page, which needs to know whether to show the
        # badge before anyone opens a menu. One row by a unique index.
        if existing is None:
            return json_response({"query_id": query_id, "verified": False})
        return json_response(
            {
                "query_id": query_id,
                "verified": True,
                "question": existing.question,
                "note": existing.note,
                "verified_by": existing.verified_by.name if existing.verified_by else None,
                "verified_at": existing.verified_at,
                "current": existing.still_current,
            }
        )

    if request.method == "DELETE":
        if existing is not None:
            models.db.session.delete(existing)
            models.db.session.commit()
        record_event(
            current_org,
            current_user._get_current_object(),
            {"action": "unverify", "object_id": query_id, "object_type": "query"},
        )
        return json_response({"query_id": query_id, "verified": False})

    body = request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        abort(400, message="A JSON object is expected.")

    if existing is None:
        # `query_id`, not `query_rel`. Assigning the relationship marks the
        # query dirty, so committing bumps `queries.updated_at` -- and then
        # confirming a query makes it jump to the top of every "recently
        # updated" list and the query page says it was edited just now.
        # Confirming is a statement about a query, not a change to it.
        existing = models.CatalogVerifiedQuery(org=current_org, query_id=query.id)
        models.db.session.add(existing)
    existing.verified_by = current_user._get_current_object()
    existing.verified_at = models.db.func.now()
    existing.query_hash = query.query_hash
    if "question" in body:
        existing.question = (body["question"] or "").strip() or None
    if "note" in body:
        existing.note = (body["note"] or "").strip() or None
    models.db.session.commit()

    record_event(
        current_org,
        current_user._get_current_object(),
        {"action": "verify", "object_id": query_id, "object_type": "query"},
    )
    return json_response(
        {
            "query_id": query_id,
            "verified": True,
            "question": existing.question,
            "note": existing.note,
            "current": True,
        }
    )


@routes.route("/api/catalog/score", methods=["GET"])
@login_required
@require_feature(features.MANAGE_CATALOG)
def catalog_score():
    """
    The last retrieval score, if a nightly run has recorded one.

    `null` where nothing has, which is the normal state: the score only exists
    where somebody has written a questions file and pointed
    `SQLDESK_CATALOG_EVAL_FILE` at it. The page shows nothing at all rather
    than a widget saying "not set up", which is furniture nobody removes.
    """
    from sqldesk.ai.eval import last_score

    return json_response({"score": last_score(current_org)})


@routes.route("/api/catalog/export", methods=["GET"])
@login_required
@require_feature(features.MANAGE_CATALOG)
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
    readable = _curatable_source_ids()
    sources = models.DataSource.query.filter(
        models.DataSource.org == current_org, models.DataSource.id.in_(readable or [0])
    )
    source_id = request.args.get("data_source_id", type=int)
    if source_id:
        sources = sources.filter(models.DataSource.id == source_id)
    sources = sources.order_by(models.DataSource.name).all()
    if source_id and not sources:
        abort(404)

    # One source at a time, and only the ones this person can read: the
    # export carries the SQL of every verified query, which is the source's
    # data as much as its tables are.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
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

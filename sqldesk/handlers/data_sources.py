import logging
import re
import time

from flask import make_response, request
from flask_restful import abort
from funcy import project
from sqlalchemy.exc import IntegrityError

from sqldesk import models
from sqldesk.handlers.base import (
    BaseResource,
    get_object_or_404,
    require_fields,
)
from sqldesk.permissions import (
    require_access,
    require_admin,
    require_permission,
    view_only,
)
from sqldesk.query_runner import (
    get_configuration_schema_for_query_runner_type,
    query_runners,
)
from sqldesk.serializers import serialize_job
from sqldesk.tasks.general import get_schema, test_connection
from sqldesk.utils import filter_none
from sqldesk.utils.configuration import ConfigurationContainer, ValidationError


class DataSourceTypeListResource(BaseResource):
    @require_admin
    def get(self):
        return [q.to_dict() for q in sorted(query_runners.values(), key=lambda q: q.name().lower())]


#: A queue name is used to build Redis keys and is read by a worker from an
#: environment variable, so it has to survive both. Letters, digits, dash and
#: underscore -- the same set every queue in SQLDesk already uses.
QUEUE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_QUEUE_NAME = 64


def _queue_problem(name):
    """
    Why this queue name cannot be used, or None.

    Said rather than silently corrected, because the consequence of a name
    nothing serves is a data source whose queries sit in a queue forever with
    nothing in any log to explain it -- and the person typing it is the one who
    also has to configure a worker for it.
    """
    if not name:
        return None
    if len(name) > MAX_QUEUE_NAME:
        return "A queue name is at most {} characters.".format(MAX_QUEUE_NAME)
    if not QUEUE_NAME.match(name):
        return "A queue name may use letters, digits, dashes and underscores only."
    return None


class DataSourceResource(BaseResource):
    def get(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        require_access(data_source, self.current_user, view_only)

        ds = {}
        if self.current_user.has_permission("list_data_sources"):
            # if it's a non-admin, limit the information
            ds = data_source.to_dict(all=self.current_user.has_permission("admin"))

        # add view_only info, required for frontend permissions
        ds["view_only"] = all(project(data_source.groups, self.current_user.group_ids).values())
        self.record_event({"action": "view", "object_id": data_source_id, "object_type": "datasource"})
        return ds

    @require_admin
    def post(self, data_source_id):
        data_source = models.DataSource.get_by_id_and_org(data_source_id, self.current_org)
        req = request.get_json(True)

        schema = get_configuration_schema_for_query_runner_type(req["type"])
        if schema is None:
            abort(400)
        try:
            data_source.options.set_schema(schema)
            data_source.options.update(filter_none(req["options"]))
        except ValidationError:
            abort(400)

        data_source.type = req["type"]
        data_source.name = req["name"]
        # Optional, and absent means "leave it alone" rather than "clear it":
        # the data source form is saved for all sorts of reasons and none of
        # them should silently discard somebody's notes.
        if "description" in req:
            data_source.description = req["description"] or None

        # Which queues this source's queries go on. Until now the only way to
        # set these was an UPDATE against the `data_sources` table, which the
        # Administration page actually told people to run -- and giving a slow
        # warehouse a queue of its own is the single most useful thing an
        # administrator can do to stop it starving everything else.
        #
        # Absent means "leave it alone", like the description. Blank means
        # "back to the default", because a queue name somebody has emptied is
        # a queue name they have withdrawn.
        for field, default in (("queue_name", "queries"), ("scheduled_queue_name", "scheduled_queries")):
            if field in req:
                name = (req[field] or "").strip()
                problem = _queue_problem(name)
                if problem:
                    abort(400, message=problem)
                setattr(data_source, field, name or default)

        models.db.session.add(data_source)

        try:
            models.db.session.commit()
        except IntegrityError as e:
            if req["name"] in str(e):
                abort(
                    400,
                    message="Data source with the name {} already exists.".format(req["name"]),
                )

            abort(400)

        self.record_event({"action": "edit", "object_id": data_source.id, "object_type": "datasource"})

        return data_source.to_dict(all=True)

    @require_admin
    def delete(self, data_source_id):
        data_source = models.DataSource.get_by_id_and_org(data_source_id, self.current_org)
        data_source.delete()

        self.record_event(
            {
                "action": "delete",
                "object_id": data_source_id,
                "object_type": "datasource",
            }
        )

        return make_response("", 204)


class DataSourceListResource(BaseResource):
    @require_permission("list_data_sources")
    def get(self):
        if self.current_user.has_permission("admin"):
            data_sources = models.DataSource.all(self.current_org)
        else:
            data_sources = models.DataSource.all(self.current_org, group_ids=self.current_user.group_ids)

        response = {}
        for ds in data_sources:
            if ds.id in response:
                continue

            try:
                d = ds.to_dict()
                d["view_only"] = all(project(ds.groups, self.current_user.group_ids).values())
                # The editor leaves these out of its picker; Streams uses them.
                d["streams_only"] = ds.streams_only
                response[ds.id] = d
            except AttributeError:
                logging.exception("Error with DataSource#to_dict (data source id: %d)", ds.id)

        self.record_event(
            {
                "action": "list",
                "object_id": "admin/data_sources",
                "object_type": "datasource",
            }
        )

        return sorted(list(response.values()), key=lambda d: d["name"].lower())

    @require_admin
    def post(self):
        req = request.get_json(True)
        require_fields(req, ("options", "name", "type"))

        schema = get_configuration_schema_for_query_runner_type(req["type"])
        if schema is None:
            abort(400)

        config = ConfigurationContainer(filter_none(req["options"]), schema)
        if not config.is_valid():
            abort(400)

        try:
            datasource = models.DataSource.create_with_group(
                org=self.current_org,
                name=req["name"],
                type=req["type"],
                options=config,
                description=req.get("description") or None,
            )

            models.db.session.commit()
        except IntegrityError as e:
            if req["name"] in str(e):
                abort(
                    400,
                    message="Data source with the name {} already exists.".format(req["name"]),
                )

            abort(400)

        self.record_event(
            {
                "action": "create",
                "object_id": datasource.id,
                "object_type": "datasource",
            }
        )

        return datasource.to_dict(all=True)


class DataSourceSchemaResource(BaseResource):
    def get(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        require_access(data_source, self.current_user, view_only)
        refresh = request.args.get("refresh") is not None

        if not refresh:
            cached_schema = data_source.get_cached_schema()

            if cached_schema is not None:
                return {"schema": cached_schema}

        job = get_schema.delay(data_source.id, refresh, meta=self.job_meta())

        return serialize_job(job)


class DataSourcePauseResource(BaseResource):
    @require_admin
    def post(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        data = request.get_json(force=True, silent=True)
        if data:
            reason = data.get("reason")
        else:
            reason = request.args.get("reason")

        data_source.pause(reason)
        models.db.session.commit()

        self.record_event(
            {
                "action": "pause",
                "object_id": data_source.id,
                "object_type": "datasource",
            }
        )
        return data_source.to_dict()

    @require_admin
    def delete(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        data_source.resume()
        models.db.session.commit()

        self.record_event(
            {
                "action": "resume",
                "object_id": data_source.id,
                "object_type": "datasource",
            }
        )
        return data_source.to_dict()


class DataSourceTestResource(BaseResource):
    @require_admin
    def post(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)

        response = {}

        job = test_connection.delay(data_source.id)
        while not (job.is_finished or job.is_failed):
            time.sleep(1)
            job.refresh()

        if isinstance(job.result, Exception):
            response = {"message": str(job.result), "ok": False}
        else:
            response = {"message": "success", "ok": True}

        self.record_event(
            {
                "action": "test",
                "object_id": data_source_id,
                "object_type": "datasource",
                "result": response,
            }
        )
        return response

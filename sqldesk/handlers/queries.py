import sqlparse
from flask import jsonify, request, url_for
from flask_login import login_required
from flask_restful import abort
from funcy import partial
from sqlalchemy.orm.exc import StaleDataError

from sqldesk import history, models, settings
from sqldesk.authentication.org_resolving import current_org
from sqldesk.handlers.base import (
    BaseResource,
    filter_by_tags,
    get_object_or_404,
    org_scoped_rule,
    paginate,
    routes,
)
from sqldesk.handlers.base import order_results as _order_results
from sqldesk.handlers.query_results import run_query
from sqldesk.models.parameterized_query import ParameterizedQuery
from sqldesk.permissions import (
    can_modify,
    not_view_only,
    require_access,
    require_admin_or_owner,
    require_object_modify_permission,
    require_permission,
    view_only,
)
from sqldesk.serializers import QuerySerializer
from sqldesk.utils import collect_parameters_from_request

# Ordering map for relationships
order_map = {
    "name": "lowercase_name",
    "-name": "-lowercase_name",
    "created_at": "created_at",
    "-created_at": "-created_at",
    "schedule": "interval",
    "-schedule": "-interval",
    "runtime": "query_results-runtime",
    "-runtime": "-query_results-runtime",
    # A plain column on query_results, denormalised at write time, and already
    # loaded by all_queries() -- so ordering by it costs nothing extra and does
    # not widen the join onto the result payload.
    "row_count": "query_results-row_count",
    "-row_count": "-query_results-row_count",
    "executed_at": "query_results-retrieved_at",
    "-executed_at": "-query_results-retrieved_at",
    "created_by": "users-name",
    "-created_by": "-users-name",
    "starred_at": "favorites-created_at",
    "-starred_at": "-favorites-created_at",
}

order_results = partial(_order_results, default_order="-created_at", allowed_orders=order_map)


def filter_by_kind(results):
    """
    `?kind=streaming` for the queries that read a stream, `?kind=saved` for the
    rest.

    The two halves do not overlap, which is the point: a streaming query in the
    ordinary list would be a thing filed in two places, and "where is my query"
    would have two answers. Absent, the filter does nothing -- search wants
    both, because somebody searching by name does not know which half a thing
    is in.

    A query's kind is its data source's type: one foreign key, so there is no
    column to keep in step and nothing that can go stale. Asked of the
    registered runners through `streaming_source_types()`, so a second
    streaming connector needs no second list.

    A query with no data source at all would fall out of both halves, because
    `NOT IN` against a NULL is NULL rather than true. It is left that way
    deliberately: every list here is built on `all_queries()`, which joins
    `DataSourceGroup` to decide what this person may see, so a query without a
    data source never reaches one of these lists in the first place. A list
    that does not make that join would have to say what it wants of those rows.
    """
    kind = request.args.get("kind")
    if kind not in ("streaming", "saved"):
        return results

    reads_a_stream = models.Query.data_source_id.in_(
        models.db.session.query(models.DataSource.id).filter(
            models.DataSource.type.in_(models.streaming_source_types())
        )
    )
    return results.filter(reads_a_stream if kind == "streaming" else ~reads_a_stream)


@routes.route(org_scoped_rule("/api/queries/format"), methods=["POST"])
@login_required
def format_sql_query(org_slug=None):
    """
    Formats an SQL query using the Python ``sqlparse`` formatter.

    :<json string query: The SQL text to format
    :>json string query: Formatted SQL text
    """
    arguments = request.get_json(force=True)
    query = arguments.get("query", "")

    return jsonify({"query": sqlparse.format(query, **settings.SQLPARSE_FORMAT_OPTIONS)})


def require_valid_schedule(query_def):
    """Reject a cron expression croniter cannot read.

    Without this the expression is stored happily and only fails later, inside
    outdated_queries -- which reacts by disabling the query's schedule and
    logging. The query then quietly stops refreshing and the person who set it
    is told nothing.
    """
    schedule = query_def.get("schedule")
    if not isinstance(schedule, dict):
        return

    cron = schedule.get("cron")
    if cron and not models.is_valid_cron(cron):
        abort(400, message="'{}' is not a valid cron expression.".format(cron))


class QuerySearchResource(BaseResource):
    @require_permission("view_query")
    def get(self):
        """
        Search query text, names, and descriptions.

        :qparam string q: Search term
        :qparam number include_drafts: Whether to include draft in results

        Responds with a list of :ref:`query <query-response-label>` objects.
        """
        term = request.args.get("q", "")
        if not term:
            return []

        include_drafts = request.args.get("include_drafts") is not None

        self.record_event({"action": "search", "object_type": "query", "term": term})

        # this redirects to the new query list API that is aware of search
        new_location = url_for(
            "queries",
            q=term,
            org_slug=current_org.slug,
            drafts="true" if include_drafts else "false",
        )
        return {}, 301, {"Location": new_location}


class QueryRecentResource(BaseResource):
    @require_permission("view_query")
    def get(self):
        """
        Retrieve up to 10 queries recently modified by the user.

        Responds with a list of :ref:`query <query-response-label>` objects.
        """

        results = models.Query.by_user(self.current_user).order_by(models.Query.updated_at.desc()).limit(10)
        return QuerySerializer(results, with_last_modified_by=False, with_user=False).serialize()


class BaseQueryListResource(BaseResource):
    def get_queries(self, search_term):
        if search_term:
            results = models.Query.search(
                search_term,
                self.current_user.group_ids,
                self.current_user.id,
                include_drafts=True,
                multi_byte_search=current_org.get_setting("multi_byte_search_enabled"),
            )
        else:
            results = models.Query.all_queries(self.current_user.group_ids, self.current_user.id, include_drafts=True)
        return filter_by_tags(results, models.Query.tags)

    @require_permission("view_query")
    def get(self):
        """
        Retrieve a list of queries.

        :qparam number page_size: Number of queries to return per page
        :qparam number page: Page number to retrieve
        :qparam number order: Name of column to order by
        :qparam number q: Full text search term

        Responds with an array of :ref:`query <query-response-label>` objects.
        """
        # See if we want to do full-text search or just regular queries
        search_term = request.args.get("q", "")

        queries = self.get_queries(search_term)

        results = filter_by_tags(queries, models.Query.tags)
        results = filter_by_kind(results)

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        ordered_results = order_results(results, fallback=not bool(search_term))

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)

        response = paginate(
            ordered_results,
            page=page,
            page_size=page_size,
            serializer=QuerySerializer,
            with_stats=True,
            with_last_modified_by=False,
        )

        # Failing count over the WHOLE filtered set, not just this page, so a
        # header can say "2 failing" truthfully. One COUNT against the same
        # query the page came from, which keeps it consistent with whatever
        # search and tag filters are applied.
        response["failing_count"] = ordered_results.filter(models.Query.schedule_failures > 0).count()

        if search_term:
            self.record_event({"action": "search", "object_type": "query", "term": search_term})
        else:
            self.record_event({"action": "list", "object_type": "query"})

        return response


#: Fields the client never gets to set: who owns a query, which organization
#: it belongs to, whether it is archived, what its hash is.
NOT_FROM_THE_CLIENT = (
    "id",
    "created_at",
    "api_key",
    "visualizations",
    "latest_query_data",
    "user",
    "user_id",
    "last_modified_by",
    "last_modified_by_id",
    "org",
    "org_id",
    "is_archived",
    "query_hash",
    "schedule_failures",
)

#: The fields that decide what runs on the data source.
RUNS_ON_THE_SOURCE = ("query", "query_text", "options", "schedule")


def require_result_from_the_same_source(query_def, data_source_id, org):
    """
    The query page saves the result it just ran, so `latest_query_data_id`
    is the client's to set -- but only to a result of the query's own data
    source. Any result in the organization was accepted, and the dropdown
    endpoint then served its rows to whoever could read the query.
    """
    result_id = query_def.get("latest_query_data_id")
    if result_id is None:
        return
    result = get_object_or_404(models.QueryResult.get_by_id_and_org, result_id, org)
    if result.data_source_id != data_source_id:
        abort(400, message="That result is not from this query's data source.")


def require_permission_to_schedule(user):
    if not user.has_permission("schedule_query"):
        abort(403, message="You do not have permission to schedule queries.")


def require_access_to_dropdown_queries(user, query_def):
    """
    Each dropdown query on its own. Checked together, one query the user
    could read made the group check pass for one they could not, whose
    values the dropdown endpoint then served.
    """
    parameters = query_def.get("options", {}).get("parameters", [])
    dropdown_query_ids = set([str(p["queryId"]) for p in parameters if p["type"] == "query"])

    for dropdown_query_id in dropdown_query_ids:
        try:
            dropdown_query = models.Query.get_by_id_and_org(dropdown_query_id, user.org)
        except (models.NoResultFound, ValueError):
            abort(
                400,
                message="You are trying to associate a dropdown query that does not have a matching group. "
                "Please verify the dropdown query id you are trying to associate with this query.",
            )
        require_access(dropdown_query, user, view_only)


class QueryListResource(BaseQueryListResource):
    @require_permission("create_query")
    def post(self):
        """
        Create a new query.

        :<json number data_source_id: The ID of the data source this query will run on
        :<json string query: Query text
        :<json string name:
        :<json string description:
        :<json string schedule: Schedule interval, in seconds, for repeated execution of this query
        :<json object options: Query options

        .. _query-response-label:

        :>json number id: Query ID
        :>json number latest_query_data_id: ID for latest output data from this query
        :>json string name:
        :>json string description:
        :>json string query: Query text
        :>json string query_hash: Hash of query text
        :>json string schedule: Schedule interval, in seconds, for repeated execution of this query
        :>json string api_key: Key for public access to this query's results.
        :>json boolean is_archived: Whether this query is displayed in indexes and search results or not.
        :>json boolean is_draft: Whether this query is a draft or not
        :>json string updated_at: Time of last modification, in ISO format
        :>json string created_at: Time of creation, in ISO format
        :>json number data_source_id: ID of the data source this query will run on
        :>json object options: Query options
        :>json number version: Revision version (for update conflict avoidance)
        :>json number user_id: ID of query creator
        :>json number last_modified_by_id: ID of user who last modified this query
        :>json string retrieved_at: Time when query results were last retrieved, in ISO format (may be null)
        :>json number runtime: Runtime of last query execution, in seconds (may be null)
        """
        query_def = request.get_json(force=True)
        require_valid_schedule(query_def)
        data_source = models.DataSource.get_by_id_and_org(query_def.pop("data_source_id"), self.current_org)
        require_access(data_source, self.current_user, not_view_only)
        require_access_to_dropdown_queries(self.current_user, query_def)

        for field in NOT_FROM_THE_CLIENT:
            query_def.pop(field, None)
        if query_def.get("schedule"):
            require_permission_to_schedule(self.current_user)
        require_result_from_the_same_source(query_def, data_source.id, self.current_org)

        query_def["query_text"] = query_def.pop("query")
        query_def["user"] = self.current_user
        query_def["data_source"] = data_source
        query_def["org"] = self.current_org
        query_def["is_draft"] = True
        query = models.Query.create(**query_def)
        models.db.session.add(query)
        models.db.session.commit()
        query.update_latest_result_by_query_hash()
        models.db.session.commit()

        self.record_event({"action": "create", "object_id": query.id, "object_type": "query"})

        return QuerySerializer(query, with_visualizations=True, with_api_key=True).serialize()


class QueryArchiveResource(BaseQueryListResource):
    def get_queries(self, search_term):
        if search_term:
            return models.Query.search(
                search_term,
                self.current_user.group_ids,
                self.current_user.id,
                include_drafts=False,
                include_archived=True,
                multi_byte_search=current_org.get_setting("multi_byte_search_enabled"),
            )
        else:
            return models.Query.all_queries(
                self.current_user.group_ids,
                self.current_user.id,
                include_drafts=False,
                include_archived=True,
            )


class MyQueriesResource(BaseResource):
    @require_permission("view_query")
    def get(self):
        """
        Retrieve a list of queries created by the current user.

        :qparam number page_size: Number of queries to return per page
        :qparam number page: Page number to retrieve
        :qparam number order: Name of column to order by
        :qparam number search: Full text search term

        Responds with an array of :ref:`query <query-response-label>` objects.
        """
        search_term = request.args.get("q", "")
        if search_term:
            results = models.Query.search_by_user(
                search_term,
                self.current_user,
                multi_byte_search=current_org.get_setting("multi_byte_search_enabled"),
            )
        else:
            results = models.Query.by_user(self.current_user)

        results = filter_by_tags(results, models.Query.tags)
        results = filter_by_kind(results)

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        ordered_results = order_results(results, fallback=not bool(search_term))

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        return paginate(
            ordered_results,
            page,
            page_size,
            QuerySerializer,
            with_stats=True,
            with_last_modified_by=False,
        )


class QueryResource(BaseResource):
    @require_permission("edit_query")
    def post(self, query_id):
        """
        Modify a query.

        :param query_id: ID of query to update
        :<json number data_source_id: The ID of the data source this query will run on
        :<json string query: Query text
        :<json string name:
        :<json string description:
        :<json string schedule: Schedule interval, in seconds, for repeated execution of this query
        :<json object options: Query options

        Responds with the updated :ref:`query <query-response-label>` object.
        """
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        query_def = request.get_json(force=True)
        require_valid_schedule(query_def)

        require_object_modify_permission(query, self.current_user)
        require_access_to_dropdown_queries(self.current_user, query_def)

        for field in NOT_FROM_THE_CLIENT:
            query_def.pop(field, None)

        # Editing the text, the parameters or the schedule is deciding what
        # runs on the data source, which the editor only lets people with full
        # access to it do. The API let a view-only owner, or somebody granted
        # editing rights on the query alone, do it anyway.
        if query.data_source is not None and any(field in query_def for field in RUNS_ON_THE_SOURCE):
            require_access(query.data_source, self.current_user, not_view_only)
        if "schedule" in query_def and query_def["schedule"] != query.schedule:
            require_permission_to_schedule(self.current_user)
        require_result_from_the_same_source(
            query_def, query_def.get("data_source_id", query.data_source_id), self.current_org
        )

        if "query" in query_def:
            query_def["query_text"] = query_def.pop("query")

        if "tags" in query_def:
            query_def["tags"] = [tag for tag in query_def["tags"] if tag]

        if "data_source_id" in query_def:
            data_source = models.DataSource.get_by_id_and_org(query_def["data_source_id"], self.current_org)
            require_access(data_source, self.current_user, not_view_only)

        query_def["last_modified_by"] = self.current_user
        # SQLAlchemy handles the case where a concurrent transaction beats us
        # to the update. But we still have to make sure that we're not starting
        # out behind.
        if "version" in query_def and query_def["version"] != query.version:
            abort(409)

        try:
            self.update_model(query, query_def)
            # The version somebody can look at later. `changes` has recorded
            # queries being created and archived since long before this fork and
            # never recorded one being edited, so the history it held was almost
            # empty -- the handler set a `changed_by` that nothing read.
            #
            # Only when something moved: the editor sends the whole query
            # whether or not anything in it did, and a version that says nothing
            # happened is a version somebody has to read to find that out.
            if query.pending_changes():
                query.record_changes(self.current_user)
            models.db.session.commit()
            query.update_latest_result_by_query_hash()
            models.db.session.commit()
        except StaleDataError:
            abort(409)

        return QuerySerializer(query, with_visualizations=True, with_api_key=True).serialize()

    @require_permission("view_query")
    def get(self, query_id):
        """
        Retrieve a query.

        :param query_id: ID of query to fetch

        Responds with the :ref:`query <query-response-label>` contents.
        """
        q = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_access(q, self.current_user, view_only)

        result = QuerySerializer(q, with_visualizations=True, with_api_key=True).serialize()
        if self.current_user.is_api_user():
            # A dashboard's public token, or the query's own key, gets what the
            # public dashboard shows: the chart, not the SQL or the author.
            # A dashboard token does not get the query's own key either; the
            # query's key is handed back only to the caller already holding it,
            # because the embed page builds its download links from it.
            for field in ("query", "user", "last_modified_by", "schedule"):
                result.pop(field, None)
            if self.current_user.id != q.api_key:
                result.pop("api_key", None)
        elif not can_modify(q, self.current_user):
            # The key is a credential that outlives group membership; it goes
            # to the people who may also regenerate it.
            result.pop("api_key", None)
        result["can_edit"] = can_modify(q, self.current_user)

        self.record_event({"action": "view", "object_id": query_id, "object_type": "query"})

        return result

    # TODO: move to resource of its own? (POST /queries/{id}/archive)
    def delete(self, query_id):
        """
        Archives a query.

        :param query_id: ID of query to archive
        """
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_admin_or_owner(query.user_id)
        query.archive(self.current_user)
        models.db.session.commit()


class QueryPermanentDeleteResource(BaseResource):
    """
    Delete a query outright, rather than hiding it.

    Its own path rather than a flag on the archive endpoint, because the two
    are not variations of one action: archiving is reversible for the query
    itself, and this is not reversible at all. A query that was archived can
    be deleted from here as well -- that is the usual route, since people
    archive things to get rid of them and then find the archive full.
    """

    @require_permission("edit_query")
    def delete(self, query_id):
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_admin_or_owner(query.user_id)

        # Recorded before it goes: the audit keeps the name, because
        # afterwards there is nothing left to look it up from.
        self.record_event(
            {
                "action": "delete",
                "object_id": query_id,
                "object_type": "query",
                "name": query.name,
            }
        )
        removed = query.delete_permanently()
        models.db.session.commit()
        return {"deleted": removed}


class QueryRegenerateApiKeyResource(BaseResource):
    @require_permission("edit_query")
    def post(self, query_id):
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_admin_or_owner(query.user_id)
        query.regenerate_api_key()
        models.db.session.commit()

        self.record_event(
            {
                "action": "regnerate_api_key",
                "object_id": query_id,
                "object_type": "query",
            }
        )

        # with_api_key, or the one thing the caller asked for is the one thing
        # missing from the answer: the dialog reads `api_key` off this response
        # and would blank its own field and build `?api_key=undefined` URLs.
        return QuerySerializer(query, with_api_key=True).serialize()


class QueryForkResource(BaseResource):
    @require_permission("edit_query")
    def post(self, query_id):
        """
        Creates a new query, copying the query text from an existing one.

        :param query_id: ID of query to fork

        Responds with created :ref:`query <query-response-label>` object.
        """
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_access(query.data_source, self.current_user, not_view_only)
        forked_query = query.fork(self.current_user)
        models.db.session.commit()

        self.record_event({"action": "fork", "object_id": query_id, "object_type": "query"})

        return QuerySerializer(forked_query, with_visualizations=True, with_api_key=True).serialize()


class QueryRefreshResource(BaseResource):
    def post(self, query_id):
        """
        Execute a query, updating the query object with the results.

        :param query_id: ID of query to execute

        Responds with query task details.
        """
        # TODO: this should actually check for permissions, but because currently you can only
        # get here either with a user API key or a query one, we can just check whether it's
        # an api key (meaning this is a query API key, which only grants read access).
        if self.current_user.is_api_user():
            abort(403, message="Please use a user API key.")

        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_access(query, self.current_user, not_view_only)

        parameter_values = collect_parameters_from_request(request.args)
        parameterized_query = ParameterizedQuery(query.query_text, org=self.current_org)
        should_apply_auto_limit = query.options.get("apply_auto_limit", False)
        return run_query(parameterized_query, parameter_values, query.data_source, query.id, should_apply_auto_limit)


class QueryTagsResource(BaseResource):
    def get(self):
        """
        Returns all query tags including those for drafts.
        """
        tags = models.Query.all_tags(self.current_user, include_drafts=True)
        return {"tags": [{"name": name, "count": count} for name, count in tags]}


class QueryFavoriteListResource(BaseResource):
    def get(self):
        search_term = request.args.get("q")

        if search_term:
            base_query = models.Query.search(
                search_term,
                self.current_user.group_ids,
                include_drafts=True,
                limit=None,
                multi_byte_search=current_org.get_setting("multi_byte_search_enabled"),
            )
            favorites = models.Query.favorites(self.current_user, base_query=base_query)
        else:
            favorites = models.Query.favorites(self.current_user)

        favorites = filter_by_tags(favorites, models.Query.tags)
        favorites = filter_by_kind(favorites)

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        ordered_favorites = order_results(favorites, fallback=not bool(search_term))

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        response = paginate(
            ordered_favorites,
            page,
            page_size,
            QuerySerializer,
            with_stats=True,
            with_last_modified_by=False,
        )

        self.record_event(
            {
                "action": "load_favorites",
                "object_type": "query",
                "params": {
                    "q": search_term,
                    "tags": request.args.getlist("tags"),
                    "page": page,
                },
            }
        )

        return response


class QueryVersionListResource(BaseResource):
    @require_permission("view_query")
    def get(self, query_id):
        """
        This query's versions, newest first.

        Anyone who may read the query may read its history. The SQL is the
        whole of what a version holds, and they can already read the SQL.
        """
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_access(query, self.current_user, view_only)

        return {"versions": history.versions(query)}


class QueryVersionRestoreResource(BaseResource):
    @require_permission("edit_query")
    def post(self, query_id, change_id):
        """
        Put a version back, as a new version.

        Never a rewrite: restoring version 2 writes a new one that says what 2
        said, and version 2 stays where it was.

        It asks for exactly what editing by hand asks for. A restore writes the
        SQL, the parameters and the schedule, which is deciding what runs on the
        data source -- so somebody with view-only access to the source, or
        editing rights on this query alone, cannot do by restoring what they
        cannot do by typing.
        """
        query = get_object_or_404(models.Query.get_by_id_and_org, query_id, self.current_org)
        require_object_modify_permission(query, self.current_user)
        if query.data_source is not None:
            require_access(query.data_source, self.current_user, not_view_only)

        version = history.version(query, change_id)
        if version is None:
            abort(404, message="No such version of this query.")

        taken = history.snapshot(version)
        if taken.get("schedule") != query.schedule:
            require_permission_to_schedule(self.current_user)
        # The dropdowns a version names, as saving them by hand would check:
        # otherwise a version that once pointed at a query this person cannot
        # read gets them its values through the dropdown endpoint.
        require_access_to_dropdown_queries(self.current_user, {"options": taken.get("options") or {}})
        # A schedule that was valid when it was saved and is not now -- a cron
        # expression a later version of croniter rejects, an interval below a
        # minimum somebody has since set. Caught here rather than stored again
        # and failing quietly in the refresh loop.
        require_valid_schedule({"schedule": taken.get("schedule")})

        moved = history.restore(query, version)
        if moved:
            query.last_modified_by = self.current_user
            query.record_changes(self.current_user)
            models.db.session.commit()

        self.record_event(
            {
                "action": "restore_version",
                "object_id": query.id,
                "object_type": "query",
                "params": {"change_id": version.id, "restored": moved},
            }
        )

        return QuerySerializer(query, with_visualizations=True, with_api_key=True).serialize()

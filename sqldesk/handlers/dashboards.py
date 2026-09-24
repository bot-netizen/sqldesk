from flask import request, url_for
from flask_restful import abort
from funcy import partial, project
from sqlalchemy.orm.exc import StaleDataError

from sqldesk import live, models
from sqldesk.handlers.base import (
    BaseResource,
    filter_by_tags,
    get_object_or_404,
    paginate,
)
from sqldesk.handlers.base import order_results as _order_results
from sqldesk.permissions import (
    can_modify,
    require_admin_or_owner,
    require_object_modify_permission,
    require_permission,
)
from sqldesk.security import csp_allows_embeding
from sqldesk.serializers import DashboardSerializer, public_dashboard
from sqldesk.utils import utcnow

# Ordering map for relationships
order_map = {
    "name": "lowercase_name",
    "-name": "-lowercase_name",
    "created_at": "created_at",
    "-created_at": "-created_at",
    "starred_at": "favorites-created_at",
    "-starred_at": "-favorites-created_at",
}

order_results = partial(_order_results, default_order="-created_at", allowed_orders=order_map)


class DashboardListResource(BaseResource):
    @require_permission("list_dashboards")
    def get(self):
        """
        Lists all accessible dashboards.

        :qparam number page_size: Number of queries to return per page
        :qparam number page: Page number to retrieve
        :qparam number order: Name of column to order by
        :qparam number q: Full text search term

        Responds with an array of :ref:`dashboard <dashboard-response-label>`
        objects.
        """
        search_term = request.args.get("q")

        if search_term:
            results = models.Dashboard.search(
                self.current_org,
                self.current_user.group_ids,
                self.current_user.id,
                search_term,
            )
        else:
            results = models.Dashboard.all(self.current_org, self.current_user.group_ids, self.current_user.id)

        results = filter_by_tags(results, models.Dashboard.tags)

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
            serializer=DashboardSerializer,
        )

        if search_term:
            self.record_event({"action": "search", "object_type": "dashboard", "term": search_term})
        else:
            self.record_event({"action": "list", "object_type": "dashboard"})

        return response

    @require_permission("create_dashboard")
    def post(self):
        """
        Creates a new dashboard.

        :<json string name: Dashboard name

        Responds with a :ref:`dashboard <dashboard-response-label>`.
        """
        dashboard_properties = request.get_json(force=True)
        dashboard = models.Dashboard(
            name=dashboard_properties["name"],
            org=self.current_org,
            user=self.current_user,
            is_draft=True,
            layout=[],
        )
        models.db.session.add(dashboard)
        models.db.session.commit()
        return DashboardSerializer(dashboard).serialize()


class MyDashboardsResource(BaseResource):
    @require_permission("list_dashboards")
    def get(self):
        """
        Retrieve a list of dashboards created by the current user.

        :qparam number page_size: Number of dashboards to return per page
        :qparam number page: Page number to retrieve
        :qparam number order: Name of column to order by
        :qparam number search: Full text search term

        Responds with an array of :ref:`dashboard <dashboard-response-label>`
        objects.
        """
        search_term = request.args.get("q", "")
        if search_term:
            results = models.Dashboard.search_by_user(search_term, self.current_user)
        else:
            results = models.Dashboard.by_user(self.current_user)

        results = filter_by_tags(results, models.Dashboard.tags)

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        ordered_results = order_results(results, fallback=not bool(search_term))

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        return paginate(ordered_results, page, page_size, DashboardSerializer)


class DashboardResource(BaseResource):
    @require_permission("list_dashboards")
    def get(self, dashboard_id=None):
        """
        Retrieves a dashboard.

        :qparam number id: Id of dashboard to retrieve.

        .. _dashboard-response-label:

        :>json number id: Dashboard ID
        :>json string name:
        :>json string slug:
        :>json number user_id: ID of the dashboard creator
        :>json string created_at: ISO format timestamp for dashboard creation
        :>json string updated_at: ISO format timestamp for last dashboard modification
        :>json number version: Revision number of dashboard
        :>json boolean dashboard_filters_enabled: Whether filters are enabled or not
        :>json boolean is_archived: Whether this dashboard has been removed from the index or not
        :>json boolean is_draft: Whether this dashboard is a draft or not.
        :>json array layout: Array of arrays containing widget IDs, corresponding to the rows and columns the widgets are displayed in
        :>json array widgets: Array of arrays containing :ref:`widget <widget-response-label>` data
        :>json object options: Dashboard options

        .. _widget-response-label:

        Widget structure:

        :>json number widget.id: Widget ID
        :>json number widget.width: Widget size
        :>json object widget.options: Widget options
        :>json number widget.dashboard_id: ID of dashboard containing this widget
        :>json string widget.text: Widget contents, if this is a text-box widget
        :>json object widget.visualization: Widget contents, if this is a visualization widget
        :>json string widget.created_at: ISO format timestamp for widget creation
        :>json string widget.updated_at: ISO format timestamp for last widget modification
        """
        if request.args.get("legacy") is not None:
            fn = models.Dashboard.get_by_slug_and_org
        else:
            fn = models.Dashboard.get_by_id_and_org

        dashboard = get_object_or_404(fn, dashboard_id, self.current_org)
        response = DashboardSerializer(dashboard, with_widgets=True, user=self.current_user).serialize()

        api_key = models.ApiKey.get_by_object(dashboard)
        if api_key:
            response["public_url"] = url_for(
                "sqldesk.public_dashboard",
                token=api_key.api_key,
                org_slug=self.current_org.slug,
                _external=True,
            )
            response["api_key"] = api_key.api_key

        response["can_edit"] = can_modify(dashboard, self.current_user)

        self.record_event({"action": "view", "object_id": dashboard.id, "object_type": "dashboard"})

        return response

    @require_permission("edit_dashboard")
    def post(self, dashboard_id):
        """
        Modifies a dashboard.

        :qparam number id: Id of dashboard to retrieve.

        Responds with the updated :ref:`dashboard <dashboard-response-label>`.

        :status 200: success
        :status 409: Version conflict -- dashboard modified since last read
        """
        dashboard_properties = request.get_json(force=True)
        # TODO: either convert all requests to use slugs or ids
        dashboard = models.Dashboard.get_by_id_and_org(dashboard_id, self.current_org)

        require_object_modify_permission(dashboard, self.current_user)

        updates = project(
            dashboard_properties,
            (
                "name",
                "layout",
                "version",
                "tags",
                "is_draft",
                "is_archived",
                "dashboard_filters_enabled",
                "options",
            ),
        )

        # SQLAlchemy handles the case where a concurrent transaction beats us
        # to the update. But we still have to make sure that we're not starting
        # out behind.
        if "version" in updates and updates["version"] != dashboard.version:
            abort(409)

        updates["changed_by"] = self.current_user

        self.update_model(dashboard, updates)
        models.db.session.add(dashboard)
        try:
            models.db.session.commit()
        except StaleDataError:
            abort(409)

        result = DashboardSerializer(dashboard, with_widgets=True, user=self.current_user).serialize()

        self.record_event({"action": "edit", "object_id": dashboard.id, "object_type": "dashboard"})

        return result

    @require_permission("edit_dashboard")
    def delete(self, dashboard_id):
        """
        Archives a dashboard.

        :qparam number id: Id of dashboard to retrieve.

        Responds with the archived :ref:`dashboard <dashboard-response-label>`.
        """
        dashboard = models.Dashboard.get_by_id_and_org(dashboard_id, self.current_org)
        dashboard.is_archived = True
        dashboard.record_changes(changed_by=self.current_user)
        models.db.session.add(dashboard)
        d = DashboardSerializer(dashboard, with_widgets=True, user=self.current_user).serialize()
        models.db.session.commit()

        self.record_event({"action": "archive", "object_id": dashboard.id, "object_type": "dashboard"})

        return d


class PublicDashboardResource(BaseResource):
    decorators = BaseResource.decorators + [csp_allows_embeding]

    def get(self, token):
        """
        Retrieve a public dashboard.

        :param token: An API key for a public dashboard.
        :>json array widgets: An array of arrays of :ref:`public widgets <public-widget-label>`, corresponding to the rows and columns the widgets are displayed in
        """
        if self.current_org.get_setting("disable_public_urls"):
            abort(400, message="Public URLs are disabled.")

        if not isinstance(self.current_user, models.ApiUser):
            api_key = get_object_or_404(models.ApiKey.get_by_api_key, token)
            dashboard = api_key.object
        else:
            dashboard = self.current_user.object

        return public_dashboard(dashboard)


class DashboardLiveResource(BaseResource):
    @require_permission("edit_dashboard")
    def post(self, dashboard_id):
        """
        Turn a dashboard live, change how often it refreshes, pause or resume
        it, or turn it off.

        :<json number interval: seconds between refreshes (30, 60, 120 or 300),
                                or null to turn the dashboard off
        :<json boolean paused: pause or resume a live dashboard for everyone
        :>json object live: the dashboard's live wanted, or null

        Needs the manage_live_dashboards permission (admins have it) and the
        right to edit the dashboard.
        """
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        if not live.can_manage_live(self.current_user):
            abort(403, message="Turning dashboards live needs the manage_live_dashboards permission.")
        require_object_modify_permission(dashboard, self.current_user)

        body = request.get_json(force=True, silent=True) or {}
        current = live.live_settings(dashboard)
        wanted = dict(current) if current else None
        actions = []

        if "interval" in body:
            interval = body["interval"]
            if interval is None:
                wanted = None
                actions.append("live_off")
            elif interval in live.LIVE_INTERVALS:
                wanted = {**(wanted or {"paused": False}), "interval": interval}
                actions.append("live_on" if current is None else "live_interval")
            else:
                offered = ", ".join(map(str, live.LIVE_INTERVALS))
                abort(400, message="Interval must be one of {} seconds.".format(offered))

        if "paused" in body:
            if wanted is None:
                abort(400, message="Only a live dashboard can be paused.")
            if body["paused"]:
                wanted.update(live.pause_record(self.current_user))
                actions.append("live_pause")
            else:
                wanted.update({"paused": False, "paused_by": None, "paused_at": None})
                actions.append("live_resume")

        if not actions:
            abort(400, message="Send an interval, or paused.")

        # Written straight to the row rather than through the ORM: the ORM would
        # bump the dashboard's version, and anyone editing its layout at that
        # moment would be told their save conflicts with a change they cannot
        # see. Live wanted are not part of what an editor saves.
        models.db.session.execute(
            models.Dashboard.__table__.update().where(models.Dashboard.id == dashboard.id).values(live=wanted)
        )
        models.db.session.commit()
        models.db.session.refresh(dashboard)

        for action in actions:
            self.record_event({"action": action, "object_id": dashboard.id, "object_type": "dashboard"})

        # Going live, a new interval or Resume: refresh what is stale now, so
        # the person who pressed it sees it start. Off or paused, a no-op.
        # Asked for by hand, so it does not wait out the last attempt -- a
        # query that has been failing should be tried again immediately on a
        # new interval, not at the end of the old one.
        live.forget_attempts(dashboard)
        live.refresh_dashboard(dashboard)

        return {"live": live.describe(dashboard)}


class DashboardLiveWatchResource(BaseResource):
    @require_permission("list_dashboards")
    def post(self, dashboard_id):
        """
        Check in as a viewer of a live dashboard, or say you have left.

        :<json string viewer: an id the viewer's tab keeps for its lifetime
        :<json boolean leaving: true when the tab is closed or hidden
        :>json object live: the dashboard's live settings, or null
        :>json object results: {widget id: newest result id} for the widgets
                               this user may see

        A live dashboard is refreshed only while at least one viewer has checked
        in recently; a hidden tab should say it is leaving and stop checking in.
        """
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        return _watch(dashboard, "u{}".format(self.current_user.id), self.current_user)


class PublicDashboardLiveWatchResource(BaseResource):
    decorators = BaseResource.decorators + [csp_allows_embeding]

    def post(self, token):
        """
        Check in as a viewer of a live dashboard through its public link.
        Same body and response as the signed-in version.
        """
        if self.current_org.get_setting("disable_public_urls"):
            abort(400, message="Public URLs are disabled.")

        if not isinstance(self.current_user, models.ApiUser):
            api_key = get_object_or_404(models.ApiKey.get_by_api_key, token)
            dashboard = api_key.object
        else:
            dashboard = self.current_user.object

        # A public viewer sees every widget, as the public dashboard does.
        return _watch(dashboard, "public", None)


def _watch(dashboard, who, user):
    body = request.get_json(force=True, silent=True) or {}
    viewer = str(body.get("viewer") or "")[:64]
    if not viewer:
        abort(400, message="Send a viewer id.")
    member = "{}:{}".format(who, viewer)

    described = live.describe(dashboard) if not dashboard.is_archived else None
    if body.get("leaving"):
        live.leave(dashboard.id, member)
        return {"live": described}
    if described is None:
        return {"live": None}

    # Nobody was watching, so nothing has been refreshed: the first viewer back
    # -- often the same person returning to a hidden tab -- starts it now
    # rather than on the scheduler's next tick.
    #
    # In a job, not here. Working out what to start walks every widget and
    # renders every parameterized query, and this runs inside a check-in that
    # every open tab makes every few seconds. The queries are enqueued either
    # way; the viewer just no longer waits for the decision.
    was_watched = live.is_watched(dashboard.id)
    live.check_in(dashboard.id, member)
    if not was_watched:
        from sqldesk.tasks.live import refresh_live_dashboard

        refresh_live_dashboard.delay(dashboard.id)
    return {
        "live": described,
        "results": live.latest_results(dashboard, user),
        # The viewer counts down to the next refresh from result times the
        # server wrote, so it needs the server's clock, not its own.
        "server_time": utcnow().isoformat(),
    }


class DashboardShareResource(BaseResource):
    def post(self, dashboard_id):
        """
        Allow anonymous access to a dashboard.

        :param dashboard_id: The numeric ID of the dashboard to share.
        :>json string public_url: The URL for anonymous access to the dashboard.
        :>json api_key: The API key to use when accessing it.
        """
        dashboard = models.Dashboard.get_by_id_and_org(dashboard_id, self.current_org)
        require_admin_or_owner(dashboard.user_id)
        api_key = models.ApiKey.create_for_object(dashboard, self.current_user)
        models.db.session.flush()
        models.db.session.commit()

        public_url = url_for(
            "sqldesk.public_dashboard",
            token=api_key.api_key,
            org_slug=self.current_org.slug,
            _external=True,
        )

        self.record_event(
            {
                "action": "activate_api_key",
                "object_id": dashboard.id,
                "object_type": "dashboard",
            }
        )

        return {"public_url": public_url, "api_key": api_key.api_key}

    def delete(self, dashboard_id):
        """
        Disable anonymous access to a dashboard.

        :param dashboard_id: The numeric ID of the dashboard to unshare.
        """
        dashboard = models.Dashboard.get_by_id_and_org(dashboard_id, self.current_org)
        require_admin_or_owner(dashboard.user_id)
        api_key = models.ApiKey.get_by_object(dashboard)

        if api_key:
            api_key.active = False
            models.db.session.add(api_key)
            models.db.session.commit()

        self.record_event(
            {
                "action": "deactivate_api_key",
                "object_id": dashboard.id,
                "object_type": "dashboard",
            }
        )


class DashboardTagsResource(BaseResource):
    @require_permission("list_dashboards")
    def get(self):
        """
        Lists all accessible dashboards.
        """
        tags = models.Dashboard.all_tags(self.current_org, self.current_user)
        return {"tags": [{"name": name, "count": count} for name, count in tags]}


class DashboardFavoriteListResource(BaseResource):
    def get(self):
        search_term = request.args.get("q")

        if search_term:
            base_query = models.Dashboard.search(
                self.current_org,
                self.current_user.group_ids,
                self.current_user.id,
                search_term,
            )
            favorites = models.Dashboard.favorites(self.current_user, base_query=base_query)
        else:
            favorites = models.Dashboard.favorites(self.current_user)

        favorites = filter_by_tags(favorites, models.Dashboard.tags)

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        favorites = order_results(favorites, fallback=not bool(search_term))

        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        # TODO: we don't need to check for favorite status here
        response = paginate(favorites, page, page_size, DashboardSerializer)

        self.record_event(
            {
                "action": "load_favorites",
                "object_type": "dashboard",
                "params": {
                    "q": search_term,
                    "tags": request.args.getlist("tags"),
                    "page": page,
                },
            }
        )

        return response


class DashboardForkResource(BaseResource):
    @require_permission("edit_dashboard")
    def post(self, dashboard_id):
        dashboard = models.Dashboard.get_by_id_and_org(dashboard_id, self.current_org)

        fork_dashboard = dashboard.fork(self.current_user)
        models.db.session.commit()

        self.record_event({"action": "fork", "object_id": dashboard_id, "object_type": "dashboard"})

        return DashboardSerializer(fork_dashboard, with_widgets=True).serialize()

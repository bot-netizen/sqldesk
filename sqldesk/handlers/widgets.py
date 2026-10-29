from flask import request
from flask_restful import abort

from sqldesk import models
from sqldesk.handlers.base import BaseResource
from sqldesk.permissions import (
    require_access,
    require_object_modify_permission,
    require_permission,
    view_only,
)
from sqldesk.serializers import serialize_widget


def _refuse_to_mix(dashboard, visualization):
    """
    A dashboard is a streaming one or an ordinary one, never both.

    Not tidiness. A dashboard has a **single refresh interval**: a stream panel
    wants two seconds and a warehouse panel wants thirty or more. Mix them and
    the choice is between running every warehouse query behind the board every
    two seconds -- a dashboard that quietly hammers a warehouse all day -- and
    showing a stream that is half a minute stale, which is the one thing a
    stream exists not to be.

    A textbox belongs on either.

    Measured against the dashboard's declared `kind` rather than against
    whatever happens to be on it already. The old rule let the first widget
    decide, which meant the refusal could only ever arrive at the *second* one
    -- after somebody had built half a board. Now an empty dashboard already
    knows what it is, and the message can say so.
    """
    if visualization is None:
        return

    source = getattr(visualization.query_rel, "data_source", None)
    adding = bool(source is not None and source.streams_only)
    if adding == dashboard.is_streaming:
        return

    if dashboard.is_streaming:
        message = (
            "This is a streaming dashboard, so its panels come from streaming queries. A dashboard "
            "has one refresh interval, and a stream needs seconds where a saved query needs half a "
            "minute. Put this on an ordinary dashboard."
        )
    else:
        message = (
            "This is an ordinary dashboard, so its panels come from saved queries. A dashboard has "
            "one refresh interval, and a stream needs seconds where a saved query needs half a "
            "minute. Put this on a streaming dashboard."
        )
    abort(400, message=message)


#: How many visualizations one widget will offer as tabs, the widget's own
#: included. Past half a dozen a tab strip stops being a way to choose and
#: starts being a thing to read.
MAX_WIDGET_TABS = 6


def clean_tabs(visualization, options):
    """
    The sibling visualizations this widget offers as tabs, checked.

    Every tab has to be a visualization of the **same query** as the widget's
    own, and that is not a tidiness rule. It is what makes the feature worth
    having and what makes it safe:

    The whole point is that a dashboard fetches the query once and draws it
    several ways. Three widgets on one query fetch and parse that query three
    times; one widget with three tabs fetches it once. A tab belonging to some
    other query would have to fetch and that promise would be gone.

    And because every tab draws the result the viewer is already being shown,
    a tab adds no data they could not already see. Allowing a tab from another
    query would put a second query's results behind a widget whose access was
    checked against the first -- a permission hole wearing a tab strip.

    Returns the ids to store. Anything that is not a visualization of this
    widget's query is dropped rather than refused: the list is cosmetic, the
    widget still draws, and a dashboard that will not save because one stale
    id is in a options blob helps nobody.
    """
    if visualization is None:
        return []

    wanted = (options or {}).get("tabs")
    if not isinstance(wanted, list):
        return []

    # The widget's own visualization is always the first tab, so naming it
    # here would draw it twice.
    ids = []
    for one in wanted:
        if isinstance(one, bool) or not isinstance(one, int):
            continue
        if one == visualization.id or one in ids:
            continue
        ids.append(one)

    if not ids:
        return []

    siblings = {
        row.id
        for row in models.Visualization.query.filter(
            models.Visualization.id.in_(ids),
            models.Visualization.query_id == visualization.query_id,
        )
    }
    return [one for one in ids if one in siblings][: MAX_WIDGET_TABS - 1]


def apply_tabs(widget, options):
    """Store the cleaned tab list on the widget's options, or remove the key."""
    options = dict(options or {})
    tabs = clean_tabs(widget.visualization, options)
    if tabs:
        options["tabs"] = tabs
    else:
        options.pop("tabs", None)
    return options


class WidgetListResource(BaseResource):
    @require_permission("edit_dashboard")
    def post(self):
        """
        Add a widget to a dashboard.

        :<json number dashboard_id: The ID for the dashboard being added to
        :<json visualization_id: The ID of the visualization to put in this widget
        :<json object options: Widget options
        :<json string text: Text box contents
        :<json number width: Width for widget display

        :>json object widget: The created widget
        """
        widget_properties = request.get_json(force=True)
        dashboard = models.Dashboard.get_by_id_and_org(widget_properties.get("dashboard_id"), self.current_org)
        require_object_modify_permission(dashboard, self.current_user)

        widget_properties.pop("id", None)

        # Absent, not just null: the browser always sends the key, an API
        # client writing a textbox has no reason to, and a KeyError here is a
        # 500 with a traceback for what is a perfectly good request.
        visualization_id = widget_properties.pop("visualization_id", None)
        if visualization_id:
            visualization = models.Visualization.get_by_id_and_org(visualization_id, self.current_org)
            require_access(visualization.query_rel, self.current_user, view_only)
        else:
            visualization = None

        _refuse_to_mix(dashboard, visualization)

        widget_properties["visualization"] = visualization

        widget = models.Widget(**widget_properties)
        widget.options = apply_tabs(widget, widget.options)
        models.db.session.add(widget)

        models.db.session.commit()
        return serialize_widget(widget)


class WidgetResource(BaseResource):
    @require_permission("edit_dashboard")
    def post(self, widget_id):
        """
        Updates a widget in a dashboard.
        This method currently handles Text Box widgets only.

        :param number widget_id: The ID of the widget to modify

        :<json string text: The new contents of the text box
        """
        widget = models.Widget.get_by_id_and_org(widget_id, self.current_org)
        require_object_modify_permission(widget.dashboard, self.current_user)
        widget_properties = request.get_json(force=True)
        widget.text = widget_properties["text"]
        widget.options = apply_tabs(widget, widget_properties["options"])
        models.db.session.commit()
        return serialize_widget(widget)

    @require_permission("edit_dashboard")
    def delete(self, widget_id):
        """
        Remove a widget from a dashboard.

        :param number widget_id: ID of widget to remove
        """
        widget = models.Widget.get_by_id_and_org(widget_id, self.current_org)
        require_object_modify_permission(widget.dashboard, self.current_user)
        self.record_event({"action": "delete", "object_id": widget_id, "object_type": "widget"})
        models.db.session.delete(widget)
        models.db.session.commit()

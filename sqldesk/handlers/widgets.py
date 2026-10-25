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
        widget.options = widget_properties["options"]
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

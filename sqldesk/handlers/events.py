import geolite2
import maxminddb
from flask import request
from flask_restful import abort
from user_agents import parse as parse_ua

from sqldesk.handlers.base import BaseResource, paginate, record_events
from sqldesk.permissions import require_admin


def get_location(ip):
    if ip is None:
        return "Unknown"

    with maxminddb.open_database(geolite2.geolite2_database()) as reader:
        try:
            match = reader.get(ip)
            return match["country"]["names"]["en"]
        except Exception:
            return "Unknown"


def event_details(event):
    details = {}
    if event.object_type == "data_source" and event.action == "execute_query":
        details["query"] = (event.additional_properties or {}).get("query")
        details["data_source"] = event.object_id
    elif event.object_type == "page" and event.action == "view":
        details["page"] = event.object_id
    else:
        details["object_id"] = event.object_id
        details["object_type"] = event.object_type

    return details


def serialize_event(event):
    d = {
        "org_id": event.org_id,
        "user_id": event.user_id,
        "action": event.action,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "created_at": event.created_at,
    }

    if event.user_id:
        d["user_name"] = event.additional_properties.get("user_name", "User {}".format(event.user_id))

    if not event.user_id:
        d["user_name"] = event.additional_properties.get("api_key", "Unknown")

    d["browser"] = str(parse_ua(event.additional_properties.get("user_agent", "")))
    d["location"] = get_location(event.additional_properties.get("ip"))
    d["details"] = event_details(event)

    return d


#: The most events one request may carry.
#:
#: There was no limit: a list of ten thousand became ten thousand jobs, from
#: an endpoint any signed-in session can post to. A page sends its events for
#: the last second, which is a handful even on a large dashboard.
MAX_EVENTS = 50


class EventsResource(BaseResource):
    def post(self):
        events_list = request.get_json(force=True)
        if not isinstance(events_list, list):
            abort(400, message="A list of events is expected.")
        if len(events_list) > MAX_EVENTS:
            abort(400, message="At most {} events per request.".format(MAX_EVENTS))
        # One job for the batch. A dashboard of thirty widgets queued about
        # seventy-five of them, each with its own transaction.
        record_events(self.current_org, self.current_user, [event for event in events_list if isinstance(event, dict)])

    @require_admin
    def get(self):
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        return paginate(self.current_org.events, page, page_size, serialize_event)

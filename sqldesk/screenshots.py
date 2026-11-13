"""
Pictures of dashboards and queries, for attaching to an alert.

Nothing in this image can draw one. Producing a picture of a dashboard means
running the dashboard, which means a browser, and putting a browser in here
would add several hundred megabytes to an image the server and the worker
share -- for a feature most installs never turn on. So the browser lives in
its own optional service and this module is the client for it: a POST with a
URL, a PNG back. Point SQLDESK_SCREENSHOT_URL at one and the feature turns on;
leave it unset and everything here declines quietly.

Grafana reached the same arrangement for the same reason, and Superset, which
did not, tells its users to build their own image instead.

The rule that matters here: **a picture is a nice-to-have and an alert is
not.** Every failure in this file is caught and logged, and the alert goes out
without the image. Nothing in here is allowed to be the reason a threshold
breach went unreported.
"""

import logging

import pytz
import requests

from sqldesk import models, render_pass, settings
from sqldesk.permissions import has_access, view_only

logger = logging.getLogger(__name__)

#: What a renderer is asked to wait for before it captures. The embed page
#: sets this once the result is in and the chart has drawn; without it the
#: normal failure is a picture of a spinner.
READY_SELECTOR = "[data-rendered='true']"

DASHBOARD = "dashboard"
QUERY = "query"

#: What the renderer may be asked for. An alert always wants a picture; a
#: subscription may want a printable page instead.
PNG = "png"
PDF = "pdf"


#: The narrowest and widest dashboard a picture is drawn at, in CSS pixels.
#: Below this a dashboard collapses to its phone layout, which is a different
#: picture of a different thing; above it the image is too big to be worth
#: sending. A 4K screen at 100% is 3840.
MIN_SCREEN_WIDTH = 600
MAX_SCREEN_WIDTH = 3840

#: What the branded frame adds either side of the dashboard: 40px a side
#: (ScreenshotFrame.less, and MARGIN in the export's compose.js). The window
#: is this much wider than the dashboard, so the dashboard is exactly as wide
#: as it was on the screen it was sent from.
FRAME_WIDTH = 80


def clean_screen_width(value):
    """A dashboard width worth drawing at, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    width = int(round(value))
    return width if MIN_SCREEN_WIDTH <= width <= MAX_SCREEN_WIDTH else None


def clean_time_zone(value):
    """An IANA time zone the renderer can be put in, or None."""
    if isinstance(value, str) and value in pytz.all_timezones_set:
        return value
    return None


def screen_of(user):
    """
    The screen this person's pictures are drawn for: the dashboard's width
    and their time zone, as their browser last reported them -- or Nones.

    A dashboard lays itself out to the width it is given. Its widgets keep
    their height and gain or lose width, so tiles and table columns that fit
    on one screen wrap or vanish on another. Export as image photographs the
    dashboard as it is on the screen in front of somebody; the renderer had a
    window of its own, 1400px, and drew a dashboard laid out on a 2800px
    screen with a third of its tiles scrolled out of sight. So the browser
    says how wide the dashboard is whenever somebody exports, sends or
    subscribes, and the pictures sent in their name are drawn at that width
    and in their time zone -- the picture they would have exported.
    """
    details = getattr(user, "details", None) or {}
    screen = details.get("screen") if isinstance(details, dict) else None
    if not isinstance(screen, dict):
        return None, None
    return clean_screen_width(screen.get("width")), clean_time_zone(screen.get("time_zone"))


#: How many dashboards' table orders are kept for one person, most recent
#: last, and how many tables on one dashboard. A ceiling, so a person's record
#: cannot grow without end.
MAX_SORTED_DASHBOARDS = 50
MAX_SORTED_TABLES = 50
SORT_DIRECTIONS = ("ascend", "descend")


def clean_table_orders(value):
    """
    `{widget_id: [{name, direction}]}` as a table reports the order it is
    showing, keeping only well-formed entries: a widget id, a column name, and
    "ascend" or "descend", at most five columns deep.
    """
    if not isinstance(value, dict):
        return {}
    orders = {}
    for widget_id, order in list(value.items())[:MAX_SORTED_TABLES]:
        if not str(widget_id).isdigit() or not isinstance(order, list):
            continue
        clean = [
            {"name": item["name"], "direction": item["direction"]}
            for item in order[:5]
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and 0 < len(item["name"]) <= 255
            and item.get("direction") in SORT_DIRECTIONS
        ]
        if clean:
            orders[str(widget_id)] = clean
    return orders


def remember_table_orders(user, dashboard_id, orders):
    """
    Keep the order this person's tables were in on this dashboard, the last
    time they exported, sent or subscribed to it. True if anything changed.

    Clicking a column header sorts the rows in the browser and nowhere else,
    so Export as image showed them sorted and the Slack picture of the same
    dashboard showed the query's own order. An empty `orders` forgets the
    dashboard: nothing sorted, so the query's order is the right one.

    A list, most recent last, because Postgres does not keep the order of an
    object's keys and the oldest is the one to let go.
    """
    details = user.details if isinstance(user.details, dict) else {}
    kept = [
        entry
        for entry in (details.get("table_orders") or [])
        if isinstance(entry, dict) and str(entry.get("dashboard")) != str(dashboard_id)
    ]
    if orders:
        kept.append({"dashboard": int(dashboard_id), "tables": orders})
    kept = kept[-MAX_SORTED_DASHBOARDS:]
    if kept == (details.get("table_orders") or []):
        return False
    if user.details is None:
        user.details = {}
    user.details["table_orders"] = kept
    return True


def table_orders_of(user, dashboard):
    """The order each table on this dashboard was in for this person, by widget id."""
    details = getattr(user, "details", None)
    if not isinstance(details, dict):
        return {}
    for entry in reversed(details.get("table_orders") or []):
        if isinstance(entry, dict) and str(entry.get("dashboard")) == str(dashboard.id):
            return clean_table_orders(entry.get("tables"))
    return {}


def enabled():
    return settings.FEATURE_ALERT_SCREENSHOTS and bool(settings.SCREENSHOT_URL)


def _target_url(kind, obj, token):
    """
    The page to photograph, as the renderer will ask for it.

    Both are pages the application already serves -- there is no separate
    rendering path to keep in step with what people actually see.

    A dashboard's page takes its credential in the path, because that is how
    the route is shaped; it is a pass good for five minutes rather than a link
    anybody keeps. A query's goes in a header instead, since that route has
    somewhere to put it.
    """
    base = settings.INTERNAL_BASE_URL.rstrip("/")
    if kind == DASHBOARD:
        return f"{base}/public/dashboards/{token}?screenshot=1"

    visualization = _first_visualization(obj)
    if visualization is None:
        return None
    return f"{base}/embed/query/{obj.id}/visualization/{visualization.id}?screenshot=1"


def _first_visualization(query):
    """
    Which of a query's visualizations to draw.

    Anything but the table, if there is one: somebody attaching a query to an
    alert wants the chart they built, and the table is what a query has when
    nobody has made one.
    """
    visualizations = sorted(query.visualizations, key=lambda v: v.id)
    drawn = [v for v in visualizations if v.type != "TABLE"]
    return (drawn or visualizations or [None])[0]


def _renderer_headers():
    """The token the renderer expects, when one is set."""
    return {"X-Screenshot-Token": settings.SCREENSHOT_TOKEN} if settings.SCREENSHOT_TOKEN else {}


def capture(kind, obj, viewer, fmt=PNG):
    """
    A PNG of one dashboard or query, or None.

    None covers every way this can fail, because they all mean the same thing
    to the caller: send the alert without a picture.

    `viewer` is whose sight of it this is -- the alert's owner. A pass is
    minted for them, for this object alone, and withdrawn as soon as the
    renderer answers. Before this the renderer was handed the dashboard's
    *public* link, so a dashboard could only be pictured once it had been
    shared with the internet; a picture in an email is not a reason to make
    one public.
    """
    if not enabled():
        return None

    token = render_pass.issue(viewer, obj)
    if token is None:
        logger.warning("Could not issue a render pass for %s %s.", kind, getattr(obj, "id", "?"))
        return None

    width, time_zone = screen_of(viewer)

    url = _target_url(kind, obj, token)
    if url is None:
        logger.warning("Nothing to draw for %s %s; skipping its screenshot.", kind, getattr(obj, "id", "?"))
        render_pass.withdraw(token)
        return None

    try:
        response = requests.post(
            f"{settings.SCREENSHOT_URL.rstrip('/')}/screenshot",
            headers=_renderer_headers(),
            json={
                "url": url,
                # The pass goes in a header, not the URL, wherever the
                # route allows it: two services would otherwise write a
                # working credential into their logs.
                "headers": {"Authorization": f"Key {token}"},
                "wait_for": READY_SELECTOR,
                "format": fmt,
                "timeout": settings.SCREENSHOT_TIMEOUT,
                # A dashboard is usually taller than a window. The renderer
                # captures the whole page rather than the first screen of it.
                # A PDF paginates instead, so this says nothing about one.
                "full_page": kind == DASHBOARD,
                # Drawn the way the person it is sent for sees it -- see
                # `screen_of`. A query's picture is one chart, which has no
                # layout to keep, so it keeps the renderer's own window.
                **({"width": width + FRAME_WIDTH} if width and kind == DASHBOARD else {}),
                **({"time_zone": time_zone} if time_zone else {}),
            },
            timeout=settings.SCREENSHOT_TIMEOUT + 5,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Could not get a screenshot of %s %s.", kind, getattr(obj, "id", "?"))
        return None
    finally:
        # Whatever happened, this pass has had its turn.
        render_pass.withdraw(token)

    image = response.content
    if not image:
        logger.warning("The renderer returned an empty image for %s %s.", kind, getattr(obj, "id", "?"))
        return None

    return image


def _load(kind, object_id, org):
    try:
        if kind == DASHBOARD:
            return models.Dashboard.get_by_id_and_org(object_id, org)
        if kind == QUERY:
            return models.Query.get_by_id_and_org(object_id, org)
    except Exception:
        # Deleted since it was attached, or never in this organization.
        logger.warning("Alert attachment %s %s could not be loaded.", kind, object_id)
    return None


def may_see_dashboard(dashboard, user):
    """
    Whether this person may see this dashboard.

    Named and exported because two things ask it: an alert, about the person
    it is drawing for, and a subscription, about its owner *and* every
    recipient before each send.
    """
    return (
        user.has_permission("admin")
        or models.Dashboard.all(dashboard.org, user.group_ids, user.id)
        .filter(models.Dashboard.id == dashboard.id)
        .count()
        > 0
    )


def _owner_may_see(kind, obj, owner):
    """
    Access is checked when an attachment is saved; it is checked again here
    because access changes, and a picture drawn for somebody would otherwise
    outlive their right to look at it.
    """
    if kind == QUERY:
        return has_access(obj, owner, view_only)
    return may_see_dashboard(obj, owner)


def for_alert(alert):
    """
    Every picture an alert asks for.

    Each one carries its own title as well as its bytes, because the email has
    to name them: a recipient whose client blocks images -- which many do by
    default -- otherwise gets five empty boxes saying nothing at all.

    Capped, and the cap is the point: an alert carrying twenty dashboards
    would take minutes to send and arrive as something nobody opens.
    """
    if not enabled():
        return []

    attachments = (alert.options or {}).get("attachments") or []
    org = alert.query_rel.org

    images = []
    for attachment in attachments[: settings.MAX_ALERT_ATTACHMENTS]:
        kind = attachment.get("type")
        obj = _load(kind, attachment.get("id"), org)
        if obj is None or not _owner_may_see(kind, obj, alert.user):
            continue

        image = capture(kind, obj, alert.user)
        if image is None:
            continue

        images.append(
            {
                "filename": f"{kind}-{obj.id}.png",
                "image": image,
                # The object's own name, read now rather than the one saved on
                # the alert, which goes stale the moment anybody renames it.
                "title": obj.name,
                "kind": kind,
            }
        )

    return images

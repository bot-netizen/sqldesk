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

import requests

from sqldesk import models, settings

logger = logging.getLogger(__name__)

#: What a renderer is asked to wait for before it captures. The embed page
#: sets this once the result is in and the chart has drawn; without it the
#: normal failure is a picture of a spinner.
READY_SELECTOR = "[data-rendered='true']"

DASHBOARD = "dashboard"
QUERY = "query"


def enabled():
    return settings.FEATURE_ALERT_SCREENSHOTS and bool(settings.SCREENSHOT_URL)


def _token(kind, obj):
    """
    The key that lets the renderer see this page, or None.

    A query always has one of its own. A dashboard only has one once somebody
    has shared it, and this deliberately does **not** create one: making a
    dashboard publicly reachable is a decision for the person who owns it, not
    a side effect of attaching it to an alert. The alert editor says so when
    you pick a dashboard that has not been shared.
    """
    if kind == QUERY:
        return obj.api_key

    key = models.ApiKey.get_by_object(obj)
    return key.api_key if key else None


def _target_url(kind, obj):
    """
    The page to photograph, as the renderer will ask for it.

    Both are pages the application already serves -- there is no separate
    rendering path to keep in step with what people actually see.
    """
    base = settings.INTERNAL_BASE_URL.rstrip("/")
    if kind == DASHBOARD:
        return f"{base}/public/dashboards/{_token(kind, obj)}?screenshot=1"

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


def capture(kind, obj):
    """
    A PNG of one dashboard or query, or None.

    None covers every way this can fail, because they all mean the same thing
    to the caller: send the alert without a picture.
    """
    if not enabled():
        return None

    token = _token(kind, obj)
    if token is None:
        # A dashboard nobody has shared. Not an error -- there is simply no
        # link for a browser to open.
        logger.warning("%s %s has no shareable link, so it cannot be drawn.", kind, getattr(obj, "id", "?"))
        return None

    url = _target_url(kind, obj)
    if url is None:
        logger.warning("Nothing to draw for %s %s; skipping its screenshot.", kind, getattr(obj, "id", "?"))
        return None

    try:
        response = requests.post(
            f"{settings.SCREENSHOT_URL.rstrip('/')}/screenshot",
            json={
                "url": url,
                # The key goes in a header, not the URL: two services would
                # otherwise write a working credential into their logs.
                "headers": {"Authorization": f"Key {token}"},
                "wait_for": READY_SELECTOR,
                "timeout": settings.SCREENSHOT_TIMEOUT,
                # A dashboard is usually taller than a window. The renderer
                # captures the whole page rather than the first screen of it.
                "full_page": kind == DASHBOARD,
            },
            timeout=settings.SCREENSHOT_TIMEOUT + 5,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Could not get a screenshot of %s %s.", kind, getattr(obj, "id", "?"))
        return None

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


def for_alert(alert):
    """
    Every picture an alert asks for, as [(filename, png)].

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
        if obj is None:
            continue

        image = capture(kind, obj)
        if image is None:
            continue

        images.append((f"{kind}-{obj.id}.png", image))

    return images

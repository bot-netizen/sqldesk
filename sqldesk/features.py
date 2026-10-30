"""
The things an administrator can hand to a group, in one list.

A *feature* here is different from the dozen permissions every group is born
with. Those describe the ordinary work of the application -- writing a query,
making a dashboard -- and every group has them. A feature is something an
administrator decides a particular group may do: reach the warehouse from an
AI client, curate what that client is told, keep an uploaded file past its
expiry. Nobody has one until somebody says so.

Adding a feature is one entry below. The grant endpoint will accept it, the
Group page will draw a checkbox for it, and `can()` will answer for it.

`enabled` is what decides whether an install offers the feature at all: there
is no sense showing "Connect AI clients" where MCP is switched off. A feature
that is off is not grantable and `can()` says no, whatever a group's row
happens to hold -- so turning MCP off takes the ability away rather than
leaving it granted and inert.
"""

from sqldesk import settings


class Feature:
    def __init__(self, name, label, description, enabled=None):
        self.name = name
        self.label = label
        self.description = description
        # Read when asked, not at import: an install switches MCP on and off
        # with a setting, and the tests move it about.
        self._enabled = enabled

    @property
    def enabled(self):
        return self._enabled() if self._enabled else True

    def to_dict(self):
        return {"name": self.name, "label": self.label, "description": self.description}


def _mcp_is_on():
    # The setting's name is older than the feature: it gates MCP and the catalog.
    return settings.FEATURE_AI


def _uploads_expire():
    # Nothing to be allowed to stop where nothing expires. An install that has
    # turned the lifecycle off should not offer a permission that does nothing.
    return settings.UPLOAD_LIFETIME_DAYS > 0


def _rendering_is_on():
    # Nothing can send a dashboard without something to draw it, and the
    # renderer is a separate, optional container. Offering the feature where
    # there is no renderer would be offering a button that cannot work.
    return settings.FEATURE_ALERT_SCREENSHOTS and bool(settings.SCREENSHOT_URL)


def _streams_are_on():
    """
    Whether this install can consume a topic at all.

    Two things have to be true and they fail differently. The runner needs
    librdkafka, which is in the optional dependency group with every other data
    source's SDK -- without it there is nothing to connect to a broker with.
    And the deployment has to have been asked for streams: the image carries
    the library whether or not anybody runs a stream worker, so an install that
    runs none would otherwise offer a permission whose pages never fill.

    Both are the same answer to somebody holding the permission -- nothing
    happens -- so neither is worth offering.
    """
    from sqldesk.query_runner import get_query_runner

    if not settings.STREAMS_ENABLED:
        return False
    return get_query_runner("kafka_stream", {}) is not None


USE_MCP = "use_mcp"
MANAGE_CATALOG = "manage_catalog"
MANAGE_LIVE_DASHBOARDS = "manage_live_dashboards"
SEND_DASHBOARDS = "send_dashboards"
KEEP_UPLOADS = "keep_uploads"
MANAGE_STREAMS = "manage_streams"
USE_STREAMS = "use_streams"
USE_NOTEBOOKS = "use_notebooks"

#: Every feature, whether or not this install offers it.
FEATURES = (
    Feature(
        MANAGE_LIVE_DASHBOARDS,
        "Make dashboards live",
        "Turn a dashboard live, so it refreshes on the server for everyone watching it.",
    ),
    Feature(
        USE_NOTEBOOKS,
        "Use notebooks",
        "Chain SQL and Python cells together, where a saved query ends in one SELECT.",
    ),
    Feature(
        USE_MCP,
        "Connect AI clients over MCP",
        "Answer questions from an AI client, as themselves and within their own data source access.",
        enabled=_mcp_is_on,
    ),
    Feature(
        MANAGE_CATALOG,
        "Curate the catalog",
        "Describe tables and agree the measures an AI client is told about.",
        enabled=_mcp_is_on,
    ),
    Feature(
        SEND_DASHBOARDS,
        "Send dashboards",
        "Mail a dashboard to colleagues on a schedule, and share one to Slack.",
        enabled=_rendering_is_on,
    ),
    Feature(
        MANAGE_STREAMS,
        "Set up streams",
        "Choose which of a Kafka cluster's topics can be queried, and how much of each is kept.",
        enabled=_streams_are_on,
    ),
    Feature(
        USE_STREAMS,
        "Watch streams",
        "Start a stream and watch it live. Starting one takes a slot; watching somebody else's does not.",
        enabled=_streams_are_on,
    ),
    Feature(
        KEEP_UPLOADS,
        "Keep uploaded files",
        "Stop an uploaded file expiring, so it stays until somebody deletes it.",
        enabled=_uploads_expire,
    ),
)


def all_features():
    return FEATURES


def grantable():
    """The features this install offers, which is what an administrator sees."""
    return [feature for feature in FEATURES if feature.enabled]


def by_name(name):
    for feature in FEATURES:
        if feature.name == name:
            return feature
    return None


def can(user, name):
    """
    Whether this person may use a feature.

    Administrators may use every feature that the install offers -- there is
    no checkbox that keeps an administrator out of something, because an
    administrator can grant it to themselves in one click and the pretence
    would only be in the way.
    """
    feature = by_name(name)
    if feature is None or not feature.enabled:
        return False
    if user.has_permission("admin"):
        return True
    return user.has_permission(name)

"""
Live dashboard work that must not happen inside a request.

Deciding what a live dashboard should run means walking its widgets, running
every parameterized query through Mustache and asking the database what it
already has -- and the one place that used to do it synchronously was a
viewer's check-in, which happens every few seconds per open tab. The first
viewer back to a dashboard nobody was watching paid for all of it before
getting a reply.
"""

from sqldesk import live, models
from sqldesk.worker import get_job_logger, job

logger = get_job_logger(__name__)


@job("default", timeout=live.SWEEP_TIMEOUT)
def refresh_live_dashboard(dashboard_id):
    """Start a live dashboard's queries now, rather than on the next tick."""
    dashboard = models.Dashboard.query.get(dashboard_id)
    if dashboard is None:
        logger.info("Live dashboard %s has gone; nothing to refresh.", dashboard_id)
        return []
    return live.refresh_dashboard(dashboard)

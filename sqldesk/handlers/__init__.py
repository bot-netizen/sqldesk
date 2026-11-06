from flask import Response, abort, jsonify, request
from flask_login import login_required

from sqldesk.handlers.api import api
from sqldesk.handlers.base import routes
from sqldesk.monitor import get_status
from sqldesk.permissions import require_super_admin
from sqldesk.security import talisman


@routes.route("/ping", methods=["GET"])
@talisman(force_https=False)
def ping():
    return "PONG."


@routes.route("/metrics")
@talisman(force_https=False)
def metrics():
    """
    What a Prometheus scraper reads.

    Outside the API and outside the session: a scraper has no cookie and no
    organization, and this describes the *instance* rather than anybody's
    data. Not mounted at all unless a token is configured, and 404 rather than
    403 when it is not -- a refusal would confirm there is something here.
    """
    from sqldesk.metrics import prometheus

    if not prometheus.enabled():
        abort(404)
    if not prometheus.authorised(request.headers.get("Authorization")):
        # The same 404. Which half was wrong is not a scraper's business, and
        # not a scanner's either.
        abort(404)
    return Response(prometheus.collect(), mimetype="text/plain; version=0.0.4; charset=utf-8")


@routes.route("/status.json")
@login_required
@require_super_admin
def status_api():
    status = get_status()
    return jsonify(status)


def init_app(app):
    from sqldesk.handlers import (
        admin,
        authentication,
        embed,
        home,
        mcp,
        oauth,
        organization,
        queries,
        setup,
        static,
    )

    app.register_blueprint(routes)
    api.init_app(app)

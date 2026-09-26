from flask import jsonify
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
        organization,
        queries,
        setup,
        static,
    )

    app.register_blueprint(routes)
    api.init_app(app)

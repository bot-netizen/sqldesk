from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from sqldesk import settings


class SQLDesk(Flask):
    """A custom Flask app for SQLDesk"""

    def __init__(self, *args, **kwargs):
        kwargs.update(
            {
                "template_folder": settings.FLASK_TEMPLATE_PATH,
                "static_folder": settings.STATIC_ASSETS_PATH,
                "static_url_path": "/static",
            }
        )
        super(SQLDesk, self).__init__(__name__, *args, **kwargs)
        # Make sure we get the right referral address even behind proxies like nginx.
        #
        # `x_proto` is stated rather than left to werkzeug, which already
        # defaults it to 1. Two reasons to write it down: OAuth for MCP depends
        # on it -- authlib refuses an authorization request whose URL does not
        # look like https, so behind a TLS-terminating proxy the whole flow
        # rests on `X-Forwarded-Proto` being read -- and it keeps the forwarded
        # scheme in step with the forwarded address where two proxies are in
        # front, which the default does not.
        #
        # `PROXIES_COUNT` says how many proxies there are, and a header from
        # further away than that is ignored; where nothing is in front, nothing
        # sets these headers.
        self.wsgi_app = ProxyFix(
            self.wsgi_app,
            x_for=settings.PROXIES_COUNT,
            x_proto=settings.PROXIES_COUNT,
            x_host=1,
        )
        # Configure SQLDesk using our settings
        self.config.from_object("sqldesk.settings")


def create_app():
    from . import (
        authentication,
        compression,
        handlers,
        limiter,
        mail,
        migrate,
        oauth,
        security,
        tasks,
    )
    from .handlers.webpack import configure_webpack
    from .metrics import request as request_metrics
    from .models import db, users
    from .utils import sentry
    from .version_check import reset_new_version_status

    sentry.init()
    app = SQLDesk()

    # Check and update the cached version for use by the client
    reset_new_version_status()

    security.init_app(app)
    # Before the handlers, so the after_request hook it installs runs outermost
    # and sees the finished body of every response the app produces.
    compression.init_app(app)
    request_metrics.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    authentication.init_app(app)
    limiter.init_app(app)
    handlers.init_app(app)
    # After the handlers: the authorization server's endpoints live on the
    # same blueprint, and registering the grants needs the app.
    oauth.init_app(app)
    configure_webpack(app)
    users.init_app(app)
    tasks.init_app(app)

    return app

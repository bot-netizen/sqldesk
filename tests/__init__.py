import datetime
import logging
import os
from contextlib import contextmanager
from unittest import TestCase

from sqlalchemy.orm import configure_mappers

os.environ["SQLDESK_REDIS_URL"] = os.environ.get("SQLDESK_REDIS_URL", "redis://localhost:6379/0").replace("/0", "/5")
# Use different url for RQ to avoid DB being cleaned up:
os.environ["RQ_REDIS_URL"] = os.environ.get("SQLDESK_REDIS_URL", "redis://localhost:6379/0").replace("/5", "/6")

# Dummy values for oauth login
os.environ["SQLDESK_GOOGLE_CLIENT_ID"] = "dummy"
os.environ["SQLDESK_GOOGLE_CLIENT_SECRET"] = "dummy"
os.environ["SQLDESK_MULTI_ORG"] = "true"

# Make sure rate limit is enabled
os.environ["SQLDESK_RATELIMIT_ENABLED"] = "true"

os.environ["SQLDESK_ENFORCE_CSRF"] = "false"

from sqldesk import limiter, redis_connection  # noqa: E402
from sqldesk.app import create_app  # noqa: E402
from sqldesk.models import db  # noqa: E402
from sqldesk.utils import json_dumps  # noqa: E402
from tests.factories import Factory, user_factory  # noqa: E402

logging.disable(logging.INFO)
logging.getLogger("metrics").setLevel(logging.ERROR)


def authenticate_request(c, user):
    with c.session_transaction() as sess:
        sess["_user_id"] = user.get_id()


@contextmanager
def authenticated_user(c, user=None):
    if not user:
        user = user_factory.create()
        db.session.commit()
    authenticate_request(c, user)

    yield user


#: The schema is built once per process, by the first test that asks for a
#: database. Everything after that empties the tables instead.
_schema_built = False
_truncate_all = None


def _reset_database(app):
    """
    Give the test an empty database without rebuilding the schema.

    `db.drop_all(); db.create_all()` ran on **every** test. Against this
    schema's 38 tables, 39 indexes and 143 constraints that is 0.63s of a
    0.84s test on this host; one `TRUNCATE` of every table is 0.07s. It
    leaves the same thing behind -- every table empty, every sequence back at
    1, committed rather than held open in a transaction -- so no test has to
    know this changed.

    Rolling back a transaction per test would be cheaper again (0.0007s for
    connect/begin/rollback), and was the first plan. It asks for more than it
    is worth: the session has to be rebound to a held connection with a
    SAVEPOINT restarted after every `commit()`, and the tests that rebuild
    the schema inside themselves, execute DDL, or write outside the session
    would each need adapting to it. `TRUNCATE` needs none of that and takes
    about nine tenths of the saving, so the last tenth is left alone.
    """

    global _schema_built, _truncate_all

    db.session.close()

    if not _schema_built:
        db.drop_all()
        # `create_all` only creates the full-text search trigger if the
        # mappers are already configured. `sqlalchemy_searchable`'s
        # `make_searchable` attaches its per-table DDL listeners from the
        # mapper `after_configured` event, so until something has triggered
        # mapper configuration there is no `after_create` listener to create
        # `queries_search_vector_trigger` -- the table is created without it,
        # `search_vector` stays NULL for every row, and every search test
        # finds nothing while nothing raises.
        #
        # This was always true, and used to be hidden: the schema was rebuilt
        # for every test, so the first ORM use configured the mappers and
        # every later test got its trigger. Building it once makes the first
        # test decide for the whole run, which is how it surfaced. Measured
        # both ways in `probe7`: no `configure_mappers()` and the trigger is
        # absent, with it the trigger is there and the vector populated.
        configure_mappers()
        db.create_all()
        _truncate_all = "TRUNCATE {} RESTART IDENTITY CASCADE".format(
            ", ".join('"{}"'.format(name) for name in db.metadata.tables)
        )
        _schema_built = True
        return

    # The transaction is explicit rather than left to SQLAlchemy. 1.3 decides
    # whether to commit a textual statement by matching it against
    # `AUTOCOMMIT_REGEXP`, which is `UPDATE|INSERT|CREATE|DELETE|DROP|ALTER`
    # and does not contain `TRUNCATE`. It is committed here anyway -- measured,
    # because the first guess was that it would not be -- but the behaviour
    # rests on a heuristic that 2.0 removes, and a reset that silently stops
    # resetting is the worst way for this to fail. `begin()` costs nothing and
    # does not need the heuristic to be right.
    #
    # The connection is explicit because connectionless execution closes it
    # before `sqldesk/metrics/database.py`'s `after_execute` listener reads
    # `conn.info` off it, which raises `ResourceClosedError`.
    connection = db.get_engine(app).connect()
    try:
        with connection.begin():
            connection.execute(_truncate_all)
    finally:
        connection.close()


class BaseTestCase(TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = db
        self.app.config["TESTING"] = True
        limiter.enabled = False
        self.app_ctx = self.app.app_context()
        self.app_ctx.push()
        _reset_database(self.app)
        self.factory = Factory()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.get_engine(self.app).dispose()
        self.app_ctx.pop()
        redis_connection.flushdb()

    def make_request(
        self,
        method,
        path,
        org=None,
        user=None,
        data=None,
        is_json=True,
        follow_redirects=False,
    ):
        if user is None:
            user = self.factory.user

        if org is None:
            org = self.factory.org

        if org is not False:
            path = "/{}{}".format(org.slug, path)

        if user:
            authenticate_request(self.client, user)

        method_fn = getattr(self.client, method.lower())
        headers = {}

        if data and is_json:
            data = json_dumps(data)

        if is_json:
            content_type = "application/json"
        else:
            content_type = None

        response = method_fn(
            path,
            data=data,
            headers=headers,
            content_type=content_type,
            follow_redirects=follow_redirects,
        )
        return response

    def get_request(self, path, org=None, headers=None, client=None):
        if org:
            path = "/{}{}".format(org.slug, path)

        if client is None:
            client = self.client
        return client.get(path, headers=headers)

    def post_request(self, path, data=None, org=None, headers=None):
        if org:
            path = "/{}{}".format(org.slug, path)

        return self.client.post(path, data=data, headers=headers)

    def assertResponseEqual(self, expected, actual):
        for k, v in expected.items():
            if isinstance(v, datetime.datetime) or isinstance(actual[k], datetime.datetime):
                continue

            if isinstance(v, list):
                continue

            if isinstance(v, dict):
                self.assertResponseEqual(v, actual[k])
                continue

            self.assertEqual(
                v,
                actual[k],
                "{} not equal (expected: {}, actual: {}).".format(k, v, actual[k]),
            )

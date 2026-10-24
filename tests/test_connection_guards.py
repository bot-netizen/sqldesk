"""
What a database connection from this process carries, and why it differs by
process.
"""

from unittest import mock

from sqldesk.models.base import statement_timeouts
from tests import BaseTestCase


class TestStatementTimeouts(BaseTestCase):
    """
    One lock nobody expected, or a plan that went wrong after a table grew,
    used to hold a gunicorn worker until gunicorn killed the worker outright
    -- taking every other request it was serving with it. Postgres cancelling
    one statement costs one request.
    """

    def _options(self, role, statement=30000, idle=60000):
        with mock.patch("sqldesk.settings.PROCESS_ROLE", role), mock.patch(
            "sqldesk.settings.SQLALCHEMY_STATEMENT_TIMEOUT_MS", statement
        ), mock.patch("sqldesk.settings.SQLALCHEMY_IDLE_IN_TRANSACTION_TIMEOUT_MS", idle):
            return statement_timeouts()

    def test_the_web_tier_gets_both(self):
        options = self._options("server")

        self.assertIn("statement_timeout=30000", options)
        self.assertIn("idle_in_transaction_session_timeout=60000", options)

    def test_a_worker_gets_only_the_idle_one(self):
        # Storing a very large result is one long INSERT, and cancelling that
        # would fail a query that had already run.
        options = self._options("worker")

        self.assertNotIn("statement_timeout", options)
        self.assertIn("idle_in_transaction_session_timeout=60000", options)

    def test_zero_means_off_and_leaves_the_connection_alone(self):
        self.assertEqual("", self._options("server", statement=0, idle=0))

    def test_a_manage_command_is_not_the_web_tier_either(self):
        self.assertNotIn("statement_timeout", self._options(""))


class TestPoolPrePing(BaseTestCase):
    def test_it_is_on_by_default(self):
        from sqldesk import settings

        # A connection pooled across a Postgres restart, a failover, or an
        # idle timeout on a proxy is dead in a way nothing notices until a
        # request uses it -- and then that request is a 500 for no visible
        # reason.
        self.assertTrue(settings.SQLALCHEMY_ENABLE_POOL_PRE_PING)

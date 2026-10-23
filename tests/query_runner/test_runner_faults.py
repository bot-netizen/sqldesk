"""
Small faults in individual runners, each of which turned a working query, a
cancel or a security setting into something else.
"""

import decimal
from unittest import TestCase, mock

from sqldesk.query_runner import JobTimeoutException, installed
from sqldesk.utils import json_dumps, json_loads


class TestAnEncoderMayAnswerZero(TestCase):
    """
    A runner's JSON encoder was taken to have declined whenever its answer was
    falsy. Mongo's Decimal128("0") is Decimal("0"), so a result holding a zero
    price fell through to json's default, which raised, and the result failed to
    store.
    """

    def test_a_zero_decimal_from_mongo_is_stored(self):
        if not installed("bson"):
            self.skipTest("pymongo is in the all_ds group")
        from bson.decimal128 import Decimal128

        self.assertEqual({"price": 0.0}, json_loads(json_dumps({"price": Decimal128("0")})))

    def test_and_any_encoder_answering_a_falsy_value_is_believed(self):
        class Zero:
            pass

        def encoder(_self, o):
            return decimal.Decimal("0") if isinstance(o, Zero) else None

        with mock.patch("sqldesk.query_runner.query_runners", {"fake": mock.Mock(custom_json_encoder=encoder)}):
            self.assertEqual({"x": 0.0}, json_loads(json_dumps({"x": Zero()})))


class TestMysqlTakesTheModeItIsGiven(TestCase):
    def test_a_mode_that_insists_on_tls_applies_without_the_checkbox(self):
        """Verify Identity without ticking Use SSL decided nothing: the connection took what the server offered."""
        from sqldesk.query_runner.mysql import Mysql

        runner = Mysql({"host": "db", "db": "x", "ssl_mode": "verify-identity"})

        self.assertEqual("VERIFY_IDENTITY", runner._get_ssl_mode())

    def test_preferred_alone_still_changes_nothing(self):
        from sqldesk.query_runner.mysql import Mysql

        self.assertIsNone(Mysql({"host": "db", "db": "x", "ssl_mode": "preferred"})._get_ssl_mode())


class TestBigQueryCanBeCancelledEarly(TestCase):
    def test_there_is_no_job_id_before_a_job(self):
        """Read by the cancel handler; first set only after the insert, so an early cancel raised AttributeError."""
        if not installed("googleapiclient"):
            self.skipTest("google-api-python-client is in the all_ds group")
        from sqldesk.query_runner.big_query import BigQuery

        self.assertIsNone(BigQuery({"projectId": "p", "jsonKeyFile": ""}).current_job_id)


class TestPrestoKeepsTheEnginesMessage(TestCase):
    def test_a_failure_without_failure_info_says_what_presto_said(self):
        if not installed("pyhive"):
            self.skipTest("pyhive is in the all_ds group")
        from pyhive.exc import DatabaseError

        from sqldesk.query_runner import presto

        cursor = mock.Mock()
        cursor.execute.side_effect = DatabaseError({"message": "line 1:8: Column 'x' cannot be resolved"})
        with mock.patch.object(presto.presto, "connect", return_value=mock.Mock(cursor=lambda: cursor)):
            _, error = presto.Presto({"host": "p"}).run_query("SELECT x", None)

        self.assertEqual("line 1:8: Column 'x' cannot be resolved", error)


class TestSqliteStopsWhenTold(TestCase):
    def test_a_timeout_interrupts_the_query(self):
        """`cancel` does not exist on sqlite3; the AttributeError replaced the timeout and nothing stopped."""
        from sqldesk.query_runner import sqlite

        connection = mock.Mock(spec=["cursor", "interrupt", "close"])
        connection.cursor.return_value.execute.side_effect = JobTimeoutException()
        with mock.patch.object(sqlite.sqlite3, "connect", return_value=connection):
            with self.assertRaises(JobTimeoutException):
                sqlite.Sqlite({"dbpath": "/tmp/x.db"}).run_query("SELECT 1", None)

        connection.interrupt.assert_called_once()

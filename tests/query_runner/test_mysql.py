"""The SSL settings on a MySQL data source, which used to decide nothing."""

from unittest import TestCase

from sqldesk.query_runner.mysql import MariaDB, Mysql, RDSMySQL


class TestMysqlSSLMode(TestCase):
    def test_the_mode_reaches_the_driver_in_mysqls_own_spelling(self):
        # The form says "verify-identity"; MySQL calls it VERIFY_IDENTITY. The value
        # was previously filed into the ssl mapping under the key "preferred", where
        # mysqlclient ignores it without complaining -- so the dropdown was decorative
        # and an install that asked to verify the server verified nothing.
        runner = Mysql({"db": "x", "use_ssl": True, "ssl_mode": "verify-identity"})
        self.assertEqual(runner._get_ssl_mode(), "VERIFY_IDENTITY")

    def test_every_mode_the_form_offers_is_translated(self):
        offered = [
            option["value"] for option in Mysql.configuration_schema()["properties"]["ssl_mode"]["extendedEnum"]
        ]
        for value in offered:
            runner = Mysql({"db": "x", "use_ssl": True, "ssl_mode": value})
            self.assertIsNotNone(runner._get_ssl_mode(), "{} has no MySQL spelling".format(value))

    def test_a_mode_that_insists_on_tls_needs_no_checkbox(self):
        # Choosing Required without also ticking Use SSL used to decide
        # nothing: the connection took whatever the server offered.
        self.assertEqual("REQUIRED", Mysql({"db": "x", "ssl_mode": "required"})._get_ssl_mode())

    def test_but_preferred_alone_changes_nothing(self):
        self.assertIsNone(Mysql({"db": "x", "ssl_mode": "preferred"})._get_ssl_mode())

    def test_an_unknown_mode_is_not_invented(self):
        self.assertIsNone(Mysql({"db": "x", "use_ssl": True, "ssl_mode": "nonsense"})._get_ssl_mode())

    def test_the_mode_is_not_in_the_certificate_mapping(self):
        # mysqlclient reads only ca/capath/cert/key/cipher out of `ssl`.
        params = Mysql(
            {"db": "x", "use_ssl": True, "ssl_mode": "required", "ssl_cacert": "/ca.pem"}
        )._get_ssl_parameters()
        self.assertEqual(params, {"ca": "/ca.pem"})

    def test_no_certificates_without_use_ssl(self):
        self.assertIsNone(Mysql({"db": "x", "ssl_cacert": "/ca.pem"})._get_ssl_parameters())


class TestRDSMySQL(TestCase):
    def test_use_ssl_now_verifies_against_the_bundled_ca(self):
        # We ship Amazon's CA bundle and hand it to the driver; without a mode the
        # default applied, which accepts an unencrypted connection.
        runner = RDSMySQL({"db": "x", "user": "u", "passwd": "p", "host": "h", "use_ssl": True})
        self.assertEqual(runner._get_ssl_mode(), "VERIFY_CA")
        self.assertIn("ca", runner._get_ssl_parameters())

    def test_nothing_changes_when_ssl_is_off(self):
        runner = RDSMySQL({"db": "x", "user": "u", "passwd": "p", "host": "h"})
        self.assertIsNone(runner._get_ssl_mode())
        self.assertIsNone(runner._get_ssl_parameters())


class TestMariaDB(TestCase):
    def test_it_has_its_own_name_and_type(self):
        self.assertEqual(MariaDB.type(), "mariadb")
        self.assertEqual(MariaDB.name(), "MariaDB")

    def test_it_is_a_mysql_runner(self):
        self.assertTrue(issubclass(MariaDB, Mysql))
        self.assertEqual(
            MariaDB.configuration_schema()["properties"].keys(),
            Mysql.configuration_schema()["properties"].keys(),
        )

    def test_existing_mysql_connections_keep_their_type(self):
        self.assertEqual(Mysql.type(), "mysql")


class TestMysqlStreamsItsResult(TestCase):
    """Unbuffered, read within the budget, and the connection killed when the rest is not wanted."""

    def run_with(self, chunks, budget_mb=100):
        import threading
        from unittest.mock import MagicMock, patch

        cursor = MagicMock()
        cursor.description = [("n", 3, None, None, None, None, None)]
        cursor.fetchmany.side_effect = list(chunks) + [[]] * 5
        cursor.nextset.return_value = None
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.thread_id.return_value = 42
        runner = Mysql({"host": "h", "db": "d"})
        result = MagicMock()
        with patch("sqldesk.settings.QUERY_RESULT_MAX_MB", budget_mb), patch.object(runner, "_cancel") as cancel:
            runner._run_query("select 1", None, connection, result, threading.Event())
        return result, cursor, connection, cancel

    def test_it_reads_unbuffered(self):
        import MySQLdb.cursors

        _, _, connection, _ = self.run_with([[(1,), (2,)]])
        connection.cursor.assert_called_with(MySQLdb.cursors.SSCursor)

    def test_a_small_result_is_all_there(self):
        result, cursor, _, cancel = self.run_with([[(1,), (2,)]])
        self.assertEqual(result.data["rows"], [{"n": 1}, {"n": 2}])
        cancel.assert_not_called()
        cursor.close.assert_called()

    def test_past_the_budget_the_query_is_killed_not_read_to_the_end(self):
        result, cursor, _, cancel = self.run_with(
            [[(i,) for i in range(n, n + 1000)] for n in range(0, 200000, 1000)], 0.05
        )
        self.assertTrue(result.data["truncated"])
        cancel.assert_called_with(42)
        # Closing an unbuffered cursor would read every remaining row.
        cursor.close.assert_not_called()

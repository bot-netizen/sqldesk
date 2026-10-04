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

    def test_no_mode_without_use_ssl(self):
        self.assertIsNone(Mysql({"db": "x", "ssl_mode": "required"})._get_ssl_mode())

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

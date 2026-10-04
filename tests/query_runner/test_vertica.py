"""Vertica, which was unreachable on Python 3.13 until the driver was upgraded."""

from unittest import TestCase

from sqldesk.query_runner import TYPE_DATETIME, TYPE_STRING
from sqldesk.query_runner.vertica import Vertica, types_map


class TestVerticaIsAvailable(TestCase):
    def test_the_driver_imports(self):
        # vertica-python 1.1.1 imported the stdlib `crypt`, removed in 3.13 by PEP 594.
        # `enabled()` caught the ImportError and Vertica silently vanished from the
        # data source list -- no error anywhere, just a type nobody could choose.
        self.assertTrue(Vertica.enabled(), "vertica-python does not import")


class TestVerticaTLS(TestCase):
    def test_tls_mode_is_offered(self):
        # This runner had no TLS option of any kind: every connection, and so every
        # password, went over the wire in the clear with no way to say otherwise.
        schema = Vertica.configuration_schema()
        self.assertIn("tlsmode", schema["properties"])
        offered = [o["value"] for o in schema["properties"]["tlsmode"]["extendedEnum"]]
        self.assertEqual(offered, ["disable", "prefer", "require", "verify-ca", "verify-full"])

    def test_the_driver_accepts_every_mode_offered(self):
        from vertica_python.vertica.connection import TLSMode

        for value in [o["value"] for o in Vertica.configuration_schema()["properties"]["tlsmode"]["extendedEnum"]]:
            TLSMode(value)

    def test_the_dead_read_timeout_is_gone(self):
        # vertica-python dropped the option. Left in the form it promised a limit
        # that nothing enforced.
        self.assertNotIn("read_timeout", Vertica.configuration_schema()["properties"])


class TestVerticaTypes(TestCase):
    def test_the_type_codes_still_match_the_driver(self):
        """types_map is keyed by Vertica's own numeric type codes, so a driver upgrade
        that renumbered them would leave every column untyped and say nothing."""
        from vertica_python.datatypes import VerticaType

        known = {
            getattr(VerticaType, name)
            for name in dir(VerticaType)
            if name.isupper() and isinstance(getattr(VerticaType, name), int)
        }
        self.assertEqual(
            sorted(set(types_map) - known),
            [],
            "the driver no longer knows these type codes",
        )

    def test_an_interval_is_not_a_timestamp(self):
        from vertica_python.datatypes import VerticaType

        self.assertEqual(types_map[VerticaType.INTERVAL], TYPE_STRING)
        self.assertEqual(types_map[VerticaType.INTERVALYM], TYPE_STRING)

    def test_a_timestamp_still_is_one(self):
        from vertica_python.datatypes import VerticaType

        self.assertEqual(types_map[VerticaType.TIMESTAMP], TYPE_DATETIME)
        self.assertEqual(types_map[VerticaType.TIMESTAMPTZ], TYPE_DATETIME)

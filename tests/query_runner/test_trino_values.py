"""
Values fetched as Trino sends them, converted here: the stored result has to
be exactly what the typed client and SQLDesk's JSON encoder made of them.
"""
import math
import random
from unittest import TestCase
from unittest.mock import MagicMock, patch

from trino import exceptions as trino_exceptions
from trino.mapper import RowMapperFactory, TimestampValueMapper

from sqldesk.query_runner.trino import Trino, _explain, _fast_converters, _timestamp
from sqldesk.utils import JSONEncoder, json_dumps


def column(raw, *arguments):
    return {"name": raw, "typeSignature": {"rawType": raw, "arguments": list(arguments)}}


def precision(p):
    return {"kind": "LONG", "value": p}


class TestTimestampsMatchTheTypedPath(TestCase):
    def stored(self, value, p):
        """What the typed client and the JSON encoder made of this value."""
        return JSONEncoder().default(TimestampValueMapper(p).map(value))

    def test_every_precision_up_to_microseconds(self):
        rng = random.Random(7)
        for p in range(0, 7):
            for _ in range(300):
                whole = "20%02d-%02d-%02d %02d:%02d:%02d" % (
                    rng.randint(0, 99),
                    rng.randint(1, 12),
                    rng.randint(1, 28),
                    rng.randint(0, 23),
                    rng.randint(0, 59),
                    rng.randint(0, 59),
                )
                digits = "".join(rng.choice("0000123456789") for _ in range(p))
                value = whole + ("." + digits if p else "")
                self.assertEqual(_timestamp(value), self.stored(value, p), value)

    def test_the_cases_that_have_bitten(self):
        self.assertEqual(_timestamp("2026-11-14 09:30:01.000"), "2026-11-14T09:30:01")
        self.assertEqual(_timestamp("2026-11-14 09:30:01.5"), "2026-11-14T09:30:01.500")
        self.assertEqual(_timestamp("2026-11-14 09:30:01.000123"), "2026-11-14T09:30:01.000")
        self.assertEqual(_timestamp("2026-11-14 09:30:01"), "2026-11-14T09:30:01")


class TestColumnConverters(TestCase):
    def test_simple_types_need_no_work_or_a_float(self):
        converters = _fast_converters(
            [column("bigint"), column("varchar", precision(10)), column("date"), column("boolean")]
        )
        self.assertEqual(converters, [None, None, None, None])

    def test_a_decimal_is_stored_as_the_float_it_always_was(self):
        (convert,) = _fast_converters([column("decimal", precision(12), precision(2))])
        self.assertEqual(convert("173665.47"), 173665.47)

    def test_a_double_sent_as_nan_is_still_nan(self):
        (convert,) = _fast_converters([column("double")])
        self.assertTrue(math.isnan(convert("NaN")))
        self.assertEqual(convert(1.5), 1.5)

    def test_a_nanosecond_timestamp_goes_through_the_clients_own_mapper(self):
        (convert,) = _fast_converters([column("timestamp", precision(9))])
        self.assertEqual(
            json_dumps(convert("2026-11-14 09:30:01.123999999")),
            json_dumps(
                RowMapperFactory()
                ._create_value_mapper(column("timestamp", precision(9))["typeSignature"])
                .map("2026-11-14 09:30:01.123999999")
            ),
        )


def cursor_with(chunks, columns, query_id="20261114_0001"):
    cursor = MagicMock()
    cursor.fetchmany.side_effect = list(chunks) + [[]] * 5
    cursor.description = [(c["name"], c["typeSignature"]["rawType"]) for c in columns]
    cursor._query.columns = columns
    cursor.query_id = query_id
    return cursor


class TestTrinoReadsWithinTheBudget(TestCase):
    columns = [column("bigint"), column("varchar")]

    def run_with(self, cursor, budget_mb=1, configuration=None):
        with patch("trino.dbapi.connect") as connect, patch("sqldesk.settings.QUERY_RESULT_MAX_MB", budget_mb):
            connect.return_value.cursor.return_value = cursor
            return Trino(configuration or {"host": "h", "username": "u"}).run_query("select 1", None)

    def test_a_result_past_the_budget_is_cut_and_the_rest_cancelled_on_trino(self):
        chunks = [[[i, "x" * 200] for i in range(n, n + 1000)] for n in range(0, 20000, 1000)]
        cursor = cursor_with(chunks, self.columns)
        data, error = self.run_with(cursor, budget_mb=1)
        self.assertIsNone(error)
        self.assertTrue(data["truncated"])
        self.assertEqual(data["truncation"], {"reason": "size", "limit_mb": 1})
        self.assertLess(len(data["rows"]), 20000)
        cursor.cancel.assert_called()

    def test_a_result_inside_the_budget_is_all_there(self):
        cursor = cursor_with([[[1, "a"], [2, "b"]]], self.columns)
        data, error = self.run_with(cursor, budget_mb=100)
        self.assertEqual(data["rows"], [{"bigint": 1, "varchar": "a"}, {"bigint": 2, "varchar": "b"}])
        self.assertNotIn("truncated", data)
        cursor.cancel.assert_not_called()

    def test_a_connection_that_drops_says_so_and_stops_the_query(self):
        cursor = cursor_with([], self.columns)
        cursor.fetchmany.side_effect = trino_exceptions.TrinoConnectionError(
            "failed to fetch: ('Connection broken: IncompleteRead(0 bytes read, 2 more expected)')"
        )
        data, error = self.run_with(cursor)
        self.assertIsNone(data)
        self.assertIn("connection to Trino dropped", error)
        self.assertIn("20261114_0001", error)
        cursor.cancel.assert_called()


class TestTrinoSaysWhatWentWrong(TestCase):
    configuration = {"host": "trino.example", "port": 8080}

    def test_a_query_error_keeps_trinos_words_and_names_the_query(self):
        error = trino_exceptions.TrinoUserError({"message": "Table x does not exist"}, "q1")
        self.assertEqual(_explain(error, "q1", self.configuration), "Table x does not exist (Trino query q1)")

    def test_unreachable(self):
        message = _explain(
            trino_exceptions.TrinoConnectionError("failed to execute: refused"), None, self.configuration
        )
        self.assertIn("could not reach Trino at trino.example:8080", message)

    def test_a_gateway_error_is_not_lost(self):
        message = _explain(trino_exceptions.Http503Error("error 503: service unavailable"), "q2", self.configuration)
        self.assertIn("restarting or overloaded", message)

    def test_spooling_storage_out_of_reach(self):
        failure = trino_exceptions.OperationalError("error 404: <Code>NoSuchBucket</Code>")
        self.assertIn("spooling storage", _explain(failure, "q3", self.configuration))
        self.assertIn("Direct", _explain(failure, "q3", self.configuration))
        self.assertNotIn("spooling", _explain(failure, "q3", dict(self.configuration, encoding="direct")))

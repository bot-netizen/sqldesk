"""
A stream's DuckDB file: what goes in, what comes out, and what is never done.

The claim this suite exists to hold up is that **no message is decoded in
Python on the ingest path**. Everything else here follows from it: the batch
write, the inferred schema, the malformed counter, the truncation.
"""

import json
import os
import shutil
import tempfile
from unittest import TestCase, mock

from sqldesk.streams.store import MALFORMED, RECEIVED, Store


def events(*payloads):
    """Raw message bytes, as they would come off a topic."""
    return [json.dumps(payload).encode("utf-8") for payload in payloads]


class StoreTestCase(TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.folder, "stream.duckdb"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.folder, ignore_errors=True)


class TestNothingIsParsedInPython(StoreTestCase):
    def test_appending_never_reaches_json_loads(self):
        """
        The measurement this design was chosen on: `json.loads` one message at
        a time managed 250,000 events a second and DuckDB parsing the whole
        batch managed 914,000. A well-meaning change that adds a validation
        pass, or a counter that peeks at a field, costs most of that -- and
        would pass every other test in this file.
        """
        with mock.patch("json.loads", side_effect=AssertionError("the ingest path decoded a message")):
            with mock.patch("json.JSONDecoder.decode", side_effect=AssertionError("decoded a message")):
                added, malformed = self.store.append(events({"x": 1}, {"x": 2}))

        self.assertEqual(2, added)
        self.assertEqual(0, malformed)

    def test_nor_does_truncating_or_counting(self):
        self.store.append(events({"x": 1}))

        with mock.patch("json.loads", side_effect=AssertionError("decoded a message")):
            self.store.truncate(300)
            self.store.rows()
            self.store.observed_rate()

    def test_a_message_that_is_not_text_at_all_does_not_raise(self):
        # Raw bytes off a wire. Anything may be on it, and the ingest path is
        # the last place that should be throwing.
        added, malformed = self.store.append([b"\xff\xfe not json", b'{"x": 1}'])

        self.assertEqual(1, added)
        self.assertEqual(1, malformed)


class TestWhatGoesIn(StoreTestCase):
    def test_an_empty_flush_does_nothing(self):
        self.assertEqual((0, 0), self.store.append([]))
        self.assertEqual(0, self.store.rows())

    def test_the_columns_are_inferred_from_the_first_flush(self):
        # A better guess than ours, and the only one available before a person
        # has looked at the topic.
        self.store.append(events({"user": "a", "amount": 12}))

        names = [name for name, _kind in self.store.columns()]
        self.assertIn("user", names)
        self.assertIn("amount", names)

    def test_and_the_arrival_time_is_ours(self):
        # Not a timestamp out of the message: a topic may not have one, may
        # have it in any format, and a producer's clock is not ours.
        self.store.append(events({"x": 1}))

        self.assertEqual(RECEIVED, self.store.columns()[-1][0])

    def test_a_producer_adding_a_field_does_not_break_the_stream(self):
        # The event is stored; the new field is ignored until somebody
        # re-infers the schema. Deliberate: a chart should not change shape
        # because a producer shipped a field, and a stream whose columns moved
        # on their own would make every saved query on it a guess.
        self.store.append(events({"x": 1}))

        added, malformed = self.store.append(events({"x": 2, "extra": "new"}))

        self.assertEqual(1, added)
        self.assertEqual(0, malformed)
        self.assertNotIn("extra", [name for name, _kind in self.store.columns()])

    def test_a_field_that_changes_type_is_null_for_that_row_not_the_end(self):
        """
        The first flush fixed `id` as a number. One message sending a string
        made the INSERT a conversion error, and the consumer stopped -- again
        on every restart while that message was in the window.
        """
        self.store.append(events({"id": 1, "v": 10}))

        added, _ = self.store.append(events({"id": "a-17", "v": 11}, {"id": 3, "v": 12}))

        self.assertEqual(2, added)
        stored = self.store.connection.execute("SELECT id, v FROM events ORDER BY v").fetchall()
        self.assertEqual([(1, 10), (None, 11), (3, 12)], stored)

    def test_a_field_name_with_a_quote_in_it_is_still_a_column(self):
        self.store.append(events({'say "hi"': 1}))

        added, _ = self.store.append(events({'say "hi"': 2}))

        self.assertEqual(1, added)
        self.assertEqual(2, self.store.rows())

    def test_and_the_event_itself_is_not_lost_to_it(self):
        # Ignoring the field must not mean dropping the message.
        self.store.append(events({"x": 1}))
        self.store.append(events({"x": 2, "extra": "new"}))

        stored = self.store.connection.execute("SELECT x FROM events ORDER BY x").fetchall()
        self.assertEqual([(1,), (2,)], stored)

    def test_a_producer_dropping_a_field_does_not_either(self):
        self.store.append(events({"x": 1, "y": 2}))

        added, _malformed = self.store.append(events({"x": 3}))

        self.assertEqual(1, added)

    def test_malformed_messages_are_counted_not_kept(self):
        # Worth a number on the stream's page and nothing more. A consumer
        # that stopped for one is a consumer somebody restarts at 3am.
        added, malformed = self.store.append([b'{"x": 1}', b"{not json", b'{"x": 2}'])

        self.assertEqual(2, added)
        self.assertEqual(1, malformed)

    def test_one_odd_message_cannot_decide_the_schema(self):
        """
        The reason non-objects are filtered out before DuckDB sees them.

        Handed one `[1,2,3]` or `"a string"` in the first flush,
        `read_json_auto` abandons column inference and returns a single opaque
        `json` column -- for the life of the stream, since the schema is
        decided once. Every chart built on the topic would be reading one text
        column. The malformed count is identical either way, which is why this
        needs its own test: it is the only thing the filter is for.
        """
        added, malformed = self.store.append(
            [b'{"user": "a", "amount": 1}', b"[1,2,3]", b'"a string"', b'{"user": "b", "amount": 2}']
        )

        names = [name for name, _kind in self.store.columns()]
        self.assertIn("user", names)
        self.assertIn("amount", names)
        self.assertNotIn("json", names)
        self.assertEqual(2, added)
        self.assertEqual(2, malformed)

    def test_a_message_with_one_real_value_is_kept(self):
        # The case that actually occurs: a producer omitting some fields.
        self.store.append(events({"region": "eu", "amount": 1}))

        added, malformed = self.store.append(events({"region": None, "amount": 1}))

        self.assertEqual(1, added)
        self.assertEqual(0, malformed)

    def test_but_a_message_with_no_values_at_all_is_counted_as_malformed(self):
        """
        A known consequence, pinned here so it is a decision rather than a
        surprise. A row of nothing but nulls is what `ignore_errors=true`
        produces for a line DuckDB could not read, and a message carrying no
        non-null value produces the same thing -- there is no way to tell them
        apart. For an event stream, that message has no data in it.
        """
        self.store.append(events({"region": "eu", "amount": 1}))

        added, malformed = self.store.append(events({"region": None}))

        self.assertEqual(0, added)
        self.assertEqual(1, malformed)

    def test_a_flush_of_nothing_but_rubbish_is_survivable(self):
        added, malformed = self.store.append([b"nope", b"also nope"])

        self.assertEqual(0, added)
        self.assertEqual(2, malformed)

    def test_the_spill_file_does_not_survive_the_flush(self):
        # It holds the raw messages. Leaving them beside the database would be
        # a second copy of the data nobody is counting or cleaning up.
        self.store.append(events({"x": 1}))

        leftovers = [name for name in os.listdir(self.folder) if name.endswith(".ndjson")]
        self.assertEqual([], leftovers)

    def test_and_not_even_when_the_load_fails(self):
        with mock.patch.object(Store, "_load", side_effect=RuntimeError("duckdb said no")):
            with self.assertRaises(RuntimeError):
                self.store.append(events({"x": 1}))

        leftovers = [name for name in os.listdir(self.folder) if name.endswith(".ndjson")]
        self.assertEqual([], leftovers)

    def test_the_spill_path_has_no_tmp_in_it(self):
        """
        DuckDB 1.3.2 refuses to open a path containing `tmp` once the
        database's own `<db>.tmp/` directory is on the allowed list. Since
        `tempfile` always produces `tmp`-prefixed names, the obvious
        implementation refused every flush with a permission error naming a
        file in an allowed directory -- which is a confusing afternoon waiting
        for whoever reinstates it.
        """
        path, _dropped = self.store._spill([b'{"x":1}'])

        self.assertNotIn("tmp", os.path.basename(path))


class TestTrimming(StoreTestCase):
    def age(self, seconds):
        """Push every row back, so truncation has something to find."""
        self.store.connection.execute(
            "UPDATE events SET {} = {} - INTERVAL '{} seconds'".format(RECEIVED, RECEIVED, int(seconds))
        )

    def test_old_rows_go_and_new_ones_stay(self):
        self.store.append(events({"x": 1}))
        self.age(600)
        self.store.append(events({"x": 2}))

        went = self.store.truncate(300)

        self.assertEqual(1, went)
        self.assertEqual(1, self.store.rows())

    def test_truncating_an_empty_store_is_not_an_error(self):
        self.assertEqual(0, self.store.truncate(300))

    def test_nothing_within_the_window_is_touched(self):
        self.store.append(events({"x": 1}, {"x": 2}))

        self.assertEqual(0, self.store.truncate(300))
        self.assertEqual(2, self.store.rows())


class TestMeasuringTheRate(StoreTestCase):
    def test_an_empty_stream_is_doing_nothing(self):
        self.assertEqual(0.0, self.store.observed_rate())

    def test_sixty_events_in_the_last_minute_is_one_a_second(self):
        self.store.append(events(*[{"x": n} for n in range(60)]))

        self.assertAlmostEqual(1.0, self.store.observed_rate(over_seconds=60), places=2)

    def test_rows_outside_the_measured_period_do_not_count(self):
        # Measured over a minute rather than all time: the window calculation
        # depends on the rate *now*, and a stream that was busy an hour ago
        # should not be given a five-minute window for it.
        self.store.append(events(*[{"x": n} for n in range(60)]))
        self.store.connection.execute("UPDATE events SET {} = {} - INTERVAL '10 minutes'".format(RECEIVED, RECEIVED))

        self.assertEqual(0.0, self.store.observed_rate(over_seconds=60))


class TestTheSandbox(StoreTestCase):
    def test_a_streams_sql_cannot_read_the_rest_of_the_machine(self):
        # The store is queried through the ordinary query editor, so DuckDB's
        # defaults would be every user's: `read_text` on any path, `glob` over
        # every organisation's uploads.
        self.store.append(events({"x": 1}))

        with self.assertRaises(Exception):
            self.store.connection.execute("SELECT * FROM read_text('/etc/passwd')").fetchall()

    def test_nor_install_an_extension_to_reach_the_network(self):
        self.store.append(events({"x": 1}))

        with self.assertRaises(Exception):
            self.store.connection.execute("INSTALL httpfs").fetchall()

    def test_the_malformed_column_name_is_not_one_a_topic_can_claim(self):
        # Ours, so a producer with a field of that name cannot shadow it.
        self.assertTrue(MALFORMED.startswith("_"))
        self.assertTrue(RECEIVED.startswith("_"))


class TestItCanBeClosedAndUsedAgain(StoreTestCase):
    """
    Closing between flushes is only useful if writing still works afterwards.

    The consumer releases the file after every flush so that readers can get
    in; the next flush has to reopen it without being handed a new Store.
    """

    def test_a_closed_store_reopens_to_write(self):
        store = Store(os.path.join(self.folder, "stream.duckdb"))
        store.append(events({"x": 1}))
        store.close()

        store.append(events({"x": 2}))

        self.assertEqual(2, store.rows())
        store.close()

    def test_a_read_only_store_will_not_write(self):
        # The page, the rollup and the query runner all open it this way. A
        # reader that could write would be a second writer, which is the thing
        # the lock exists to prevent.
        path = os.path.join(self.folder, "stream.duckdb")
        writer = Store(path)
        writer.append(events({"x": 1}))
        writer.close()

        reader = Store(path, read_only=True)
        try:
            self.assertEqual(1, reader.rows())
            with self.assertRaises(Exception):
                reader.append(events({"x": 2}))
        finally:
            reader.close()


class TestTheTypesAQueryReportsBack(StoreTestCase):
    """
    Column types come from DESCRIBE, not from the cursor.

    DuckDB's DB-API `description` answers in the generic DB-API codes -- every
    number is "NUMBER", every string "STRING" -- which match none of the names
    the runner's type map is keyed by. Reading types from it typed every column
    in every stream query as text: the query worked, the table looked right,
    and no chart would plot a value until somebody cast it by hand.

    The same line also unpacked `description` into two names, and it holds
    seven, so in fact nothing ran at all.
    """

    def described(self, query):
        from sqldesk.query_runner.kafka_stream import _described

        store = Store(os.path.join(self.folder, "stream.duckdb"))
        try:
            return _described(store.connection, query)
        finally:
            store.close()

    def test_duckdbs_own_names_come_back(self):
        found = self.described("SELECT 1::BIGINT AS a, 'x' AS b, 1.5::DOUBLE AS c")

        self.assertEqual({"a": "BIGINT", "b": "VARCHAR", "c": "DOUBLE"}, found)

    def test_a_parameterised_type_loses_its_brackets(self):
        # `DECIMAL(18,3)` is keyed as `DECIMAL`, and what is in the brackets
        # says nothing about how to chart it.
        found = self.described("SELECT 1.5::DECIMAL(18,3) AS a")

        self.assertEqual("DECIMAL", found["a"])

    def test_and_they_map_to_something_a_chart_can_use(self):
        from sqldesk.query_runner import TYPE_FLOAT, TYPE_INTEGER, TYPE_STRING
        from sqldesk.query_runner.kafka_stream import TYPES

        found = self.described("SELECT 1::BIGINT AS a, 'x' AS b, 1.5::DOUBLE AS c")

        self.assertEqual(TYPE_INTEGER, TYPES[found["a"]])
        self.assertEqual(TYPE_STRING, TYPES.get(found["b"], TYPE_STRING))
        self.assertEqual(TYPE_FLOAT, TYPES[found["c"]])

    def test_a_query_that_cannot_be_planned_says_nothing_rather_than_raising(self):
        # The query itself raises a moment later with a better message.
        self.assertEqual({}, self.described("SELECT * FROM a_table_that_is_not_there"))

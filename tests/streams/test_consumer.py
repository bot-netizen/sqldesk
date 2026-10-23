"""
The consumer loop, driven by a fake broker that hands back bytes.

Kafka itself is behind one class; everything above it -- the sampling decision,
the flush, the window, the rate, the schema -- is here, and none of it needs a
broker. What a broker would add is confidence that librdkafka behaves as
`Broker` assumes, which is a different test and needs one running.
"""

import datetime
import json
import shutil
import tempfile
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.streams import consumer
from sqldesk.streams.store import Store
from sqldesk.utils import utcnow
from tests import BaseTestCase


def message(payload, key=None):
    """A `(key, value)` pair as the broker hands it over: bytes, undecoded."""
    return (key, json.dumps(payload).encode("utf-8"))


class FakeBroker:
    """
    A broker that returns what it was told to, and records what was asked of it.

    Not a mock of `confluent_kafka` -- a stand-in for `Broker`, which is the
    seam. Pretending to be librdkafka would be testing our idea of librdkafka.
    """

    def __init__(self, *batches):
        self.batches = list(batches)
        self.opened = False
        self.closed = False
        self.sought = False
        self.polls = 0
        self.commits = 0
        self.last_positions = {}

    def open(self):
        self.opened = True
        return self

    def poll(self, limit=None, timeout=None):
        self.polls += 1
        return self.batches.pop(0) if self.batches else []

    def seek_to_end(self):
        self.sought = True
        return True

    def commit_position(self):
        self.commits += 1
        return True

    def close(self):
        self.closed = True


def until_drained(broker, cap=50):
    """
    Keep going while the broker has batches left, up to a hard cap.

    The cap is not tidiness. A `should_continue` that only reads the broker's
    remaining batches never becomes false if the loop stops polling -- which is
    exactly what a mutation of the poll loop does, and it turned a mutation run
    into a hang. A test that fails is a finding; a test that hangs is an
    afternoon.
    """
    seen = {"calls": 0}

    def answer():
        seen["calls"] += 1
        return bool(broker.batches) and seen["calls"] < cap

    return answer


class ConsumerTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

    def stream(self, **fields):
        source = self.factory.create_data_source(name="Topic", type="duckdb")
        stream = models.Stream(org=self.factory.org, data_source=source, topic="events", **fields)
        db.session.add(stream)
        db.session.commit()
        return stream

    def store_for(self, stream):
        store = Store(stream.store_path())
        self.addCleanup(store.close)
        return store


class TestOneFlush(ConsumerTestCase):
    def test_the_events_are_stored(self):
        stream = self.stream()
        store = self.store_for(stream)

        result = consumer.flush_once(stream, store, [message({"x": 1}), message({"x": 2})])

        self.assertEqual(2, result.stored)
        self.assertEqual(2, store.rows())

    def test_and_what_the_page_reads_is_updated(self):
        stream = self.stream()
        store = self.store_for(stream)

        consumer.flush_once(stream, store, [message({"x": n}) for n in range(10)])

        self.assertEqual(10, stream.rows)
        self.assertGreater(stream.observed_rate, 0)
        self.assertGreater(stream.window_seconds, 0)
        self.assertIsNotNone(stream.last_flush_at)

    def test_the_columns_are_remembered_from_the_first_flush(self):
        stream = self.stream()
        store = self.store_for(stream)

        consumer.flush_once(stream, store, [message({"user": "a", "amount": 1})])

        names = [column["name"] for column in stream.columns]
        self.assertIn("user", names)
        self.assertIn("amount", names)

    def test_a_schema_somebody_settled_is_not_overwritten(self):
        """
        The columns are inferred once and then left alone. Re-inferring on every
        flush would undo a correction the moment the next message arrived, and
        would change a chart's shape because a producer shipped a field --
        which is the thing freezing a schema exists to prevent.
        """
        stream = self.stream()
        store = self.store_for(stream)
        consumer.flush_once(stream, store, [message({"x": 1})])
        stream.columns = [{"name": "x", "type": "VARCHAR"}]
        db.session.commit()

        consumer.flush_once(stream, store, [message({"x": 2})])

        self.assertEqual([{"name": "x", "type": "VARCHAR"}], list(stream.columns))

    def test_a_flush_of_nothing_is_not_an_error(self):
        # A quiet topic flushes empty once a second for as long as it is active.
        stream = self.stream()
        store = self.store_for(stream)

        result = consumer.flush_once(stream, store, [])

        self.assertEqual(0, result.stored)
        self.assertEqual(0, stream.rows)

    def test_malformed_messages_are_counted_and_accumulate(self):
        stream = self.stream()
        store = self.store_for(stream)

        consumer.flush_once(stream, store, [message({"x": 1}), (None, b"not json")])
        consumer.flush_once(stream, store, [(None, b"also not json")])

        self.assertEqual(2, stream.malformed)

    def test_a_message_with_no_value_at_all_is_skipped(self):
        # A tombstone: a key and a null value, which Kafka uses for deletion.
        # It is not an event and `read_json_auto` has nothing to do with it.
        stream = self.stream()
        store = self.store_for(stream)

        result = consumer.flush_once(stream, store, [(b"k", None), message({"x": 1})])

        self.assertEqual(1, result.stored)
        # And not counted as malformed. A compacted topic is full of these, and
        # a page reporting half a topic as broken is a page nobody trusts.
        self.assertEqual(0, result.malformed)
        self.assertEqual(0, stream.malformed)


class TestTheWindowMovesWithTheRate(ConsumerTestCase):
    def test_a_quiet_stream_gets_the_long_window(self):
        stream = self.stream()
        store = self.store_for(stream)

        consumer.flush_once(stream, store, [message({"x": 1})])

        from sqldesk.streams import window

        self.assertEqual(window.MAX_WINDOW, stream.window_seconds)

    def test_a_busier_one_gets_a_window_the_budget_buys(self):
        # Between the floor and the ceiling, which is the only range where the
        # arithmetic shows: a test that lands on either bound passes whatever
        # the rate is.
        stream = self.stream(row_budget=600)
        store = self.store_for(stream)
        now = utcnow()

        # One event a second, five seconds running.
        for second in range(5):
            now = now + datetime.timedelta(seconds=1)
            consumer.flush_once(stream, store, [message({"x": second})], now=now)

        # 1/sec, and 600 rows buys 600 seconds of it.
        self.assertEqual(600, stream.window_seconds)

    def test_events_past_the_window_are_trimmed_on_the_flush(self):
        # On the flush rather than on a timer: a timer that stopped would be a
        # disk filling with nobody watching.
        stream = self.stream()
        store = self.store_for(stream)
        consumer.flush_once(stream, store, [message({"x": 1})])
        store.connection.execute("UPDATE events SET _received_at = _received_at - INTERVAL '2 hours'")

        consumer.flush_once(stream, store, [message({"x": 2})])

        self.assertEqual(1, stream.rows)


class TestSampling(ConsumerTestCase):
    def test_under_the_ceiling_everything_is_kept(self):
        stream = self.stream()
        store = self.store_for(stream)

        result = consumer.flush_once(stream, store, [message({"x": n}) for n in range(20)])

        self.assertEqual(20, result.kept)
        self.assertEqual(1, result.sampled_at)

    def test_a_stream_already_sampling_keeps_one_in_n(self):
        stream = self.stream(sample_rate=4)
        store = self.store_for(stream)

        result = consumer.flush_once(stream, store, [message({"x": n}) for n in range(40)])

        # Keyless, so sampled by position: exactly one in four.
        self.assertEqual(10, result.kept)
        self.assertEqual(30, result.dropped)

    def test_the_ceiling_is_measured_against_the_real_rate_not_the_sampled_one(self):
        """
        A stream sampling one-in-four and storing 1,000/sec is seeing 4,000.
        Comparing the *stored* rate against the ceiling would let the sample
        rate drift back to 1, the real rate reappear, and the whole thing
        oscillate -- so the observed rate is scaled back up before the
        comparison.
        """
        stream = self.stream(sample_rate=4, events_per_second=5)
        store = self.store_for(stream)
        # 10 arrive in the second; 3 are stored at one-in-four. Against the
        # ceiling of 5 the stored 3 would say "keep everything"; the 10 that
        # arrived say one in two.
        consumer.flush_once(stream, store, [message({"x": n}) for n in range(10)])

        self.assertEqual(2, stream.sample_rate)

    def test_a_topic_over_the_ceiling_settles_rather_than_running_away(self):
        """
        At twice the ceiling, a minute of flushes. The rate used to be read off
        the rows stored in the last minute times the current sample rate, which
        fed on itself: it climbed past 100 within half a minute, stored almost
        nothing, collapsed back to 1 and did it again.
        """
        stream = self.stream(events_per_second=50)
        store = self.store_for(stream)
        now = utcnow()
        rates = []
        for second in range(60):
            now = now + datetime.timedelta(seconds=1)
            batch = [message({"n": second * 100 + n}) for n in range(100)]
            consumer.flush_once(stream, store, batch, now=now)
            rates.append(stream.sample_rate)

        self.assertEqual({2}, set(rates[5:]))
        self.assertLessEqual(max(rates), 2)

    def test_a_keyed_stream_keeps_the_same_keys(self):
        # So a per-key count can be scaled back up honestly.
        stream = self.stream(sample_rate=3)
        store = self.store_for(stream)
        batch = [message({"user": "u{}".format(n % 9)}, key="u{}".format(n % 9).encode()) for n in range(90)]

        first = consumer.flush_once(stream, store, batch)
        stream.sample_rate = 3
        second = consumer.flush_once(stream, store, batch)

        self.assertEqual(first.kept, second.kept)


class TestTheLoop(ConsumerTestCase):
    def test_nothing_from_the_first_poll_is_thrown_away(self):
        """
        `open` positions the consumer -- at the end, the beginning, a saved
        offset or wherever the last job reached -- so the first poll is already
        what was wanted. It used to be discarded before a seek to the end,
        which was right only while every start meant the end.
        """
        stream = self.stream()
        broker = FakeBroker([message({"first": 1})])
        calls = iter([True, False])
        flushed = []

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0):
            with mock.patch.object(
                consumer, "flush_once", side_effect=lambda s, st, batch, **k: flushed.extend(batch) or consumer.Flush()
            ):
                consumer.consume(stream, broker, lambda: next(calls, False))

        self.assertTrue(broker.opened)
        self.assertFalse(broker.sought)
        self.assertEqual(1, len(flushed))
        self.assertIn(b"first", flushed[0][1])

    def test_the_position_is_offered_for_committing_after_every_flush(self):
        # Whether it is committed is the broker's decision, made from the
        # topic's setting; the loop's job is to ask only once the window has it.
        stream = self.stream()
        broker = FakeBroker([message({"x": 1})], [message({"x": 2})], [message({"x": 3})])
        flushes = []
        order = []

        def flush(*args, **kwargs):
            flushes.append(1)
            order.append(("flush", broker.commits))
            return consumer.Flush()

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0):
            with mock.patch.object(consumer, "flush_once", side_effect=flush):
                consumer.consume(stream, broker, until_drained(broker))

        self.assertTrue(flushes)
        self.assertEqual(len(flushes), broker.commits)
        # And each commit comes after its flush, never before: at every flush
        # the count of commits is the count of flushes before it.
        self.assertEqual([("flush", n) for n in range(len(flushes))], order)

    # `test_the_first_poll_is_only_for_the_assignment` used to stand here,
    # asserting the first poll was thrown away as stale. The protection it gave
    # -- no backlog stamped with an arrival time of now -- moved into
    # `Broker.open`, which now assigns at the end before any poll. It is held by
    # `test_broker_positioning.py` (the default is the end) and by
    # `test_broker.py::test_a_backlog_is_not_replayed_on_a_fresh_start`
    # against a real broker; `test_nothing_from_the_first_poll_is_thrown_away`
    # above is its replacement.

    def test_every_flush_polls_at_least_once(self):
        # A plain `while elapsed < interval` polls zero times when the interval
        # is small or the clock is coarse, so the loop spun flushing nothing
        # while the topic piled up behind it.
        stream = self.stream()
        broker = FakeBroker([], [message({"x": 1})], [message({"x": 2})])

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0):
            consumer.consume(stream, broker, until_drained(broker))

        self.assertEqual(2, models.Stream.query.get(stream.id).rows)

    def test_nothing_is_decoded_in_the_loop(self):
        stream = self.stream()
        broker = FakeBroker([], [message({"x": 1}), message({"x": 2})])

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0):
            with mock.patch("json.loads", side_effect=AssertionError("the loop decoded a message")):
                consumer.consume(stream, broker, until_drained(broker))

        self.assertEqual(2, models.Stream.query.get(stream.id).rows)


class TestTheWindowIsNotHeldOpen(ConsumerTestCase):
    """
    A consumer must not hold the window's file for its whole run.

    DuckDB gives a database file to one process at a time. A consumer that
    opened the window and kept it until its deadline locked out every other
    process for minutes: the Streams page silently fell back to the schema
    stored on the row, the rollup job could not aggregate, and a query against
    the stream failed outright with a conflicting lock. The fault was invisible
    to every test here, because a fake broker and a reader in the same process
    never contend.
    """

    def test_every_flush_is_followed_by_releasing_the_file(self):
        # The order is the whole of it: a close at the end of the run would
        # satisfy a count and leave the lock held for the minutes in between.
        from sqldesk.streams import consumer as consumer_module
        from sqldesk.streams.store import Store

        stream = self.stream()
        broker = FakeBroker([message({"x": 1})], [message({"x": 2})], [message({"x": 3})])
        carry_on = iter([True] * 6 + [False])
        happened = []

        original_flush = consumer_module.flush_once
        original_close = Store.close

        def noted_flush(*args, **kwargs):
            happened.append("flush")
            return original_flush(*args, **kwargs)

        def noted_close(self):
            happened.append("close")
            return original_close(self)

        with mock.patch("sqldesk.settings.STREAM_FLUSH_SECONDS", 0):
            with mock.patch.object(consumer_module, "flush_once", noted_flush):
                with mock.patch.object(Store, "close", noted_close):
                    consumer.consume(stream, broker, lambda: next(carry_on, False))

        self.assertIn("flush", happened)
        # Nothing between a flush and the release of the file.
        for index, event in enumerate(happened):
            if event == "flush":
                self.assertEqual("close", happened[index + 1])

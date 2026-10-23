"""
A cluster is the data source; a topic is a table.

The shape this replaces had one topic per data source, which meant a ticket to
an administrator for every topic somebody wanted to look at. Now an
administrator registers the cluster once and the topics enabled on it are its
tables -- so **enabling a topic is the real access decision**, and that is what
the streams permission guards.
"""

import unittest
from unittest import TestCase, mock

from sqldesk.query_runner.kafka_stream import names_in, table_name
from tests import BaseTestCase


class TestTheIdentifierATopicIsQueriedBy(TestCase):
    """
    Kafka allows dots and hyphens in a topic name and SQL does not get on with
    either. The schema browser shows the same name this produces, so what is on
    screen is what somebody types.
    """

    def test_a_plain_name_is_itself(self):
        self.assertEqual("orders", table_name("orders"))

    def test_dots_and_hyphens_become_underscores(self):
        self.assertEqual("prod_orders_v2", table_name("prod.orders.v2"))
        self.assertEqual("order_events", table_name("order-events"))

    def test_it_is_lowercased(self):
        self.assertEqual("orders", table_name("Orders"))

    def test_a_name_that_starts_with_a_digit_gets_a_prefix(self):
        # `2024_orders` is not an identifier anywhere.
        self.assertEqual("t_2024_orders", table_name("2024-orders"))

    def test_leading_and_trailing_punctuation_is_dropped(self):
        self.assertEqual("orders", table_name(".orders."))

    def test_a_name_with_nothing_usable_in_it_still_produces_one(self):
        # Rather than an empty identifier, which would fail at a confusing
        # distance from the topic that caused it.
        self.assertEqual("topic", table_name("..."))
        self.assertEqual("topic", table_name(""))


class TestWhichTopicsAQueryNames(TestCase):
    """
    Which topics a query mentions decides two things: which consumers it keeps
    running, and which "this stream is paused" explanation to give when a table
    is missing. A substring match would keep half the cluster consuming on any
    query with a common word in it.
    """

    def test_a_query_names_the_table_it_selects_from(self):
        self.assertTrue(names_in("SELECT * FROM orders", "orders"))

    def test_whole_words_only(self):
        self.assertFalse(names_in("SELECT * FROM orders_archive", "orders"))
        self.assertFalse(names_in("SELECT * FROM old_orders", "orders"))

    def test_case_does_not_matter(self):
        self.assertTrue(names_in("select * from ORDERS", "orders"))

    def test_a_query_naming_none_of_them_names_none(self):
        self.assertFalse(names_in("SELECT 1", "orders"))

    def test_a_join_names_both(self):
        query = "SELECT * FROM orders JOIN payments USING (id)"

        self.assertTrue(names_in(query, "orders"))
        self.assertTrue(names_in(query, "payments"))


class FakeStream:
    """A stream row, as `_attached` uses one: a topic and a path."""

    def __init__(self, topic, path):
        self.topic = topic
        self._path = path
        self.columns = []

    def store_path(self):
        return self._path


class TestAttachingTheWindows(TestCase):
    """
    One database file per topic, attached read-only into one connection.

    That is what lets a query name two topics and join them, and what keeps the
    consumers out of each other's way -- a single file for the whole cluster
    would put every topic behind one writer lock.

    The cases that matter are the ones where there is nothing to attach. A
    consumer creates its file on the first connection and the `events` table on
    the first flush, so between the two there is a window with no table in it;
    attaching that and creating a view over it fails with DuckDB complaining
    about a table, which is a confusing way to learn that nothing has arrived.
    """

    def setUp(self):
        import tempfile

        from sqldesk.query_runner.kafka_stream import KafkaStream

        self.folder = tempfile.mkdtemp()
        self.runner = KafkaStream({"brokers": "localhost:9092"})

    def tearDown(self):
        import shutil

        shutil.rmtree(self.folder, ignore_errors=True)

    def window(self, topic, rows=1):
        """A window file with `rows` events in it, as a consumer leaves one."""
        import os

        from sqldesk.streams.store import Store

        path = os.path.join(self.folder, "{}.duckdb".format(topic))
        store = Store(path)
        store.append([b'{"n": %d}' % index for index in range(rows)])
        store.close()
        return FakeStream(topic, path)

    def empty_window(self, topic):
        """A file a consumer has opened and not yet flushed into."""
        import os

        from sqldesk.streams.store import Store

        path = os.path.join(self.folder, "{}.duckdb".format(topic))
        store = Store(path)
        store.connection.execute("SELECT 1")
        store.close()
        return FakeStream(topic, path)

    def missing(self, topic):
        import os

        return FakeStream(topic, os.path.join(self.folder, "{}.duckdb".format(topic)))

    def test_a_topic_with_a_window_is_queryable_by_its_name(self):
        streams = [self.window("orders", rows=3)]

        connection, attached = self.runner._attached(streams, "SELECT * FROM orders")
        try:
            self.assertEqual(["orders"], [stream.topic for stream in attached])
            self.assertEqual(3, connection.execute("SELECT count(*) FROM orders").fetchone()[0])
        finally:
            connection.close()

    def test_two_topics_can_be_joined(self):
        # The whole reason for one connection with several files attached.
        streams = [self.window("orders", rows=3), self.window("payments", rows=2)]

        connection, attached = self.runner._attached(streams, "SELECT * FROM orders, payments")
        try:
            self.assertEqual(2, len(attached))
            self.assertEqual(6, connection.execute("SELECT count(*) FROM orders CROSS JOIN payments").fetchone()[0])
        finally:
            connection.close()

    def test_a_window_with_no_events_yet_is_not_counted_as_attached(self):
        streams = [self.window("orders"), self.empty_window("payments")]

        connection, attached = self.runner._attached(streams, "SELECT * FROM orders, payments")
        try:
            self.assertEqual(["orders"], [stream.topic for stream in attached])
        finally:
            connection.close()

    def test_and_so_is_a_topic_with_no_file_at_all(self):
        streams = [self.window("orders"), self.missing("payments")]

        connection, attached = self.runner._attached(streams, "SELECT * FROM orders, payments")
        try:
            self.assertEqual(["orders"], [stream.topic for stream in attached])
        finally:
            connection.close()

    def test_but_a_quiet_topic_is_still_a_table_a_query_may_name(self):
        """
        A join across two topics where one is quiet should give a quiet answer,
        not fail outright. The quiet one becomes an empty table with the
        columns it had when it last consumed.
        """
        quiet = self.missing("payments")
        quiet.columns = [{"name": "payment_id"}, {"name": "amount"}]
        streams = [self.window("orders", rows=3), quiet]

        connection, _ = self.runner._attached(streams, "SELECT * FROM orders, payments")
        try:
            self.assertEqual(0, connection.execute("SELECT count(*) FROM payments").fetchone()[0])
            self.assertEqual(3, connection.execute("SELECT count(*) FROM orders").fetchone()[0])
        finally:
            connection.close()

    def test_one_that_has_never_consumed_anything_has_no_columns_to_offer(self):
        # Nothing to build a table from, so it stays absent and naming it gets
        # the explanation rather than a table of nothing.
        quiet = self.missing("payments")
        quiet.columns = []
        streams = [self.window("orders"), quiet]

        connection, _ = self.runner._attached(streams, "SELECT * FROM payments")
        try:
            with self.assertRaises(Exception):
                connection.execute("SELECT count(*) FROM payments").fetchone()
        finally:
            connection.close()

    def test_a_topic_whose_name_is_not_an_identifier_is_still_attached(self):
        streams = [self.window("prod.orders.v2", rows=2)]

        connection, attached = self.runner._attached(streams, "SELECT * FROM prod_orders_v2")
        try:
            self.assertEqual(1, len(attached))
            self.assertEqual(2, connection.execute("SELECT count(*) FROM prod_orders_v2").fetchone()[0])
        finally:
            connection.close()


class TestAStreamQueryIsLockedIn(TestAttachingTheWindows):
    """
    The SQL here is typed by anybody who can read the cluster, and it runs in
    the web process. Until 0.7.7 the connection was DuckDB's default, which
    could read any file the server can -- `/proc/self/environ` holds the secret
    key and the database URL -- write files, and install extensions.
    """

    def locked(self, *topics):
        streams = [self.window(topic, rows=3) for topic in topics]
        connection, _ = self.runner._attached(streams, "SELECT * FROM " + ", ".join(topics))
        self.addCleanup(connection.close)
        return connection

    def test_the_windows_it_names_are_still_readable(self):
        connection = self.locked("orders")

        self.assertEqual(3, connection.execute("SELECT count(*) FROM orders").fetchone()[0])

    def test_everything_else_is_refused(self):
        import os

        connection = self.locked("orders")
        other = self.window("payments", rows=1).store_path()
        escapes = {
            "read a file": "SELECT * FROM read_text('/etc/hosts')",
            "list files": "SELECT * FROM glob('{}/*')".format(self.folder),
            "write a file": "COPY (SELECT 1) TO '{}'".format(os.path.join(self.folder, "out.csv")),
            "attach another window": "ATTACH '{}' AS other (READ_ONLY)".format(other),
            "install an extension": "INSTALL httpfs",
            "load an extension": "LOAD httpfs",
            "switch access back on": "SET enable_external_access = true",
            "unlock": "SET lock_configuration = false",
        }
        for what, sql in escapes.items():
            with self.subTest(what):
                with self.assertRaises(Exception):
                    connection.execute(sql).fetchall()
        self.assertFalse(os.path.exists(os.path.join(self.folder, "out.csv")))

    def test_a_topic_the_query_does_not_name_is_not_attached(self):
        streams = [self.window("orders"), self.window("payments")]

        connection, attached = self.runner._attached(streams, "SELECT * FROM orders")
        self.addCleanup(connection.close)

        self.assertEqual(["orders"], [stream.topic for stream in attached])
        self.assertEqual(
            0,
            connection.execute(
                "SELECT count(*) FROM duckdb_databases() WHERE database_name = 'payments__window'"
            ).fetchone()[0],
        )

    def test_a_lock_that_cannot_be_applied_refuses_the_query(self):
        from sqldesk.query_runner import kafka_stream

        streams = [self.window("orders")]
        with mock.patch.object(kafka_stream, "LOCKED_DOWN", ("SET no_such_setting = 1",)):
            with mock.patch.object(self.runner, "_streams", return_value=streams):
                with mock.patch("sqldesk.streams.activity.note_viewed"):
                    data, error = self.runner.run_query("SELECT * FROM orders", None)

        self.assertIsNone(data)
        self.assertIn("could not be run safely", error)


class TestAStreamQueryIsBounded(TestAttachingTheWindows):
    """It runs in the web process every couple of seconds, so it has a ceiling in rows and in time."""

    def run_on(self, streams, sql):
        from sqldesk.utils import json_loads

        # Recording that the topic was viewed needs a real stream row; what is
        # under test is the query.
        with mock.patch.object(self.runner, "_streams", return_value=streams):
            with mock.patch("sqldesk.streams.activity.note_viewed"):
                data, error = self.runner.run_query(sql, None)
        return (json_loads(data) if data else None), error

    def test_it_stops_at_its_row_ceiling_and_says_so(self):
        result, error = self.run_on([self.window("orders", rows=self.runner.MAX_ROWS + 50)], "SELECT * FROM orders")

        self.assertIsNone(error)
        self.assertEqual(self.runner.MAX_ROWS, len(result["rows"]))
        self.assertTrue(result["truncated"])

    def test_under_it_nothing_is_marked(self):
        result, _ = self.run_on([self.window("orders", rows=5)], "SELECT * FROM orders")

        self.assertEqual((5, False), (len(result["rows"]), result["truncated"]))

    def test_a_query_that_runs_too_long_is_stopped_with_a_sentence(self):
        with mock.patch("sqldesk.settings.STREAM_QUERY_SECONDS", 0.2):
            _, error = self.run_on(
                [self.window("orders", rows=3)],
                "SELECT count(*) FROM orders, range(100000000000) a",
            )

        self.assertIn("longer than 0.2 seconds", error)


def _kafka_runner_available():
    from sqldesk.query_runner import get_query_runner

    return get_query_runner("kafka_stream", {}) is not None


@unittest.skipUnless(
    _kafka_runner_available(),
    "the kafka_stream runner is not registered here -- confluent-kafka is in the "
    "optional all_ds group, so a cluster does not even appear in the list",
)
class TestAClusterIsNotOfferedInTheQueryEditor(BaseTestCase):
    """
    A window exists only while somebody is watching.

    So a saved query against one would run against whatever happened to be
    there, and a dashboard widget over it would be empty most of the time --
    which reads as a broken dashboard rather than as a feature working the way
    it was designed. Streams have their own tab; the editor's picker leaves
    clusters out.
    """

    def test_the_list_marks_a_cluster_as_streams_only(self):
        self.factory.create_data_source(name="Cluster", type="kafka_stream", group=self.factory.default_group)
        self.factory.create_data_source(name="Warehouse", type="pg", group=self.factory.default_group)

        listed = {one["name"]: one for one in self.make_request("get", "/api/data_sources").json}

        self.assertTrue(listed["Cluster"]["streams_only"])
        self.assertFalse(listed["Warehouse"]["streams_only"])


@unittest.skipUnless(
    _kafka_runner_available(),
    "without the kafka runner a cluster is not recognised as one, so the guard " "has nothing to fire on",
)
class TestAnAlertCannotWatchAStream(BaseTestCase):
    """
    An alert is checked when its query's new result is stored, and a stream
    stores no result -- its window exists only while somebody is watching, and
    at three in the morning nobody is.

    So an alert on one would be an alert that never fires, which is worse than
    one that cannot be made: a person told no goes and builds something that
    works, and a person whose alert is silent believes nothing has happened.
    """

    def stream_query(self):
        from sqldesk.models import db

        source = self.factory.create_data_source(name="Cluster", type="kafka_stream", group=self.factory.default_group)
        query = self.factory.create_query(data_source=source)
        db.session.commit()
        return query

    def test_making_one_is_refused_with_the_reason(self):
        query = self.stream_query()

        rv = self.make_request(
            "post",
            "/api/alerts",
            data={"name": "Too many", "query_id": query.id, "options": {"op": ">", "value": 1}},
        )

        self.assertEqual(400, rv.status_code)
        self.assertIn("stream", rv.json["message"])

    def test_and_so_is_pointing_an_existing_one_at_a_stream(self):
        # The same decision, made the other way round -- and the way somebody
        # would get there if only the create path were guarded.
        from sqldesk.models import db

        alert = self.factory.create_alert()
        db.session.commit()
        query = self.stream_query()

        rv = self.make_request("post", "/api/alerts/{}".format(alert.id), data={"query_id": query.id})

        self.assertEqual(400, rv.status_code)

    def test_an_ordinary_query_is_unaffected(self):
        from sqldesk.models import db

        query = self.factory.create_query()
        db.session.commit()

        rv = self.make_request(
            "post",
            "/api/alerts",
            data={"name": "Too many", "query_id": query.id, "options": {"op": ">", "value": 1}},
        )

        self.assertEqual(200, rv.status_code)

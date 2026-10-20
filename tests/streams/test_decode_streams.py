"""
A stream that reads Avro or Protobuf: what lands in its window, and the
settings that say how to read it.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.streams import consumer, decode
from sqldesk.streams.store import Store
from tests import BaseTestCase
from tests.streams.test_decode import (
    AN_ORDER,
    HAVE,
    MONEY,
    ORDER,
    PAYMENT,
    WHY_NOT,
    avro_bytes,
    avsc,
    proto,
)


def order(n, **changes):
    return (None, avro_bytes(ORDER, dict(AN_ORDER, id=n, score=1.5, **changes)))


@unittest.skipUnless(HAVE, WHY_NOT)
class TestTheWindow(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        source = self.factory.create_data_source(name="Topic", type="duckdb")
        self.stream = models.Stream(org=self.factory.org, data_source=source, topic="orders")
        db.session.add(self.stream)
        db.session.commit()
        self.store = Store(self.stream.store_path())
        self.addCleanup(self.store.close)

    def read_as_avro(self):
        schema = decode.load(decode.AVRO, [avsc("order.avsc", ORDER)])
        self.stream.value_format = decode.AVRO
        self.stream.value_schema = schema.stored()
        self.stream.message_type = schema.message_type
        db.session.commit()
        return decode.StreamDecoder(self.stream)

    def test_avro_lands_with_columns_duckdb_typed_properly(self):
        decoder = self.read_as_avro()

        result = consumer.flush_once(self.stream, self.store, [order(1), order(2)], decoder=decoder)

        self.assertEqual(2, result.stored)
        types = dict(self.store.columns())
        self.assertEqual("BIGINT", types["id"])
        self.assertEqual("TIMESTAMP", types["at"])
        self.assertEqual("DATE", types["day"])
        self.assertEqual("DOUBLE", types["amount"])
        self.assertEqual(
            [(1, "WEST"), (2, "WEST")],
            self.store.connection.execute("SELECT id, region FROM events ORDER BY id").fetchall(),
        )

    def test_messages_that_do_not_decode_are_counted_as_malformed(self):
        decoder = self.read_as_avro()

        result = consumer.flush_once(self.stream, self.store, [order(1), (None, b"\x02")], decoder=decoder)

        self.assertEqual((1, 1), (result.stored, result.malformed))
        self.assertEqual(1, self.stream.malformed)

    def test_when_nothing_decodes_the_page_says_why_and_stops_saying_it_after(self):
        decoder = self.read_as_avro()

        consumer.flush_once(self.stream, self.store, [(None, b'{"x": 1}')], decoder=decoder)
        self.assertTrue(decode.is_problem(self.stream.last_error))
        self.assertIn("none of them match com.acme.Order in order.avsc", self.stream.last_error)

        consumer.flush_once(self.stream, self.store, [order(1)], decoder=decoder)
        self.assertIsNone(self.stream.last_error)

    def test_an_empty_flush_does_not_clear_the_reason(self):
        decoder = self.read_as_avro()
        consumer.flush_once(self.stream, self.store, [(None, b"\x02")], decoder=decoder)

        consumer.flush_once(self.stream, self.store, [], decoder=decoder)

        self.assertTrue(decode.is_problem(self.stream.last_error))

    def test_somebody_elses_reason_is_left_alone(self):
        decoder = self.read_as_avro()
        self.stream.last_error = "No consumer slot is free."

        consumer.flush_once(self.stream, self.store, [order(1)], decoder=decoder)

        self.assertEqual("No consumer slot is free.", self.stream.last_error)

    def test_json_streams_still_never_parse_json(self):
        decoder = decode.StreamDecoder(self.stream)

        with mock.patch("json.loads", side_effect=AssertionError("the ingest path decoded a message")):
            result = consumer.flush_once(self.stream, self.store, [(None, b'{"x": 1}')], decoder=decoder)

        self.assertEqual(1, result.stored)

    def test_changing_how_it_reads_starts_the_window_again(self):
        """Mid-run: the consumer sees the new settings on its next flush, not when its job ends."""
        decoder = decode.StreamDecoder(self.stream)
        consumer.flush_once(self.stream, self.store, [(None, b'{"old": 1}')], decoder=decoder)
        self.assertEqual(["old"], [name for name, _ in self.store.columns() if not name.startswith("_")])

        schema = decode.load(decode.AVRO, [avsc("order.avsc", ORDER)])
        self.stream.value_format = decode.AVRO
        self.stream.value_schema = schema.stored()
        self.stream.message_type = schema.message_type
        consumer.flush_once(self.stream, self.store, [order(1)], decoder=decoder)

        names = [name for name, _ in self.store.columns() if not name.startswith("_")]
        self.assertNotIn("old", names)
        self.assertIn("region", names)
        self.assertEqual(1, self.store.rows())
        self.assertIn("region", [column["name"] for column in self.stream.columns])


@unittest.skipUnless(HAVE, WHY_NOT)
class TestTheSettings(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        allowed = mock.patch("sqldesk.features.can", lambda *a, **k: True)
        allowed.start()
        self.addCleanup(allowed.stop)
        self.source = self.factory.create_data_source(
            name="Cluster", type="kafka_stream", options={"brokers": "broker:9092"}, group=self.factory.default_group
        )
        db.session.commit()

    def enable(self, topic="orders", **body):
        return self.make_request("post", "/api/data_sources/{}/topics/{}".format(self.source.id, topic), data=body)

    def proto_files(self):
        return [proto("payment.proto", PAYMENT), proto("money.proto", MONEY)]

    def test_uploaded_files_are_checked_and_their_messages_offered(self):
        rv = self.make_request(
            "post",
            "/api/data_sources/{}/stream_schema".format(self.source.id),
            data={"value_format": "protobuf", "schema_files": self.proto_files()},
        )

        self.assertEqual(200, rv.status_code, rv.json)
        self.assertEqual("acme.Payment", rv.json["message_type"])
        self.assertIn("acme.common.Money", rv.json["message_types"])

    def test_a_proto_that_does_not_compile_is_a_sentence_under_the_upload(self):
        rv = self.make_request(
            "post",
            "/api/data_sources/{}/stream_schema".format(self.source.id),
            data={"value_format": "protobuf", "schema_files": [proto("x.proto", 'syntax = "proto3";\nmessage X {')]},
        )

        self.assertEqual(400, rv.status_code)
        self.assertIn("x.proto:2:", rv.json["message"])

    def test_enabling_an_avro_topic_keeps_its_schema(self):
        rv = self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])

        self.assertEqual(200, rv.status_code, rv.json)
        stream = models.Stream.query.filter_by(topic="orders").one()
        self.assertEqual(("avro", "com.acme.Order"), (stream.value_format, stream.message_type))
        self.assertEqual("order.avsc", stream.value_schema["files"][0]["name"])

    def test_the_page_is_given_file_names_not_their_contents(self):
        self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])

        rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))
        with mock.patch("sqldesk.streams.consumer.list_topics", lambda *a, **k: [{"name": "orders"}]):
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))

        topic = rv.json["topics"][0]
        self.assertEqual(["order.avsc"], topic["schema_files"])
        self.assertEqual(["com.acme.Order"], topic["message_types"])
        self.assertNotIn("Region", json.dumps(topic))

    def test_choosing_another_message_does_not_need_the_files_again(self):
        self.enable(value_format="protobuf", schema_files=self.proto_files(), message_type="acme.Payment")

        rv = self.enable(value_format="protobuf", message_type="acme.Refund")

        self.assertEqual(200, rv.status_code, rv.json)
        stream = models.Stream.query.filter_by(topic="orders").one()
        self.assertEqual("acme.Refund", stream.message_type)
        self.assertEqual(2, len(stream.value_schema["files"]))

    def test_refusals(self):
        cases = [
            ({"value_format": "xml"}, "The format is one of"),
            ({"value_format": "avro"}, "Upload the schema file first"),
            ({"value_format": "protobuf", "schema_files": self.proto_files()}, "Choose one"),
            ({"value_format": "avro", "schema_files": [proto("p.proto", PAYMENT)]}, "not an .avsc file"),
        ]
        for body, message in cases:
            rv = self.enable(**body)
            self.assertEqual(400, rv.status_code, body)
            self.assertIn(message, rv.json["message"])
        # Refused before anything was committed. The test shares the app's
        # session, which a real request would roll back at teardown.
        db.session.rollback()
        self.assertIsNone(models.Stream.query.filter_by(topic="orders").first())

    def test_back_to_automatic_forgets_the_schema(self):
        self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])

        self.enable(value_format="auto")

        stream = models.Stream.query.filter_by(topic="orders").one()
        self.assertEqual(("auto", None, None), (stream.value_format, stream.value_schema, stream.message_type))

    def test_reading_differently_throws_away_a_window_read_the_old_way(self):
        self.enable()
        stream = models.Stream.query.filter_by(topic="orders").one()
        stream.columns = [{"name": "old", "type": "BIGINT"}]
        stream.rows = 40
        db.session.commit()
        os.makedirs(os.path.dirname(stream.store_path()), exist_ok=True)
        open(stream.store_path(), "w").close()

        with mock.patch("sqldesk.tasks.streams._being_consumed", return_value=False):
            self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])

        db.session.refresh(stream)
        self.assertEqual((None, 0), (stream.columns, stream.rows))
        self.assertFalse(os.path.exists(stream.store_path()))

    def test_saving_the_same_reading_keeps_the_window(self):
        self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])
        stream = models.Stream.query.filter_by(topic="orders").one()
        stream.rows = 40
        db.session.commit()

        self.enable(consumer_group="sqldesk-x")

        db.session.refresh(stream)
        self.assertEqual(40, stream.rows)

    def test_analysis_reads_the_sample_the_chosen_way(self):
        seen = {}

        def analyse(options, topic, decoder=None):
            seen["decoder"] = decoder
            return {"topic": topic}

        with mock.patch("sqldesk.streams.analysis.analyse", analyse):
            rv = self.make_request(
                "post",
                "/api/data_sources/{}/topics/orders/analyse".format(self.source.id),
                data={"value_format": "avro", "schema_files": [avsc("order.avsc", ORDER)]},
            )

        self.assertEqual(200, rv.status_code, rv.json)
        self.assertEqual("avro", seen["decoder"].value_format)

    def test_analysing_an_enabled_topic_again_uses_the_schema_it_already_has(self):
        """The page holds file names, never contents, so it cannot send them back."""
        self.enable(value_format="avro", schema_files=[avsc("order.avsc", ORDER)])
        seen = {}

        def analyse(options, topic, decoder=None):
            seen["decoder"] = decoder
            return {"topic": topic}

        with mock.patch("sqldesk.streams.analysis.analyse", analyse):
            for body in ({}, {"value_format": "avro"}):
                rv = self.make_request(
                    "post", "/api/data_sources/{}/topics/orders/analyse".format(self.source.id), data=body
                )
                self.assertEqual(200, rv.status_code, rv.json)
                self.assertEqual("com.acme.Order", seen["decoder"].schema.message_type)

    def test_analysis_with_a_broken_schema_says_so_before_reading_anything(self):
        with mock.patch("sqldesk.streams.analysis.analyse", side_effect=AssertionError("read the topic")):
            rv = self.make_request(
                "post",
                "/api/data_sources/{}/topics/orders/analyse".format(self.source.id),
                data={"value_format": "avro", "schema_files": [{"name": "x.avsc", "content": "{"}]},
            )

        self.assertEqual(400, rv.status_code)
        self.assertIn("x.avsc is not valid JSON", rv.json["message"])

"""
Avro and Protobuf topics: the schema files, the registry, and the JSON lines
they turn into.

Where a message has to be encoded, Confluent's own serializers do it wherever
they can -- `confluent_kafka.schema_registry` -- against a registry served over
real HTTP. A decoder tested only against bytes its own author framed proves
that the two halves agree with each other, not that either agrees with what a
producer actually sends.
"""

import base64
import datetime
import decimal
import io
import json
import re
import ssl
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import unquote

from sqldesk.query_runner import installed
from sqldesk.streams import decode

HAVE = installed("fastavro") and installed("grpc_tools") and installed("confluent_kafka")
WHY_NOT = "fastavro, grpc_tools and confluent_kafka are in the all_ds group; CI installs them"


def avsc(name, document):
    return {"name": name, "content": json.dumps(document)}


def proto(name, text):
    return {"name": name, "content": text}


def avro_bytes(document, value, named=None):
    import fastavro

    out = io.BytesIO()
    fastavro.schemaless_writer(out, fastavro.parse_schema(document, named_schemas=named or {}), value)
    return out.getvalue()


def parsed(line):
    return json.loads(line.decode("utf-8"))


ORDER = {
    "type": "record",
    "name": "Order",
    "namespace": "com.acme",
    "fields": [
        {"name": "id", "type": "long"},
        {"name": "at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
        {"name": "day", "type": {"type": "int", "logicalType": "date"}},
        {"name": "amount", "type": {"type": "bytes", "logicalType": "decimal", "precision": 10, "scale": 2}},
        {"name": "ref", "type": {"type": "string", "logicalType": "uuid"}},
        {"name": "region", "type": {"type": "enum", "name": "Region", "symbols": ["EAST", "WEST"]}},
        {"name": "note", "type": ["null", "string"], "default": None},
        {"name": "score", "type": "double"},
        {"name": "tags", "type": {"type": "map", "values": "int"}},
        {"name": "raw", "type": "bytes"},
        {
            "name": "lines",
            "type": {
                "type": "array",
                "items": {
                    "type": "record",
                    "name": "Line",
                    "fields": [{"name": "sku", "type": "string"}, {"name": "qty", "type": "int"}],
                },
            },
        },
    ],
}

AN_ORDER = {
    "id": 2**40,
    "at": datetime.datetime(2026, 10, 20, 10, 30, tzinfo=datetime.timezone.utc),
    "day": datetime.date(2026, 10, 20),
    "amount": decimal.Decimal("12.34"),
    "ref": uuid.UUID("12345678-1234-5678-1234-567812345678"),
    "region": "WEST",
    "note": None,
    "score": float("nan"),
    "tags": {"a": 1},
    "raw": b"\x01\x02",
    "lines": [{"sku": "bolt", "qty": 3}],
}

MONEY = 'syntax = "proto3";\npackage acme.common;\nmessage Money {\n  string currency = 1;\n  int64 units = 2;\n}\n'

PAYMENT = """syntax = "proto3";
package acme;

import "common/money.proto";
import "google/protobuf/timestamp.proto";
import "google/protobuf/duration.proto";
import "google/protobuf/wrappers.proto";
import "google/protobuf/struct.proto";

message Payment {
  enum Status { UNKNOWN = 0; PAID = 1; }
  message Card { string last4 = 1; }

  int64 id = 1;
  acme.common.Money total = 2;
  google.protobuf.Timestamp at = 3;
  Status status = 4;
  map<string, int32> tags = 5;
  repeated string notes = 6;
  optional double rate = 7;
  bytes raw = 8;
  Card card = 9;
  google.protobuf.Duration took = 10;
  google.protobuf.Int64Value retries = 11;
  google.protobuf.Struct extra = 12;
  oneof method { string iban = 13; string wallet = 14; }
  double ratio = 15;
  uint64 big = 16;
}

message Refund {
  int64 payment_id = 1;
}
"""


def payment_class(files=None, name="acme.Payment"):
    files = files or [proto("payment.proto", PAYMENT), proto("money.proto", MONEY)]
    return decode._message_class(decode.compile_proto(decode._placed(files)), name)


@unittest.skipUnless(HAVE, WHY_NOT)
class TestAvroSchemaFiles(unittest.TestCase):
    def test_every_kind_of_field_comes_out_as_something_duckdb_types(self):
        schema = decode.load(decode.AVRO, [avsc("order.avsc", ORDER)])

        row = parsed(decode.line(schema.decode(avro_bytes(ORDER, AN_ORDER))))

        self.assertEqual(2**40, row["id"])  # a number, not a string
        self.assertEqual("2026-10-20T10:30:00+00:00", row["at"])  # DuckDB reads this as TIMESTAMP
        self.assertEqual("2026-10-20", row["day"])
        self.assertEqual(12.34, row["amount"])
        self.assertEqual("12345678-1234-5678-1234-567812345678", row["ref"])
        self.assertEqual("WEST", row["region"])
        self.assertIsNone(row["note"])
        self.assertIsNone(row["score"])  # NaN has no JSON; DuckDB would drop the line
        self.assertEqual({"a": 1}, row["tags"])
        self.assertEqual(base64.b64encode(b"\x01\x02").decode(), row["raw"])
        self.assertEqual([{"sku": "bolt", "qty": 3}], row["lines"])

    def test_a_type_from_another_file_resolves_whichever_order_they_arrive_in(self):
        customer = {
            "type": "record",
            "name": "Customer",
            "namespace": "com.acme",
            "fields": [{"name": "name", "type": "string"}],
        }
        visit = {
            "type": "record",
            "name": "Visit",
            "namespace": "com.acme",
            "fields": [{"name": "who", "type": "com.acme.Customer"}],
        }
        import fastavro

        named = {}
        fastavro.parse_schema(customer, named_schemas=named)
        message = avro_bytes(visit, {"who": {"name": "Ann"}}, named=named)

        for files in (
            [avsc("visit.avsc", visit), avsc("customer.avsc", customer)],
            [avsc("customer.avsc", customer), avsc("visit.avsc", visit)],
        ):
            schema = decode.load(decode.AVRO, files, "com.acme.Visit")
            self.assertEqual({"who": {"name": "Ann"}}, parsed(decode.line(schema.decode(message))))

    def test_a_file_whose_top_level_is_a_union_offers_each_record(self):
        union = [
            {"type": "record", "name": "A", "namespace": "x", "fields": [{"name": "a", "type": "int"}]},
            {"type": "record", "name": "B", "namespace": "x", "fields": [{"name": "b", "type": "string"}]},
        ]
        schema = decode.load(decode.AVRO, [avsc("both.avsc", union)], "x.B")

        self.assertEqual(["x.A", "x.B"], schema.message_types)
        self.assertEqual({"b": "hi"}, parsed(decode.line(schema.decode(avro_bytes(union[1], {"b": "hi"})))))

    def test_more_than_one_record_has_to_be_chosen(self):
        union = [
            {"type": "record", "name": "A", "fields": [{"name": "a", "type": "int"}]},
            {"type": "record", "name": "B", "fields": [{"name": "b", "type": "int"}]},
        ]
        with self.assertRaisesRegex(decode.SchemaError, "Choose one: A, B"):
            decode.load(decode.AVRO, [avsc("both.avsc", union)])
        with self.assertRaisesRegex(decode.SchemaError, "There is no C in the Avro schema. It has: A, B"):
            decode.load(decode.AVRO, [avsc("both.avsc", union)], "C")

        # The page offering the choice shows the first as selected.
        self.assertEqual(
            "A", decode.load(decode.AVRO, [avsc("both.avsc", union)], first_if_unchosen=True).message_type
        )

    def test_bytes_left_over_mean_it_is_the_wrong_schema(self):
        schema = decode.load(decode.AVRO, [avsc("order.avsc", ORDER)])

        with self.assertRaisesRegex(ValueError, "2 bytes left"):
            schema.decode(avro_bytes(ORDER, AN_ORDER) + b"!!")

    def test_files_that_are_not_avro_schemas_are_refused_by_name(self):
        with self.assertRaisesRegex(decode.SchemaError, "order.json is not an .avsc file"):
            decode.load(decode.AVRO, [{"name": "order.json", "content": "{}"}])
        with self.assertRaisesRegex(decode.SchemaError, "order.avsc is not valid JSON"):
            decode.load(decode.AVRO, [{"name": "order.avsc", "content": "{nope"}])
        with self.assertRaisesRegex(decode.SchemaError, "order.avsc is not a schema Avro can use"):
            decode.load(decode.AVRO, [avsc("order.avsc", {"type": "record", "name": "X", "fields": [{"name": "a"}]})])
        with self.assertRaisesRegex(decode.SchemaError, "Upload the schema file first"):
            decode.load(decode.AVRO, [])


@unittest.skipUnless(HAVE, WHY_NOT)
class TestProtobufSchemaFiles(unittest.TestCase):
    def files(self):
        return [proto("payment.proto", PAYMENT), proto("money.proto", MONEY)]

    def test_every_kind_of_field_comes_out_as_something_duckdb_types(self):
        Payment = payment_class()
        message = Payment(id=2**40, status=1, notes=["late"], raw=b"\x01\x02", ratio=float("inf"), big=2**63 + 5)
        message.total.currency = "CAD"
        message.total.units = 5
        message.at.seconds = int(datetime.datetime(2026, 10, 20, 10, 30, tzinfo=datetime.timezone.utc).timestamp())
        message.at.nanos = 250000000
        message.tags["k"] = 3
        message.took.seconds = 2
        message.took.nanos = 500000000
        message.retries.value = 4
        message.extra.update({"source": "web", "n": 1})
        message.wallet = "apple"

        schema = decode.load(decode.PROTOBUF, self.files(), "acme.Payment")
        row = parsed(decode.line(schema.decode(message.SerializeToString())))

        self.assertEqual(2**40, row["id"])  # Protobuf's own JSON mapping makes this a string
        self.assertEqual(2**63 + 5, row["big"])
        self.assertEqual({"currency": "CAD", "units": 5}, row["total"])
        self.assertEqual("2026-10-20T10:30:00.250000+00:00", row["at"])
        self.assertEqual("PAID", row["status"])
        self.assertEqual({"k": 3}, row["tags"])
        self.assertEqual(["late"], row["notes"])
        self.assertIsNone(row["rate"])  # optional and unset: null, not 0
        self.assertEqual("AQI=", row["raw"])
        self.assertIsNone(row["card"])  # an unset message is null, not {}
        self.assertEqual(2.5, row["took"])
        self.assertEqual(4, row["retries"])
        self.assertEqual({"source": "web", "n": 1.0}, row["extra"])
        self.assertIsNone(row["iban"])  # the other side of the oneof
        self.assertEqual("apple", row["wallet"])
        self.assertIsNone(row["ratio"])  # infinity has no JSON

    def test_every_field_is_written_even_when_unset(self):
        """The columns the first flush infers must not depend on which fields that second used."""
        schema = decode.load(decode.PROTOBUF, self.files(), "acme.Payment")
        first = parsed(decode.line(schema.decode(payment_class()(id=1).SerializeToString())))
        Payment = payment_class()
        busy = Payment(id=2, status=1)
        busy.card.last4 = "4242"
        second = parsed(decode.line(schema.decode(busy.SerializeToString())))

        self.assertEqual(sorted(first), sorted(second))
        self.assertEqual(0, first["ratio"])  # proto3 scalars without presence are their zero

    def test_an_import_finds_the_upload_by_the_path_it_names(self):
        # Uploaded as money.proto, imported as common/money.proto.
        schema = decode.load(decode.PROTOBUF, self.files(), "acme.Payment")
        self.assertIn("acme.common.Money", schema.message_types)

    def test_the_well_known_types_need_no_upload(self):
        text = 'syntax = "proto3";\nimport "google/protobuf/timestamp.proto";\nmessage E { google.protobuf.Timestamp at = 1; }\n'
        self.assertEqual(["E"], decode.load(decode.PROTOBUF, [proto("e.proto", text)]).message_types)

    def test_the_file_nothing_imports_offers_its_messages_first(self):
        schema = decode.load(decode.PROTOBUF, list(reversed(self.files())), first_if_unchosen=True)

        self.assertEqual(
            ["acme.Payment", "acme.Payment.Card", "acme.Refund", "acme.common.Money"], schema.message_types
        )
        self.assertEqual("acme.Payment", schema.message_type)

    def test_a_compile_error_names_their_file_not_ours(self):
        with self.assertRaises(decode.SchemaError) as raised:
            decode.load(decode.PROTOBUF, [proto("bad.proto", 'syntax = "proto3";\nmessage X { int32 a = 1 }\n')])

        message = str(raised.exception)
        self.assertIn("bad.proto:2:", message)
        self.assertNotIn("sqldesk-proto-", message)

    def test_a_missing_import_says_which(self):
        with self.assertRaisesRegex(decode.SchemaError, "common/money.proto"):
            decode.load(decode.PROTOBUF, [proto("payment.proto", PAYMENT)], "acme.Payment")

    def test_an_import_that_climbs_out_is_refused(self):
        files = [
            proto("a.proto", 'syntax = "proto3";\nimport "../b.proto";\nmessage A { int32 x = 1; }\n'),
            proto("b.proto", 'syntax = "proto3";\nmessage B { int32 y = 1; }\n'),
        ]
        with self.assertRaisesRegex(decode.SchemaError, "not a path a .proto file can be imported from"):
            decode.load(decode.PROTOBUF, files)

    def test_only_proto_files(self):
        with self.assertRaisesRegex(decode.SchemaError, "payment.desc is not a .proto file"):
            decode.load(decode.PROTOBUF, [{"name": "payment.desc", "content": "x"}])


class _RegistryHandler(BaseHTTPRequestHandler):
    """The HTTP side of `FakeRegistry`, which it reaches as `self.server.registry`."""

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/vnd.schemaregistry.v1+json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _start(self, method):
        """Record the request and check its credentials. The path, or None if refused."""
        registry = self.server.registry
        path = self.path.split("?")[0]
        registry.requests.append((method, path))
        if registry.credentials:
            expected = "Basic " + base64.b64encode("{}:{}".format(*registry.credentials).encode()).decode()
            if self.headers.get("Authorization") != expected:
                self._send(401, {"error_code": 40101, "message": "Unauthorized"})
                return None
        return path

    def _version(self, subject, version):
        registry = self.server.registry
        ids = registry.subjects[subject]
        number = len(ids) if version == "latest" else int(version)
        body = registry.document(ids[number - 1])
        body.update({"subject": subject, "version": number, "id": ids[number - 1]})
        return body

    def do_GET(self):
        registry = self.server.registry
        path = self._start("GET")
        if path is None:
            return
        if path == "/subjects":
            return self._send(200, sorted(registry.subjects))
        found = re.match(r"^/schemas/ids/(\d+)$", path)
        if found and int(found.group(1)) in registry.schemas:
            return self._send(200, registry.document(int(found.group(1))))
        found = re.match(r"^/subjects/([^/]+)/versions/(latest|\d+)$", path)
        if found and unquote(found.group(1)) in registry.subjects:
            return self._send(200, self._version(unquote(found.group(1)), found.group(2)))
        self._send(404, {"error_code": 40403, "message": "Schema not found"})

    def do_POST(self):
        registry = self.server.registry
        path = self._start("POST")
        if path is None:
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        found = re.match(r"^/subjects/([^/]+)/versions$", path)
        if found:
            subject = unquote(found.group(1))
            schema_id = registry.register(
                subject, body["schema"], body.get("schemaType", "AVRO"), body.get("references")
            )
            return self._send(200, {"id": schema_id})
        found = re.match(r"^/subjects/([^/]+)$", path)
        if found:
            subject = unquote(found.group(1))
            for version, schema_id in enumerate(registry.subjects.get(subject, []), 1):
                if registry.schemas[schema_id]["schema"] == body["schema"]:
                    return self._send(200, self._version(subject, version))
        self._send(404, {"error_code": 40403, "message": "Schema not found"})


class FakeRegistry:
    """
    Confluent's schema registry API, as much of it as producers and SQLDesk use,
    over real HTTP on a free port. `requests` lists every path asked for.
    """

    def __init__(self, username=None, password=None, tls=None):
        self.schemas = {}
        self.subjects = {}
        self.requests = []
        self.credentials = (username, password) if username else None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RegistryHandler)
        self.server.registry = self
        scheme = "http"
        if tls:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as chain:
                chain.write(tls["server_cert"] + tls["server_key"])
            context.load_cert_chain(chain.name)
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
            scheme = "https"
        self.url = "{}://{}:{}".format(scheme, "localhost" if tls else "127.0.0.1", self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def register(self, subject, schema, schema_type="AVRO", references=None):
        for schema_id, existing in self.schemas.items():
            if existing["schema"] == schema and existing["schemaType"] == schema_type:
                break
        else:
            schema_id = len(self.schemas) + 1
            self.schemas[schema_id] = {"schema": schema, "schemaType": schema_type, "references": references or []}
        versions = self.subjects.setdefault(subject, [])
        if schema_id not in versions:
            versions.append(schema_id)
        return schema_id

    def document(self, schema_id):
        stored = self.schemas[schema_id]
        body = {"schema": stored["schema"], "references": stored["references"]}
        if stored["schemaType"] != "AVRO":
            # Confluent leaves it out for Avro, which is the default.
            body["schemaType"] = stored["schemaType"]
        return body

    def asked(self, path):
        return sum(1 for _method, seen in self.requests if seen == path)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def serialize(serializer, value, topic="orders"):
    from confluent_kafka.serialization import MessageField, SerializationContext

    return serializer(value, SerializationContext(topic, MessageField.VALUE))


@unittest.skipUnless(HAVE, WHY_NOT)
class TestARegistry(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.addCleanup(self.registry.close)

    def client(self):
        from confluent_kafka.schema_registry import SchemaRegistryClient

        return SchemaRegistryClient({"url": self.registry.url})

    def decoder(self, **options):
        options.setdefault("schema_registry_url", self.registry.url)
        return decode.Decoder(decode.AUTO, registry=decode.registry_for(options))

    def test_avro_written_by_confluents_serializer_is_read(self):
        from confluent_kafka.schema_registry.avro import AvroSerializer

        serializer = AvroSerializer(self.client(), json.dumps(ORDER), conf={"auto.register.schemas": True})
        messages = [serialize(serializer, dict(AN_ORDER, id=n)) for n in range(50)]

        found = self.decoder().decode(messages)

        self.assertEqual(0, found.failed)
        self.assertEqual(list(range(50)), [parsed(line)["id"] for line in found.lines])
        self.assertEqual({"Avro": 50}, found.kinds)
        # Asked once for fifty messages.
        self.assertEqual(1, self.registry.asked("/schemas/ids/1"))

    def test_avro_that_refers_to_another_subject_is_read(self):
        customer = {
            "type": "record",
            "name": "Customer",
            "namespace": "com.acme",
            "fields": [{"name": "name", "type": "string"}],
        }
        visit = {
            "type": "record",
            "name": "Visit",
            "namespace": "com.acme",
            "fields": [{"name": "who", "type": "com.acme.Customer"}],
        }
        self.registry.register("customer-value", json.dumps(customer))
        visit_id = self.registry.register(
            "visits-value",
            json.dumps(visit),
            references=[{"name": "com.acme.Customer", "subject": "customer-value", "version": 1}],
        )
        import fastavro

        named = {}
        fastavro.parse_schema(customer, named_schemas=named)
        message = b"\x00" + visit_id.to_bytes(4, "big") + avro_bytes(visit, {"who": {"name": "Ann"}}, named)

        found = self.decoder().decode([message])

        self.assertEqual([{"who": {"name": "Ann"}}], [parsed(line) for line in found.lines])

    def protobuf_serializer(self, message_class, subject="payments-value"):
        from confluent_kafka.schema_registry.protobuf import ProtobufSerializer

        return ProtobufSerializer(
            message_class,
            self.client(),
            conf={"auto.register.schemas": False, "use.latest.version": True, "use.deprecated.format": False},
        )

    def register_payment(self):
        self.registry.register("common/money.proto", MONEY, "PROTOBUF")
        return self.registry.register(
            "payments-value",
            PAYMENT,
            "PROTOBUF",
            references=[{"name": "common/money.proto", "subject": "common/money.proto", "version": 1}],
        )

    def test_protobuf_written_by_confluents_serializer_is_read(self):
        self.register_payment()
        Payment = payment_class()
        message = Payment(id=7, status=1)
        message.total.currency = "CAD"
        serializer = self.protobuf_serializer(Payment)

        found = self.decoder().decode([serialize(serializer, message, topic="payments")])

        self.assertEqual(0, found.failed, found.problem)
        row = parsed(found.lines[0])
        self.assertEqual((7, "PAID", "CAD"), (row["id"], row["status"], row["total"]["currency"]))
        self.assertEqual({"Protobuf": 1}, found.kinds)

    def test_a_nested_protobuf_message_is_found_by_its_index(self):
        """The header says which message in the file: here the second index, inside the first message."""
        self.register_payment()
        Card = payment_class(name="acme.Payment.Card")
        serializer = self.protobuf_serializer(Card)

        framed = serialize(serializer, Card(last4="4242"), topic="payments")
        found = self.decoder().decode([framed])

        self.assertEqual([0, 0], decode.message_indexes(framed[5:])[0])
        self.assertEqual([{"last4": "4242"}], [parsed(line) for line in found.lines])

    def test_the_second_top_level_message_is_found_by_its_index(self):
        self.register_payment()
        Refund = payment_class(name="acme.Refund")
        framed = serialize(self.protobuf_serializer(Refund), Refund(payment_id=9), topic="payments")

        found = self.decoder().decode([framed])

        self.assertEqual([1], decode.message_indexes(framed[5:])[0])
        self.assertEqual([{"payment_id": 9}], [parsed(line) for line in found.lines])

    def test_json_schema_messages_go_through_as_the_json_they_carry(self):
        from confluent_kafka.schema_registry.json_schema import JSONSerializer

        schema = json.dumps({"title": "Tick", "type": "object", "properties": {"x": {"type": "integer"}}})
        serializer = JSONSerializer(schema, self.client(), conf={"auto.register.schemas": True})
        framed = serialize(serializer, {"x": 1})

        found = self.decoder().decode([framed])

        self.assertEqual([{"x": 1}], [parsed(line) for line in found.lines])
        self.assertEqual({"JSON Schema": 1}, found.kinds)

    def test_credentials_are_sent_and_wrong_ones_said_so(self):
        self.registry.close()
        self.registry = FakeRegistry(username="key", password="secret")
        schema_id = self.registry.register("orders-value", json.dumps(ORDER))
        message = b"\x00" + schema_id.to_bytes(4, "big") + avro_bytes(ORDER, AN_ORDER)

        wrong = self.decoder(schema_registry_username="key", schema_registry_password="nope").decode([message])
        right = self.decoder(schema_registry_username="key", schema_registry_password="secret").decode([message])

        self.assertEqual(1, wrong.failed)
        self.assertIn("refused the credentials", wrong.problem)
        self.assertEqual(1, len(right.lines))

    def test_a_registry_that_is_down_is_named_and_not_asked_again_at_once(self):
        url = self.registry.url
        self.registry.close()
        decoder = decode.Decoder(decode.AUTO, registry=decode.Registry(url, timeout=1))
        message = b"\x00\x00\x00\x00\x01" + b"rest"

        first = decoder.decode([message])
        with mock.patch.object(decode.Registry, "_build", side_effect=AssertionError("asked again")):
            second = decoder.decode([message])

        self.assertTrue(first.problem.startswith(decode.PROBLEM))
        self.assertIn(url, first.problem)
        self.assertEqual(1, second.failed)

    def test_bytes_that_only_look_framed_cannot_flood_it(self):
        """A plain binary topic whose messages start with a zero byte has a different "id" in each."""
        decoder = self.decoder()
        garbage = [b"\x00" + n.to_bytes(4, "big") + b"x" for n in range(1000, 1100)]

        found = decoder.decode(garbage)

        self.assertEqual(100, found.failed)
        self.assertEqual(
            decode.MAX_FAILED_IDS, sum(1 for _m, path in self.registry.requests if "/schemas/ids/" in path)
        )

    def test_over_tls_it_trusts_the_clusters_own_ca(self):
        """
        With a CA whose certificates carry no Authority Key Identifier, as these
        do and as many internal ones do: Python 3.13's strict default refuses
        them, librdkafka does not, and the registry has to agree with the
        brokers it sits beside.
        """
        from tests.streams.test_tls import _certificates

        certs = _certificates("localhost")
        self.registry.close()
        self.registry = FakeRegistry(tls=certs)
        schema_id = self.registry.register("orders-value", json.dumps(ORDER))
        message = b"\x00" + schema_id.to_bytes(4, "big") + avro_bytes(ORDER, AN_ORDER)

        untrusted = self.decoder().decode([message])

        trusted = self.decoder(ssl_ca_File=base64.b64encode(certs["ca"].encode()).decode()).decode([message])

        self.assertEqual(1, untrusted.failed)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", untrusted.problem)
        self.assertEqual(1, len(trusted.lines))

    def test_the_connection_test_checks_the_registry_too(self):
        from sqldesk.query_runner.kafka_stream import KafkaStream

        url = self.registry.url
        self.registry.close()
        runner = KafkaStream({"brokers": "broker:9092", "schema_registry_url": url})
        with mock.patch("sqldesk.streams.consumer.describe_topic", return_value=None):
            with self.assertRaisesRegex(Exception, "the schema registry did not"):
                runner.test_connection()


@unittest.skipUnless(HAVE, WHY_NOT)
class TestAutomatic(unittest.TestCase):
    def test_json_goes_through_as_the_same_bytes_without_being_parsed(self):
        messages = [b'{"x": 1}', b'  {"y": 2}']

        with mock.patch("json.loads", side_effect=AssertionError("JSON was parsed")):
            found = decode.Decoder().decode(messages)

        self.assertIs(messages[0], found.lines[0])
        self.assertIs(messages[1], found.lines[1])
        self.assertEqual({"JSON": 2}, found.kinds)
        self.assertIsNone(found.problem)

    def test_a_registry_header_with_no_registry_says_to_add_one(self):
        found = decode.Decoder().decode([b"\x00\x00\x00\x00\x01payload"])

        self.assertEqual(1, found.failed)
        self.assertEqual(decode.NO_REGISTRY, found.problem)

    def test_bytes_that_are_neither_say_to_choose_the_format(self):
        found = decode.Decoder().decode([b"\x08\x96\x01", b"plain text"])

        self.assertEqual(decode.NOT_JSON, found.problem)
        # Left for the store to drop and count, as before there was a decoder.
        self.assertEqual(2, len(found.lines))

    def test_one_odd_message_among_good_ones_is_not_a_headline(self):
        found = decode.Decoder().decode([b'{"x": 1}', b"\x00\x00\x00\x00\x01odd"])

        self.assertIsNone(found.problem)
        self.assertEqual(1, found.failed)


@unittest.skipUnless(HAVE, WHY_NOT)
class TestTheCost(unittest.TestCase):
    """
    Decoding runs after sampling, so it never sees more than the ceiling --
    5,000 events a second per stream by default. A second's worth has to
    decode in well under a second, or the consumer falls behind the ceiling it
    promised. Bounds are generous, for a loaded CI machine. Measured on one
    core of a laptop: about 49,000 of these Avro messages a second and 45,000
    of the Protobuf -- so a stream at its ceiling spends about a tenth of a
    core decoding.
    """

    CEILING = 5000

    def timed(self, decoder, messages):
        started = time.perf_counter()
        found = decoder.decode(messages)
        elapsed = time.perf_counter() - started
        self.assertEqual(len(messages), len(found.lines))
        return elapsed

    def test_a_seconds_worth_of_avro(self):
        schema = decode.load(decode.AVRO, [avsc("order.avsc", ORDER)])
        messages = [avro_bytes(ORDER, dict(AN_ORDER, id=n, score=1.5)) for n in range(self.CEILING)]

        elapsed = self.timed(decode.Decoder(decode.AVRO, schema=schema), messages)

        self.assertLess(elapsed, 2.0)

    def test_a_seconds_worth_of_protobuf(self):
        schema = decode.load(
            decode.PROTOBUF, [proto("payment.proto", PAYMENT), proto("money.proto", MONEY)], "acme.Payment"
        )
        Payment = payment_class()
        messages = []
        for n in range(self.CEILING):
            message = Payment(id=n, status=1, notes=["a"])
            message.total.currency = "CAD"
            message.at.seconds = 1700000000
            messages.append(message.SerializeToString())

        elapsed = self.timed(decode.Decoder(decode.PROTOBUF, schema=schema), messages)

        self.assertLess(elapsed, 2.0)

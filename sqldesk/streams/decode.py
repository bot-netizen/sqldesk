"""
Avro and Protobuf, turned into the JSON the store already reads.

The store's rule is that no message is decoded in Python: JSON goes to DuckDB as
the bytes it arrived as, which is what lets the ingest path keep up. Avro and
Protobuf cannot be read that way -- they are binary, and the schema that says
what the bytes mean is not in them -- so they are decoded here, one message at
a time, into JSON lines the store takes exactly as if a producer had sent them.

**JSON is never touched.** A message that is already a JSON object passes
through as the same bytes object. Only what needs a schema pays for one.

**After sampling, never before.** The consumer samples first, so the work done
here is bounded by the stream's ceiling (5,000 events a second by default)
however fast the topic is. Measured in `tests/streams/test_decode.py`.

Where the schema comes from:

- **A schema registry.** Confluent's wire format -- which Confluent, Redpanda,
  Karapace and Apicurio all speak -- puts a zero byte and a four-byte schema
  id in front of every message. The id is looked up once and kept; the
  registry says whether it is Avro, Protobuf or JSON Schema. Nothing has to be
  set per topic.
- **Files somebody uploads.** An `.avsc` for Avro, `.proto` files for
  Protobuf, for messages that carry no registry header at all.

Every value comes out as something DuckDB will type sensibly: timestamps as ISO
strings (which it reads as TIMESTAMP), 64-bit integers as numbers rather than
the strings Protobuf's own JSON mapping uses, bytes as base64, enums by name.
And every field is written on every message, set or not, so the columns the
first flush infers do not depend on which fields that second happened to use.
"""

import base64
import datetime
import decimal
import io
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import quote

from sqldesk.query_runner import deferred

fastavro = deferred("fastavro")

logger = logging.getLogger(__name__)

AUTO = "auto"
AVRO = "avro"
PROTOBUF = "protobuf"
FORMATS = (AUTO, AVRO, PROTOBUF)

#: The first byte of a message in Confluent's wire format.
MAGIC = 0

#: How much schema somebody may upload for one topic. A schema is text; a
#: megabyte of it is already a very large one.
MAX_SCHEMA_BYTES = 1024 * 1024

#: How long a schema the registry could not give is not asked for again. Long
#: enough not to send it a request per message while it is down, short enough
#: that it is noticed when it is back.
RETRY_SECONDS = 30

#: How many different schema ids may fail to load in one retry period before
#: the rest are not asked for. A topic of plain binary that happens to start
#: with a zero byte would otherwise send the registry a request for every
#: random "id" in it.
MAX_FAILED_IDS = 10

#: Every problem this module reports starts with this, so the consumer can tell
#: its own sentence on a stream from somebody else's and clear only its own.
PROBLEM = "Messages could not be read: "


class SchemaError(ValueError):
    """A schema that cannot be used, with a sentence a person can act on."""


def is_problem(text):
    return bool(text) and text.startswith(PROBLEM)


# --- schema files ------------------------------------------------------------


class Schema:
    """
    A topic's uploaded schema, loaded and checked.

    `message_types` is what can be chosen; `message_type` is what was. Built by
    `load`, which is the only place uploaded files are trusted to be read.
    """

    def __init__(self, value_format, files, message_types, message_type, decode):
        self.value_format = value_format
        self.files = files
        self.message_types = message_types
        self.message_type = message_type
        self.decode = decode

    def stored(self):
        """What a stream keeps, so the page can show it without recompiling."""
        return {"files": self.files, "message_types": self.message_types}


def load(value_format, files, message_type=None, first_if_unchosen=False):
    """
    Check uploaded schema files and build the decoder they describe.

    Raises `SchemaError` with a sentence for the person who uploaded them. Run
    when they are uploaded, again when a topic is enabled, and when a consumer
    starts -- a schema that loaded once is not trusted to load for ever, since
    the files are the record and this is cheap.
    """
    files = _clean(files)
    if value_format == AVRO:
        return _load_avro(files, message_type, first_if_unchosen)
    if value_format == PROTOBUF:
        return _load_protobuf(files, message_type, first_if_unchosen)
    raise SchemaError("Only Avro and Protobuf take a schema file.")


def _clean(files):
    if not files:
        raise SchemaError("Upload the schema file first.")
    cleaned = []
    total = 0
    for item in files:
        name = os.path.basename(str((item or {}).get("name") or "")).strip()
        content = (item or {}).get("content")
        if not name or not isinstance(content, str):
            raise SchemaError("Each schema file needs a name and its text.")
        total += len(content.encode("utf-8"))
        cleaned.append({"name": name, "content": content})
    if total > MAX_SCHEMA_BYTES:
        raise SchemaError("The schema files come to more than a megabyte, which is not a schema.")
    if len({item["name"] for item in cleaned}) != len(cleaned):
        raise SchemaError("Two schema files have the same name.")
    return cleaned


def _choose(candidates, message_type, where, first_if_unchosen=False):
    if not candidates:
        raise SchemaError("There is no message in the {} to read with.".format(where))
    if not message_type and first_if_unchosen:
        # Only for the page offering the choice, which shows the first as
        # selected. Anything that reads messages is told which.
        return candidates[0]
    if message_type:
        if message_type not in candidates:
            raise SchemaError(
                "There is no {} in the {}. It has: {}.".format(message_type, where, ", ".join(candidates))
            )
        return message_type
    if len(candidates) > 1:
        raise SchemaError(
            "There is more than one message in the {}. Choose one: {}.".format(where, ", ".join(candidates))
        )
    return candidates[0]


# --- Avro ----------------------------------------------------------------------


def _load_avro(files, message_type, first_if_unchosen=False):
    for item in files:
        if not item["name"].lower().endswith(".avsc"):
            raise SchemaError("{} is not an .avsc file. Avro schemas are uploaded as .avsc.".format(item["name"]))

    documents = []
    for item in files:
        try:
            parsed = json.loads(item["content"])
        except ValueError as error:
            raise SchemaError("{} is not valid JSON: {}".format(item["name"], error))
        # A file whose top level is a union is several schemas in one file,
        # which is how some teams keep a topic's types together. Each branch
        # is a schema of its own here.
        for part in parsed if isinstance(parsed, list) else [parsed]:
            documents.append((item["name"], part))

    named, unparsed = _parse_avro(documents)
    if unparsed:
        name, problem = unparsed
        raise SchemaError("{} is not a schema Avro can use: {}".format(name, problem))

    candidates = []
    for _name, document in documents:
        candidates.extend(_avro_records(document))
    chosen = _choose(candidates, message_type, "Avro schema", first_if_unchosen)

    # Built from the chosen record's own definition, with every other file's
    # types to refer to: fastavro cannot build a reader from a name alone.
    own = next(document for _name, document in documents if chosen in _avro_records(document))
    others, _ = _parse_avro([(name, document) for name, document in documents if document is not own])
    schema = fastavro.parse_schema(own, named_schemas=others)
    return Schema(AVRO, files, candidates, chosen, _avro_decoder(schema))


def _parse_avro(documents):
    """
    Parse schemas that may refer to each other's named types, in any order.

    Returns the named types and, if some never parsed, the last reason why.
    Parsed until nothing more does, so the order files were uploaded in does
    not matter.
    """
    named = {}
    waiting = list(documents)
    while waiting:
        failed = []
        error = None
        for name, document in waiting:
            # Into a copy, kept only if the whole file parses: a file that
            # fails halfway would otherwise leave the types it got through
            # behind, and its retry would fail on them as redefined.
            trial = dict(named)
            try:
                fastavro.parse_schema(document, named_schemas=trial)
            except Exception as problem:  # fastavro raises several kinds
                failed.append((name, document))
                error = (name, problem)
                continue
            named = trial
        if len(failed) == len(waiting):
            return named, error
        waiting = failed
    return named, None


def _avro_records(document, namespace=None):
    """The record names a file declares at its top level -- what a message can be."""
    if isinstance(document, list):
        names = []
        for branch in document:
            names.extend(_avro_records(branch, namespace))
        return names
    if isinstance(document, dict) and document.get("type") == "record":
        name = document.get("name", "")
        space = document.get("namespace", namespace)
        return [name if "." in name or not space else "{}.{}".format(space, name)]
    return []


def _avro_decoder(schema):
    def decode(data):
        handle = io.BytesIO(data)
        value = fastavro.schemaless_reader(handle, schema, None)
        # Bytes left over mean the schema is not the one these bytes were
        # written with. Avro has no framing to say so; this is the only check.
        if handle.tell() != len(data):
            raise ValueError("{} bytes left after the record".format(len(data) - handle.tell()))
        return value

    return decode


# --- Protobuf --------------------------------------------------------------------

IMPORT = re.compile(r'\bimport\s+(?:public\s+|weak\s+)?"([^"]+)"\s*;')


def _load_protobuf(files, message_type, first_if_unchosen=False):
    for item in files:
        if not item["name"].lower().endswith(".proto"):
            raise SchemaError("{} is not a .proto file. Protobuf schemas are uploaded as .proto.".format(item["name"]))

    placed = _placed(files)
    descriptors = compile_proto(placed)
    # The file nothing else imports is the one a topic is usually about, so
    # its messages come first; what it imports follows.
    imported = {path for content in placed.values() for path in IMPORT.findall(content)}
    ours = [proto for proto in descriptors.file if proto.name in placed]
    candidates = []
    for proto in sorted(ours, key=lambda proto: proto.name in imported):
        candidates.extend(_proto_messages(proto))

    chosen = _choose(candidates, message_type, ".proto files", first_if_unchosen)
    return Schema(PROTOBUF, files, candidates, chosen, _proto_decoder(_message_class(descriptors, chosen)))


def _placed(files):
    """
    Where each uploaded file has to sit for the others' imports to find it.

    An upload has a name and no directory, but `import "common/money.proto"`
    names one. So a file goes where something imports it from, if anything does,
    and at its own name otherwise -- written once either way, since protoc
    refuses the same file under two paths.
    """
    by_name = {item["name"]: item["content"] for item in files}
    placed = {}
    for name, content in by_name.items():
        wanted = name
        for other in by_name.values():
            for path in IMPORT.findall(other):
                if os.path.basename(path) == name:
                    wanted = path
        placed[wanted] = content
    return placed


def _include():
    import grpc_tools

    return os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")


def compile_proto(placed, timeout=30):
    """
    `.proto` text in, a `FileDescriptorSet` out.

    protoc in a child process, not in this one. Its errors go to file
    descriptor 2, and taking that over inside a web server or a worker that
    other threads are writing to is a worse problem than the 200 ms a process
    costs -- paid once per schema, never per message. The well-known types
    (`google/protobuf/*.proto`) ship with grpc_tools and are on the path.
    """
    from google.protobuf import descriptor_pb2

    directory = tempfile.mkdtemp(prefix="sqldesk-proto-")
    try:
        for path, content in placed.items():
            if os.path.isabs(path) or ".." in path.split("/"):
                raise SchemaError("{} is not a path a .proto file can be imported from.".format(path))
            target = os.path.join(directory, "src", path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(content)
        out = os.path.join(directory, "set.desc")
        command = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I",
            os.path.join(directory, "src"),
            "-I",
            _include(),
            "--include_imports",
            "--descriptor_set_out=" + out,
        ] + sorted(placed)
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise SchemaError("Compiling the .proto files took longer than {} seconds.".format(timeout))
        if done.returncode != 0:
            message = (done.stderr or done.stdout or "protoc failed").strip()
            # protoc names the temporary directory; the person only knows
            # their own file names.
            message = message.replace(os.path.join(directory, "src") + os.sep, "")
            raise SchemaError("The .proto files do not compile: {}".format(message))
        with open(out, "rb") as handle:
            return descriptor_pb2.FileDescriptorSet.FromString(handle.read())
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _proto_messages(proto):
    """Every message a file defines, nested ones included, by full name."""
    prefix = proto.package + "." if proto.package else ""
    names = []

    def walk(messages, outer):
        for message in messages:
            if message.options.map_entry:
                continue
            name = outer + message.name
            names.append(name)
            walk(message.nested_type, name + ".")

    walk(proto.message_type, prefix)
    return names


def _message_class(descriptors, full_name):
    from google.protobuf import descriptor_pool, message_factory

    # A pool of its own, so two topics with a message of the same name -- two
    # versions of one schema, say -- never meet. The well-known types arrive
    # in the set like any other import, `--include_imports` having put them
    # there in dependency order.
    pool = descriptor_pool.DescriptorPool()
    for proto in descriptors.file:
        pool.AddSerializedFile(proto.SerializeToString())
    return message_factory.GetMessageClass(pool.FindMessageTypeByName(full_name))


def _proto_decoder(message_class):
    def decode(data):
        message = message_class()
        message.ParseFromString(data)
        return _message(message)

    return decode


def _repeated(field):
    flag = getattr(field, "is_repeated", None)
    if flag is not None:
        return flag
    return field.label == field.LABEL_REPEATED


def _message(message):
    descriptor = message.DESCRIPTOR
    special = _WELL_KNOWN.get(descriptor.full_name)
    if special:
        return special(message)
    out = {}
    for field in descriptor.fields:
        value = getattr(message, field.name)
        if field.message_type is not None and field.message_type.GetOptions().map_entry:
            value_field = field.message_type.fields_by_name["value"]
            out[field.name] = {str(key): _single(value_field, item) for key, item in value.items()}
        elif _repeated(field):
            out[field.name] = [_single(field, item) for item in value]
        elif field.has_presence and not message.HasField(field.name):
            # Unset, and the schema can tell unset from zero. Written as null
            # so the column exists from the first message either way.
            out[field.name] = None
        else:
            out[field.name] = _single(field, value)
    return out


def _single(field, value):
    if field.message_type is not None:
        return _message(value)
    if field.enum_type is not None:
        known = field.enum_type.values_by_number.get(value)
        return known.name if known is not None else value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _timestamp(message):
    moment = datetime.datetime.fromtimestamp(message.seconds, tz=datetime.timezone.utc)
    return (moment + datetime.timedelta(microseconds=message.nanos // 1000)).isoformat()


def _wrapped(message):
    return _single(message.DESCRIPTOR.fields_by_name["value"], message.value)


def _as_json(message):
    from google.protobuf import json_format

    return json_format.MessageToDict(message)


_WELL_KNOWN = {
    "google.protobuf.Timestamp": _timestamp,
    "google.protobuf.Duration": lambda message: message.seconds + message.nanos / 1e9,
    "google.protobuf.DoubleValue": _wrapped,
    "google.protobuf.FloatValue": _wrapped,
    "google.protobuf.Int64Value": _wrapped,
    "google.protobuf.UInt64Value": _wrapped,
    "google.protobuf.Int32Value": _wrapped,
    "google.protobuf.UInt32Value": _wrapped,
    "google.protobuf.BoolValue": _wrapped,
    "google.protobuf.StringValue": _wrapped,
    "google.protobuf.BytesValue": _wrapped,
    "google.protobuf.Struct": _as_json,
    "google.protobuf.Value": _as_json,
    "google.protobuf.ListValue": _as_json,
    "google.protobuf.FieldMask": lambda message: ",".join(message.paths),
    "google.protobuf.Empty": lambda message: {},
    "google.protobuf.Any": lambda message: {
        "type_url": message.type_url,
        "value": base64.b64encode(message.value).decode("ascii"),
    },
}


# --- turning a decoded value into a line -----------------------------------------


def _plain(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    raise TypeError("cannot write a {} as JSON".format(type(value).__name__))


def _finite(value):
    """NaN and infinity have no JSON; DuckDB would refuse the whole line."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def line(value):
    """
    One decoded message as one JSON line.

    A message that is not a record -- an Avro schema that is just a string, say
    -- becomes `{"value": ...}`, so it is still an event with a column.
    """
    if not isinstance(value, dict):
        value = {"value": value}
    text = json.dumps(value, default=_plain, ensure_ascii=False, separators=(",", ":"))
    # The slow path only when it can matter: a string field containing "NaN"
    # costs one extra walk, a real NaN would have cost the row.
    if "NaN" in text or "Infinity" in text:
        text = json.dumps(_finite(value), default=_plain, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


# --- Confluent's wire format ---------------------------------------------------------


def framed(data):
    """`(schema_id, payload)` for a message with a registry header, else None."""
    if len(data) < 5 or data[0] != MAGIC:
        return None
    return int.from_bytes(data[1:5], "big"), data[5:]


def _zigzag(data, at):
    shift = 0
    result = 0
    while True:
        if at >= len(data):
            raise ValueError("the message index runs past the end of the message")
        byte = data[at]
        at += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            break
        shift += 7
    return (result >> 1) ^ -(result & 1), at


def message_indexes(payload):
    """
    Which message in the schema a Protobuf payload is, and the bytes after.

    A count and then that many indexes, zigzag varints, walking from the file's
    top-level messages inward. A lone zero byte is the common case -- the first
    top-level message -- written short.
    """
    count, at = _zigzag(payload, 0)
    if count == 0:
        return [0], payload[at:]
    if count < 0 or count > 100:
        raise ValueError("not a message index")
    indexes = []
    for _ in range(count):
        index, at = _zigzag(payload, at)
        indexes.append(index)
    return indexes, payload[at:]


def _name_at(proto, indexes):
    messages = proto.message_type
    names = []
    for index in indexes:
        if index < 0 or index >= len(messages):
            raise ValueError("message index {} is not in the schema".format(indexes))
        names.append(messages[index].name)
        messages = messages[index].nested_type
    return ".".join(([proto.package] if proto.package else []) + names)


class Registry:
    """
    A schema registry, asked once per schema id and remembered.

    Confluent's REST API, which Redpanda, Karapace and Apicurio's compatibility
    endpoint also answer. Basic authentication is how Confluent Cloud takes an
    API key and secret. TLS trusts the system's authorities plus the cluster's
    own CA when one is given, since an internal registry is usually signed by
    the same PKI as the brokers beside it.
    """

    def __init__(self, url, username=None, password=None, ca_pem=None, verify_hostname=True, timeout=5):
        self.url = url.rstrip("/")
        self.auth = (username, password or "") if username else None
        self.ca_pem = ca_pem
        self.verify_hostname = verify_hostname
        self.timeout = timeout
        self._writers = {}
        self._failed = {}
        self._lock = threading.Lock()
        self._session = None

    def _http(self):
        if self._session is None:
            import ssl

            import requests
            from requests.adapters import HTTPAdapter

            context = ssl.create_default_context()
            # Python 3.13 turned strict X.509 checking on by default, which
            # refuses a certificate without an Authority Key Identifier --
            # common from internal and self-signed CAs. librdkafka does not
            # insist on it, so without this the brokers connect and the
            # registry beside them on the same PKI is refused. Signatures,
            # expiry and names are all still checked.
            context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
            if self.ca_pem:
                context.load_verify_locations(cadata=self.ca_pem)
            if not self.verify_hostname:
                context.check_hostname = False

            class Trusting(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    kwargs["ssl_context"] = context
                    return super().init_poolmanager(*args, **kwargs)

            session = requests.Session()
            session.mount("https://", Trusting())
            session.auth = self.auth
            session.headers["Accept"] = "application/vnd.schemaregistry.v1+json, application/json"
            self._session = session
        return self._session

    def _get(self, path):
        response = self._http().get(self.url + path, timeout=self.timeout)
        if response.status_code == 404:
            raise LookupError("the registry has no {}".format(path))
        if response.status_code in (401, 403):
            raise PermissionError("the registry refused the credentials ({})".format(response.status_code))
        response.raise_for_status()
        return response.json()

    def check(self):
        """Something cheap that proves the URL and the credentials."""
        self._get("/subjects")

    def writer(self, schema_id):
        """`(kind, decode)` for a schema id. Raises while the registry cannot say."""
        with self._lock:
            if schema_id in self._writers:
                return self._writers[schema_id]
            now = time.monotonic()
            self._failed = {key: value for key, value in self._failed.items() if now - value[0] < RETRY_SECONDS}
            if schema_id in self._failed:
                raise self._failed[schema_id][1]
            if len(self._failed) >= MAX_FAILED_IDS:
                raise LookupError(
                    "{} different schema ids failed in the last {} seconds, so no more are being asked for; "
                    "these may not be registry messages at all".format(len(self._failed), RETRY_SECONDS)
                )
        try:
            found = self._build(schema_id)
        except Exception as error:
            with self._lock:
                self._failed[schema_id] = (time.monotonic(), error)
            raise
        with self._lock:
            self._writers[schema_id] = found
            self._failed.pop(schema_id, None)
        return found

    def _build(self, schema_id):
        document = self._get("/schemas/ids/{}".format(int(schema_id)))
        kind = (document.get("schemaType") or "AVRO").upper()
        if kind == "JSON":
            return "JSON", None
        references = self._references(document.get("references") or [], set())
        if kind == "AVRO":
            named = {}
            for _name, text in references:
                fastavro.parse_schema(json.loads(text), named_schemas=named)
            schema = fastavro.parse_schema(json.loads(document["schema"]), named_schemas=named)
            return "AVRO", _avro_decoder(schema)
        if kind == "PROTOBUF":
            main = "registry-schema-{}.proto".format(int(schema_id))
            placed = dict(references)
            placed[main] = document["schema"]
            descriptors = compile_proto(placed)
            proto = next(item for item in descriptors.file if item.name == main)
            return "PROTOBUF", _ProtobufBySchema(descriptors, proto)
        raise ValueError(
            "the registry says schema {} is {}, which is not something SQLDesk reads".format(schema_id, kind)
        )

    def _references(self, references, seen):
        """Every schema these refer to, theirs first, as `(name, text)`."""
        found = []
        for reference in references:
            key = (reference.get("subject"), reference.get("version"))
            if key in seen:
                continue
            seen.add(key)
            # Quoted whole, slashes included: a Protobuf reference's subject is
            # usually its import path, `common/money.proto`, and unquoted that
            # is a different URL.
            document = self._get(
                "/subjects/{}/versions/{}".format(quote(str(reference["subject"]), safe=""), reference["version"])
            )
            found.extend(self._references(document.get("references") or [], seen))
            found.append((reference["name"], document["schema"]))
        return found


class _ProtobufBySchema:
    """A registry Protobuf schema: which message a payload is, then decoding it."""

    def __init__(self, descriptors, proto):
        self.descriptors = descriptors
        self.proto = proto
        self._classes = {}

    def __call__(self, payload):
        indexes, rest = message_indexes(payload)
        key = tuple(indexes)
        decode = self._classes.get(key)
        if decode is None:
            decode = _proto_decoder(_message_class(self.descriptors, _name_at(self.proto, indexes)))
            self._classes[key] = decode
        return decode(rest)


def registry_for(options):
    """The data source's registry, or None if it has none."""
    options = options or {}
    url = (options.get("schema_registry_url") or "").strip()
    if not url:
        return None
    ca = options.get("ssl_ca_File")
    if ca:
        from sqldesk.streams.consumer import _pem

        ca = _pem(ca)
    return Registry(
        url,
        username=(options.get("schema_registry_username") or "").strip() or None,
        password=options.get("schema_registry_password"),
        ca_pem=ca or None,
        verify_hostname=options.get("ssl_verify_hostname") is not False,
    )


# --- the decoder a consumer uses ---------------------------------------------------------


class Decoded:
    """
    One flush, decoded: the lines to store, how many could not be, and why.

    `kinds` counts what was found -- JSON, Avro, Protobuf, JSON Schema -- so
    the page analysing a topic can say what is on it rather than leave it to be
    guessed from the columns.
    """

    def __init__(self, lines, failed=0, problem=None, kinds=None):
        self.lines = lines
        self.failed = failed
        self.problem = problem
        self.kinds = kinds or {}


NO_REGISTRY = (
    PROBLEM + "they carry a schema registry header, and this Kafka data source has no schema registry URL. "
    "Add it to the data source, or choose the format and upload the schema under How it reads."
)
NOT_JSON = (
    PROBLEM + "they are not JSON and carry no schema registry header. If they are Avro or Protobuf, "
    "choose the format and upload the schema under How it reads."
)


#: What the registry calls each kind, as a person would.
REGISTRY_KINDS = {"AVRO": "Avro", "PROTOBUF": "Protobuf", "JSON": "JSON Schema"}


class Decoder:
    """
    Raw message bytes in, JSON lines out, for one stream.

    `AUTO` passes JSON through untouched and decodes whatever carries a registry
    header. `AVRO` and `PROTOBUF` decode every message with an uploaded schema.
    """

    def __init__(self, value_format=AUTO, schema=None, registry=None):
        self.value_format = value_format or AUTO
        self.schema = schema
        self.registry = registry

    def decode(self, messages):
        if self.value_format != AUTO:
            return self._with_schema(messages)
        return self._auto(messages)

    def _with_schema(self, messages):
        lines = []
        failed = 0
        first = None
        for data in messages:
            try:
                lines.append(line(self.schema.decode(data)))
            except Exception as error:
                failed += 1
                first = first or error
        problem = None
        if failed and not lines:
            problem = PROBLEM + "none of them match {} in {}: {}".format(
                self.schema.message_type, ", ".join(item["name"] for item in self.schema.files), first
            )
        kind = "Avro" if self.value_format == AVRO else "Protobuf"
        return Decoded(lines, failed, problem, {kind: len(lines)} if lines else {})

    def _auto(self, messages):
        lines = []
        kinds = {}
        objects = 0
        decoded = 0
        plain = 0
        failed = 0
        no_registry = False
        registry_problem = None
        for data in messages:
            # The common case first, and as cheap as the store's own check: a
            # JSON object goes through as the very same bytes.
            if data[:1] == b"{" or data.lstrip()[:1] == b"{":
                lines.append(data)
                objects += 1
                continue
            found = framed(data)
            if found is None:
                # Not ours to judge: the store drops what is not a JSON object
                # and counts it, exactly as it did before there was a decoder.
                lines.append(data)
                plain += 1
                continue
            if self.registry is None:
                failed += 1
                no_registry = True
                continue
            schema_id, payload = found
            try:
                kind, decode = self.registry.writer(schema_id)
                lines.append(payload if kind == "JSON" else line(decode(payload)))
                decoded += 1
                name = REGISTRY_KINDS.get(kind, kind)
                kinds[name] = kinds.get(name, 0) + 1
            except Exception as error:
                failed += 1
                registry_problem = registry_problem or PROBLEM + "schema {} from the registry at {}: {}".format(
                    schema_id, self.registry.url, error
                )

        # Said only when nothing in the flush could be read. One odd message
        # among good ones is the malformed count's business, not a headline.
        problem = None
        if messages and not objects and not decoded:
            if no_registry:
                problem = NO_REGISTRY
            elif registry_problem:
                problem = registry_problem
            elif plain:
                problem = NOT_JSON
        if objects:
            kinds["JSON"] = objects
        return Decoded(lines, failed, problem, kinds)


def for_reading(value_format, files=None, message_type=None, options=None):
    """The decoder a request describes, before any stream has been saved."""
    value_format = value_format or AUTO
    if value_format not in FORMATS:
        raise SchemaError("The format is one of: {}.".format(", ".join(FORMATS)))
    if value_format == AUTO:
        return Decoder(AUTO, registry=registry_for(options))
    return Decoder(value_format, schema=load(value_format, files, message_type))


def signature(stream):
    """What decides how a stream's messages are read, as one comparable value."""
    return (
        getattr(stream, "value_format", None) or AUTO,
        getattr(stream, "message_type", None),
        json.dumps((getattr(stream, "value_schema", None) or {}).get("files"), sort_keys=True),
    )


class StreamDecoder:
    """
    A stream's decoder, rebuilt when somebody changes how it reads.

    A consumer runs for minutes. Without this, choosing Avro and uploading the
    schema would change nothing until the job ended -- and the flushes between
    would be read the old way into a window about to be thrown away.
    """

    def __init__(self, stream, options=None):
        self.stream = stream
        self.options = options
        self._signature = None
        self._decoder = None

    def refresh(self):
        """Rebuild if the reading changed. True when it did, after the first."""
        current = signature(self.stream)
        if current == self._signature:
            return False
        first = self._decoder is None
        self._decoder = for_stream(self.stream, self.options)
        self._signature = current
        return not first

    def decode(self, messages):
        if self._decoder is None:
            self.refresh()
        return self._decoder.decode(messages)


def for_stream(stream, options=None):
    """
    The decoder a stream's settings describe.

    A stream whose uploaded schema no longer loads raises `SchemaError`, which
    stops its consumer with the reason rather than letting it run and count
    every message as malformed.
    """
    value_format = getattr(stream, "value_format", None) or AUTO
    if value_format == AUTO:
        return Decoder(AUTO, registry=registry_for(options))
    stored = getattr(stream, "value_schema", None) or {}
    schema = load(value_format, stored.get("files"), getattr(stream, "message_type", None))
    return Decoder(value_format, schema=schema)

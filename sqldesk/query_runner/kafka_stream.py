"""
Querying a stream: SQL over the window SQLDesk is holding.

A topic is a data source, so it has to answer the two questions every data
source answers -- what tables are here, and run this SQL -- and both are
answered from the stream's own DuckDB file rather than from Kafka. Kafka has no
query interface and SQLDesk is not going to pretend otherwise: what you can
query is the window, which is what the chart says above itself.

Two tables, deliberately:

- `events`, the raw window. Minutes of it, however many the row budget buys.
- `rollup`, per-minute buckets going back a day, read from Postgres through a
  view so one query can join "now" to "this morning" without two data sources.

The connection is the stream's store, locked down the same way an upload's is:
a stream's SQL is written by people, so DuckDB's defaults would be theirs.
"""

import logging
import os
import re
import time

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    JobTimeoutException,
    register,
)
from sqldesk.utils import json_dumps

logger = logging.getLogger(__name__)

#: DuckDB's own type names, as SQLDesk's. Anything unrecognised is a string,
#: which is the one answer that is never actively wrong.
TYPES = {
    "BOOLEAN": TYPE_BOOLEAN,
    "TINYINT": TYPE_INTEGER,
    "SMALLINT": TYPE_INTEGER,
    "INTEGER": TYPE_INTEGER,
    "BIGINT": TYPE_INTEGER,
    "HUGEINT": TYPE_INTEGER,
    "UBIGINT": TYPE_INTEGER,
    "FLOAT": TYPE_FLOAT,
    "DOUBLE": TYPE_FLOAT,
    "DECIMAL": TYPE_FLOAT,
    "DATE": TYPE_DATETIME,
    "TIMESTAMP": TYPE_DATETIME,
    "TIMESTAMP WITH TIME ZONE": TYPE_DATETIME,
}


def _empty_view(connection, name, stream):
    """
    A topic with no window, as an empty table with its known columns.

    From the schema recorded on the stream the last time it consumed. With no
    columns recorded it has never seen an event at all, and there is nothing to
    build -- that one stays absent, and naming it gets the explanation rather
    than a table of nothing.
    """
    columns = [column.get("name") for column in (stream.columns or []) if column.get("name")]
    if not columns:
        return
    selected = ", ".join('NULL AS "{}"'.format(column.replace('"', '""')) for column in columns)
    try:
        connection.execute('CREATE VIEW "{}" AS SELECT {} WHERE false'.format(name.replace('"', '""'), selected))
    except Exception:
        logger.warning("could not offer %s as an empty table", stream.topic, exc_info=True)


def _described(connection, query):
    """
    `{column: DuckDB type}` for a query, or nothing if it cannot be planned.

    Normalised to the names `TYPES` is keyed by: a parameterised type arrives
    as `DECIMAL(18,3)`, and the part in brackets says nothing about how to
    chart it.
    """
    try:
        rows = connection.execute("DESCRIBE {}".format(query)).fetchall()
    except Exception:
        # The query itself will raise in a moment and say something better.
        return {}
    kinds = {}
    for row in rows:
        kinds[row[0]] = (row[1] or "").split("(")[0].strip().upper()
    return kinds


def table_name(topic):
    """
    The identifier a topic is queried by.

    Kafka topic names allow dots, hyphens and underscores; SQL identifiers do
    not get on with the first two, and quoting them everywhere would make every
    query in the editor uglier than it needs to be. `prod.orders.v2` is queried
    as `prod_orders_v2`, and the schema browser shows the same name, so what is
    on screen is what you type.
    """
    name = re.sub(r"[^A-Za-z0-9_]", "_", topic or "").strip("_").lower() or "topic"
    if name[0].isdigit():
        name = "t_" + name
    return name


def names_in(query, identifier):
    """Whether a query mentions an identifier as a whole word."""
    return re.search(r"\b{}\b".format(re.escape(identifier)), query or "", re.IGNORECASE) is not None


class KafkaStream(BaseSQLQueryRunner):
    should_annotate_query = False

    #: Kept out of the ordinary query editor. A window exists only while
    #: somebody is watching, so a saved query against one would run against
    #: whatever happened to be there -- and a dashboard widget over it would be
    #: empty most of the time, which looks like a broken dashboard rather than
    #: like a feature working as designed.
    streams_only = True

    @classmethod
    def name(cls):
        return "Kafka stream"

    @classmethod
    def type(cls):
        return "kafka_stream"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "brokers": {
                    "type": "string",
                    "title": "Bootstrap servers",
                    "default": "localhost:9092",
                },
                # Everything a broker needs to let us in, in the shape
                # librdkafka wants, because there are too many combinations of
                # SASL and TLS to put each on a form -- and inventing a subset
                # would be the one that does not cover somebody's cluster.
                "security_protocol": {
                    "type": "string",
                    "title": "Security protocol",
                    "default": "PLAINTEXT",
                    "extendedEnum": [
                        {"value": "PLAINTEXT", "name": "PLAINTEXT"},
                        {"value": "SSL", "name": "SSL"},
                        {"value": "SASL_PLAINTEXT", "name": "SASL_PLAINTEXT"},
                        {"value": "SASL_SSL", "name": "SASL_SSL"},
                    ],
                },
                "sasl_mechanism": {"type": "string", "title": "SASL mechanism", "default": ""},
                "sasl_username": {"type": "string", "title": "SASL username"},
                "sasl_password": {"type": "string", "title": "SASL password"},
                # For SSL and SASL_SSL against a broker whose certificate is not
                # signed by a public CA -- an internal PKI, a self-signed
                # cluster -- and for brokers that want a client certificate.
                # Without them, TLS only worked when the system trust store
                # already happened to trust the broker. Names ending in `File`
                # are uploads in the form, arriving base64-encoded.
                "ssl_ca_File": {"type": "string", "title": "CA certificate (PEM)"},
                "ssl_certificate_File": {"type": "string", "title": "Client certificate (PEM, for mutual TLS)"},
                "ssl_key_File": {"type": "string", "title": "Client key (PEM, for mutual TLS)"},
                "ssl_key_password": {"type": "string", "title": "Client key password"},
                "ssl_verify_hostname": {
                    "type": "boolean",
                    "title": "Check the broker's certificate matches its name",
                    "default": True,
                },
                # For Avro and Protobuf topics whose producers use a schema
                # registry: every message names its schema, and this is where
                # it is looked up. Confluent, Redpanda, Karapace and Apicurio's
                # compatibility API all answer. Confluent Cloud takes its API
                # key and secret as the username and password.
                "schema_registry_url": {"type": "string", "title": "Schema registry URL"},
                "schema_registry_username": {"type": "string", "title": "Schema registry username (or API key)"},
                "schema_registry_password": {"type": "string", "title": "Schema registry password (or API secret)"},
                "row_budget": {
                    "type": "number",
                    "title": "Rows to keep, per topic",
                    "default": 0,
                    "info": "The default for topics on this cluster; each can override it. "
                    "0 uses the install's setting. A topic's window follows from this and its rate.",
                },
                "events_per_second": {
                    "type": "number",
                    "title": "Events a second to store, per topic",
                    "default": 0,
                    "info": "Past this a topic is sampled and every chart says so. " "0 uses the install's setting.",
                },
            },
            "required": ["brokers"],
            "secret": [
                "sasl_password",
                "ssl_ca_File",
                "ssl_certificate_File",
                "ssl_key_File",
                "ssl_key_password",
                "schema_registry_password",
            ],
            "extra_options": [
                "schema_registry_username",
                "schema_registry_password",
                "ssl_ca_File",
                "ssl_certificate_File",
                "ssl_key_File",
                "ssl_key_password",
                "ssl_verify_hostname",
            ],
            "order": [
                "brokers",
                "security_protocol",
                "sasl_mechanism",
                "sasl_username",
                "sasl_password",
                "ssl_ca_File",
                "ssl_certificate_File",
                "ssl_key_File",
                "ssl_key_password",
                "ssl_verify_hostname",
                "schema_registry_url",
                "schema_registry_username",
                "schema_registry_password",
                "row_budget",
                "events_per_second",
            ],
        }

    @classmethod
    def enabled(cls):
        # Needs librdkafka, which is in the optional dependency group with
        # every other data source's SDK. A missing one makes this runner
        # unavailable, not the application broken.
        from sqldesk.query_runner import installed

        return installed("confluent_kafka")

    def __init__(self, configuration):
        super().__init__(configuration)
        self._store = None
        self._data_source_id = None

    def for_data_source(self, data_source_id):
        """
        Which data source this runner was built for.

        A runner is normally told nothing about the row it came from -- its
        configuration is the connection and nothing else. This one needs it,
        because the window it queries belongs to the `Stream` that hangs off
        the data source, and `DataSource.query_runner` is the only place that
        knows which one that is.
        """
        self._data_source_id = data_source_id

    # --- what the rest of SQLDesk asks of a data source --------------------

    def _streams(self):
        """
        The topics somebody has enabled on this cluster, as `Stream` rows.

        Looked up rather than held: a runner is built per query, and these rows
        carry the window and the sample rate, both of which the consumers are
        changing underneath us.
        """
        from sqldesk import models

        # The configuration fallback is for a runner built by hand, in a test
        # or a shell; through the application it arrives by `for_data_source`.
        source_id = self._data_source_id or self.configuration.get("data_source_id")
        if not source_id:
            return []
        return (
            models.Stream.query.filter(models.Stream.data_source_id == source_id).order_by(models.Stream.topic).all()
        )

    def _attached(self, streams, query):
        """
        A connection with every enabled topic's window attached as a view.

        One database file per topic, attached read-only into one in-memory
        connection, so a query can name two topics and join them. Read-only
        because the consumer owns the write lock; attaching waits out a flush
        rather than failing on one, which is the same bargain readers strike
        everywhere else here.

        A topic that has never consumed anything has no file at all, so there is
        nothing to attach; naming it gets the explanation from
        `activity.why_it_is_quiet` rather than DuckDB's "table does not exist".
        """
        import duckdb

        from sqldesk.streams.store import Store

        connection = duckdb.connect(":memory:")
        attached = []
        for stream in streams:
            name = table_name(stream.topic)
            path = stream.store_path()
            if not os.path.exists(path):
                # Consuming, but nothing flushed yet -- or paused with its
                # window already dropped. Either way the topic is a table a
                # query may legitimately name, so it becomes an empty one with
                # the right columns rather than a missing one. A join across
                # two topics where one is quiet should give a quiet answer, not
                # fail outright; and a query naming only quiet topics gets the
                # note the handler attaches, which says so in words.
                _empty_view(connection, name, stream)
                continue
            quoted = path.replace("'", "''")
            last = None
            for attempt in range(Store.READ_ATTEMPTS):
                try:
                    connection.execute("ATTACH '{}' AS \"{}__window\" (READ_ONLY)".format(quoted, name))
                    last = None
                    break
                except Exception as error:  # noqa: PERF203 -- the retry is the point
                    last = error
                    time.sleep(Store.READ_PAUSE_SECONDS)
            if last is not None:
                logger.warning("could not attach the window for %s: %s", stream.topic, last)
                continue
            # A consumer creates the file on its first connection and the table
            # on its first flush, so between the two there is a window with no
            # `events` in it. Detached again rather than left attached, so the
            # topic lands in the "nothing has arrived yet" explanation instead
            # of DuckDB's complaint about a view it could not create.
            present = connection.execute(
                "SELECT count(*) FROM duckdb_tables() WHERE database_name = ? AND table_name = 'events'",
                ["{}__window".format(name)],
            ).fetchone()
            if not present or not present[0]:
                connection.execute('DETACH "{}__window"'.format(name))
                _empty_view(connection, name, stream)
                continue
            connection.execute('CREATE VIEW "{}" AS SELECT * FROM "{}__window".events'.format(name, name))
            attached.append(stream)
        return connection, attached

    def run_query(self, query, user):
        streams = self._streams()
        if not streams:
            return None, (
                "No topics are set up on this cluster yet. Somebody with the streams permission "
                "enables them under Streams \u2192 Manage topics."
            )

        # Querying a topic is what "somebody is watching" means, and it is per
        # topic: a query naming `orders` should not keep `payments` consuming.
        # A query naming none of them -- `select 1` -- counts for none.
        from sqldesk.streams import activity

        named = [stream for stream in streams if names_in(query, table_name(stream.topic))]
        for stream in named:
            try:
                activity.note_viewed(stream)
            except Exception:
                logger.warning("could not note that stream %s was viewed", stream.id, exc_info=True)

        connection, attached = self._attached(streams, query)
        try:
            kinds = _described(connection, query)
            cursor = connection.cursor()
            cursor.execute(query)
            columns = self.fetch_columns(
                [(column[0], TYPES.get(kinds.get(column[0], ""), TYPE_STRING)) for column in cursor.description]
            )
            rows = [dict(zip((column["name"] for column in columns), row)) for row in cursor.fetchall()]
            return json_dumps({"columns": columns, "rows": rows}), None
        except JobTimeoutException:
            raise
        except Exception as error:
            return None, self._explain(error, named, attached)
        finally:
            connection.close()

    def _explain(self, error, named, attached):
        """
        Why a query failed, in terms of the stream rather than of DuckDB.

        A topic nobody has watched for a while has no window and therefore no
        table, and "Table with name orders does not exist" is a confusing way to
        learn that the stream is paused.
        """
        from sqldesk.streams import activity

        missing = [stream for stream in named if stream not in attached]
        for stream in missing:
            if names_in(str(error), table_name(stream.topic)):
                quiet = activity.why_it_is_quiet(stream)
                if quiet:
                    return quiet
        return str(error)

    def get_schema(self, get_stats=False):
        """
        One table per enabled topic, named as it is queried.

        From each stream's recorded columns rather than from its file, so a
        topic whose consumer is paused still shows what it holds -- a schema
        browser that empties itself when nobody is watching would read as the
        data having gone.
        """
        schema = []
        for stream in self._streams():
            if not stream.columns:
                continue
            schema.append(
                {
                    "name": table_name(stream.topic),
                    "columns": [column["name"] for column in stream.columns],
                }
            )
        return schema

    def test_connection(self):
        """
        Whether the broker will let us in.

        Asked when somebody saves the cluster, which is the moment to find out.
        Not whether any particular topic exists: a cluster is registered before
        anybody has chosen topics, and which ones exist is the question the
        Manage topics page asks next.
        """
        from sqldesk.streams.consumer import describe_topic

        error = describe_topic(self.configuration)
        if error:
            raise Exception(error)
        # And the registry, when there is one: a wrong URL or key otherwise
        # shows up only later, as every message on an Avro topic failing.
        from sqldesk.streams.decode import registry_for

        registry = registry_for(self.configuration)
        if registry is not None:
            try:
                registry.check()
            except Exception as problem:
                raise Exception("The broker answered, but the schema registry did not: {}".format(problem))
        return True


register(KafkaStream)

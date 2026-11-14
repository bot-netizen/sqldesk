import functools
import logging
import os
from urllib.parse import urlsplit

import requests

from sqldesk.models.users import ApiUser, User
from sqldesk.query_runner import (
    FETCH_BATCH,
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    InterruptException,
    JobTimeoutException,
    fetch_within_budget,
    mark_truncated,
    register,
)
from sqldesk.settings import parse_boolean

logger = logging.getLogger(__name__)
ANNOTATE_QUERY = parse_boolean(os.environ.get("TRINO_ANNOTATE_QUERY", "true"))
# Values arrive as Trino sends them and are converted here, which measured
# 35% faster than having the client build a Decimal and a datetime for every
# value. The stored result is the same either way; this is the way back.
FAST_TYPES = parse_boolean(os.environ.get("TRINO_FAST_TYPES", "true"))

try:
    import trino
    from trino import exceptions as trino_exceptions
    from trino.exceptions import DatabaseError
    from trino.mapper import RowMapperFactory
    from trino.types import NamedRowTuple

    enabled = True
except ImportError:
    enabled = False

#: How a result comes back from Trino -- the data source's "encoding", a name
#: kept so saved data sources keep their choice.
#:
#: Empty is automatic, and always was, whatever the form said: the client asks
#: for the spooled protocol whenever it is not told otherwise, so a Trino with
#: spooling configured was already spooling to SQLDesk. That is the fast path --
#: measured on a million rows, 10.3s direct against 2.5-5s spooled, with the
#: coordinator released in 3s rather than held for the whole read -- but it
#: needs the workers to reach Trino's spooling storage, and there was no way to
#: say "they cannot". Direct is that way.
DIRECT = "direct"
TRANSFER_CHOICES = [
    {"value": "", "name": "Automatic: spooled when Trino offers it, otherwise direct (recommended)"},
    {"value": DIRECT, "name": "Direct: through the coordinator, never spooled"},
    {"value": "json+zstd", "name": "Spooled, zstd"},
    {"value": "json+lz4", "name": "Spooled, lz4"},
    {"value": "json", "name": "Spooled, uncompressed"},
]


def _convert_row_types(value):
    """Convert NamedRowTuple instances to dicts so ROW fields are serialized with their names."""
    if isinstance(value, NamedRowTuple):
        names = value.__annotations__.get("names", [])
        return {
            name if name is not None else f"_field{i}": _convert_row_types(v)
            for i, (name, v) in enumerate(zip(names, value))
        }
    if isinstance(value, (list, tuple)):
        return [_convert_row_types(v) for v in value]
    return value


TRINO_TYPES_MAPPING = {
    "boolean": TYPE_BOOLEAN,
    "tinyint": TYPE_INTEGER,
    "smallint": TYPE_INTEGER,
    "integer": TYPE_INTEGER,
    "long": TYPE_INTEGER,
    "bigint": TYPE_INTEGER,
    "float": TYPE_FLOAT,
    "real": TYPE_FLOAT,
    "double": TYPE_FLOAT,
    # A decimal is not an integer. Typed as one, every price and rate in a Trino
    # table arrived with its fractional part treated as noise.
    "decimal": TYPE_FLOAT,
    "varchar": TYPE_STRING,
    "char": TYPE_STRING,
    "string": TYPE_STRING,
    "json": TYPE_STRING,
    "varbinary": TYPE_STRING,
    "uuid": TYPE_STRING,
    "ipaddress": TYPE_STRING,
    "time": TYPE_STRING,
    "time with time zone": TYPE_STRING,
    "date": TYPE_DATE,
    "timestamp": TYPE_DATETIME,
    "timestamp with time zone": TYPE_DATETIME,
}


def _trino_type(declared_type):
    """Map a type as Trino reports it, which is rarely the bare name.

    `cursor.description` carries the declared type: `varchar(255)`, `decimal(10,2)`,
    and since Trino made precision explicit, `timestamp(3)` and
    `timestamp(6) with time zone`. A bare-name lookup misses every one of those, so
    the common case -- a table of varchars, decimals and timestamps -- came back with
    no column types at all, and nothing downstream could format or chart it.

    The parameters are dropped and the rest is kept, which also leaves `row(...)`,
    `array(...)` and `map(...)` unmapped on purpose: those values are structures, and
    calling them strings would be a worse answer than calling them nothing.
    """
    if not declared_type:
        return None

    name = str(declared_type).strip().lower()
    if "(" in name:
        head, _, tail = name.partition("(")
        # `timestamp(6) with time zone` -> `timestamp` + ` with time zone`
        _, _, after = tail.partition(")")
        name = (head + after).strip()

    return TRINO_TYPES_MAPPING.get(name, None)


def _database_error_message(db):
    """Trino's own message for a failed query, or a description of why there isn't one.

    What this replaced read `db.args[0].get("failureInfo", {"message", None})` -- a set
    literal, not a dict, a comma where a colon was meant. Whenever `failureInfo` was
    absent the default was a `set`, `.get` on it raised AttributeError, and the handler
    whose job was to report the error became the error. Which is the worst possible
    moment to lose the message.
    """
    default_message = "Unspecified DatabaseError: {0}".format(str(db))

    args = getattr(db, "args", None) or ()
    if not args or not isinstance(args[0], dict):
        return default_message

    failure_info = args[0].get("failureInfo")
    message = failure_info.get("message") if isinstance(failure_info, dict) else None
    if message is None:
        message = args[0].get("message")

    return message or default_message


IDENTITY_TYPES = {"boolean", "tinyint", "smallint", "integer", "bigint", "varchar", "char", "json", "date"}


def _float(value):
    """A double or real as the typed client gives it: NaN and infinity arrive as strings."""
    return float(value) if isinstance(value, str) else value


def _decimal(value):
    """A decimal as it is stored: the typed client's Decimal went to JSON as a float."""
    return float(value)


def _timestamp(value):
    """
    `2026-11-14 09:30:01.123456` as a stored result has always had it:
    `2026-11-14T09:30:01.123` -- milliseconds, cut not rounded, and no fraction
    at all when it is zero. That is what the typed client's datetime came to
    through SQLDesk's JSON encoder, for any precision up to microseconds.
    """
    whole, _, fraction = value.partition(".")
    whole = whole.replace(" ", "T", 1)
    if not fraction or not fraction.strip("0"):
        return whole
    return whole + "." + (fraction + "00")[:3]


def _precision(signature, default=3):
    for argument in signature.get("arguments") or []:
        if argument.get("kind") == "LONG":
            return argument.get("value", default)
    return default


def _fast_converters(columns):
    """
    One converter per column for values fetched as Trino sends them, or None
    where the value is already what would be stored.

    The common types are a string or a float() away from what the typed client
    and the JSON encoder made of them. Anything else -- time zones, times,
    intervals, arrays, maps, rows, sub-microsecond timestamps -- goes through
    the client's own mapper for its type, exactly as before.
    """
    factory = RowMapperFactory()
    converters = []
    for column in columns:
        signature = column.get("typeSignature") or {}
        raw = signature.get("rawType")
        if raw in IDENTITY_TYPES:
            converters.append(None)
        elif raw in ("double", "real"):
            converters.append(_float)
        elif raw in ("decimal", "number"):
            converters.append(_decimal)
        elif raw == "timestamp" and _precision(signature) <= 6:
            converters.append(_timestamp)
        else:
            mapper = factory._create_value_mapper(signature)
            converters.append(lambda value, mapper=mapper: _convert_row_types(mapper.map(value)))
    return converters


def _explain(error, query_id, configuration):
    """
    What went wrong, for whoever ran the query, with what to do about it.

    A dropped connection used to reach the page as "Unspecified DatabaseError:
    failed to fetch: ('Connection broken: IncompleteRead(0 bytes read, 2 more
    expected)')", and a gateway error as nothing at all -- the client raises
    those outside the DatabaseError the runner was catching.
    """
    where = " (Trino query {})".format(query_id) if query_id else ""
    detail = str(error)
    if isinstance(error, trino_exceptions.TrinoQueryError):
        return "{}{}".format(_database_error_message(error), where)
    if isinstance(error, trino_exceptions.TrinoAuthError):
        return "Trino refused this data source's credentials: {}".format(detail)
    if isinstance(error, trino_exceptions.TrinoConnectionError):
        if "failed to fetch" in detail:
            return (
                "The connection to Trino dropped while the result was being read{}, so the query was stopped. "
                "A coordinator that restarted or ran out of memory is the usual cause, and a very large result "
                "makes it likelier: run it again, or add a LIMIT. ({})".format(where, detail)
            )
        return "SQLDesk could not reach Trino at {}:{}. Check the host and port, and that the workers can reach it. ({})".format(
            configuration.get("host", ""), configuration.get("port", 8080), detail
        )
    if isinstance(error, trino_exceptions.HttpError):
        return "Trino answered {}{} -- it may be restarting or overloaded. Try again in a moment.".format(
            detail, where
        )
    spooled = (configuration.get("encoding") or "").strip() != DIRECT
    if isinstance(error, requests.exceptions.RequestException):
        # Raised by the client as it is, not as a DatabaseError: on the spooled
        # protocol that is a segment download, so the host it was reaching for
        # says whether it was the storage or Trino that could not be reached.
        failed_host = urlsplit(getattr(error.request, "url", None) or "").hostname
        if spooled and failed_host and failed_host != configuration.get("host"):
            return (
                "SQLDesk could not download the result from Trino's spooling storage at {}{}, so the query was "
                "stopped. The workers need to reach the object storage Trino spools to; if they cannot, set this "
                "data source's Result transfer to Direct. ({})".format(failed_host, where, detail)
            )
        return (
            "The connection to Trino dropped while the result was being read{}, so the query was stopped. "
            "Run it again; if it keeps happening, check that the workers can reach {}:{}. ({})".format(
                where, configuration.get("host", ""), configuration.get("port", 8080), detail
            )
        )
    if spooled and isinstance(error, DatabaseError) and _looks_like_storage(detail):
        # A spooled segment the workers could not download comes back as a
        # bare HTTP error from the storage, not from Trino.
        return (
            "SQLDesk could not download the result from Trino's spooling storage{}. The workers need to reach "
            "the object storage Trino spools to; if they cannot, set this data source's Result transfer to "
            "Direct. ({})".format(where, detail)
        )
    return _database_error_message(error) + where


def _looks_like_storage(detail):
    lowered = detail.lower()
    return any(
        word in lowered for word in ("segment", "bucket", "s3", "x-amz", "error 403", "error 404")
    ) or lowered.startswith("error ")


class Trino(BaseSQLQueryRunner):
    """Trino, optionally over the spooled protocol.

    Under the standard protocol every row of every result is paged through the
    **coordinator's heap** as JSON, which is Trino's own ceiling on large
    results. The spooled protocol has the workers write segments to object
    storage and the client fetch them directly, compressed with lz4 or zstd.

    Result transfer "Automatic", the default, takes it whenever the server
    offers it (Trino 466 and later, with spooling configured) and the standard
    protocol otherwise. "Direct" turns it off, for workers that cannot reach
    the storage Trino spools to.
    """

    noop_query = "SELECT 1"
    should_annotate_query = ANNOTATE_QUERY

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "default": "http"},
                "host": {"type": "string"},
                "port": {"type": "number"},
                "username": {"type": "string"},
                "password": {"type": "string"},
                "source": {"type": "string", "default": "sqldesk"},
                "client_tags": {"type": "string", "title": "Client tags (comma separated)"},
                "catalog": {"type": "string"},
                "schema": {"type": "string"},
                "encoding": {
                    "type": "string",
                    "title": "Result transfer (spooling needs Trino 466+)",
                    "extendedEnum": TRANSFER_CHOICES,
                },
                "impersonation": {"type": "boolean", "default": False},
                "impersonationField": {
                    "type": "string",
                    "title": "Impersonation User Attribute",
                    "default": "email",
                    "extendedEnum": [{"value": "email", "name": "Email"}, {"value": "name", "name": "Name"}],
                },
            },
            "order": [
                "protocol",
                "host",
                "port",
                "username",
                "password",
                "source",
                "client_tags",
                "catalog",
                "schema",
                "encoding",
                "impersonation",
            ],
            "required": ["host", "username"],
            "secret": ["password"],
            "extra_options": [
                "client_tags",
                "encoding",
                "impersonation",
                "impersonationField",
            ],
        }

    @classmethod
    def enabled(cls):
        return enabled

    @classmethod
    def type(cls):
        return "trino"

    def get_schema(self, get_stats=False):
        if self.configuration.get("catalog"):
            catalogs = [self.configuration.get("catalog")]
        else:
            catalogs = self._get_catalogs()

        schema = {}
        for catalog in catalogs:
            query = f"""
                SELECT table_schema, table_name, column_name, data_type
                FROM {catalog}.information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """
            results, error = self.run_query(query, None)

            if error is not None:
                self._handle_run_query_error(error)

            for row in results["rows"]:
                table_name = f'{catalog}.{row["table_schema"]}.{row["table_name"]}'

                if table_name not in schema:
                    schema[table_name] = {"name": table_name, "columns": []}

                column = {"name": row["column_name"], "type": row["data_type"]}
                schema[table_name]["columns"].append(column)

        return list(schema.values())

    def _get_catalogs(self):
        query = """
            SHOW CATALOGS
        """
        results, error = self.run_query(query, None)

        if error is not None:
            self._handle_run_query_error(error)

        catalogs = []
        for row in results["rows"]:
            catalog = row["Catalog"]
            if "." in catalog:
                catalog = f'"{catalog}"'
            catalogs.append(catalog)
        return catalogs

    def _get_trino_user(self, user):
        """Determine the Trino user based on impersonation settings."""
        default_user = self.configuration.get("username")

        if not self.configuration.get("impersonation") or user is None:
            return default_user

        impersonation_field = self.configuration.get("impersonationField", "email")

        if isinstance(user, User):
            if impersonation_field == "email":
                return user.email or default_user
            elif impersonation_field == "name":
                return user.name or default_user
        elif isinstance(user, ApiUser):
            return user.name or default_user

        return default_user

    def _get_client_tags(self):
        client_tags = self.configuration.get("client_tags")
        if not client_tags:
            return None
        tags = [tag.strip() for tag in client_tags.split(",") if tag.strip()]
        return tags or None

    def run_query(self, query, user):
        if self.configuration.get("password"):
            auth = trino.auth.BasicAuthentication(
                username=self.configuration.get("username"), password=self.configuration.get("password")
            )
        else:
            auth = trino.constants.DEFAULT_AUTH

        extra = {}
        # Only when it has been chosen: the client's default is a sentinel that
        # means "spooled if offered". None is what turns spooling off.
        encoding = (self.configuration.get("encoding") or "").strip()
        if encoding == DIRECT:
            extra["encoding"] = None
        elif encoding:
            extra["encoding"] = encoding
        if FAST_TYPES:
            extra["legacy_primitive_types"] = True

        connection = trino.dbapi.connect(
            http_scheme=self.configuration.get("protocol", "http"),
            host=self.configuration.get("host", ""),
            source=self.configuration.get("source", "sqldesk"),
            port=self.configuration.get("port", 8080),
            catalog=self.configuration.get("catalog", ""),
            schema=self.configuration.get("schema", ""),
            user=self._get_trino_user(user),
            client_tags=self._get_client_tags(),
            auth=auth,
            **extra,
        )

        cursor = connection.cursor()

        try:
            cursor.execute(query)
            # The columns are known once the first page has arrived.
            first = cursor.fetchmany(FETCH_BATCH)
            description = cursor.description or []
            columns = self.fetch_columns([(c[0], _trino_type(c[1])) for c in description])
            column_names = [c["name"] for c in columns]
            to_row = self._row_maker(cursor, column_names)
            pending = [first]

            def fetchmany(size):
                return pending.pop() if pending else cursor.fetchmany(size)

            rows, truncated = fetch_within_budget(fetchmany, to_row)
            if truncated:
                # The rest is not wanted. Left alone, the coordinator holds it
                # for a reader that has stopped reading.
                _stop(cursor)
            data = {"columns": columns, "rows": rows}
            if truncated:
                mark_truncated(data)
            error = None
        except (KeyboardInterrupt, InterruptException, JobTimeoutException):
            _stop(cursor)
            raise
        except (
            DatabaseError,
            trino_exceptions.HttpError,
            trino_exceptions.TrinoQueryError,
            requests.exceptions.RequestException,
        ) as failure:
            # Whatever stopped the read, the query may still be running.
            _stop(cursor)
            data = None
            error = _explain(failure, getattr(cursor, "query_id", None), self.configuration)
        finally:
            # A dbapi connection holds an HTTP session to the coordinator. Left open,
            # the worker accumulates one per query it has ever run.
            try:
                connection.close()
            except Exception:
                logger.warning("Trino connection did not close cleanly", exc_info=True)

        return data, error

    def _row_maker(self, cursor, column_names):
        """Turns one fetched row into the dict a result stores."""
        if not FAST_TYPES:
            return lambda r: dict(zip(column_names, [_convert_row_types(v) for v in r]))
        columns = getattr(getattr(cursor, "_query", None), "columns", None) or []
        converters = _fast_converters(columns) if len(columns) == len(column_names) else None
        if converters is None:
            # Not the shape this was written against: keep every value as sent.
            logger.warning("Trino column types unavailable; storing values as Trino sent them")
            return lambda r: dict(zip(column_names, r))
        pairs = list(zip(column_names, converters))

        def to_row(r):
            return {
                name: (value if convert is None or value is None else convert(value))
                for (name, convert), value in zip(pairs, r)
            }

        return to_row


#: (connect, read) seconds for downloading one spooled segment. Reading waits
#: as long as a large segment can take between bytes.
SEGMENT_TIMEOUT = (10, 120)


def _download_with_a_timeout(send):
    """
    The client downloads a spooled segment with no timeout at all.

    It builds a fresh request for every segment, so a session given to the
    connection never reaches it. With storage the workers could not reach,
    each of three attempts waited for the kernel to give up on the TCP
    connection, and the page said "Executing query" for six and a half
    minutes before it said anything else -- measured on minikube, with a
    NetworkPolicy between the workers and the storage.
    """

    @functools.wraps(send)
    def send_with_a_timeout(self, uri, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = SEGMENT_TIMEOUT
        return send(self, uri, **kwargs)

    send_with_a_timeout.gives_a_timeout = True
    return send_with_a_timeout


def _give_segment_downloads_a_timeout():
    segment = getattr(getattr(trino, "client", None), "SpooledSegment", None)
    send = getattr(segment, "_send_spooling_request", None)
    if send is None:
        logger.warning("trino.client.SpooledSegment has no _send_spooling_request: segment downloads keep no timeout")
        return
    if not getattr(send, "gives_a_timeout", False):
        segment._send_spooling_request = _download_with_a_timeout(send)


if enabled:
    _give_segment_downloads_a_timeout()


def _stop(cursor):
    """Cancel the query on Trino, if it is still going. Never the reason for a failure."""
    try:
        cursor.cancel()
    except Exception:
        logger.warning("Could not cancel a Trino query", exc_info=True)


register(Trino)

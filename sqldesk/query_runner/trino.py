import logging
import os

from sqldesk.models.users import ApiUser, User
from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    InterruptException,
    JobTimeoutException,
    register,
)
from sqldesk.settings import parse_boolean

logger = logging.getLogger(__name__)
ANNOTATE_QUERY = parse_boolean(os.environ.get("TRINO_ANNOTATE_QUERY", "true"))

try:
    import trino
    from trino.exceptions import DatabaseError
    from trino.types import NamedRowTuple

    enabled = True
except ImportError:
    enabled = False


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


class Trino(BaseSQLQueryRunner):
    """Trino, optionally over the spooled protocol.

    Under the standard protocol every row of every result is paged through the
    **coordinator's heap** as JSON, which is Trino's own ceiling on large
    results. The spooled protocol has the workers write segments to object
    storage and the client fetch them directly, compressed with lz4 or zstd.

    It is off unless a data source asks for it, because it needs a server that
    offers it (Trino 466 and later, with spooling configured) and there is no
    way to tell from here whether one does.
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
                    "title": "Spooled protocol encoding (Trino 466+)",
                    "extendedEnum": [
                        {"value": "", "name": "Standard protocol (default)"},
                        {"value": "json", "name": "Spooled, uncompressed"},
                        {"value": "json+lz4", "name": "Spooled, lz4"},
                        {"value": "json+zstd", "name": "Spooled, zstd"},
                    ],
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
        # Only when it has been chosen. The client's default is a sentinel
        # object, not None, so passing None would not mean "leave it alone" --
        # it would mean something else entirely.
        encoding = (self.configuration.get("encoding") or "").strip()
        if encoding:
            extra["encoding"] = encoding

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
            results = cursor.fetchall()
            description = cursor.description
            columns = self.fetch_columns([(c[0], _trino_type(c[1])) for c in description])
            column_names = [c["name"] for c in columns]
            rows = [dict(zip(column_names, [_convert_row_types(v) for v in r])) for r in results]
            data = {"columns": columns, "rows": rows}
            error = None
        except DatabaseError as db:
            data = None
            error = _database_error_message(db)
        except (KeyboardInterrupt, InterruptException, JobTimeoutException):
            cursor.cancel()
            raise
        finally:
            # A dbapi connection holds an HTTP session to the coordinator. Left open,
            # the worker accumulates one per query it has ever run.
            try:
                connection.close()
            except Exception:
                logger.warning("Trino connection did not close cleanly", exc_info=True)

        return data, error


register(Trino)

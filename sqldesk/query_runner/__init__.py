import logging
from collections import defaultdict
from contextlib import ExitStack
from functools import wraps

import sqlparse
from dateutil import parser
from rq.timeouts import JobTimeoutException
from sshtunnel import open_tunnel

from sqldesk import settings, utils
from sqldesk.utils.requests_session import (
    UnacceptableAddressException,
    requests_or_advocate,
    requests_session,
)

logger = logging.getLogger(__name__)


class deferred:
    """
    A module, or a name from one, imported the first time it is used.

    Every query runner is imported when the process starts, because that is
    how each one registers its type. The *SDKs* they depend on do not need to
    be: an install with a Postgres data source has no use for the Snowflake
    connector, and a worker running one query has no use for the other
    thirty-four.

    Measured on the development cluster before this existed: 117 MB resident
    with one runner, 273 MB with all of them -- 155 MB of SDKs, in every
    gunicorn worker and every worker pod, for data sources most installs do
    not have.

    Used in place of the import, so the bodies that call it do not change:

        pd = deferred("pandas")
        ...
        pd.read_csv(...)          # imported here, once

        InfluxDBClient = deferred("influxdb", "InfluxDBClient")
        ...
        InfluxDBClient.from_dsn(...)

    Attribute access and calling both resolve it. Anything that needs the
    real object at *import* time -- a base class, a decorator, a tuple of
    exception types -- must not use this.
    """

    def __init__(self, module, attr=None):
        self._module = module
        self._attr = attr
        self._resolved = None

    def _target(self):
        if self._resolved is None:
            import importlib

            imported = importlib.import_module(self._module)
            self._resolved = getattr(imported, self._attr) if self._attr else imported
        return self._resolved

    def __getattr__(self, name):
        # Guard the privates so `copy`, `pickle` and the debugger cannot
        # trigger an import by looking for `__deepcopy__` and friends.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._target(), name)

    def __call__(self, *args, **kwargs):
        return self._target()(*args, **kwargs)

    def __repr__(self):
        name = "{}.{}".format(self._module, self._attr) if self._attr else self._module
        return "<deferred {} ({})>".format(name, "loaded" if self._resolved is not None else "not yet")


def installed(*modules):
    """
    Whether these modules could be imported, without importing them.

    What `enabled()` needs to answer: a runner whose SDK is not installed is
    not offered. Asking the question by importing is what made every process
    carry every SDK.
    """
    import importlib.util

    for module in modules:
        try:
            if importlib.util.find_spec(module) is None:
                return False
        except (ImportError, ValueError):
            # A parent package that is itself missing, or a name that cannot
            # be a module. Either way: not available.
            return False
    return True


__all__ = [
    "BaseQueryRunner",
    "BaseHTTPQueryRunner",
    "InterruptException",
    "JobTimeoutException",
    "BaseSQLQueryRunner",
    "TYPE_DATETIME",
    "TYPE_BOOLEAN",
    "TYPE_INTEGER",
    "TYPE_STRING",
    "TYPE_DATE",
    "TYPE_FLOAT",
    "SUPPORTED_COLUMN_TYPES",
    "LANGUAGE_SQL",
    "LANGUAGE_PYTHON",
    "READ_ONLY_LANGUAGES",
    "UNCHECKABLE_LANGUAGES",
    "query_language_for",
    "register",
    "get_query_runner",
    "import_query_runners",
    "guess_type",
]

# Valid types of columns returned in results:
TYPE_INTEGER = "integer"
TYPE_FLOAT = "float"
TYPE_BOOLEAN = "boolean"
TYPE_STRING = "string"
TYPE_DATETIME = "datetime"
TYPE_DATE = "date"

#: What a saved query against a data source is actually written in. Most of
#: them are SQL, so that is the default and only the rest say anything.
#:
#: It is a property of the language rather than of the runner on purpose.
#: Whether a query can be read for writes was decided, until now, from a list
#: of data source *types* kept in `sqldesk/mcp`, and a runner added without a
#: line in that list was read as SQL: every PromQL query against a Mimir
#: source was refused for not beginning with SELECT, and `yandex_*` and
#: `google_search_console` had the same gap from the day they arrived. Two
#: runners that speak the same language now answer the same way without
#: anybody remembering to add them twice.
LANGUAGE_SQL = "sql"
LANGUAGE_PYTHON = "python"

#: Languages whose queries cannot write: the engine has no write syntax, or
#: the runner only ever reaches the read half of an API. A query in one of
#: these needs no parsing before it runs.
READ_ONLY_LANGUAGES = frozenset(
    {
        "promql",
        "graphite",
        "elasticsearch",
        "jql",
        "soql",
        "axibase_sql",
        "query_results",
        # A declarative request -- YAML or JSON -- naming what to fetch from
        # an API that serves reads and nothing else.
        "read_only_api",
    }
)

#: Languages with a grammar of their own that nothing here can read for
#: writes. A caller that is not a person is refused and sent to the editor.
UNCHECKABLE_LANGUAGES = frozenset(
    {
        LANGUAGE_PYTHON,
        "kql",
        "aql",
        "dgraph",
        "sparql",
        "flux",
    }
)

SUPPORTED_COLUMN_TYPES = set([TYPE_INTEGER, TYPE_FLOAT, TYPE_BOOLEAN, TYPE_STRING, TYPE_DATETIME, TYPE_DATE])


def split_sql_statements(query):
    def strip_trailing_comments(stmt):
        idx = len(stmt.tokens) - 1
        while idx >= 0:
            tok = stmt.tokens[idx]
            if tok.is_whitespace or sqlparse.utils.imt(tok, i=sqlparse.sql.Comment, t=sqlparse.tokens.Comment):
                stmt.tokens[idx] = sqlparse.sql.Token(sqlparse.tokens.Whitespace, " ")
            else:
                break
            idx -= 1
        return stmt

    def strip_trailing_semicolon(stmt):
        idx = len(stmt.tokens) - 1
        while idx >= 0:
            tok = stmt.tokens[idx]
            # we expect that trailing comments already are removed
            if not tok.is_whitespace:
                if sqlparse.utils.imt(tok, t=sqlparse.tokens.Punctuation) and tok.value == ";":
                    stmt.tokens[idx] = sqlparse.sql.Token(sqlparse.tokens.Whitespace, " ")
                break
            idx -= 1
        return stmt

    def is_empty_statement(stmt):
        # copy statement object. `copy.deepcopy` fails to do this, so just re-parse it
        st = sqlparse.engine.FilterStack()
        st.stmtprocess.append(sqlparse.filters.StripCommentsFilter())
        stmt = next(st.run(str(stmt)), None)
        if stmt is None:
            return True

        return str(stmt).strip() == ""

    stack = sqlparse.engine.FilterStack()

    result = [stmt for stmt in stack.run(query)]
    result = [strip_trailing_comments(stmt) for stmt in result]
    result = [strip_trailing_semicolon(stmt) for stmt in result]
    result = [str(stmt).strip() for stmt in result if not is_empty_statement(stmt)]

    if len(result) > 0:
        return result

    return [""]  # if all statements were empty - return a single empty statement


def combine_sql_statements(queries):
    return ";\n".join(queries)


def find_last_keyword_idx(parsed_query):
    for i in reversed(range(len(parsed_query.tokens))):
        if parsed_query.tokens[i].ttype in sqlparse.tokens.Keyword:
            return i
    return -1


class InterruptException(Exception):
    pass


class NotSupported(Exception):
    pass


def has_odbc_driver(name):
    """
    Whether unixODBC knows a driver by this name.

    pyodbc installs on every architecture, the drivers it loads do not: the
    image puts Microsoft's and Databricks' on amd64 only. A runner that only
    checked for pyodbc was offered on arm64 and failed every connection test
    with "Can't open lib".
    """
    try:
        import pyodbc

        return name in pyodbc.drivers()
    except Exception:
        return False


class BaseQueryRunner:
    #: Whether this kind of data source belongs in the ordinary query editor.
    #: A stream does not: its tables exist only while somebody is watching, so
    #: a dashboard widget over one is an empty widget, and a saved query
    #: against one would run against whatever happened to be in the window.
    #: Streams have their own place; see `handlers/streams.py`.
    streams_only = False

    #: The language a query against this kind of source is written in. See
    #: `LANGUAGE_SQL`; a runner whose queries are not SQL overrides it.
    query_language = LANGUAGE_SQL

    deprecated = False
    should_annotate_query = True
    noop_query = None
    limit_query = " LIMIT 1000"
    limit_keywords = ["LIMIT", "OFFSET"]
    limit_after_select = False

    def __init__(self, configuration):
        self.syntax = "sql"
        self.configuration = configuration

    @classmethod
    def name(cls):
        return cls.__name__

    @classmethod
    def type(cls):
        return cls.__name__.lower()

    @classmethod
    def enabled(cls):
        return True

    @property
    def host(self):
        """Returns this query runner's configured host.
        This is used primarily for temporarily swapping endpoints when using SSH tunnels to connect to a data source.

        `BaseQueryRunner`'s naïve implementation supports query runner implementations that store endpoints using `host` and `port`
        configuration values. If your query runner uses a different schema (e.g. a web address), you should override this function.
        """
        if "host" in self.configuration:
            return self.configuration["host"]
        else:
            raise NotImplementedError()

    @host.setter
    def host(self, host):
        """Sets this query runner's configured host.
        This is used primarily for temporarily swapping endpoints when using SSH tunnels to connect to a data source.

        `BaseQueryRunner`'s naïve implementation supports query runner implementations that store endpoints using `host` and `port`
        configuration values. If your query runner uses a different schema (e.g. a web address), you should override this function.
        """
        if "host" in self.configuration:
            self.configuration["host"] = host
        else:
            raise NotImplementedError()

    @property
    def port(self):
        """Returns this query runner's configured port.
        This is used primarily for temporarily swapping endpoints when using SSH tunnels to connect to a data source.

        `BaseQueryRunner`'s naïve implementation supports query runner implementations that store endpoints using `host` and `port`
        configuration values. If your query runner uses a different schema (e.g. a web address), you should override this function.
        """
        if "port" in self.configuration:
            return self.configuration["port"]
        else:
            raise NotImplementedError()

    @port.setter
    def port(self, port):
        """Sets this query runner's configured port.
        This is used primarily for temporarily swapping endpoints when using SSH tunnels to connect to a data source.

        `BaseQueryRunner`'s naïve implementation supports query runner implementations that store endpoints using `host` and `port`
        configuration values. If your query runner uses a different schema (e.g. a web address), you should override this function.
        """
        if "port" in self.configuration:
            self.configuration["port"] = port
        else:
            raise NotImplementedError()

    @classmethod
    def configuration_schema(cls):
        return {}

    def annotate_query(self, query, metadata):
        if not self.should_annotate_query:
            return query

        annotation = ", ".join(["{}: {}".format(k, v) for k, v in metadata.items()])
        annotated_query = "/* {} */ {}".format(annotation, query)
        return annotated_query

    def test_connection(self):
        if self.noop_query is None:
            raise NotImplementedError()
        data, error = self.run_query(self.noop_query, None)

        if error is not None:
            raise Exception(error)

    def run_query(self, query, user):
        raise NotImplementedError()

    def fetch_columns(self, columns):
        column_names = set()
        duplicates_counters = defaultdict(int)
        new_columns = []

        for col in columns:
            column_name = col[0]
            while column_name in column_names:
                duplicates_counters[col[0]] += 1
                column_name = "{}{}".format(col[0], duplicates_counters[col[0]])

            column_names.add(column_name)
            new_columns.append({"name": column_name, "friendly_name": column_name, "type": col[1]})

        return new_columns

    def get_schema(self, get_stats=False):
        raise NotSupported()

    def _handle_run_query_error(self, error):
        if error is None:
            return

        logger.error(error)
        raise Exception(f"Error during query execution. Reason: {error}")

    def _run_query_internal(self, query):
        results, error = self.run_query(query, None)

        if error is not None:
            raise Exception("Failed running query [%s]." % query)
        return results["rows"]

    @classmethod
    def to_dict(cls):
        return {
            "name": cls.name(),
            "type": cls.type(),
            "configuration_schema": cls.configuration_schema(),
            **({"deprecated": True} if cls.deprecated else {}),
        }

    @property
    def supports_auto_limit(self):
        return False

    def apply_auto_limit(self, query_text, should_apply_auto_limit):
        return query_text

    def gen_query_hash(self, query_text, set_auto_limit=False):
        query_text = self.apply_auto_limit(query_text, set_auto_limit)
        return utils.gen_query_hash(query_text)


class BaseSQLQueryRunner(BaseQueryRunner):
    def get_schema(self, get_stats=False):
        schema_dict = {}
        self._get_tables(schema_dict)
        if settings.SCHEMA_RUN_TABLE_SIZE_CALCULATIONS and get_stats:
            self._get_tables_stats(schema_dict)
        return list(schema_dict.values())

    def _get_tables(self, schema_dict):
        return []

    def _get_tables_stats(self, tables_dict):
        for t in tables_dict.keys():
            if isinstance(tables_dict[t], dict):
                res = self._run_query_internal("select count(*) as cnt from %s" % t)
                tables_dict[t]["size"] = res[0]["cnt"]

    @property
    def supports_auto_limit(self):
        return True

    def query_is_select_no_limit(self, query):
        parsed_query_list = sqlparse.parse(query)
        if len(parsed_query_list) == 0:
            return False
        parsed_query = parsed_query_list[0]
        last_keyword_idx = find_last_keyword_idx(parsed_query)
        # Either invalid query or query that is not select
        if last_keyword_idx == -1 or parsed_query.tokens[0].value.upper() != "SELECT":
            return False

        no_limit = parsed_query.tokens[last_keyword_idx].value.upper() not in self.limit_keywords

        return no_limit

    def add_limit_to_query(self, query):
        parsed_query = sqlparse.parse(query)[0]
        limit_tokens = sqlparse.parse(self.limit_query)[0].tokens
        length = len(parsed_query.tokens)
        if not self.limit_after_select:
            if parsed_query.tokens[length - 1].ttype == sqlparse.tokens.Punctuation:
                parsed_query.tokens[length - 1 : length - 1] = limit_tokens
            else:
                parsed_query.tokens += limit_tokens
        else:
            for i in range(length - 1, -1, -1):
                if parsed_query[i].value.upper() == "SELECT":
                    index = parsed_query.token_index(parsed_query[i + 1])
                    parsed_query = sqlparse.sql.Statement(
                        parsed_query.tokens[:index] + limit_tokens + parsed_query.tokens[index:]
                    )
                    break
        return str(parsed_query)

    def apply_auto_limit(self, query_text, should_apply_auto_limit):
        queries = split_sql_statements(query_text)
        if should_apply_auto_limit:
            # we only check for last one in the list because it is the one that we show result
            last_query = queries[-1]
            if self.query_is_select_no_limit(last_query):
                queries[-1] = self.add_limit_to_query(last_query)
        return combine_sql_statements(queries)


class BaseHTTPQueryRunner(BaseQueryRunner):
    should_annotate_query = False
    response_error = "Endpoint returned unexpected status code"
    requires_authentication = False
    requires_url = True
    url_title = "URL base path"
    username_title = "HTTP Basic Auth Username"
    password_title = "HTTP Basic Auth Password"

    @classmethod
    def configuration_schema(cls):
        schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "title": cls.url_title},
                "username": {"type": "string", "title": cls.username_title},
                "password": {"type": "string", "title": cls.password_title},
            },
            "secret": ["password"],
            "order": ["url", "username", "password"],
        }

        if cls.requires_url or cls.requires_authentication:
            schema["required"] = []

        if cls.requires_url:
            schema["required"] += ["url"]

        if cls.requires_authentication:
            schema["required"] += ["username", "password"]
        return schema

    def get_auth(self):
        username = self.configuration.get("username")
        password = self.configuration.get("password")
        if username and password:
            return (username, password)
        if self.requires_authentication:
            raise ValueError("Username and Password required")
        else:
            return None

    def get_response(self, url, auth=None, http_method="get", **kwargs):
        # Get authentication values if not given
        if auth is None:
            auth = self.get_auth()

        # Then call requests to get the response from the given endpoint
        # URL optionally, with the additional requests parameters.
        error = None
        response = None
        try:
            response = requests_session.request(http_method, url, auth=auth, **kwargs)
            # Raise a requests HTTP exception with the appropriate reason
            # for 4xx and 5xx response status codes which is later caught
            # and passed back.
            response.raise_for_status()

            # Any other responses (e.g. 2xx and 3xx):
            if response.status_code != 200:
                error = "{} ({}).".format(self.response_error, response.status_code)

        except requests_or_advocate.HTTPError as exc:
            logger.exception(exc)
            error = "Failed to execute query. "
            f"Return Code: {response.status_code} Reason: {response.text}"
        except UnacceptableAddressException as exc:
            logger.exception(exc)
            error = "Can't query private addresses."
        except requests_or_advocate.RequestException as exc:
            # Catch all other requests exceptions and return the error.
            logger.exception(exc)
            error = str(exc)

        # Return response and error.
        return response, error


query_runners = {}


def register(query_runner_class):
    global query_runners
    if query_runner_class.enabled():
        logger.debug(
            "Registering %s (%s) query runner.",
            query_runner_class.name(),
            query_runner_class.type(),
        )
        query_runners[query_runner_class.type()] = query_runner_class
    else:
        logger.debug(
            "%s query runner enabled but not supported, not registering. Either disable or install missing "
            "dependencies.",
            query_runner_class.name(),
        )


def get_query_runner(query_runner_type, configuration):
    query_runner_class = query_runners.get(query_runner_type, None)
    if query_runner_class is None:
        return None

    return query_runner_class(configuration)


def query_language_for(query_runner_type):
    """What a query against this kind of data source is written in.

    Answered from the class, not from an instance: nothing is connected to and
    no configuration is needed, so a caller deciding what it may do with a
    query -- MCP -- can ask before it has anything to run it with. A type no
    runner claims is SQL, which is what the rest of the application assumes of
    one it cannot place.
    """
    return getattr(query_runners.get(query_runner_type), "query_language", LANGUAGE_SQL)


def get_configuration_schema_for_query_runner_type(query_runner_type):
    query_runner_class = query_runners.get(query_runner_type, None)
    if query_runner_class is None:
        return None

    return query_runner_class.configuration_schema()


def import_query_runners(query_runner_imports):
    for runner_import in query_runner_imports:
        __import__(runner_import)


def guess_type(value):
    if isinstance(value, bool):
        return TYPE_BOOLEAN
    elif isinstance(value, int):
        return TYPE_INTEGER
    elif isinstance(value, float):
        return TYPE_FLOAT

    return guess_type_from_string(value)


def guess_type_from_string(string_value):
    if string_value == "" or string_value is None:
        return TYPE_STRING

    try:
        int(string_value)
        return TYPE_INTEGER
    except (ValueError, OverflowError):
        pass

    try:
        float(string_value)
        return TYPE_FLOAT
    except (ValueError, OverflowError):
        pass

    if str(string_value).lower() in ("true", "false"):
        return TYPE_BOOLEAN

    try:
        parser.parse(string_value)
        return TYPE_DATETIME
    except (ValueError, OverflowError):
        pass

    return TYPE_STRING


def with_ssh_tunnel(query_runner, details):
    def tunnel(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                remote_host, remote_port = query_runner.host, query_runner.port
            except NotImplementedError:
                raise NotImplementedError("SSH tunneling is not implemented for this query runner yet.")

            stack = ExitStack()
            try:
                bastion_address = (details["ssh_host"], details.get("ssh_port", 22))
                remote_address = (remote_host, remote_port)
                auth = {
                    "ssh_username": details["ssh_username"],
                    **settings.dynamic_settings.ssh_tunnel_auth(),
                }
                server = stack.enter_context(open_tunnel(bastion_address, remote_bind_address=remote_address, **auth))
            except Exception as error:
                raise type(error)("SSH tunnel: {}".format(str(error)))

            with stack:
                try:
                    query_runner.host, query_runner.port = server.local_bind_address
                    result = f(*args, **kwargs)
                finally:
                    query_runner.host, query_runner.port = remote_host, remote_port

                return result

        return wrapper

    query_runner.run_query = tunnel(query_runner.run_query)

    return query_runner


#: Keeps `x -> x + 1` working in somebody's saved query.
#:
#: DuckDB 2.0 made the PEG parser the default, and it refuses the single-arrow
#: lambda that every DuckDB release before it accepted -- `list_transform(l, x
#: -> x * 2)` and friends. That is not our syntax to deprecate on a user's
#: behalf: a query that ran in 0.7.10 should run in 0.8.
#:
#: A reprieve rather than a fix. DuckDB removes the flag *and* the syntax in
#: 2.1, so this buys one release in which to tell people, and the release
#: notes say so. Applied before `lock_configuration`, which is the only order
#: that works.
LEGACY_LAMBDA = "SET lambda_syntax = 'enable_single_arrow'"


def storage_config():
    """
    The storage format to write, as a DuckDB connection config.

    DuckDB 2.0 writes a file the 1.5.6 in 0.7.x cannot read, and a stream's
    store is written continuously -- so without this, upgrading to 0.8 would
    quietly make every window file unopenable by the release somebody might
    roll back to. Empty when the setting is `latest`, which is how an install
    opts into the newer format and out of going back.

    Read-only connections take it too. Harmless there, and it keeps the two
    paths from drifting.
    """
    chosen = (settings.DUCKDB_STORAGE_COMPATIBILITY or "").strip()
    if not chosen or chosen == "latest":
        return {}
    return {"storage_compatibility_version": chosen}

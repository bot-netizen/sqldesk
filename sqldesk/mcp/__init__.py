"""
An MCP server, on the SQLDesk server.

The 0.6 plan said this would be a separate optional container, on the
reasoning that kept the screenshot renderer out of the image. That reasoning
was about Chromium -- 400MB nobody who turns the feature off should carry.
MCP is JSON-RPC over HTTP and adds no dependency at all, while a separate
process would need its own copy of the permission model, its own database
connection and its own deployment. So it lives here, and the argument for
splitting it out can be made again the day it needs something heavy.

The tools are task-shaped rather than CRUD-shaped: `find_context` answers a
question in one call, where a `list_tables`/`get_schema` pair makes a model
issue forty and wander. Retrieval happens here, with the catalog, not in the
model's context window.

Every call runs as the SQLDesk user whose API key was presented, and every
data source access goes through the same `has_access` the rest of the
application uses: reading the catalog needs what viewing a dashboard needs,
running SQL needs what the editor needs. There is no service account.
"""

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar

import sqlglot
from sqlalchemy import and_, or_
from sqlalchemy.orm import load_only
from sqlglot import exp
from sqlglot.tokens import TokenType

from sqldesk import __version__, features, models, settings
from sqldesk.ai.catalog.retrieve import context_for
from sqldesk.ai.optimizer import analyze, dialect_for
from sqldesk.permissions import has_access, not_view_only, view_only

#: The editor's own ceiling, reused rather than invented. A model exploring
#: should not be able to ask for more than a person clicking Execute can.
ROW_LIMIT = 1000
#: How long a tool call waits for a worker. Past this the query is still
#: running -- it is the waiting that stops, not the work. Both are capped again
#: by the request's own budget (`time_budget`), which the web server's timeout
#: sets: a wait that outlives gunicorn's kills the worker mid-answer, and the
#: client sees a dropped connection instead of a reason.
RUN_TIMEOUT = 45
EXPLAIN_TIMEOUT = 20
#: Ceilings on what a caller can make as large as it likes. SQL is parsed in
#: the web process, and every search term is another ILIKE.
MAX_SQL = 100000
MAX_TERMS = 12

#: A client asking for every agreed measure should get a usable list, not a
#: dump: past this the answer stops being something a model reads.
MAX_MEASURES = 50
MAX_NAMES = 20

logger = logging.getLogger(__name__)

#: Newest first. A client names the version it wants when it calls initialize;
#: if it is one of these we answer in that version, and otherwise we answer in
#: ours and leave the client to decide whether it can go on. Answering with our
#: own version at a client that asked for an older one is a handshake that
#: fails in a way nobody can read.
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
PROTOCOL_VERSION = SUPPORTED_PROTOCOLS[0]
SERVER_INFO = {
    "name": "sqldesk",
    "title": "SQLDesk",
    # Read from the one place the version is written down, so it cannot
    # disagree with itself after a release.
    "version": __version__,
}

#: Kept small on purpose. Every tool here is one a model can use well; a tool
#: it uses badly costs more than not having it.
TOOLS = [
    {
        "name": "find_context",
        "title": "Find the tables a question is about",
        "description": (
            "Given a question in plain English, return the handful of tables most likely to answer it, "
            "with their columns already pruned to the ones people actually use, and the joins observed "
            "between them. One call replaces browsing the schema."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question, in plain English."},
                "data_source": {"type": "string", "description": "Restrict to one data source by name."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "find_measures",
        "title": "The numbers this organization has agreed on",
        "description": (
            "The measures a curator has signed off on -- what each one is called, what it computes and "
            "which table it comes from. Ask before writing an aggregate of your own: if a measure exists "
            "for what you need, using it is the difference between the organization's number and a "
            "plausible one."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "What you are trying to measure, in plain English. Omit for all of them.",
                },
                "data_source": {"type": "string", "description": "Restrict to one data source by name."},
            },
        },
    },
    {
        "name": "expand_table",
        "title": "Every column of one table",
        "description": (
            "Full column detail for named tables. Use after find_context when the pruned column list " "is not enough."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {"type": "array", "items": {"type": "string"}, "description": "Table names."},
                "data_source": {"type": "string"},
            },
            "required": ["names"],
        },
    },
    {
        "name": "list_data_sources",
        "title": "Data sources this user can read",
        "description": "The data sources available, with their type and dialect.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_queries",
        "title": "Queries somebody has already written",
        "description": (
            "Search saved queries by name and description, and by their charts' names and descriptions. "
            "Before writing SQL, look for the question already answered -- a saved query carries its "
            "author's understanding of the data, which no amount of schema does. Each result lists its "
            "charts: what kind, which columns they plot, and what their author said they show. "
            "Results marked [VERIFIED] have been read and confirmed by a person as the right answer to "
            "their question; prefer one of those, unchanged, over SQL of your own."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string"}, "data_source": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "find_dashboards",
        "title": "Dashboards somebody has already built",
        "description": (
            "Search dashboards by name, the text on them, and their charts. Often the answer is a page "
            "that already exists, and the useful reply is its address rather than a new query. Each "
            "result lists the charts on it that you can see: what kind, which columns they plot, which "
            "query they come from, and what their author said they show."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "explain_query",
        "title": "What a query will cost, before running it",
        "description": (
            "Run EXPLAIN against the data source and return the plan. Use this between writing SQL "
            "and running it: check_sql says whether the shape is wrong, this says what it will cost. "
            "Pass the query itself, without EXPLAIN; only a single read is accepted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}, "data_source": {"type": "string"}},
            "required": ["sql", "data_source"],
        },
    },
    {
        "name": "run_query",
        "title": "Run SQL and return rows",
        "description": (
            "Execute one read-only statement (SELECT, WITH, SHOW, DESCRIBE) against a data source "
            "and return up to {} rows. Runs on a worker as the user whose key this is, appears in the "
            "admin's list of running queries, and can be cancelled there like any other. Check the "
            "plan with explain_query first."
        ).format(ROW_LIMIT),
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}, "data_source": {"type": "string"}},
            "required": ["sql", "data_source"],
        },
    },
    {
        "name": "check_sql",
        "title": "Check SQL before running it",
        "description": (
            "Parse SQL for the given data source's dialect and report expensive patterns -- a join with "
            "no condition, SELECT * on a columnar table, a filter that defeats partition pruning. "
            "Nothing is executed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "data_source": {"type": "string"},
            },
            "required": ["sql"],
        },
    },
]


class McpError(Exception):
    """A JSON-RPC error with a code, rather than a 500."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


#: The JSON-RPC codes, used for what they mean. A client that retries is
#: entitled to decide from the code whether retrying is pointless: -32600 says
#: "you sent nonsense, sending it again will not help", and -32603 says "we
#: broke, it might work next time". Answering a crash with the former tells
#: the client to give up on a request that was fine.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


#: Every wait in one HTTP request draws on this, so a batch of slow calls
#: cannot add up to more than the web server will wait for.
_deadline = ContextVar("mcp_deadline", default=None)


@contextmanager
def time_budget(seconds):
    token = _deadline.set(time.time() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def _readable_sources(user, org, need=view_only):
    """
    The data sources this user may use, by the same rule the rest of the
    application uses. An MCP client gets no more than its user would.

    `view_only` is enough to read the catalog and find saved work -- what a
    person who can only view dashboards may see. Running SQL of one's own
    takes `not_view_only`, which is what the query editor asks for too:
    a view-only group can look at the answers, not ask new questions.
    """
    return [
        source
        for source in models.DataSource.query.filter(models.DataSource.org == org).order_by(models.DataSource.name)
        if has_access(source, user, need)
    ]


def _resolve_source(user, org, name, need=view_only):
    sources = _readable_sources(user, org, need)
    if not name:
        return None
    for source in sources:
        if source.name == name:
            return source
    if need is not_view_only and any(source.name == name for source in _readable_sources(user, org)):
        raise McpError(
            INVALID_PARAMS,
            "You can view {!r} but not run SQL against it: that needs full access to the data source, "
            "the same as the query editor.".format(name),
        )
    raise McpError(
        INVALID_PARAMS,
        "No data source called {!r} that you can read. Available: {}".format(
            name, ", ".join(s.name for s in sources) or "none"
        ),
    )


def _runnable_source(user, org, arguments, required_message):
    """
    The data source to run new SQL against, checked the way the query
    editor checks it: the `execute_query` permission, full rather than
    view-only access, and a source that is not paused.
    """
    if not user.has_permission("execute_query"):
        raise McpError(
            INVALID_PARAMS, "Your groups do not allow running queries, so neither can a client using your key."
        )
    source = _resolve_source(user, org, (arguments or {}).get("data_source"), need=not_view_only)
    if source is None:
        raise McpError(INVALID_PARAMS, required_message)
    if source.paused:
        raise McpError(
            INVALID_PARAMS,
            "{} is paused{}. Try again later.".format(
                source.name, " ({})".format(source.pause_reason) if source.pause_reason else ""
            ),
        )
    return source


def _text(body):
    """MCP tool results are content blocks; ours are all text."""
    return {"content": [{"type": "text", "text": body}], "isError": False}


def _terms(question):
    return [word for word in question.lower().split() if len(word) > 2][:MAX_TERMS]


def _sql_argument(arguments):
    sql = ((arguments or {}).get("sql") or "").strip()
    if not sql:
        raise McpError(INVALID_PARAMS, "`sql` is required.")
    if len(sql) > MAX_SQL:
        raise McpError(INVALID_PARAMS, "That SQL is over {} characters.".format(MAX_SQL))
    return sql


#: Statements a model may run. Everything else -- a write, DDL, a GRANT, a
#: procedure call -- belongs in the editor, where a person reads it first.
READS = (exp.Query, exp.Values, exp.Describe, exp.Show)
#: Anywhere in a statement, not only at its root: `WITH gone AS (DELETE ...)
#: SELECT * FROM gone` is a SELECT that deletes, and `SELECT ... INTO`
#: creates a table.
WRITES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Into,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Copy,
    exp.LoadData,
    exp.Command,
)
#: The first word of a read, for SQL the parser cannot follow.
READ_WORDS = {"select", "with", "show", "describe", "desc", "values"}
_LEADING_NOISE = re.compile(r"^(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/|\()*", re.S)

#: Sources whose query language cannot write, or that reach an API which only
#: reads. Their queries go through unparsed.
READ_ONLY_LANGUAGES = {
    "elasticsearch",
    "elasticsearch2",
    "elasticsearch2_OpenDistroSQLElasticSearch",
    "elasticsearch2_XPackSQLElasticSearch",
    "aws_es",
    "kibana",
    "url",
    "prometheus",
    "graphite",
    "google_spreadsheets",
    "csv",
    "excel",
    "jirajql",
    "results",
    "cloudwatch",
    "cloudwatch_insights",
    "salesforce",
    "google_analytics4",
    "axibasetsd",
}
#: Sources whose language this cannot read for writes -- a program, or a
#: query language with its own grammar. Refused; the editor is the place.
UNCHECKABLE_LANGUAGES = {
    "python",
    "insecure_script",
    "arangodb",
    "azure_kusto",
    "dgraph",
    "sparql_endpoint",
    "corporate_memory",
    "influxdbv2",
}
#: Keywords that only ever start or mark a write, wherever they appear. The
#: tokens are checked before the tree is, because a parse can succeed and
#: still hide one: T-SQL needs no semicolon, so `SELECT 1 DELETE FROM t` read
#: as one SELECT with an alias, and SQL Server ran both.
WRITE_TOKENS = {
    name
    for name in (
        "DELETE",
        "INSERT",
        "UPDATE",
        "MERGE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "EXECUTE",
        "COPY",
        "LOAD",
        "INTO",
        "SET",
        "PUT",
        "KILL",
        "LOCK",
        "ATTACH",
        "DETACH",
        "INSTALL",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "ANALYZE",
        "REFRESH",
        "USE",
        "COMMAND",
    )
    if hasattr(TokenType, name)
}
#: T-SQL statements sqlglot reads as plain words, none of which a read needs.
TSQL_STATEMENTS = {
    "waitfor",
    "shutdown",
    "backup",
    "restore",
    "dbcc",
    "deny",
    "bulk",
    "reconfigure",
    "checkpoint",
    "raiserror",
    "throw",
    "goto",
}


def _write_keyword(sql, dialect):
    """The first write keyword in the SQL's tokens, or None. Strings and quoted names are not keywords."""
    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except Exception:
        return "something the tokenizer could not read"
    for token in tokens:
        if token.token_type.name in WRITE_TOKENS:
            return token.text.upper()
        if dialect == "tsql" and token.token_type == TokenType.VAR and token.text.lower() in TSQL_STATEMENTS:
            return token.text.upper()
    return None


def _mongodb_writes(query):
    """
    MongoDB's query language reads, except where a pipeline stage writes.

    `$out` replaces a collection and `$merge` writes into one, both from an
    ordinary `aggregate` -- so a model handed this source as "read-only" could
    wipe `orders` with one stage.
    """
    try:
        parsed = json.loads(query)
    except ValueError:
        return "That is not a MongoDB query this can check: it is not JSON."

    def stages(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from stages(item)
        elif isinstance(value, list):
            for item in value:
                yield from stages(item)

    for key in stages(parsed):
        if key in ("$out", "$merge"):
            return "That pipeline writes ({}); only reads can be run from here.".format(key)
    return None


def _http_writes(query):
    """The JSON source sends GET by default and POST when asked; a POST can change things."""
    import yaml

    try:
        parsed = yaml.safe_load(query)
    except yaml.YAMLError:
        return "That is not a JSON-source query this can check."
    method = str((parsed or {}).get("method") or "get").lower() if isinstance(parsed, dict) else "get"
    if method != "get":
        return "That request is a {}; only GET can be run from here.".format(method.upper())
    return None


#: Languages that read except in a form this can spot.
LANGUAGE_CHECKS = {
    "mongodb": _mongodb_writes,
    "json": _http_writes,
}


#: What `run_query` returns at most, whatever the SQL asks for.
ROW_CAP = 1000


def _capped(sql, source):
    """
    The SQL with its outermost query limited to `ROW_CAP` rows, or None.

    On the outermost query rather than by wrapping it: SQL Server refuses an
    ORDER BY inside a derived table, and the runners' own `apply_auto_limit`
    only acts on a statement that starts with SELECT -- a WITH query, an
    explicit `LIMIT 10000000`, or any query on Athena or Presto went through
    with every row. A limit already under the cap is left as written.

    None when this cannot rewrite it safely -- an unknown dialect, or not a
    query -- and the caller falls back to the runner's limit.
    """
    dialect = dialect_for(source.type)
    if dialect is None:
        return None
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return None
    if not isinstance(tree, exp.Query):
        return None
    limit = tree.args.get("limit")
    if limit is not None:
        try:
            if int(limit.expression.name) <= ROW_CAP:
                return sql
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        return tree.limit(ROW_CAP, copy=True).sql(dialect=dialect)
    except Exception:
        return None


def _by_language(sql, source):
    """
    `(True, reason)` when the source's language decides, else `(False, None)`.

    A reason of None with True means "reads, go ahead". Everything not decided
    here is SQL, and the SQL checks follow.
    """
    if source.type in ("python", "insecure_script"):
        return True, "This data source runs Python, which a model may not."
    if source.type in UNCHECKABLE_LANGUAGES:
        return True, "This data source's queries cannot be checked for writes here; run them from the editor."
    if source.type in LANGUAGE_CHECKS:
        return True, LANGUAGE_CHECKS[source.type](sql)
    if source.type in READ_ONLY_LANGUAGES:
        return True, None
    return False, None


def _why_not_a_read(sql, source):
    """
    None when `sql` is one statement that only reads; otherwise why not.

    This is not the security boundary -- the database account's grants are,
    and an install that hands SQLDesk a writable account has decided
    something this cannot undo. What it stops is a model doing damage by
    accident: a DELETE it took for a SELECT, a second statement after a
    semicolon, an `EXPLAIN ANALYZE` that runs what it was asked only to plan.
    """
    # Decided by the language, not by which Python class the runner has:
    # Athena and Presto are SQL engines on the plain base class, and went
    # through unchecked.
    decided, reason = _by_language(sql, source)
    if decided:
        return reason

    dialect = dialect_for(source.type)
    try:
        statements = [tree for tree in sqlglot.parse(sql, read=dialect) if tree is not None]
    except Exception:
        statements = None

    if statements is not None and len(statements) != 1:
        return "One statement at a time."

    # The tokens before the tree: a parse can succeed and still hide a write
    # (T-SQL's `SELECT 1 DELETE FROM t`), or fail on one the first word
    # would have let through (MySQL's `SELECT ... INTO OUTFILE`).
    keyword = _write_keyword(sql, dialect)
    if keyword:
        return "That statement contains {}; only reads can be run from here.".format(keyword)

    if statements is None:
        # Some engines speak SQL the parser cannot read, and refusing all of
        # it would make those sources unusable. The first word is still a
        # fair statement of intent; a semicolon inside is not something that
        # can be told apart from one between two statements.
        rest = _LEADING_NOISE.sub("", sql)
        first = re.match(r"[A-Za-z]+", rest)
        if not first or first.group(0).lower() not in READ_WORDS:
            return "Only a read (SELECT, WITH, SHOW, DESCRIBE) can be run from here."
        if ";" in sql.rstrip().rstrip(";"):
            return "One statement at a time."
        return None

    tree = statements[0]
    if isinstance(tree, exp.Command):
        if str(tree.this).lower() in ("show", "describe", "desc"):
            return None
        return "Only a read (SELECT, WITH, SHOW, DESCRIBE) can be run from here, not {}.".format(
            str(tree.this).upper()
        )
    for node in tree.walk():
        if isinstance(node, WRITES):
            return "That statement changes data (it contains {}); only reads can be run from here.".format(
                type(node).__name__.upper()
            )
    if not isinstance(tree, READS):
        return "Only a read (SELECT, WITH, SHOW, DESCRIBE) can be run from here."
    return None


#: A question is a sentence or a few, not a document: each word becomes a
#: search on the catalog.
MAX_QUESTION = 2000


def tool_find_context(user, org, arguments):
    question = (arguments or {}).get("question", "")
    if not isinstance(question, str) or not question.strip():
        raise McpError(INVALID_PARAMS, "`question` is required.")
    if len(question) > MAX_QUESTION:
        raise McpError(INVALID_PARAMS, "`question` is over {} characters.".format(MAX_QUESTION))
    source = _resolve_source(user, org, (arguments or {}).get("data_source"))

    # Scoped to what this user can read even when no source is named: the
    # catalog is the organization's, and a table's name and columns are
    # themselves something a group may not be allowed to see.
    readable = {s.id for s in _readable_sources(user, org)}
    found = context_for(org, question, data_source=source, data_source_ids=readable)
    if not found["tables"]:
        return _text(
            "Nothing in the catalog matched, and the catalog may be empty. "
            "An administrator fills it with `manage ai harvest`."
        )

    lines = []
    # The source's own guidance first, where there is one and the question was
    # narrowed to a single source. It frames everything below it -- which
    # tables to trust, what a row means -- and is wasted at the bottom.
    if source is not None and source.description:
        lines.append("-- {}".format(" ".join(source.description.split())))
        lines.append("")

    # Then how old this is, if it is old. A stale catalog is dangerous in a
    # way an empty one is not: every card is still there, perfectly formatted,
    # describing last month's warehouse. Said before the schema because it
    # changes how much weight to put on what follows.
    lines.extend(_staleness_lines(org, source, readable))

    # Then what the organization has agreed these numbers mean, before the
    # tables they come from. A model that reads the schema first will write
    # its own definition of revenue; one that is told the agreed definition
    # first will use it. The ordering is the whole point -- a semantic layer
    # that arrives after the raw columns is a footnote.
    lines.extend(_measure_lines(found.get("measures")))

    for table in found["tables"]:
        lines.append(table["card"] or table["name"])
        lines.append("")
    return _text("\n".join(lines).strip())


def _staleness_lines(org, source, readable):
    """
    A warning when the catalog has not been harvested lately.

    Only for the sources this answer could have drawn on, so a question
    narrowed to a fresh source is not warned about a stale one nobody asked
    about. Nothing is said when every source is current, because a note on
    every single answer is a note nobody reads by the third one.
    """
    from sqldesk.ai.catalog.freshness import in_days, stale_sources

    ids = [source.id] if source is not None else list(readable)
    try:
        stale = stale_sources(org, ids)
    except Exception:
        # A warning that cannot be produced must not cost the answer it was
        # going to decorate.
        logger.warning("could not work out catalog freshness", exc_info=True)
        return []
    if not stale:
        return []

    names = dict(
        models.db.session.query(models.DataSource.id, models.DataSource.name).filter(
            models.DataSource.id.in_(list(stale))
        )
    )
    oldest = max(stale.values())
    described = ", ".join(sorted(names.get(source_id, str(source_id)) for source_id in stale))
    return [
        "-- Warning: this catalog has not been harvested for {}. It describes {} as it was then, "
        "so a column may have been renamed or dropped since. Check anything surprising against the "
        "data source before relying on it.".format(in_days(oldest), described),
        "",
    ]


def _measure_lines(measures):
    """Agreed measures, as a block a model reads before any schema."""
    if not measures:
        return []
    lines = ["-- Agreed measures. Use these rather than writing your own."]
    for measure in measures:
        described = " -- {}".format(" ".join(measure["description"].split())) if measure.get("description") else ""
        lines.append("{} = {} on {}{}".format(measure["name"], measure["expression"], measure["table"], described))
    lines.append("")
    return lines


def tool_find_measures(user, org, arguments):
    arguments = arguments or {}
    question = arguments.get("question") or ""
    if not isinstance(question, str):
        raise McpError(INVALID_PARAMS, "`question` must be text.")
    if len(question) > MAX_QUESTION:
        raise McpError(INVALID_PARAMS, "`question` is over {} characters.".format(MAX_QUESTION))

    source = _resolve_source(user, org, arguments.get("data_source"))
    readable = [s.id for s in _readable_sources(user, org)]
    if not readable:
        return _text("You have access to no data sources.")

    query = models.CatalogMeasure.query.filter(
        models.CatalogMeasure.org == org,
        models.CatalogMeasure.data_source_id.in_(readable),
        models.CatalogMeasure.status == models.MEASURE_APPROVED,
    )
    if source is not None:
        query = query.filter(models.CatalogMeasure.data_source_id == source.id)

    # Matched on the words of the question, against the measure's own name
    # and description -- which is what a curator wrote it for. A question
    # with no words asks for all of them, which is a reasonable thing for a
    # client to do once and keep.
    terms = [word for word in re.findall(r"[a-zA-Z0-9_]+", question.lower()) if len(word) > 2][:MAX_TERMS]
    if terms:
        matches = [
            models.db.or_(
                models.CatalogMeasure.name.ilike("%{}%".format(term)),
                models.CatalogMeasure.description.ilike("%{}%".format(term)),
                models.CatalogMeasure.table_name.ilike("%{}%".format(term)),
            )
            for term in terms
        ]
        query = query.filter(models.db.or_(*matches))

    found = query.order_by(models.CatalogMeasure.usage_count.desc().nullslast()).limit(MAX_MEASURES).all()
    if not found:
        return _text(
            "No agreed measures match. A curator approves them on the Catalog page; "
            "until then there are none to use, and you should write the aggregate yourself."
        )

    lines = []
    for measure in found:
        described = " -- {}".format(" ".join(measure.description.split())) if measure.description else ""
        lines.append(
            "{} = {}({}) on {}{}".format(
                measure.name,
                (measure.kind or "").upper(),
                measure.column_name,
                measure.table_name,
                described,
            )
        )
    return _text("\n".join(lines))


def tool_expand_table(user, org, arguments):
    names = (arguments or {}).get("names") or []
    if not names or not isinstance(names, list):
        raise McpError(INVALID_PARAMS, "`names` is required: a list of table names.")
    if len(names) > MAX_NAMES:
        raise McpError(INVALID_PARAMS, "At most {} tables at a time.".format(MAX_NAMES))
    names = [str(name) for name in names]
    source = _resolve_source(user, org, (arguments or {}).get("data_source"))

    readable = [s.id for s in _readable_sources(user, org)]
    if not readable:
        raise McpError(INVALID_PARAMS, "None of those tables are in the catalog.")
    query = models.CatalogTable.query.filter(
        models.CatalogTable.org == org,
        models.CatalogTable.name.in_(names),
        models.CatalogTable.data_source_id.in_(readable),
    )
    if source is not None:
        query = query.filter(models.CatalogTable.data_source_id == source.id)

    blocks = []
    for table in query:
        columns = table.columns.order_by(models.CatalogColumn.usage_count.desc())
        body = ", ".join("{} {}".format(c.name, c.type or "?") for c in columns)
        blocks.append("{}({})".format(table.name, body))
    if not blocks:
        raise McpError(INVALID_PARAMS, "None of those tables are in the catalog.")
    return _text("\n\n".join(blocks))


def tool_list_data_sources(user, org, arguments):
    sources = _readable_sources(user, org)
    if not sources:
        return _text("You have access to no data sources.")
    lines = []
    for source in sources:
        lines.append(
            "{} ({}{})".format(
                source.name,
                source.type,
                ", dialect {}".format(dialect_for(source.type)) if dialect_for(source.type) else "",
            )
        )
        # Standing guidance about the source -- which tables to prefer, what
        # is untrusted. It applies to every question asked of it, so it is
        # worth its few tokens here rather than being discovered the hard way.
        if source.description:
            lines.append("  {}".format(" ".join(source.description.split())))
    return _text("\n".join(lines))


def tool_check_sql(user, org, arguments):
    sql = _sql_argument(arguments)
    source = _resolve_source(user, org, (arguments or {}).get("data_source"))

    result = analyze(sql, source.type if source else None)
    if not result["applicable"]:
        return _text(result["reason"])
    if not result["findings"]:
        return _text("Parsed as {}. No findings.".format(result["dialect"]))

    lines = ["Parsed as {}.".format(result["dialect"]), ""]
    for finding in result["findings"]:
        lines.append("{}: {}".format(finding["severity"].upper(), finding["title"]))
        lines.append("  {}".format(finding["detail"]))
        if finding["suggestion"]:
            lines.append("  -> {}".format(finding["suggestion"]))
        lines.append("")
    return _text("\n".join(lines).strip())


#: A chart's columns by what they do, in the order a person reads them. The
#: names are the editor's own labels, so the words match what its author saw.
CHART_ROLES = (
    ("x", "x"),
    ("y", "y"),
    ("series", "grouped by"),
    ("size", "size"),
    ("zVal", "colour"),
    ("yError", "error"),
)

#: One page of a dashboard, the most anybody reads at once -- export's limit.
MAX_CHARTS = 12


def _one_line(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _chart_summary(visualization_type, name, description, options, source=None):
    """
    One chart in a line: its name, what kind, which columns it plots, and
    what its author said it shows. The description is the part worth having
    -- "completed orders only, refunds excluded" is written nowhere else --
    and the columns say how to reproduce it without guessing.
    """
    options = options or {}
    if visualization_type == "CHART":
        kind = "{} chart".format(options["globalSeriesType"]) if options.get("globalSeriesType") else "chart"
        mapping = options.get("columnMapping") or {}
        plotted = [
            "{}: {}".format(said, ", ".join(column for column, assigned in mapping.items() if assigned == role))
            for role, said in CHART_ROLES
            if role in mapping.values()
        ]
    elif visualization_type == "COUNTER":
        kind = "counter"
        plotted = [
            "{}: {}".format(said, options[key])
            for key, said in (("counterColName", "value"), ("targetColName", "target"))
            if options.get(key)
        ]
    else:
        kind = (visualization_type or "visualization").lower().replace("_", " ")
        plotted = []

    line = "{} ({})".format(name or "untitled", "; ".join([kind] + plotted))
    if source:
        line += ", from " + source
    if (description or "").strip():
        line += ": " + _one_line(description, 200)
    return line


def _worth_listing(visualization_type, description):
    """Every query has a plain table. Unless somebody described it, it says nothing."""
    return visualization_type != "TABLE" or bool((description or "").strip())


def _existing_work_matches(text, terms):
    """Every term somewhere in the name or the description."""
    haystack = (text or "").lower()
    return all(term in haystack for term in terms)


def tool_find_queries(user, org, arguments):
    """
    A saved query carries its author's understanding of the data -- which
    join is the right one, which status means what -- and no amount of schema
    carries that. Looking here before writing SQL is the cheapest way to be
    right.
    """
    question = ((arguments or {}).get("question") or "").strip()
    if not question:
        raise McpError(INVALID_PARAMS, "`question` is required.")
    source = _resolve_source(user, org, (arguments or {}).get("data_source"))

    readable = {s.id for s in _readable_sources(user, org)}
    if source is not None:
        readable &= {source.id}
    if not readable:
        return _text("No saved query matches that. Nobody has written it down, or it is worded differently.")

    # Matched by the database rather than over the latest few hundred in
    # Python: a query written two years ago is often exactly the answer.
    # A chart's name and description count: "churn by cohort" is often
    # written on the chart and nowhere on the query behind it.
    matches = [
        or_(
            models.Query.name.ilike(like),
            models.Query.description.ilike(like),
            models.Query.visualizations.any(
                or_(models.Visualization.name.ilike(like), models.Visualization.description.ilike(like))
            ),
        )
        for like in ("%{}%".format(term) for term in _terms(question))
    ]
    # Verified first, and verified means *this* SQL: the join matches the
    # hash as well as the id, so a query somebody verified and then edited
    # sorts with the rest. Within each group, most recently updated first.
    verified = models.CatalogVerifiedQuery
    found = (
        models.Query.query.outerjoin(
            verified,
            and_(
                verified.query_id == models.Query.id,
                verified.query_hash == models.Query.query_hash,
                verified.org_id == org.id,
            ),
        )
        .filter(
            models.Query.org == org,
            models.Query.is_archived.is_(False),
            models.Query.is_draft.is_(False),
            models.Query.data_source_id.in_(readable),
            *matches,
        )
        .order_by(verified.id.isnot(None).desc(), models.Query.updated_at.desc())
        .limit(10)
        .all()
    )

    if not found:
        return _text("No saved query matches that. Nobody has written it down, or it is worded differently.")

    charts = {}
    for visualization in models.Visualization.query.filter(
        models.Visualization.query_id.in_([query.id for query in found])
    ).order_by(models.Visualization.id):
        if _worth_listing(visualization.type, visualization.description):
            charts.setdefault(visualization.query_id, []).append(visualization)

    confirmed = _verifications_for(org, found)

    lines = []
    for query in found:
        verification = confirmed.get(query.id)
        lines.append("#{} {}{}".format(query.id, query.name, " [VERIFIED]" if verification is not None else ""))
        if verification is not None:
            lines.append("  {}".format(_verified_line(verification)))
        if query.description:
            lines.append("  {}".format(query.description.strip().replace("\n", " ")[:300]))
        lines.append(
            "  data source: {} · updated {}".format(
                query.data_source.name if query.data_source else "none",
                query.updated_at.date() if query.updated_at else "?",
            )
        )
        for visualization in charts.get(query.id, [])[:MAX_CHARTS]:
            lines.append(
                "  - "
                + _chart_summary(
                    visualization.type, visualization.name, visualization.description, visualization.options
                )
            )
        lines.append("")
    return _text("\n".join(lines).strip())


def _verifications_for(org, queries):
    """
    The verifications that are about the SQL these queries hold *now*.

    A verification whose hash no longer matches is left out rather than
    reported as stale. The rule is the same one the measures follow: a claim
    nobody currently stands behind is worse than no claim, because a model
    cannot weigh "verified, but the SQL changed" -- it reads the first word.
    The curator sees it on the Catalog page, where it can be acted on.
    """
    if not queries:
        return {}
    by_id = {query.id: query for query in queries}
    rows = models.CatalogVerifiedQuery.query.filter(
        models.CatalogVerifiedQuery.query_id.in_(list(by_id)),
        # Scoped like every other read of the catalog. A query belongs to one
        # organisation, so a row saying otherwise is already wrong -- which is
        # exactly the case where this check is the only thing standing there.
        models.CatalogVerifiedQuery.org == org,
    ).all()
    return {row.query_id: row for row in rows if by_id[row.query_id].query_hash == row.query_hash}


def _verified_line(verification):
    """One line saying what was confirmed, by whom, and when."""
    parts = ["verified"]
    if verification.verified_by is not None:
        parts.append("by {}".format(verification.verified_by.name))
    if verification.verified_at is not None:
        parts.append("on {}".format(verification.verified_at.date()))
    said = "; ".join(
        " ".join(text.split()) for text in (verification.question, verification.note) if text and text.strip()
    )
    line = " ".join(parts)
    return "{} -- {}".format(line, said) if said else line


def tool_find_dashboards(user, org, arguments):
    question = ((arguments or {}).get("question") or "").strip()
    if not question:
        raise McpError(INVALID_PARAMS, "`question` is required.")
    terms = _terms(question)

    # The dashboards list's own rule for who sees what, so a dashboard is
    # found here exactly when its owner's colleagues could find it there.
    visible = models.Dashboard.all(org, user.group_ids, user.id).options(load_only("id"))
    dashboards = (
        models.Dashboard.query.filter(
            models.Dashboard.id.in_(visible),
            models.Dashboard.is_draft.is_(False),
        )
        .order_by(models.Dashboard.updated_at.desc())
        .limit(200)
        .all()
    )

    # The words on a dashboard are in its textboxes, its charts and the
    # queries behind them, which is where its subject is actually written
    # down. Read in one query for all of them, not three per widget.
    #
    # A chart on a data source this user cannot read is left out entirely:
    # the dashboard shows them a locked panel with nothing on it, and neither
    # its words nor its query's name may make the dashboard match here.
    readable = {source.id for source in _readable_sources(user, org)}
    words = {dashboard.id: [dashboard.name] for dashboard in dashboards}
    widgets = {dashboard.id: 0 for dashboard in dashboards}
    charts = {dashboard.id: [] for dashboard in dashboards}
    if dashboards:
        for dashboard_id, text, query_id, query_name, source_id, chart_id, chart_type, chart_name, about in (
            models.db.session.query(
                models.Widget.dashboard_id,
                models.Widget.text,
                models.Query.id,
                models.Query.name,
                models.Query.data_source_id,
                models.Visualization.id,
                models.Visualization.type,
                models.Visualization.name,
                models.Visualization.description,
            )
            .outerjoin(models.Visualization, models.Widget.visualization_id == models.Visualization.id)
            .outerjoin(models.Query, models.Visualization.query_id == models.Query.id)
            .filter(models.Widget.dashboard_id.in_(list(words)))
            .order_by(models.Widget.id)
        ):
            widgets[dashboard_id] += 1
            if chart_id is None:
                words[dashboard_id].append(text or "")
            elif source_id in readable:
                words[dashboard_id].extend([query_name or "", chart_name or "", about or ""])
                charts[dashboard_id].append((chart_id, chart_type, chart_name, about, query_id, query_name))

    found = [
        dashboard
        for dashboard in dashboards
        if not terms or _existing_work_matches(" ".join(words[dashboard.id]), terms)
    ][:8]

    if not found:
        return _text("No dashboard matches that.")

    # Settings only for the charts about to be described: a chart's options
    # run to kilobytes, and the search above looked at two hundred dashboards.
    listed = {
        dashboard.id: [chart for chart in charts[dashboard.id] if _worth_listing(chart[1], chart[3])]
        for dashboard in found
    }
    shown = [chart for dashboard in found for chart in listed[dashboard.id][:MAX_CHARTS]]
    options = dict(
        models.db.session.query(models.Visualization.id, models.Visualization.options).filter(
            models.Visualization.id.in_([chart[0] for chart in shown] or [0])
        )
    )

    lines = []
    for dashboard in found:
        lines.append("{} — /dashboards/{}".format(dashboard.name, dashboard.id))
        lines.append(
            "  {} widgets · updated {}".format(
                widgets[dashboard.id], dashboard.updated_at.date() if dashboard.updated_at else "?"
            )
        )
        for chart_id, chart_type, chart_name, about, query_id, query_name in listed[dashboard.id][:MAX_CHARTS]:
            source = "query #{} {}".format(query_id, query_name)
            lines.append("  - " + _chart_summary(chart_type, chart_name, about, options.get(chart_id), source))
        if len(listed[dashboard.id]) > MAX_CHARTS:
            lines.append("  - and {} more".format(len(listed[dashboard.id]) - MAX_CHARTS))
        lines.append("")
    return _text("\n".join(lines).strip())


def _on_a_worker(user, source, sql, timeout):
    """
    Hand the SQL to a worker and wait for it.

    Not run here. The server does not touch a warehouse -- a four-minute
    query would hold a web worker for four minutes -- and going through the
    queue is also what puts this in the admin's list of running queries,
    under the name of whoever's key it was, cancellable like any other.
    """
    from sqldesk.tasks import Job
    from sqldesk.tasks.queries import enqueue_query

    deadline = time.time() + timeout
    budget = _deadline.get()
    if budget is not None:
        deadline = min(deadline, budget)
    waiting = int(deadline - time.time())
    if waiting < 2:
        # Checked before the query is queued: one that nobody will wait for
        # would run anyway, and cost the warehouse for nothing.
        return None, ["This request has used its time. Call the tool again on its own."]

    job = enqueue_query(
        sql,
        source,
        user.id,
        user.is_api_user(),
        metadata={"Username": user.get_actual_user(), "mcp": True},
        # Empty falls back to the data source's own queue, which is where
        # dashboards go too. An install that would rather a model could not
        # slow down the people watching a dashboard names a queue here and
        # gives it its own workers.
        queue_name=settings.MCP_QUEUE or None,
    )

    while time.time() < deadline:
        fetched = Job.fetch(job.id)
        if fetched.is_finished:
            outcome = fetched.result
            # A query the warehouse refused still *finishes*, as far as the
            # queue is concerned: the job returns a QueryExecutionError
            # rather than raising. Handing that to the database as an id gets
            # "can't adapt type 'QueryExecutionError'", which is a long way
            # from "that table does not exist".
            if not isinstance(outcome, int):
                return None, [str(outcome).strip().splitlines()[0] if outcome else "The query failed."]
            stored = models.QueryResult.query.get(outcome)
            if stored is None:
                return None, ["The query finished but its result could not be found."]
            return stored, None
        if fetched.is_failed:
            return None, (fetched.exc_info or "").strip().splitlines()[-1:] or ["the query failed"]
        time.sleep(0.4)
    return None, ["Still running after {}s. It has not been cancelled -- look under Admin.".format(waiting)]


def _rows_as_text(result, limit=50):
    """Rows a model can read: a header, then values, tab separated."""
    data = result.data if hasattr(result, "data") else result
    if isinstance(data, (int, type(None))):
        return "(no rows)"
    if isinstance(data, str):
        import json as _json

        data = _json.loads(data)
    columns = [c["name"] for c in (data.get("columns") or [])]
    rows = data.get("rows") or []
    lines = ["\t".join(columns)]
    for row in rows[:limit]:
        lines.append("\t".join("" if row.get(c) is None else str(row.get(c)) for c in columns))
    if len(rows) > limit:
        lines.append("… {} more rows returned, {} shown".format(len(rows) - limit, limit))
    return "\n".join(lines)


def tool_explain_query(user, org, arguments):
    sql = _sql_argument(arguments)
    source = _runnable_source(user, org, arguments, "`data_source` is required: a plan is the engine's, not ours.")
    # Checked before EXPLAIN goes in front of it. `ANALYZE DELETE FROM t`
    # would otherwise become `EXPLAIN ANALYZE DELETE FROM t`, which deletes.
    refused = _why_not_a_read(sql, source)
    if refused:
        return {"content": [{"type": "text", "text": refused}], "isError": True}

    result, error = _on_a_worker(user, source, "EXPLAIN {}".format(sql), timeout=EXPLAIN_TIMEOUT)
    if error:
        # A refused EXPLAIN is usually the engine saying the SQL is wrong,
        # which is worth reading rather than swallowing.
        return _text("EXPLAIN failed: {}".format(error[0]))
    return _text("Plan from {}:\n\n{}".format(source.name, _rows_as_text(result, limit=100)))


def _over_the_ceiling(user, source, sql):
    """
    The refusal, or None.

    Never raises and never refuses on an answer it did not get: an engine with
    no estimate, a ceiling nobody set, or an EXPLAIN that failed all mean "let
    it run". Refusing a query for a reason that is not true would be worse than
    running an expensive one.
    """
    from sqldesk.mcp import cost

    def run(statement):
        return _on_a_worker(user, source, statement, timeout=EXPLAIN_TIMEOUT)

    try:
        estimate = cost.estimate(source, sql, run)
    except Exception:
        logger.warning("could not estimate the cost of a query on %s", source.name, exc_info=True)
        return None
    if estimate is None or not estimate.over:
        return None
    logger.info(
        "mcp refused a query on %s: %s over a limit of %s",
        source.name,
        estimate.described,
        estimate.described_ceiling,
    )
    return estimate.refusal()


def tool_run_query(user, org, arguments):
    sql = _sql_argument(arguments)
    source = _runnable_source(user, org, arguments, "`data_source` is required.")
    refused = _why_not_a_read(sql, source)
    if refused:
        return {"content": [{"type": "text", "text": refused}], "isError": True}

    # What the engine says it will cost, where the engine will say and an
    # administrator has set a ceiling. Checked on the SQL as written rather
    # than the limited form below: a `LIMIT` does not make a full scan cheap,
    # and estimating the limited query would let one through on a number that
    # is not the one that matters.
    too_dear = _over_the_ceiling(user, source, sql)
    if too_dear:
        return {"content": [{"type": "text", "text": too_dear}], "isError": True}

    # A ceiling on the outermost query, in the source's own dialect, whatever
    # LIMIT the SQL already has. Where that cannot be done, the editor's own
    # limit from the runner that knows the dialect.
    limited = _capped(sql, source) or source.query_runner.apply_auto_limit(sql, True)

    result, error = _on_a_worker(user, source, limited, timeout=RUN_TIMEOUT)
    if error:
        return {"content": [{"type": "text", "text": error[0]}], "isError": True}
    return _text(_rows_as_text(result))


#: The one tool that writes, and the only one not offered to everybody.
#:
#: Offered only to a caller who authenticated with a personal API key *and* may
#: curate the catalog. An OAuth token never reaches it: those carry `mcp:read`,
#: and `sqldesk.oauth` promised from the start that a writing tool would get a
#: scope of its own rather than those tokens quietly growing the power to write.
UPDATE_TABLE = {
    "name": "update_table",
    "title": "Describe or hide a catalog table",
    "description": (
        "Curate the catalog: write what a table is for, or hide it from what is offered. "
        "Not for answering questions. Will not replace a description a person wrote unless "
        "`overwrite` is true."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The table's name, as the catalog has it."},
            "data_source": {
                "type": "string",
                "description": "Needed only when more than one data source has a table of that name.",
            },
            "description": {
                "type": "string",
                "description": (
                    "What it is for: what a row is, how it is partitioned, what the key looks like, "
                    "what nobody should trust. An empty string clears it."
                ),
            },
            "hidden": {
                "type": "boolean",
                "description": "Leave it off the catalog page and out of what MCP offers. It can still be queried.",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace a description a person wrote. Off unless set.",
            },
        },
        "required": ["name"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
}

#: What a description written through this tool is marked as. Not "human" and
#: not "engine": a harvest leaves it alone -- it protects anything the engine
#: did not write -- and the catalog page can say where it came from.
WRITTEN_BY_MCP = "mcp"


def may_curate(user, by_api_key):
    """Whether this caller is offered, and may call, `update_table`."""
    return bool(by_api_key) and features.can(user, features.MANAGE_CATALOG)


def tool_update_table(user, org, arguments):
    arguments = arguments or {}
    name = arguments.get("name")
    if not isinstance(name, str) or not name.strip():
        raise McpError(INVALID_PARAMS, "`name` is required: the table's name as the catalog has it.")
    name = name.strip()

    changes_description = "description" in arguments
    changes_hidden = "hidden" in arguments
    if not changes_description and not changes_hidden:
        raise McpError(INVALID_PARAMS, "Nothing to change: give a `description`, `hidden`, or both.")
    if changes_description and arguments["description"] is not None and not isinstance(arguments["description"], str):
        raise McpError(INVALID_PARAMS, "`description` is text, or an empty string to clear it.")
    if changes_hidden and not isinstance(arguments["hidden"], bool):
        raise McpError(INVALID_PARAMS, "`hidden` is true or false.")

    # Curating is not a way into a data source one cannot read: the same rule
    # every read tool uses.
    readable = [source.id for source in _readable_sources(user, org)]
    source = _resolve_source(user, org, arguments.get("data_source"))
    matches = models.CatalogTable.query.filter(
        models.CatalogTable.org == org,
        models.CatalogTable.name == name,
        models.CatalogTable.data_source_id.in_(readable or [0]),
    )
    if source is not None:
        matches = matches.filter(models.CatalogTable.data_source_id == source.id)
    matches = matches.all()

    if not matches:
        raise McpError(INVALID_PARAMS, "No table called {!r} in the catalog that you can read.".format(name))
    if len(matches) > 1:
        names = sorted(table.data_source.name for table in matches)
        raise McpError(
            INVALID_PARAMS,
            "{!r} is in {} data sources ({}). Say which with `data_source`.".format(
                name, len(matches), ", ".join(names)
            ),
        )
    table = matches[0]

    said = []
    if changes_description:
        description = (arguments.get("description") or "").strip() or None
        written_by_a_person = table.description_source not in (None, "engine", WRITTEN_BY_MCP)
        if written_by_a_person and description != table.description and not arguments.get("overwrite"):
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "{} already has a description a person wrote, so it was left alone:\n\n{}\n\n"
                            "Call again with `overwrite: true` to replace it.".format(table.name, table.description)
                        ),
                    }
                ],
                "isError": True,
            }
        table.description = description
        table.description_source = WRITTEN_BY_MCP if description else None
        said.append(
            "Described {}.".format(table.name) if description else "Cleared the description of {}.".format(table.name)
        )
    if changes_hidden:
        table.hidden = arguments["hidden"]
        said.append(
            "Hid {}: it is off the catalog page and out of what MCP offers, and can still be queried.".format(
                table.name
            )
            if table.hidden
            else "{} is shown again.".format(table.name)
        )
    models.db.session.commit()

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    # The MCP call itself is already in the MCP audit; this is the catalog's
    # own record, the same one an edit on the page writes.
    if has_request_context():
        record_event(
            org,
            user,
            {
                "action": "hide" if arguments.get("hidden") else "describe",
                "object_id": table.id,
                "object_type": "catalog_table",
                "via": "mcp",
            },
        )
    return _text(" ".join(said))


HANDLERS = {
    "find_context": tool_find_context,
    "find_measures": tool_find_measures,
    "find_queries": tool_find_queries,
    "find_dashboards": tool_find_dashboards,
    "explain_query": tool_explain_query,
    "run_query": tool_run_query,
    "expand_table": tool_expand_table,
    "list_data_sources": tool_list_data_sources,
    "check_sql": tool_check_sql,
    "update_table": tool_update_table,
}


def handle(message, user, org, by_api_key=False):
    """
    One JSON-RPC message in, one result out.

    Returns None for a notification, which has no id and expects no answer --
    `notifications/initialized` is the one every client sends.
    """
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        raise McpError(INVALID_REQUEST, "Expected a JSON-RPC 2.0 message.")

    method = message.get("method")
    if method is None:
        raise McpError(INVALID_REQUEST, "No method.")
    if "id" not in message:
        return None

    if method == "initialize":
        asked = ((message.get("params") or {}).get("protocolVersion")) or ""
        return {
            "protocolVersion": asked if asked in SUPPORTED_PROTOCOLS else PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        # A tool is listed only to somebody who may call it, so an agent working
        # for a reader never sees a way to write and never tries one.
        return {"tools": TOOLS + [UPDATE_TABLE] if may_curate(user, by_api_key) else TOOLS}
    if method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise McpError(INVALID_PARAMS, "`params` must be an object.")
        name = params.get("name")
        if name not in HANDLERS:
            raise McpError(INVALID_PARAMS, "No tool called {!r}.".format(name))
        if name == UPDATE_TABLE["name"] and not may_curate(user, by_api_key):
            raise McpError(
                INVALID_PARAMS,
                "update_table writes to the catalog, so it needs a personal API key from somebody who may curate "
                "it. OAuth sessions are read-only (mcp:read).",
            )
        arguments = params.get("arguments")
        if arguments is not None and not isinstance(arguments, dict):
            raise McpError(INVALID_PARAMS, "`arguments` must be an object.")
        try:
            return HANDLERS[name](user, org, arguments)
        except McpError:
            raise
        except Exception:
            # A tool that breaks reports that it broke. A transport-level
            # error would make the client drop the session over one bad call.
            logger.exception("MCP tool %s failed", name)
            return {
                "content": [{"type": "text", "text": "That tool failed. An administrator can see why in the log."}],
                "isError": True,
            }

    raise McpError(METHOD_NOT_FOUND, "No method {!r}.".format(method))

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

import datetime
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

from sqldesk import __version__, features, models, settings, utils
from sqldesk.ai.catalog.harvest import rebuild_card
from sqldesk.ai.catalog.retrieve import context_for
from sqldesk.ai.optimizer import analyze, dialect_for
from sqldesk.mcp import layout
from sqldesk.permissions import has_access, not_view_only, view_only
from sqldesk.query_runner import (
    LANGUAGE_PYTHON,
    LANGUAGE_SQL,
    READ_ONLY_LANGUAGES,
    UNCHECKABLE_LANGUAGES,
    query_language_for,
)

#: The editor's own ceiling, reused rather than invented. A model exploring
#: should not be able to ask for more than a person clicking Execute can.
#:
#: One number, used in three places that have to agree: what `run_query`'s
#: description promises, what the SQL is rewritten to ask for, and how many
#: rows are actually rendered back. They were three separate numbers, and two
#: of them were 1000 while the rendering stopped at 50 -- so the tool said
#: "up to 1000 rows" and handed back fifty.
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

#: How a measure may be aggregated -- the words cube uses for the same thing,
#: and the ones the harvester mines.
#: How many matching dashboards are read before the words on their widgets
#: are matched. The match itself is now done by the database, so this is a
#: ceiling on a pathological question rather than on the catalog's size.
MAX_DASHBOARDS_SEARCHED = 200

MEASURE_KINDS = ("sum", "count", "count_distinct", "avg", "min", "max")
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
            "Given a question in plain English, return the tables most likely to answer it, their "
            "columns pruned to the ones people use, and the joins observed between them. One call "
            "replaces browsing the schema."
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
            "The measures a curator has signed off on: what each is called, what it computes, which "
            "table. Ask before writing an aggregate of your own -- using one is the difference between "
            "the organization's number and a plausible one."
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
            "Search saved queries by name, description and their charts. Look here before writing "
            "SQL: a saved query carries its author's understanding of the data. Prefer a [VERIFIED] "
            "result, unchanged, over SQL of your own."
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
            "Search dashboards by name, the text on them and their charts. Often the answer is a page "
            "that already exists, and its address is the useful reply."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "find_alerts",
        "title": "Alerts, and how often they have gone off",
        "description": (
            "Search alerts by name and by the query behind them. Each one comes back with its "
            "condition in words, where it stands now, and how many times it fired in the last 24 "
            "hours -- which is what separates a threshold that is working from one that is too "
            "tight."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "explain_alert",
        "title": "Why an alert is where it is",
        "description": (
            "One alert in full: its condition, the value its query last returned and when, its "
            "recent history with the value on each line, and who gets told. Use this to answer why "
            "it fired, why it did not, or whether it is flapping."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer", "description": "The alert's id, from find_alerts."}},
            "required": ["id"],
        },
    },
    {
        "name": "explain_query",
        "title": "What a query will cost, before running it",
        "description": (
            "The data source's EXPLAIN plan for one read. check_sql says whether the shape is wrong; "
            "this says what it will cost. Pass the SQL without EXPLAIN."
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
            "Run one read-only statement (SELECT, WITH, SHOW, DESCRIBE) and return up to {} rows. "
            "Runs on a worker as this key's owner, and an administrator can cancel it. Check the plan "
            "with explain_query first."
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
            "Parse SQL in the data source's dialect and report expensive patterns -- an unconditional "
            "join, SELECT * on a columnar table, a filter that defeats partition pruning. Nothing runs."
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

#: What a write tool did, for the audit row the transport writes.
#:
#: "update_table ok" said nothing about what changed, so the audit could not
#: answer the only question anybody brings to it -- what did this agent do to
#: my catalog, and what was there before. A tool sets this; sqldesk.handlers.mcp
#: reads it and puts it in the row's detail.
_written = ContextVar("mcp_written", default=None)


def note_write(line):
    """Record, for the audit, what a write changed. Trimmed by the caller."""
    _written.set(line)


def take_write_note():
    """The last write's line, cleared. Read once, by the transport."""
    line = _written.get()
    _written.set(None)
    return line


#: The tools that change something. Capped per person per day, and audited
#: with their before and after.
WRITE_TOOLS = (
    "update_table",
    "save_query",
    "update_query",
    "save_visualization",
    "save_dashboard",
    "propose_measure",
    "save_alert",
)


def _writes_today(user, org):
    """How many writes this person's key has made since midnight UTC."""
    since = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        models.McpEvent.query.filter(
            models.McpEvent.org == org,
            models.McpEvent.user_id == user.id,
            models.McpEvent.tool.in_(WRITE_TOOLS),
            models.McpEvent.outcome == "ok",
            models.McpEvent.created_at >= since,
        ).count()
        or 0
    )


def _within_the_daily_cap(user, org, tool):
    """
    Refuse a write once the day's allowance is gone.

    An agent that has decided to describe every table in a warehouse will do
    exactly that, and a loop that is getting it wrong will do it just as
    fast. Fifty a day is enough for a person working through their catalog
    with help, and small enough that a mistake is a morning's review rather
    than a restore. The cap is per person, because it is their key.
    """
    allowed = settings.MCP_WRITES_PER_DAY
    if allowed <= 0:
        return
    if _writes_today(user, org) >= allowed:
        raise McpError(
            INVALID_PARAMS,
            "{} has written {} things to the catalog today, which is the daily limit. It resets at midnight "
            "UTC; an administrator can raise SQLDESK_MCP_WRITES_PER_DAY.".format(tool, allowed),
        )


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
    """
    A tool result: the text a model reads.

    This used to return the same answer twice -- the prose, and
    `structuredContent` carrying the same fields as data -- on the argument
    that a client parsing prose back into fields has to guess at an absent
    author or an empty tag list.

    Measured, that cost about 90% of the answer's bytes again, for something
    no client could rely on: the protocol pairs `structuredContent` with an
    `outputSchema`, and no tool here declares one. A client either ignored it
    or put it in the model's context beside the prose, so a question was paid
    for twice. The prose is written for a model to read and is what every
    client does use.

    If a typed answer is wanted later it comes back with the schema that makes
    it dependable, and the text shortens to a summary rather than repeating
    it -- which is the trade that was missing the first time.
    """
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


#: Languages that read except in a form this can spot. Keyed by the language
#: the runner declares, not by the data source type, so a second runner that
#: speaks one of them is covered the day it is added.
LANGUAGE_CHECKS = {
    "mongo": _mongodb_writes,
    "http_request": _http_writes,
}


def _capped(sql, source):
    """
    The SQL with its outermost query limited to `ROW_LIMIT` rows, or None.

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
            if int(limit.expression.name) <= ROW_LIMIT:
                return sql
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        return tree.limit(ROW_LIMIT, copy=True).sql(dialect=dialect)
    except Exception:
        return None


#: The data sources that run a program rather than a query.
PROGRAM_SOURCES = ("python", "insecure_script")


def _language(source):
    """
    What a query on this source is written in, asked of the runner itself.

    It used to be read off a list of data source types kept here, and a runner
    added without a line in that list was taken for SQL. `mimir` was: every
    PromQL query a model wrote was refused for not beginning with SELECT, and
    `yandex_*` and `google_search_console` had the same gap. The runner has
    always known; `query_language` is it saying so.
    """
    return query_language_for(source.type) if source is not None else LANGUAGE_SQL


def _not_sql_here(source):
    """
    Why SQL cannot be read, parsed or planned on this source, or None.

    What `check_sql` and `explain_query` need: both of them are about SQL in
    particular, so on a source that speaks something else they have nothing to
    say, and saying it anyway is worse than refusing -- a plan for `EXPLAIN
    up{job="api"}` is not a plan, and findings from parsing PromQL as SQL are
    findings about a query nobody wrote.
    """
    language = _language(source)
    if language == LANGUAGE_SQL:
        return None
    return "This data source's queries are written in {}, not SQL, so there is nothing here to read as SQL.".format(
        language.replace("_", " ")
    )


def _by_language(sql, source):
    """
    `(True, reason)` when the source's language decides, else `(False, None)`.

    A reason of None with True means "reads, go ahead". Everything not decided
    here is SQL, and the SQL checks follow.
    """
    # By type as well as by language, for these two alone: both runners are
    # off unless an install turns them on, and a type whose runner this
    # process never loaded has no language to be read from. A `python` data
    # source saved while it was enabled must still be refused by a worker
    # where it is not.
    if source is not None and source.type in PROGRAM_SOURCES:
        return True, "This data source runs Python, which a model may not."

    language = _language(source)
    if language == LANGUAGE_PYTHON:
        return True, "This data source runs Python, which a model may not."
    if language in UNCHECKABLE_LANGUAGES:
        return True, "This data source's queries cannot be checked for writes here; run them from the editor."
    if language in LANGUAGE_CHECKS:
        return True, LANGUAGE_CHECKS[language](sql)
    if language in READ_ONLY_LANGUAGES:
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
        # Who agreed it, where that is recorded. "Agreed" is the whole value
        # of a measure, and an agreement with nobody's name on it is a claim
        # rather than a decision -- the reviewer was only ever in an event
        # row, which no tool could return beside the measure it is about.
        if measure.reviewed_by is not None:
            lines.append(
                "  agreed by {}{}".format(
                    _who(measure.reviewed_by),
                    " on {}".format(measure.reviewed_at.date()) if measure.reviewed_at else "",
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

    # Descriptions, on the table and on every column that has one. Without
    # them this tool was a worse answer than the find_context card it exists
    # to follow: more columns, and none of what anybody knows about them --
    # so an agent that needed the full list lost the meaning to get it.
    blocks = []
    for table in query:
        columns = table.columns.order_by(models.CatalogColumn.usage_count.desc())
        body = ", ".join(
            "{} {}{}".format(
                column.name,
                column.type or "?",
                " /* {} */".format(" ".join(column.description.split())) if column.description else "",
            )
            for column in columns
        )
        lines = []
        if table.description:
            lines.append("-- {}".format(" ".join(table.description.split())))
        lines.append("{}({})".format(table.name, body))
        if source is None and len(readable) > 1:
            # Two sources can both have a `users` table, and a column list
            # with no source on it is a sentence about the wrong table.
            lines.append("  in data source {}".format(table.data_source.name))
        blocks.append("\n".join(lines))
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

    # Before the optimizer, which keeps its own idea of what is not SQL: it
    # knows eight of the thirty-odd languages here, and the rest were parsed
    # as SQL and reported on as if that had meant something.
    not_sql = _not_sql_here(source)
    if not_sql:
        return _text(not_sql)

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

#: Dashboards described in one answer. Eight dashboards at twelve charts each
#: was ninety-six lines for one question -- six times what the whole semantic
#: catalog costs. Four is enough to recognise the right one, and the answer
#: says how many more matched and how to ask for them.
MAX_DASHBOARDS = 4

#: Lines of chart per dashboard, after charts sharing a query are collapsed
#: onto one line. A board built to show every visualization of one query was
#: most of what made these answers long.
MAX_CHART_LINES = 6

#: Dashboards named in the "and N more" tail. Enough to ask for the right
#: one; past this it is a list nobody reads.
MAX_NAMED = 8


def _options_for_described(found, listed):
    """
    The options of the charts the answer will actually describe.

    One chart per query, in the order they appear, and only as many as will
    be printed: a chart's options run to kilobytes, and the search above
    looked at every match on every board.
    """
    shown = []
    for dashboard in found:
        by_query, order = _grouped_by_query(listed[dashboard.id])
        for query_id in order[:MAX_CHART_LINES]:
            shown.append(_representative(by_query[query_id]["charts"])[0])
    return dict(
        models.db.session.query(models.Visualization.id, models.Visualization.options).filter(
            models.Visualization.id.in_(shown or [0])
        )
    )


def _grouped_by_query(charts):
    """The charts of one dashboard, gathered under the query each came from."""
    by_query, order = {}, []
    for chart_id, chart_type, chart_name, about, query_id, query_name in charts:
        if query_id not in by_query:
            by_query[query_id] = {"name": query_name, "charts": []}
            order.append(query_id)
        by_query[query_id]["charts"].append((chart_id, chart_type, chart_name, about))
    return by_query, order


def _representative(charts):
    """
    The one panel that stands for the rest.

    Whichever carries a description, because the description is the part
    written nowhere else -- and because taking the words from one panel and
    the shape from another would describe a counter as plotting what the line
    chart beside it plots.
    """
    return next((chart for chart in charts if (chart[3] or "").strip()), charts[0])


def _charts_by_query(charts, options):
    """
    The panels of one dashboard, one line per query rather than per panel.

    A dashboard often shows the same query several ways -- a counter, a line
    chart and a table of the same numbers -- and three lines describing one
    query is three times the tokens for no more meaning. They are collapsed
    onto the query they come from, which is also the thing an agent needs if
    it wants the SQL.
    """
    by_query, order = _grouped_by_query(charts)

    lines = []
    for query_id in order[:MAX_CHART_LINES]:
        entry = by_query[query_id]
        chart_id, chart_type, chart_name, about = _representative(entry["charts"])
        summary = _chart_summary(chart_type, chart_name, about, options.get(chart_id))
        others = len(entry["charts"]) - 1
        lines.append(
            "- {}{} — from query #{} {}".format(
                summary,
                " (+{} more view{} of it)".format(others, "" if others == 1 else "s") if others else "",
                query_id,
                entry["name"] or "",
            ).rstrip()
        )
    if len(order) > MAX_CHART_LINES:
        lines.append(
            "- and {} more quer{}".format(
                len(order) - MAX_CHART_LINES, "y" if len(order) - MAX_CHART_LINES == 1 else "ies"
            )
        )
    return lines


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
            # No drafts, not even the caller's own. This tool answers "has
            # somebody already worked this out", and a draft is unfinished by
            # definition -- offering one as the answer is how an agent ends up
            # building on somebody's half-written query. An agent that has
            # just saved a draft is given its id in save_query's reply, so it
            # does not need to find it again here.
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
        # Who wrote it and who last touched it. A saved query is somebody's
        # work, and "ask the person who wrote this" is often the right next
        # step for an agent as much as for a person.
        lines.append("  by {}{}".format(_who(query.user), _last_changed_by(query)))
        for visualization in charts.get(query.id, [])[:MAX_CHARTS]:
            lines.append(
                "  - "
                + _chart_summary(
                    visualization.type, visualization.name, visualization.description, visualization.options
                )
            )
        # The SQL itself.
        #
        # Left out until now, which made this tool a way to *discover* that
        # the answer existed and no way to use it: an agent found a verified
        # query and then wrote its own SQL anyway, which is the opposite of
        # the point. Returned under the same rule the editor uses -- the
        # caller can already open this query and read it there, because the
        # list above is filtered to data sources they may read.
        if query.query_text:
            lines.append("  sql:")
            lines.extend("    " + line for line in _short_sql(query.query_text, query.id).splitlines())
        lines.append("")
    return _text("\n".join(lines).strip())


def _who(user):
    """A person's name, as somebody would say it."""
    return user.name if user is not None and getattr(user, "name", None) else "somebody no longer here"


def _last_changed_by(query):
    """ ", last changed by X" -- only where that is somebody else."""
    changer = query.last_modified_by
    if changer is None or changer.id == query.user_id:
        return ""
    return ", last changed by {}".format(_who(changer))


#: How much SQL goes in the text before the rest is left on the page it came
#: from. It used to be "left to the data", when the same answer was also sent
#: as `structuredContent`; there is no second copy now, so the note says where
#: the whole thing actually is.
MAX_SQL_SHOWN = 4000


def _short_sql(sql, query_id=None):
    text = sql.strip()
    if len(text) <= MAX_SQL_SHOWN:
        return text
    where = "queries/{}".format(query_id) if query_id else "the query's own page"
    return text[:MAX_SQL_SHOWN] + "\n-- (truncated here; the whole query is at {})".format(where)


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
    #
    # Narrowed by the database first, rather than taking the 200 most
    # recently updated and matching those in Python. The dashboard somebody
    # is looking for is often the one nobody has touched for a year -- which
    # is exactly the one that fell off the end of that list. The words on its
    # widgets are still matched here, because they are not in a column.
    visible = models.Dashboard.all(org, user.group_ids, user.id).options(load_only("id"))
    dashboards = models.Dashboard.query.filter(
        models.Dashboard.id.in_(visible),
        models.Dashboard.is_draft.is_(False),
    )
    if terms:
        by_name = or_(*[models.Dashboard.name.ilike("%{}%".format(term)) for term in terms])
        on_a_widget = (
            models.db.session.query(models.Widget.dashboard_id)
            .outerjoin(models.Visualization, models.Widget.visualization_id == models.Visualization.id)
            .outerjoin(models.Query, models.Visualization.query_id == models.Query.id)
            .filter(
                or_(
                    *[
                        or_(
                            models.Widget.text.ilike("%{}%".format(term)),
                            models.Visualization.name.ilike("%{}%".format(term)),
                            models.Visualization.description.ilike("%{}%".format(term)),
                            models.Query.name.ilike("%{}%".format(term)),
                        )
                        for term in terms
                    ]
                )
            )
        )
        dashboards = dashboards.filter(or_(by_name, models.Dashboard.id.in_(on_a_widget.subquery().select())))
    dashboards = dashboards.order_by(models.Dashboard.updated_at.desc()).limit(MAX_DASHBOARDS_SEARCHED).all()

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

    matching = [
        dashboard
        for dashboard in dashboards
        if not terms or _existing_work_matches(" ".join(words[dashboard.id]), terms)
    ]
    # Verified first, as find_queries already does. A board somebody has read
    # and confirmed is the one worth describing, and ordering by when it was
    # last touched would drop it behind four boards nobody has checked --
    # into a count, where an agent cannot see that it exists at all.
    matching.sort(
        key=lambda dashboard: (
            dashboard.verified_at is None,
            -(dashboard.updated_at.timestamp() if dashboard.updated_at else 0),
        )
    )
    found = matching[:MAX_DASHBOARDS]

    if not found:
        return _text("No dashboard matches that.")

    # Settings only for the charts about to be described: a chart's options
    # run to kilobytes, and the search above looked at every match.
    listed = {
        dashboard.id: [chart for chart in charts[dashboard.id] if _worth_listing(chart[1], chart[3])]
        for dashboard in found
    }
    # The options of the charts those lines will actually describe: one per
    # query, in the order they appear, and only as many as will be printed.
    options = _options_for_described(found, listed)

    lines = []
    for dashboard in found:
        verified = dashboard.verified_at is not None
        lines.append("{}{} — /dashboards/{}".format(dashboard.name, " [VERIFIED]" if verified else "", dashboard.id))
        lines.append(
            "  {} widgets · by {} · updated {}".format(
                widgets[dashboard.id],
                _who(dashboard.user),
                dashboard.updated_at.date() if dashboard.updated_at else "?",
            )
        )
        if verified:
            # A dashboard a person has read and confirmed is worth more than
            # one nobody has, and the tool never said so even though 0.7.3
            # recorded it. Said in the same words find_queries uses.
            lines.append(
                "  verified{}{}{}".format(
                    " by {}".format(_who(dashboard.verified_by)) if dashboard.verified_by else "",
                    " on {}".format(dashboard.verified_at.date()),
                    " -- {}".format(" ".join(dashboard.verified_note.split())) if dashboard.verified_note else "",
                )
            )
        for line in _charts_by_query(listed[dashboard.id], options):
            lines.append("  " + line)
        lines.append("")
    if len(matching) > MAX_DASHBOARDS:
        # Named, not just counted: "3 more match, name one" is not actionable
        # if the three are never said. A name costs a handful of tokens and is
        # the whole point of the sentence.
        rest = matching[MAX_DASHBOARDS:]
        lines.append(
            "{} more match: {}{}. Ask for one by name to see its panels.".format(
                len(rest),
                ", ".join(dashboard.name for dashboard in rest[:MAX_NAMED]),
                " and others" if len(rest) > MAX_NAMED else "",
            )
        )
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
    # A plan is a SQL engine's answer. On a source that speaks something else,
    # `EXPLAIN ` in front of the query made it a query the engine could not
    # read -- and on the read-only languages it was sent rather than refused.
    not_sql = _not_sql_here(source)
    if not_sql:
        return {"content": [{"type": "text", "text": not_sql}], "isError": True}

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
    # Every row the query was allowed to return. The SQL is already rewritten
    # to ask for no more than this, so rendering fewer only hid rows that had
    # been fetched and paid for -- and the tool's own description promised
    # them. Tab separated rather than JSON: the same rows cost two to three
    # times as much when every key is repeated on every row.
    return _text(_rows_as_text(result, limit=ROW_LIMIT))


#: The one tool that writes, and the only one not offered to everybody.
#:
#: Offered only to a caller who authenticated with a personal API key *and* may
#: curate the catalog. An OAuth token never reaches it: those carry `mcp:read`,
#: and `sqldesk.oauth` promised from the start that a writing tool would get a
#: scope of its own rather than those tokens quietly growing the power to write.
UPDATE_TABLE = {
    "name": "update_table",
    "title": "Describe a catalog table",
    "description": (
        "Write what a table is for. Not for answering questions. Will not replace a description "
        "a person wrote unless `overwrite` is true."
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
            "overwrite": {
                "type": "boolean",
                "description": "Replace a description a person wrote. Off unless set.",
            },
        },
        "required": ["name"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
}


def _short(text, limit=120):
    """One line of somebody's prose, for an audit row."""
    if not text:
        return ""
    collapsed = " ".join(str(text).split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "\u2026"


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

    if "hidden" in arguments:
        # Said before "nothing to change", so an agent that asked only to hide
        # a table is told why it cannot rather than told it asked for nothing.
        #
        # Hiding decides what everybody is offered, and any key that may
        # curate could have done it silently -- no review, and nothing on a
        # page to notice. It stays a decision somebody makes in the Catalog
        # page, with the table in front of them.
        raise McpError(
            INVALID_PARAMS,
            "Hiding a table is done in Admin -> Catalog, not from here: it changes what everybody is "
            "offered, and a person should see the table while deciding.",
        )
    if "description" not in arguments:
        raise McpError(INVALID_PARAMS, "Nothing to change: give a `description`.")
    if arguments["description"] is not None and not isinstance(arguments["description"], str):
        raise McpError(INVALID_PARAMS, "`description` is text, or an empty string to clear it.")

    _within_the_daily_cap(user, org, "update_table")

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

    before = table.description
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
    table.described_by = user if description else None
    table.described_at = models.db.func.now() if description else None
    # The card is the text an agent is handed, and only a harvest wrote it:
    # this description would not have been read back by find_context for a
    # day, or ever on a paused data source.
    rebuild_card(table)
    said = ["Described {}.".format(table.name) if description else "Cleared the description of {}.".format(table.name)]
    models.db.session.commit()

    # What the audit row says. Before and after, because the question brought
    # to an audit of an agent's writes is never "did it write" -- it is what
    # this table used to say.
    note_write(
        "{} in {}: {!r} -> {!r}".format(table.name, table.data_source.name, _short(before), _short(table.description))
    )

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    # The MCP call itself is already in the MCP audit; this is the catalog's
    # own record, the same one an edit on the page writes.
    if has_request_context():
        record_event(
            org,
            user,
            {
                "action": "describe",
                "object_id": table.id,
                "object_type": "catalog_table",
                "via": "mcp",
            },
        )
    return _text(" ".join(said))


#: The write tools beyond the catalog: saving the SQL an agent and a person
#: worked out together, and proposing a measure for a curator to agree.
#:
#: Each is a draft or a proposal, never something anybody else is shown as
#: settled. A tool that could publish, verify or approve would be a tool that
#: grants trust, and trust is a person's to give -- see SD-12 in
#: plan/0.7.7-plan.md. Everything here lands somewhere a person reviews.
SAVE_QUERY = {
    "name": "save_query",
    "title": "Save SQL as a draft query",
    "description": (
        "Save SQL somebody will want again as a draft query, with a name and a description of what "
        "it answers. It is a draft: it stays off the Queries list until a person opens it and "
        "publishes it. Use it when the SQL you just ran is worth keeping, not for every run."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "What it answers, as a person would say it."},
            "sql": {"type": "string", "description": "The query, exactly as it should be saved."},
            "data_source": {"type": "string", "description": "The data source it runs on."},
            "description": {
                "type": "string",
                "description": "What the result means, and anything somebody reading it later needs to know.",
            },
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags, if the install uses them."},
        },
        "required": ["name", "sql", "data_source"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
}

UPDATE_QUERY = {
    "name": "update_query",
    "title": "Change a draft query you can edit",
    "description": (
        "Change the SQL, name or description of an existing query. Only a draft, and only one you "
        "could edit in the browser. A published query is somebody's work that other people's "
        "dashboards read: open it in SQLDesk instead."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "The query's id, as find_queries gives it."},
            "sql": {"type": "string", "description": "The new SQL."},
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["id"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
}

PROPOSE_MEASURE = {
    "name": "propose_measure",
    "title": "Propose a measure for a curator to agree",
    "description": (
        "Propose a number and what it means -- `gross_revenue = SUM(orders.amount)` -- for a curator "
        "to agree or deny. A proposed measure reaches nobody until somebody signs it off, because a "
        "definition of revenue that is merely plausible is worse than none."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "What it is called: gross_revenue, not sum_amount."},
            "table": {"type": "string", "description": "The table it comes from, as the catalog has it."},
            "kind": {
                "type": "string",
                "enum": ["sum", "count", "count_distinct", "avg", "min", "max"],
                "description": "How it is aggregated.",
            },
            "column": {"type": "string", "description": "The column it aggregates. Omit for a count of rows."},
            "data_source": {"type": "string", "description": "Needed when two sources have that table."},
            "description": {"type": "string", "description": "What it means, and what it excludes."},
        },
        "required": ["name", "table", "kind"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
}

#: The chart types this tool can create, which is what the editor's own type
#: list offers minus the twenty-odd registered visualizations that are not
#: charts at all. Each of these nine is a column mapping and nothing else;
#: anything needing options of its own is left to the browser, because the
#: schema here is already the heaviest of the tools.
CHART_TYPES = ("column", "bar", "line", "area", "pie", "scatter", "bubble", "heatmap", "box")

SAVE_VISUALIZATION = {
    "name": "save_visualization",
    "title": "Add a chart to a draft query",
    "description": (
        "Draw the result of a draft query you can edit: a chart, a table or a single number. The "
        "query keeps its own result; this adds a way of reading it, which save_dashboard can then "
        "put on a dashboard."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query_id": {"type": "integer", "description": "The draft query to draw."},
            "kind": {
                "type": "string",
                "enum": ["chart", "table", "counter"],
                "description": "chart needs x and y; counter needs column; table needs neither.",
            },
            "name": {"type": "string", "description": "What it is called on the query page."},
            "chart_type": {
                "type": "string",
                "enum": CHART_TYPES,
                "description": (
                    "For a chart. `bar` is a column chart on its side. `bubble` also needs `size`; "
                    "`heatmap` takes one `y` as the row label and needs `value`. Default column."
                ),
            },
            "x": {"type": "string", "description": "For a chart: the column along the bottom."},
            "y": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For a chart: the column or columns measured. A heatmap takes one, its row label.",
            },
            "series": {"type": "string", "description": "For a chart: a column to split the series by."},
            "size": {"type": "string", "description": "For a bubble chart: the column the bubble area comes from."},
            "value": {"type": "string", "description": "For a heatmap: the column the colour comes from."},
            "column": {"type": "string", "description": "For a counter: the column to show."},
            "description": {"type": "string", "description": "What it shows, if the name does not say it."},
        },
        "required": ["query_id", "kind"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
}

SAVE_DASHBOARD = {
    "name": "save_dashboard",
    "title": "Put visualizations on a draft dashboard",
    "description": (
        "Make a draft dashboard from visualizations that already exist, in the order given and each "
        "at the size its kind wants -- a table is tall, a stat is small. It is a draft: it reaches "
        "nobody's list until a person opens it and publishes it. Use save_visualization first to "
        "get the ids."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "What the dashboard is for, as a person would say it."},
            "visualizations": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Visualization ids, in the order they should be read.",
            },
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags, if the install uses them."},
        },
        "required": ["name", "visualizations"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
}

#: Offered to a personal API key whose owner may write queries. Not tied to
#: MANAGE_CATALOG: saving a draft query is something any analyst does, and the
#: permission that governs it is the one that governs it in the browser.
SAVE_ALERT = {
    "name": "save_alert",
    "title": "Build an alert, muted",
    "description": (
        "Put a threshold on a saved query. The alert is created MUTED and with nobody subscribed: "
        "it evaluates and records its history, and tells nobody until a person unmutes it and "
        "chooses who to notify. Leave it muted for a day and explain_alert will say how often it "
        "would have fired, which is how a threshold gets tuned before it wakes anybody."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query_id": {"type": "integer", "description": "The saved query to watch. find_queries gives it."},
            "column": {"type": "string", "description": "The column to read, which the query must return."},
            "op": {
                "type": "string",
                "enum": [">", ">=", "<", "<=", "==", "!="],
                "description": "How the value is compared with the threshold.",
            },
            "value": {"type": "number", "description": "The threshold."},
            "name": {"type": "string", "description": "What it means when this fires, as a person would say it."},
        },
        "required": ["query_id", "column", "op", "value", "name"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False},
}

WRITE_ALERT_TOOLS = (SAVE_ALERT,)

WRITE_QUERY_TOOLS = (SAVE_QUERY, UPDATE_QUERY, SAVE_VISUALIZATION)

#: Separate from the above because it is a different browser permission:
#: somebody may be allowed to write queries and not to make dashboards.
WRITE_DASHBOARD_TOOLS = (SAVE_DASHBOARD,)


def may_write_queries(user, by_api_key):
    """
    Whether this caller is offered save_query and update_query.

    A personal API key only: an OAuth session is `mcp:read`, which was stated
    when OAuth was added and is what an agent connected by somebody else's
    client holds. And the same permission the browser checks -- a reader who
    cannot create a query there cannot create one from here.
    """
    return bool(by_api_key) and user.has_permission("create_query")


def _editable_query(user, org, query_id):
    """
    The query this caller may change through MCP, or a refusal saying why.

    Draft only, and only one they could edit in the browser. A published
    query is read by other people's dashboards and alerts: changing its SQL
    from here would change what those say, without anybody seeing a diff.
    """
    query = models.Query.query.filter(models.Query.id == query_id, models.Query.org == org).first()
    if query is None or query.is_archived:
        raise McpError(INVALID_PARAMS, "No query {} that you can see.".format(query_id))
    if query.data_source is None or not has_access(query.data_source, user, not_view_only):
        raise McpError(
            INVALID_PARAMS,
            "Query {} runs on a data source you may only read, so you cannot change it.".format(query_id),
        )
    if not query.is_draft:
        raise McpError(
            INVALID_PARAMS,
            "Query {} is published, so other people's dashboards and alerts read it. Open it in SQLDesk to "
            "change it.".format(query_id),
        )
    if query.user_id != user.id and not user.has_permission("edit_others_queries"):
        raise McpError(INVALID_PARAMS, "Query {} is somebody else's draft.".format(query_id))
    return query


def tool_save_query(user, org, arguments):
    arguments = arguments or {}
    name = (arguments.get("name") or "").strip()
    sql = (arguments.get("sql") or "").strip()
    if not name:
        raise McpError(INVALID_PARAMS, "`name` is required: what the query answers.")
    if not sql:
        raise McpError(INVALID_PARAMS, "`sql` is required.")
    if len(sql) > MAX_SQL:
        raise McpError(INVALID_PARAMS, "`sql` is over {} characters.".format(MAX_SQL))

    source = _resolve_source(user, org, arguments.get("data_source"), need=not_view_only)
    if source is None:
        raise McpError(INVALID_PARAMS, "`data_source` is required: the data source this query runs on.")

    # A draft saved from here is still a query that runs on somebody's
    # warehouse on a schedule later, so the same read-only rule applies as to
    # running one: what is saved is what a person will press Run on.
    refusal = _why_not_a_read(sql, source)
    if refusal:
        raise McpError(INVALID_PARAMS, refusal)

    _within_the_daily_cap(user, org, "save_query")

    tags = arguments.get("tags")
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)):
        raise McpError(INVALID_PARAMS, "`tags` is a list of strings.")

    query = models.Query.create(
        name=name[:255],
        description=(arguments.get("description") or "").strip() or None,
        query_text=sql,
        user=user,
        data_source=source,
        org=org,
        # Always a draft. Nobody's list, nobody's search results and nobody's
        # dashboard picker until a person has read it and published it.
        is_draft=True,
        schedule=None,
        options={},
        tags=[tag.strip() for tag in (tags or []) if tag.strip()] or None,
    )
    models.db.session.add(query)
    models.db.session.commit()

    note_write("saved query {} {!r} on {}".format(query.id, _short(name, 60), source.name))

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    if has_request_context():
        record_event(org, user, {"action": "create", "object_id": query.id, "object_type": "query", "via": "mcp"})

    return _text(
        "Saved as draft query {}, at queries/{}. It is a draft: open it in SQLDesk and publish it to put it on "
        "the Queries list.".format(query.id, query.id)
    )


def tool_update_query(user, org, arguments):
    arguments = arguments or {}
    query_id = arguments.get("id")
    if not isinstance(query_id, int):
        raise McpError(INVALID_PARAMS, "`id` is required: the query's id, as find_queries gives it.")
    changes = {field: arguments[field] for field in ("sql", "name", "description") if field in arguments}
    if not changes:
        raise McpError(INVALID_PARAMS, "Nothing to change: give `sql`, `name` or `description`.")

    query = _editable_query(user, org, query_id)
    _within_the_daily_cap(user, org, "update_query")

    said = []
    if "sql" in changes:
        sql = (changes["sql"] or "").strip()
        if not sql:
            raise McpError(INVALID_PARAMS, "`sql` cannot be emptied.")
        if len(sql) > MAX_SQL:
            raise McpError(INVALID_PARAMS, "`sql` is over {} characters.".format(MAX_SQL))
        refusal = _why_not_a_read(sql, query.data_source)
        if refusal:
            raise McpError(INVALID_PARAMS, refusal)
        before = query.query_text
        query.query_text = sql
        said.append("SQL: {!r} -> {!r}".format(_short(before, 80), _short(sql, 80)))
    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name:
            raise McpError(INVALID_PARAMS, "`name` cannot be emptied.")
        said.append("name: {!r} -> {!r}".format(_short(query.name, 60), _short(name, 60)))
        query.name = name[:255]
    if "description" in changes:
        description = (changes["description"] or "").strip() or None
        said.append("description: {!r} -> {!r}".format(_short(query.description, 60), _short(description, 60)))
        query.description = description

    # Recorded as a version, like an edit in the browser, so the history page
    # shows what changed and who -- which is the whole point of letting an
    # agent edit anything.
    query.record_changes(changed_by=user)
    query.last_modified_by = user
    models.db.session.add(query)
    models.db.session.commit()

    note_write("query {}: {}".format(query.id, "; ".join(said)))

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    if has_request_context():
        record_event(org, user, {"action": "edit", "object_id": query.id, "object_type": "query", "via": "mcp"})

    return _text("Query {} updated: {}. Its history shows the change.".format(query.id, "; ".join(said)))


def may_write_dashboards(user, by_api_key):
    """
    Whether this caller is offered save_dashboard.

    Same shape as may_write_queries -- a personal API key, and the permission
    the browser checks -- but a different permission: making dashboards and
    writing queries are separate things to be allowed to do.
    """
    return bool(by_api_key) and user.has_permission("create_dashboard")


#: Enough to build something, few enough that a runaway agent cannot bury a
#: dashboard list. The daily cap counts each of these calls as one write.
MAX_WIDGETS = 20


def _drawable_query(user, org, query_id):
    """
    The query this caller may add a visualization to.

    The same rule as editing one: a draft they could edit in the browser. A
    published query's page is read by other people, and a chart appearing on
    it that nobody added is the same surprise as its SQL changing.
    """
    return _editable_query(user, org, query_id)


def _chart_columns(chart_type, x, ys, series, arguments):
    """
    Which query column plays which part in the chart.

    `columnMapping` is what getChartData reads; a column named here that the
    result does not have simply does not appear, so the refusals below are
    about the parts that would otherwise produce a chart that looks like it
    worked -- a heatmap with no colour, a bubble chart with no sizes.
    """
    mapping = {x: "x"}

    if chart_type == "heatmap":
        # A heatmap's y is the row label, not a measure: the grid is x by y
        # and the number is the colour. Several y columns would be asking for
        # several grids in one, and with no `value` every cell is drawn at the
        # bottom of the ramp -- a full grid that says nothing.
        if len(ys) != 1:
            raise McpError(INVALID_PARAMS, "A heatmap takes one `y`: the row label. The number goes in `value`.")
        value = (arguments.get("value") or "").strip()
        if not value:
            raise McpError(INVALID_PARAMS, "A heatmap needs `value`: the column the colour comes from.")
        if series:
            raise McpError(INVALID_PARAMS, "A heatmap has no series: its grid is `x` by `y`, coloured by `value`.")
        mapping[ys[0]] = "y"
        mapping[value] = "zVal"
    else:
        for column in ys:
            mapping[column] = "y"

    if chart_type == "bubble":
        # Without a size column every bubble is drawn the same, which is a
        # scatter chart with a misleading name on it.
        size = (arguments.get("size") or "").strip()
        if not size:
            raise McpError(INVALID_PARAMS, "A bubble chart needs `size`: the column the bubble area comes from.")
        mapping[size] = "size"

    if series:
        mapping[series] = "series"

    return mapping


def tool_save_visualization(user, org, arguments):
    arguments = arguments or {}
    query_id = arguments.get("query_id")
    if not isinstance(query_id, int):
        raise McpError(INVALID_PARAMS, "`query_id` is required: the draft query to draw.")
    kind = (arguments.get("kind") or "").strip().lower()
    if kind not in ("chart", "table", "counter"):
        raise McpError(INVALID_PARAMS, "`kind` is chart, table or counter.")

    query = _drawable_query(user, org, query_id)

    if kind == "chart":
        x = (arguments.get("x") or "").strip()
        ys = arguments.get("y") or []
        if isinstance(ys, str):
            ys = [ys]
        if not isinstance(ys, list) or any(not isinstance(column, str) for column in ys):
            raise McpError(INVALID_PARAMS, "`y` is a column name or a list of them.")
        ys = [column.strip() for column in ys if column.strip()]
        if not x or not ys:
            raise McpError(INVALID_PARAMS, "A chart needs `x` and at least one `y`.")

        chart_type = (arguments.get("chart_type") or "column").strip().lower()
        if chart_type not in CHART_TYPES:
            raise McpError(INVALID_PARAMS, "`chart_type` is one of {}.".format(", ".join(CHART_TYPES)))

        series = (arguments.get("series") or "").strip()
        mapping = _chart_columns(chart_type, x, ys, series, arguments)

        options = {
            # `bar` is not a type of its own: it is a column chart with the
            # axes swapped, which is what the editor's own Horizontal does.
            "globalSeriesType": "column" if chart_type == "bar" else chart_type,
            "swappedAxes": chart_type == "bar",
            "columnMapping": mapping,
            "seriesOptions": {},
            # A legend earns its space once there is more than one thing to
            # tell apart -- except on a pie, where the slices *are* the
            # categories and the legend is how you read them at all. A heatmap
            # reads from its colour scale, which is not the legend.
            "legend": {
                "enabled": chart_type != "heatmap" and (chart_type == "pie" or len(ys) > 1 or bool(series)),
            },
        }
        default_name = "{} by {}".format(", ".join(ys), x)
    elif kind == "counter":
        column = (arguments.get("column") or "").strip()
        if not column:
            raise McpError(INVALID_PARAMS, "A counter needs `column`: the column to show.")
        # `rowNumber` is 1-based and 1 is the counter's own registered
        # default, so this is the first row -- the same options the browser
        # writes for a single-number counter.
        options = {"counterColName": column, "rowNumber": 1, "counterLabel": ""}
        default_name = column
    else:
        options = {}
        default_name = "Table"

    _within_the_daily_cap(user, org, "save_visualization")

    name = (arguments.get("name") or "").strip() or default_name
    visualization = models.Visualization(
        query_rel=query,
        # CHART, TABLE, COUNTER: the strings the renderers register under.
        type=kind.upper(),
        name=name[:255],
        description=(arguments.get("description") or "").strip() or None,
        options=options,
    )
    models.db.session.add(visualization)
    models.db.session.commit()

    note_write("visualization {} {!r} ({}) on query {}".format(visualization.id, _short(name, 60), kind, query.id))

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    if has_request_context():
        record_event(
            org,
            user,
            {"action": "create", "object_id": visualization.id, "object_type": "visualization", "via": "mcp"},
        )

    return _text(
        "Added visualization {} to draft query {}, at queries/{}. save_dashboard takes that id.".format(
            visualization.id, query.id, query.id
        )
    )


def tool_save_dashboard(user, org, arguments):
    arguments = arguments or {}
    name = (arguments.get("name") or "").strip()
    if not name:
        raise McpError(INVALID_PARAMS, "`name` is required: what the dashboard is for.")
    ids = arguments.get("visualizations")
    if not isinstance(ids, list) or not ids or any(not isinstance(one, int) for one in ids):
        raise McpError(INVALID_PARAMS, "`visualizations` is a non-empty list of visualization ids.")
    if len(ids) > MAX_WIDGETS:
        raise McpError(INVALID_PARAMS, "{} widgets is the most one dashboard takes from here.".format(MAX_WIDGETS))

    tags = arguments.get("tags")
    if tags is not None and (not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)):
        raise McpError(INVALID_PARAMS, "`tags` is a list of strings.")

    # Resolved before anything is written, so a bad id does not leave half a
    # dashboard behind. Each one has to be on a query whose data source this
    # caller can read, which is what stops a dashboard being used to show
    # somebody a result they could not have run.
    readable = {source.id for source in _readable_sources(user, org)}
    found = []
    for one in ids:
        visualization = (
            models.Visualization.query.join(models.Query)
            .filter(models.Visualization.id == one, models.Query.org == org)
            .first()
        )
        if visualization is None or visualization.query_rel.data_source_id not in readable:
            raise McpError(INVALID_PARAMS, "No visualization {} that you can see.".format(one))
        found.append(visualization)

    _within_the_daily_cap(user, org, "save_dashboard")

    dashboard = models.Dashboard(
        name=name[:100],
        org=org,
        user=user,
        # A draft, for the same reason a saved query is: nobody's list and
        # nobody's screen until a person has looked at it.
        is_draft=True,
        tags=[tag.strip() for tag in (tags or []) if tag.strip()] or None,
        kind="saved",
    )
    models.db.session.add(dashboard)
    models.db.session.flush()

    places = layout.positions([one.type for one in found])
    for index, visualization in enumerate(found):
        models.db.session.add(
            models.Widget(
                dashboard=dashboard,
                visualization=visualization,
                # width is vestigial on the model but not nullable in practice;
                # the browser writes 1 and reads `options.position`.
                width=1,
                options={
                    # Sized by what it holds, the same way the browser sizes a
                    # widget somebody drags on: a table is not a chart and
                    # neither is a stat. See sqldesk/mcp/layout.py.
                    "position": places[index],
                    "parameterMappings": {},
                },
            )
        )
    models.db.session.commit()

    note_write(
        "dashboard {} {!r} with {} widget(s): {}".format(
            dashboard.id, _short(name, 60), len(found), ", ".join(str(one.id) for one in found)
        )
    )

    from flask import has_request_context

    from sqldesk.handlers.base import record_event

    if has_request_context():
        record_event(
            org, user, {"action": "create", "object_id": dashboard.id, "object_type": "dashboard", "via": "mcp"}
        )

    return _text(
        "Saved as draft dashboard {}, at dashboards/{}-{}, with {} widget(s), each sized for what it "
        "holds. It is a draft: open it in SQLDesk and publish it to put it on the Dashboards "
        "list.".format(dashboard.id, dashboard.id, dashboard.slug, len(found))
    )


def tool_propose_measure(user, org, arguments):
    arguments = arguments or {}
    name = (arguments.get("name") or "").strip()
    table_name = (arguments.get("table") or "").strip()
    kind = (arguments.get("kind") or "").strip().lower()
    # "*" for a count of rows, which is what the harvester stores for
    # COUNT(*) -- and what the column is declared as, so None would be a
    # not-null violation reported as "that tool failed".
    column = (arguments.get("column") or "").strip() or ("*" if kind == "count" else None)
    if not name or not table_name or not kind:
        raise McpError(INVALID_PARAMS, "`name`, `table` and `kind` are required.")
    if kind not in MEASURE_KINDS:
        raise McpError(INVALID_PARAMS, "`kind` is one of {}.".format(", ".join(MEASURE_KINDS)))
    if kind != "count" and not column:
        raise McpError(INVALID_PARAMS, "`column` is required for a {}.".format(kind))

    readable = [source.id for source in _readable_sources(user, org)]
    source = _resolve_source(user, org, arguments.get("data_source"))
    matches = models.CatalogTable.query.filter(
        models.CatalogTable.org == org,
        models.CatalogTable.name == table_name,
        models.CatalogTable.data_source_id.in_(readable or [0]),
    )
    if source is not None:
        matches = matches.filter(models.CatalogTable.data_source_id == source.id)
    matches = matches.all()
    if not matches:
        raise McpError(INVALID_PARAMS, "No table called {!r} in the catalog that you can read.".format(table_name))
    if len(matches) > 1:
        raise McpError(
            INVALID_PARAMS,
            "{!r} is in {} data sources ({}). Say which with `data_source`.".format(
                table_name, len(matches), ", ".join(sorted(t.data_source.name for t in matches))
            ),
        )
    table = matches[0]

    existing = models.CatalogMeasure.query.filter(
        models.CatalogMeasure.data_source_id == table.data_source_id,
        models.CatalogMeasure.table_name == table.name,
        models.CatalogMeasure.name == name,
    ).first()
    if existing is not None and existing.status == models.MEASURE_APPROVED:
        return _text(
            "{} on {} is already agreed: {} = {}({}). Use it rather than proposing another.".format(
                existing.name,
                table.name,
                existing.name,
                (existing.kind or "").upper(),
                existing.column_name,
            )
        )

    _within_the_daily_cap(user, org, "propose_measure")

    description = (arguments.get("description") or "").strip() or None
    if existing is None:
        measure = models.CatalogMeasure(
            org=org,
            data_source_id=table.data_source_id,
            table_name=table.name,
            name=name[:255],
            kind=kind,
            column_name=column,
            description=description,
            status=models.MEASURE_PROPOSED,
            proposed_by=user,
            usage_count=0,
        )
        models.db.session.add(measure)
        was = "proposed"
    else:
        # A denied measure proposed again is a proposal, not a decision
        # reversed: it goes back on the curator's list rather than quietly
        # becoming true.
        measure = existing
        measure.kind = kind
        measure.column_name = column
        measure.description = description or measure.description
        measure.status = models.MEASURE_PROPOSED
        measure.proposed_by = user
        measure.reviewed_by = None
        measure.reviewed_at = None
        was = "re-proposed"
    models.db.session.commit()

    note_write(
        "{} {} = {}({}) on {} in {}".format(was, name, kind.upper(), column or "*", table.name, table.data_source.name)
    )

    return _text(
        "{} {} = {}({}) on {}. It reaches nobody until a curator agrees it, on the Catalog page under "
        "Measures.".format(was.capitalize(), name, kind.upper(), column or "*", table.name)
    )


#: How many alerts a search answers with, and how much history one alert
#: shows. The history cap is the lesson from 0.7.7's token work: an alert that
#: has flapped for a month should not be able to fill a context window, and
#: twenty lines is enough to see a shape.
MAX_ALERTS_SHOWN = 20
MAX_ALERT_HISTORY = 20

#: Past this, the value an alert last saw is reported as stale rather than as
#: the current one. A threshold checked against a result three days old is
#: worse than saying the query has not run -- the first reads as an answer.
ALERT_VALUE_STALE_AFTER = datetime.timedelta(hours=24)

#: The operators as somebody says them. The model stores both these and the
#: spelled-out forms it accepted years ago, and a condition is worth more as
#: `orders < 100` than as three option keys.
#: The operators save_alert accepts. The model also honours three
#: spelled-out forms kept for alerts saved years ago, but nothing new should
#: be written in them, so they are not offered here.
ALERT_OPS = (">", ">=", "<", "<=", "==", "!=")

OP_WORDS = {
    "greater than": ">",
    "less than": "<",
    "equals": "==",
}


def _alert_condition(alert):
    """
    An alert's condition on one line, as somebody would say it.

    `{"column": "orders", "op": "<", "value": 100}` is three keys that have to
    be read together before they mean anything. `orders < 100` is the same
    fact, already assembled.
    """
    options = alert.options or {}
    column = options.get("column")
    op = options.get("op")
    value = options.get("value")
    if not column or op is None:
        return "no condition set"
    # `selector` arrived after alerts already existed, so a missing one means
    # the first row -- the same default `evaluate` applies.
    selector = options.get("selector", "first")
    measured = column if selector == "first" else "{}({})".format(selector, column)
    return "{} {} {}".format(measured, OP_WORDS.get(op, op), value)


def _visible_alerts(user, org):
    """
    The alerts this caller may see.

    `Alert.all` is the alerts list's own rule -- an alert sits on a query, and
    whoever cannot read that query's data source has no business reading the
    alert on it. Scoped to the organisation as well, through the query, since
    group ids are only meaningful inside one.
    """
    return models.Alert.all(user.group_ids).filter(models.Query.org_id == org.id)


def _alert_age(alert, counts, now):
    """The three things a list row says about where an alert stands."""
    where = alert.state or models.Alert.UNKNOWN_STATE
    fired = counts.get(alert.id, 0)
    last = alert.last_triggered_at
    parts = [where]
    if fired:
        parts.append("{} fire{} in 24h".format(fired, "" if fired == 1 else "s"))
    if last is not None:
        parts.append("last fired {}".format(_when(last, now)))
    if (alert.options or {}).get("muted"):
        # Worth saying on every line that has it: an alert that is evaluating
        # and telling nobody looks identical to one that is quiet.
        parts.append("MUTED")
    return ", ".join(parts)


def _when(moment, now=None):
    """`3 hours ago`, for a timestamp a model has to weigh rather than parse."""
    if moment is None:
        return "never"
    seconds = ((now or utils.utcnow()) - moment).total_seconds()
    if seconds < 0:
        return "just now"
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = int(seconds // size)
            return "{} {}{} ago".format(count, unit, "" if count == 1 else "s")
    return "under a minute ago"


def tool_find_alerts(user, org, arguments):
    question = ((arguments or {}).get("question") or "").strip()
    if not question:
        raise McpError(INVALID_PARAMS, "`question` is required.")
    terms = _terms(question)

    alerts = _visible_alerts(user, org)
    if terms:
        # The query's name as well as the alert's. Alerts are often named for
        # the threshold ("orders below 100") while the thing somebody is
        # asking about is the subject, which is in the query's name.
        alerts = alerts.filter(
            or_(
                *[
                    or_(
                        models.Alert.name.ilike("%{}%".format(term)),
                        models.Query.name.ilike("%{}%".format(term)),
                    )
                    for term in terms
                ]
            )
        )
    alerts = alerts.order_by(models.Alert.id.desc()).limit(MAX_ALERTS_SHOWN + 1).all()

    if not alerts:
        return _text("No alerts match that. list_data_sources shows what this key can read at all.")

    more = len(alerts) > MAX_ALERTS_SHOWN
    alerts = alerts[:MAX_ALERTS_SHOWN]

    now = utils.utcnow()
    counts = models.Alert.fire_counts([alert.id for alert in alerts], now=now)
    lines = []
    for alert in alerts:
        lines.append(
            "#{} {} -- {} ({}), on query #{} {}".format(
                alert.id,
                alert.name or "untitled",
                _alert_condition(alert),
                _alert_age(alert, counts, now),
                alert.query_rel.id,
                alert.query_rel.name,
            )
        )
    if more:
        lines.append("More than {} match; ask something narrower.".format(MAX_ALERTS_SHOWN))
    lines.append("explain_alert(id) gives one of these in full, with its history.")
    return _text("\n".join(lines))


def tool_explain_alert(user, org, arguments):
    alert_id = (arguments or {}).get("id")
    if alert_id is None:
        raise McpError(INVALID_PARAMS, "`id` is required -- find_alerts gives it.")

    alert = _visible_alerts(user, org).filter(models.Alert.id == alert_id).first()
    if alert is None:
        # The same answer whether it does not exist or this key may not read
        # the data source behind it. Saying which would confirm an alert
        # exists to somebody who cannot see it.
        raise McpError(INVALID_PARAMS, "No alert #{} that this key can read.".format(alert_id))

    now = utils.utcnow()
    query = alert.query_rel
    lines = [
        "#{} {}".format(alert.id, alert.name or "untitled"),
        "Condition: {}".format(_alert_condition(alert)),
        "State: {}".format(_alert_age(alert, models.Alert.fire_counts([alert.id], now=now), now)),
    ]

    if alert.rearm:
        lines.append(
            "Rearm: {} seconds -- it will not fire again until that has passed, so a gap in the "
            "history below may be the rearm rather than the condition clearing.".format(alert.rearm)
        )

    lines.append("Query: #{} {}".format(query.id, query.name))
    lines.extend(_alert_value_lines(alert, query, now))
    lines.extend(_alert_history_lines(alert, now))
    lines.extend(_alert_destination_lines(alert))
    return _text("\n".join(lines))


def _alert_value_lines(alert, query, now):
    """
    What the query last returned, and whether that is worth trusting.

    The value is the whole point of the question "why did it not fire", and it
    is also the easiest thing to be wrong about: a result from three days ago
    presented as the current value reads as an answer, and sends somebody
    looking at the threshold when the real fault is that nothing has run.
    """
    result = query.latest_query_data
    if result is None:
        return ["Value: the query has never run, so there is nothing to check the condition against."]

    column = (alert.options or {}).get("column")
    rows = (result.data or {}).get("rows") or []
    retrieved = result.retrieved_at
    age = _when(retrieved, now)

    if not rows:
        found = "the query returned no rows"
    elif column not in rows[0]:
        found = "the query no longer returns a column called {} -- the alert cannot evaluate".format(column)
    else:
        found = "{} = {}".format(column, rows[0][column])

    if retrieved is not None and (now - retrieved) > ALERT_VALUE_STALE_AFTER:
        return [
            "Value: {}, but from {} -- too old to read as the current value. "
            "Whatever this alert is doing, it is doing it on this result.".format(found, age)
        ]
    return ["Value: {} (from the run {})".format(found, age)]


def _alert_history_lines(alert, now):
    """The recent changes, newest first, with the value each was decided on."""
    fires = alert.recent_fires(limit=MAX_ALERT_HISTORY)
    if not fires:
        return [
            "History: nothing recorded. Alerts have kept a history since 0.7.9; before that only the current state was stored."
        ]

    lines = ["History, newest first:"]
    for fire in fires:
        said = "  {} {}".format(_when(fire.created_at, now), fire.state)
        if fire.value is not None:
            said += " at {}".format(fire.value)
        if not fire.notified:
            # Worth saying: a state change nobody was told about is the
            # difference between "we missed it" and "nothing was sent".
            said += " (nobody notified)"
        lines.append(said)
    if len(fires) == MAX_ALERT_HISTORY:
        lines.append("  (the most recent {}; there may be more)".format(MAX_ALERT_HISTORY))
    return lines


def _alert_destination_lines(alert):
    """Where it notifies, which answers "was anybody actually told"."""
    subscriptions = models.AlertSubscription.all(alert.id).all()
    if not subscriptions:
        return ["Notifies: nobody is subscribed, so it changes state in silence."]
    where = []
    for subscription in subscriptions:
        if subscription.destination:
            where.append("{} ({})".format(subscription.destination.name, subscription.destination.type))
        else:
            where.append("email to {}".format(subscription.user.email))
    return ["Notifies: {}".format(", ".join(where))]


def may_write_alerts(user, by_api_key):
    """
    Whether this caller is offered save_alert.

    A personal API key only, like every other write, and the permission the
    browser checks for the alerts section. There is no separate "create
    alert" permission to check: in the browser, being able to read a query
    is what lets somebody put a threshold on it.
    """
    return bool(by_api_key) and user.has_permission("list_alerts")


def tool_save_alert(user, org, arguments):
    arguments = arguments or {}
    name = (arguments.get("name") or "").strip()
    column = (arguments.get("column") or "").strip()
    op = arguments.get("op")
    value = arguments.get("value")

    if not name:
        raise McpError(INVALID_PARAMS, "`name` is required: what it means when this fires.")
    if not column:
        raise McpError(INVALID_PARAMS, "`column` is required: the column to read.")
    if op not in ALERT_OPS:
        raise McpError(INVALID_PARAMS, "`op` must be one of {}.".format(", ".join(ALERT_OPS)))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise McpError(INVALID_PARAMS, "`value` is the threshold, as a number.")

    query = _alertable_query(user, org, arguments.get("query_id"))
    _check_column_exists(query, column)
    _within_the_daily_cap(user, org, "save_alert")

    alert = models.Alert(
        name=name[:255],
        query_rel=query,
        user=user,
        options={
            "column": column,
            "op": op,
            "value": value,
            "selector": "first",
            # The whole safety model, in one key. An alert is not like a
            # draft query, which sits inert until somebody publishes it: an
            # alert starts evaluating at once, and one with a destination
            # starts waking people up. Muted is the alert vocabulary's own
            # word for "running, telling nobody", so an agent's alert
            # records its history from the first evaluation and notifies
            # only once a person has read it and unmuted it.
            "muted": True,
        },
    )
    models.db.session.add(alert)
    models.db.session.commit()

    note_write("saved alert {} {!r} on query {}".format(alert.id, _short(name, 60), query.id))
    return _text(
        "Alert #{} on query #{}: {} {} {}. It is MUTED and nobody is subscribed, so it is "
        "recording its history and telling nobody. Unmute it at alerts/{} and add a destination "
        "there. explain_alert({}) will show what it would have done in the meantime.".format(
            alert.id, query.id, column, op, value, alert.id, alert.id
        )
    )


def _alertable_query(user, org, query_id):
    """
    The query this caller may put a threshold on, or a refusal saying why.

    The browser's own rules: a query in this organisation they can read, and
    not a stream. A stream is consumed only while somebody is watching it and
    stores no result, so an alert on one would never fire -- which is worse
    than one that cannot be made, because a person told no goes and builds
    something that works.
    """
    if query_id is None:
        raise McpError(INVALID_PARAMS, "`query_id` is required -- find_queries gives it.")
    query = models.Query.query.filter(models.Query.id == query_id, models.Query.org == org).first()
    if query is None or query.data_source_id is None:
        raise McpError(INVALID_PARAMS, "No query #{} that this key can read.".format(query_id))

    readable = {source.id for source in _readable_sources(user, org)}
    if query.data_source_id not in readable:
        # The same answer as for a query that is not there, for the reason
        # explain_alert gives one: saying which confirms it exists.
        raise McpError(INVALID_PARAMS, "No query #{} that this key can read.".format(query_id))

    if query.data_source is not None and query.data_source.streams_only:
        raise McpError(
            INVALID_PARAMS,
            "An alert cannot watch a stream. A stream is consumed only while somebody is looking "
            "at it and stores no result for an alert to check.",
        )
    return query


def _check_column_exists(query, column):
    """
    Refuse a column the query does not return.

    This is the failure worth spending a refusal on: an alert on a misspelled
    column evaluates to unknown for ever and looks, from the list, exactly
    like one that is simply not firing. Checked against the query's last
    result, because that is what the alert itself will read.
    """
    result = query.latest_query_data
    if result is None:
        raise McpError(
            INVALID_PARAMS,
            "Query #{} has never run, so there is nothing to check `column` against. Run it once "
            "-- an alert reads the stored result, so a query that has never run has nothing for "
            "an alert to watch either.".format(query.id),
        )
    columns = [c.get("name") for c in (result.data or {}).get("columns") or []]
    if column not in columns:
        raise McpError(
            INVALID_PARAMS,
            "Query #{} does not return a column called {}. It returns: {}.".format(
                query.id, column, ", ".join(str(c) for c in columns) or "nothing"
            ),
        )


HANDLERS = {
    "find_context": tool_find_context,
    "find_measures": tool_find_measures,
    "find_queries": tool_find_queries,
    "find_dashboards": tool_find_dashboards,
    "find_alerts": tool_find_alerts,
    "explain_alert": tool_explain_alert,
    "explain_query": tool_explain_query,
    "run_query": tool_run_query,
    "expand_table": tool_expand_table,
    "list_data_sources": tool_list_data_sources,
    "check_sql": tool_check_sql,
    "update_table": tool_update_table,
    "save_query": tool_save_query,
    "update_query": tool_update_query,
    "save_visualization": tool_save_visualization,
    "save_dashboard": tool_save_dashboard,
    "propose_measure": tool_propose_measure,
    "save_alert": tool_save_alert,
}


def _may_call(name, user, by_api_key):
    """
    Refuse a write tool the caller is not offered.

    Checked here as well as in the listing, because a client may call a tool
    it was never told about -- and the two write paths need different
    permissions: curating the catalog is not the same decision as saving a
    query.
    """
    if name in (UPDATE_TABLE["name"], PROPOSE_MEASURE["name"]) and not may_curate(user, by_api_key):
        raise McpError(
            INVALID_PARAMS,
            "{} writes to the catalog, so it needs a personal API key from somebody who may curate "
            "it. OAuth sessions are read-only (mcp:read).".format(name),
        )
    if name in (tool["name"] for tool in WRITE_QUERY_TOOLS) and not may_write_queries(user, by_api_key):
        raise McpError(
            INVALID_PARAMS,
            "{} saves a query, so it needs a personal API key from somebody who may create queries. "
            "OAuth sessions are read-only (mcp:read).".format(name),
        )
    if name in (tool["name"] for tool in WRITE_DASHBOARD_TOOLS) and not may_write_dashboards(user, by_api_key):
        raise McpError(
            INVALID_PARAMS,
            "{} makes a dashboard, so it needs a personal API key from somebody who may create "
            "dashboards. OAuth sessions are read-only (mcp:read).".format(name),
        )
    if name in (tool["name"] for tool in WRITE_ALERT_TOOLS) and not may_write_alerts(user, by_api_key):
        raise McpError(
            INVALID_PARAMS,
            "{} builds an alert, so it needs a personal API key from somebody who may use alerts. "
            "OAuth sessions are read-only (mcp:read).".format(name),
        )


def _offered_tools(user, by_api_key):
    """
    The tools this caller is shown.

    A tool is listed only to somebody who may call it, so an agent working for
    a reader never sees a way to write and never tries one. The permissions are
    separate because being allowed to do these things is separate: curating the
    catalog, saving queries and making dashboards are three decisions.
    """
    offered = list(TOOLS)
    if may_curate(user, by_api_key):
        offered.append(UPDATE_TABLE)
        offered.append(PROPOSE_MEASURE)
    if may_write_queries(user, by_api_key):
        offered.extend(WRITE_QUERY_TOOLS)
    if may_write_dashboards(user, by_api_key):
        offered.extend(WRITE_DASHBOARD_TOOLS)
    if may_write_alerts(user, by_api_key):
        offered.extend(WRITE_ALERT_TOOLS)
    return offered


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
        return {"tools": _offered_tools(user, by_api_key)}
    if method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise McpError(INVALID_PARAMS, "`params` must be an object.")
        name = params.get("name")
        if name not in HANDLERS:
            raise McpError(INVALID_PARAMS, "No tool called {!r}.".format(name))
        _may_call(name, user, by_api_key)
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

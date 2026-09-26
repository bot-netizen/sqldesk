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

import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar

import sqlglot
from sqlalchemy import or_
from sqlalchemy.orm import load_only
from sqlglot import exp

from sqldesk import __version__, models, settings
from sqldesk.ai.catalog.retrieve import context_for
from sqldesk.ai.optimizer import analyze, dialect_for
from sqldesk.permissions import has_access, not_view_only, view_only
from sqldesk.query_runner import BaseSQLQueryRunner

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
            "Search saved queries by name and description. Before writing SQL, look for the question "
            "already answered -- a saved query carries its author's understanding of the data, which "
            "no amount of schema does."
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
            "Search dashboards by name and the text on them. Often the answer is a page that already "
            "exists, and the useful reply is its address rather than a new query."
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


def _why_not_a_read(sql, source):
    """
    None when `sql` is one statement that only reads; otherwise why not.

    This is not the security boundary -- the database account's grants are,
    and an install that hands SQLDesk a writable account has decided
    something this cannot undo. What it stops is a model doing damage by
    accident: a DELETE it took for a SELECT, a second statement after a
    semicolon, an `EXPLAIN ANALYZE` that runs what it was asked only to plan.
    """
    runner = source.query_runner
    if not isinstance(runner, BaseSQLQueryRunner):
        # Mongo, Elasticsearch, a URL: runners that only read, in a language
        # that is not SQL. The exception is the one that runs a program.
        return "This data source runs Python, which a model may not." if source.type == "python" else None

    try:
        statements = [tree for tree in sqlglot.parse(sql, read=dialect_for(source.type)) if tree is not None]
    except Exception:
        statements = None

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

    if len(statements) != 1:
        return "One statement at a time."
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


def tool_find_context(user, org, arguments):
    question = (arguments or {}).get("question", "")
    if not question.strip():
        raise McpError(INVALID_PARAMS, "`question` is required.")
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
    for table in found["tables"]:
        lines.append(table["card"] or table["name"])
        lines.append("")
    return _text("\n".join(lines).strip())


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
    matches = [
        or_(models.Query.name.ilike("%{}%".format(term)), models.Query.description.ilike("%{}%".format(term)))
        for term in _terms(question)
    ]
    found = (
        models.Query.query.filter(
            models.Query.org == org,
            models.Query.is_archived.is_(False),
            models.Query.is_draft.is_(False),
            models.Query.data_source_id.in_(readable),
            *matches,
        )
        .order_by(models.Query.updated_at.desc())
        .limit(10)
        .all()
    )

    if not found:
        return _text("No saved query matches that. Nobody has written it down, or it is worded differently.")

    lines = []
    for query in found:
        lines.append("#{} {}".format(query.id, query.name))
        if query.description:
            lines.append("  {}".format(query.description.strip().replace("\n", " ")[:300]))
        lines.append(
            "  data source: {} · updated {}".format(
                query.data_source.name if query.data_source else "none",
                query.updated_at.date() if query.updated_at else "?",
            )
        )
        lines.append("")
    return _text("\n".join(lines).strip())


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

    # The words on a dashboard are in its textboxes and its widgets'
    # queries, which is where its subject is actually written down. Read in
    # one query for all of them, not three per widget.
    words = {dashboard.id: [dashboard.name] for dashboard in dashboards}
    widgets = {dashboard.id: 0 for dashboard in dashboards}
    if dashboards:
        for dashboard_id, text, query_name in (
            models.db.session.query(models.Widget.dashboard_id, models.Widget.text, models.Query.name)
            .outerjoin(models.Visualization, models.Widget.visualization_id == models.Visualization.id)
            .outerjoin(models.Query, models.Visualization.query_id == models.Query.id)
            .filter(models.Widget.dashboard_id.in_(list(words)))
        ):
            words[dashboard_id].append(query_name or text or "")
            widgets[dashboard_id] += 1

    found = [
        dashboard
        for dashboard in dashboards
        if not terms or _existing_work_matches(" ".join(words[dashboard.id]), terms)
    ][:8]

    if not found:
        return _text("No dashboard matches that.")

    lines = []
    for dashboard in found:
        lines.append("{} — /dashboards/{}".format(dashboard.name, dashboard.id))
        lines.append(
            "  {} widgets · updated {}".format(
                widgets[dashboard.id], dashboard.updated_at.date() if dashboard.updated_at else "?"
            )
        )
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
    source = _resolve_source(user, org, (arguments or {}).get("data_source"), need=not_view_only)
    if source is None:
        raise McpError(INVALID_PARAMS, "`data_source` is required: a plan is the engine's, not ours.")
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


def tool_run_query(user, org, arguments):
    sql = _sql_argument(arguments)
    source = _resolve_source(user, org, (arguments or {}).get("data_source"), need=not_view_only)
    if source is None:
        raise McpError(INVALID_PARAMS, "`data_source` is required.")
    refused = _why_not_a_read(sql, source)
    if refused:
        return {"content": [{"type": "text", "text": refused}], "isError": True}

    # The editor's own ceiling, applied by the runner that knows the dialect
    # -- `LIMIT` is not spelled the same everywhere, and a query that already
    # has one keeps it.
    limited = source.query_runner.apply_auto_limit(sql, True)

    result, error = _on_a_worker(user, source, limited, timeout=RUN_TIMEOUT)
    if error:
        return {"content": [{"type": "text", "text": error[0]}], "isError": True}
    return _text(_rows_as_text(result))


HANDLERS = {
    "find_context": tool_find_context,
    "find_queries": tool_find_queries,
    "find_dashboards": tool_find_dashboards,
    "explain_query": tool_explain_query,
    "run_query": tool_run_query,
    "expand_table": tool_expand_table,
    "list_data_sources": tool_list_data_sources,
    "check_sql": tool_check_sql,
}


def handle(message, user, org):
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
        return {"tools": TOOLS}
    if method == "tools/call":
        params = message.get("params") or {}
        if not isinstance(params, dict):
            raise McpError(INVALID_PARAMS, "`params` must be an object.")
        name = params.get("name")
        if name not in HANDLERS:
            raise McpError(INVALID_PARAMS, "No tool called {!r}.".format(name))
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

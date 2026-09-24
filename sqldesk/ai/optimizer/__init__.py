"""
The deterministic half of the optimize button.

No model. Parse the SQL with sqlglot and apply rules that are true from the
query's own shape -- which is why this ships before anything AI-shaped and why
it says the same thing every time you press it.

What is deliberately *not* here: anything needing to know how big a table is,
what its partition key is, or which columns are indexed. Those are the rules
that catch the expensive mistakes, and they need the catalog from phase 0. A
rule that guesses at cardinality would be wrong often enough to teach people
to ignore the whole panel.

Every finding names the thing it found and what to do instead. "Consider
optimizing your query" is not a finding.
"""

import logging

import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

#: Which sqlglot dialect to parse a data source's SQL as. A runner missing
#: from here is parsed as generic SQL, which is usually right and never worse
#: than refusing to look.
DIALECTS = {
    "athena": "athena",
    "big_query": "bigquery",
    "clickhouse": "clickhouse",
    "databricks": "databricks",
    "drill": "drill",
    "duckdb": "duckdb",
    "hive": "hive",
    "impala": "hive",
    "mssql": "tsql",
    "mysql": "mysql",
    "oracle": "oracle",
    "pg": "postgres",
    "presto": "presto",
    "redshift": "redshift",
    "snowflake": "snowflake",
    "spark": "spark",
    "sqlite": "sqlite",
    "trino": "trino",
    "vertica": "postgres",
}

#: Runners whose "SQL" is not SQL. Parsing a Mongo aggregation as SQL produces
#: nonsense findings, so the button says it does not apply rather than lying.
NOT_SQL = {
    "elasticsearch",
    "elasticsearch2",
    "mongodb",
    "google_spreadsheets",
    "json",
    "influxdb",
    "prometheus",
    "url",
}


class Finding:
    def __init__(self, rule, severity, title, detail, suggestion=None):
        self.rule = rule
        self.severity = severity
        self.title = title
        self.detail = detail
        self.suggestion = suggestion

    def to_dict(self):
        return {
            "rule": self.rule,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }


def dialect_for(data_source_type):
    return DIALECTS.get(data_source_type)


def _selects(tree):
    return list(tree.find_all(exp.Select))


def _from(select):
    """
    sqlglot 30 keys this `from_`; older versions key it `from`. Reading the
    wrong one returns None, which silently turns two rules off rather than
    failing -- both `no_predicate` and `cross_join` were doing nothing until a
    test asked them to.
    """
    return select.args.get("from_") or select.args.get("from")


def rule_select_star(tree):
    """
    `SELECT *` costs nothing on a row store and a great deal on a columnar one,
    which is what every warehouse in this project's target list is.
    """
    for select in _selects(tree):
        for projection in select.expressions:
            if isinstance(projection, exp.Star) or (
                isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)
            ):
                yield Finding(
                    "select_star",
                    WARNING,
                    "SELECT * reads every column",
                    "A columnar engine reads only the columns you name. `SELECT *` reads all of them, "
                    "including the wide ones nobody is looking at.",
                    "Name the columns you actually use.",
                )
                return


def rule_order_by_without_limit(tree):
    """
    A sort with no limit sorts the whole result on one node before returning
    any of it -- and a browser is going to show the first fifty rows.
    """
    for select in _selects(tree):
        if select.args.get("order") and not select.args.get("limit"):
            # A window function's ORDER BY is not this, and neither is an
            # ORDER BY inside a subquery feeding an aggregate.
            if select.parent_select is None:
                yield Finding(
                    "order_without_limit",
                    WARNING,
                    "ORDER BY with no LIMIT",
                    "Every row has to be sorted before the first one can be returned.",
                    "Add a LIMIT, or let the visualization do the sorting.",
                )
                return


def rule_no_predicate(tree):
    for select in _selects(tree):
        if select.parent_select is not None:
            continue
        if _from(select) and not select.args.get("where") and not select.args.get("limit"):
            yield Finding(
                "no_predicate",
                WARNING,
                "No WHERE clause and no LIMIT",
                "This reads the whole table. On a partitioned table it reads every partition.",
                "Filter on the partition column, or add a LIMIT while you are exploring.",
            )
            return


def rule_cross_join(tree):
    """
    Two tables in FROM with nothing joining them. The result is every row
    against every row, and the first anyone knows is a cluster falling over.
    """
    for select in _selects(tree):
        if not _from(select):
            continue
        joins = select.args.get("joins") or []
        unconditional = [j for j in joins if not j.args.get("on") and not j.args.get("using")]
        cross = [j for j in unconditional if (j.side, j.kind) in (("", ""), ("", "CROSS"))]
        if cross and not select.args.get("where"):
            yield Finding(
                "cross_join",
                CRITICAL,
                "Tables joined with no condition",
                "Nothing relates these tables, so every row is paired with every row. "
                "A million rows against a million rows is a trillion.",
                "Add a join condition, or say CROSS JOIN if you meant it.",
            )
            return


def rule_function_on_filtered_column(tree):
    """
    `WHERE date(ts) = '2026-01-01'` has to compute `date(ts)` for every row,
    so no index and no partition pruning applies. The rewrite is a range.
    """
    seen = set()
    for where in tree.find_all(exp.Where):
        for predicate in where.find_all(exp.EQ, exp.GT, exp.LT, exp.GTE, exp.LTE):
            left = predicate.this
            if isinstance(left, exp.Func) and left.find(exp.Column) is not None:
                name = left.sql_name() if hasattr(left, "sql_name") else type(left).__name__
                if name in seen:
                    continue
                seen.add(name)
                yield Finding(
                    "function_on_filtered_column",
                    WARNING,
                    "A function wraps a filtered column",
                    "`{}(...)` has to be computed for every row before the filter can be applied, "
                    "so no index or partition on that column is used.".format(name),
                    "Compare the bare column against a range instead.",
                )


def rule_leading_wildcard_like(tree):
    for like in tree.find_all(exp.Like, exp.ILike):
        pattern = like.expression
        if isinstance(pattern, exp.Literal) and pattern.is_string and pattern.this.startswith("%"):
            yield Finding(
                "leading_wildcard",
                INFO,
                "LIKE pattern starts with a wildcard",
                "A leading `%` means every row has to be examined; no index can help.",
                "Anchor the pattern, or use the engine's full-text search.",
            )
            return


def rule_union_not_union_all(tree):
    for union in tree.find_all(exp.Union):
        if union.args.get("distinct"):
            yield Finding(
                "union_distinct",
                INFO,
                "UNION removes duplicates",
                "UNION sorts both sides to deduplicate them. If the halves cannot overlap, "
                "that work is thrown away.",
                "UNION ALL, if duplicates are impossible or acceptable.",
            )
            return


RULES = (
    rule_cross_join,
    rule_no_predicate,
    rule_select_star,
    rule_order_by_without_limit,
    rule_function_on_filtered_column,
    rule_leading_wildcard_like,
    rule_union_not_union_all,
)

SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}


def analyze(sql, data_source_type=None):
    """
    Findings for one query, worst first.

    Returns a dict rather than raising: a query that will not parse is a thing
    the panel reports, not an error page. Half-written SQL is the normal state
    of the editor.
    """
    if data_source_type in NOT_SQL:
        return {
            "applicable": False,
            "reason": "This data source does not use SQL, so there is nothing to parse.",
            "findings": [],
        }

    sql = (sql or "").strip()
    if not sql:
        return {"applicable": False, "reason": "Nothing to look at yet.", "findings": []}

    dialect = dialect_for(data_source_type)
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except Exception as error:  # sqlglot raises several types for bad input
        return {
            "applicable": False,
            "reason": "Could not parse this as {} SQL: {}".format(dialect or "generic", error),
            "findings": [],
        }

    findings = []
    for tree in statements:
        if tree is None:
            continue
        for rule in RULES:
            try:
                findings.extend(rule(tree))
            except Exception:
                # One rule tripping over an unusual tree must not lose the
                # findings from the others.
                logger.exception("optimizer rule %s failed", rule.__name__)

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return {
        "applicable": True,
        "dialect": dialect or "generic",
        "reason": None,
        "findings": [f.to_dict() for f in findings],
    }

"""
What the queries people already wrote say about the warehouse.

The join graph, and which columns anyone actually looks at. A warehouse
rarely has foreign keys and nobody fills in a modelling tool, but every
dashboard in this instance is built on SQL somebody wrote and saved, and that
SQL says which tables go together and on what.

Read from `queries.query_text`, not from `events`. A scheduled refresh never
reaches `events` -- it goes through `refresh_queries` to `enqueue_query`,
never `run_query` -- so mining events would see ad-hoc runs only and quietly
under-weight everything on a schedule. Events are for who ran what and when;
the saved text is for structure.
"""

import logging
import re
from collections import Counter

import sqlglot
from sqlglot import exp

from sqldesk.ai.optimizer import NOT_SQL, dialect_for

logger = logging.getLogger(__name__)

#: Mustache, which is what a SQLDesk parameter is. `{{ region }}` is not SQL
#: and sqlglot refuses the whole statement over it -- and a parameterized
#: query is usually the interesting one, so skipping them is not an option.
PARAMETER = re.compile(r"\{\{[^}]*\}\}")

#: A bare token, deliberately unquoted. People write `'{{ region }}'` for a
#: string and `{{ limit }}` for a number, and one substitution has to work in
#: both: quoted it becomes a string literal, bare it becomes an identifier,
#: and both parse. Substituting `'__param__'` produces `''__param__''` inside
#: the quotes already there, which parses as nothing at all.
PARAMETER_TOKEN = "__sqldesk_param__"


def strip_parameters(sql):
    return PARAMETER.sub(PARAMETER_TOKEN, sql or "")


def _table_name(table):
    """`schema.orders` where a schema is written, `orders` where it is not."""
    parts = [p.name for p in (table.args.get("catalog"), table.args.get("db"), table.this) if p is not None]
    return ".".join(part for part in parts if part)


def _resolve(tree):
    """Alias to table name, so `a.user_id` can be read as `orders.user_id`."""
    aliases = {}
    for table in tree.find_all(exp.Table):
        name = _table_name(table)
        if not name:
            continue
        aliases[name] = name
        alias = table.alias
        if alias:
            aliases[alias] = name
    return aliases


def _column_pair(condition, aliases):
    """`a.user_id = b.id` as two (table, column) pairs, or None."""
    if not isinstance(condition, exp.EQ):
        return None
    left, right = condition.this, condition.expression
    if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
        return None

    def resolve(column):
        table = column.table
        return (aliases.get(table, table) if table else None, column.name)

    a, b = resolve(left), resolve(right)
    if not a[0] or not b[0] or a[0] == b[0]:
        return None
    # Ordered, so `a join b` and `b join a` are one edge rather than two.
    return tuple(sorted([a, b]))


def _count_tables(tree, tables):
    for table in tree.find_all(exp.Table):
        name = _table_name(table)
        if name:
            tables[name] += 1


def _count_columns(tree, aliases, columns):
    only_table = next(iter(set(aliases.values()))) if len(set(aliases.values())) == 1 else None
    for column in tree.find_all(exp.Column):
        # Where a parameter was unquoted its token now looks like a column.
        # Counting it would put a phantom in every table's most-used list.
        if column.name == PARAMETER_TOKEN or isinstance(column.this, exp.Star) or not column.name:
            continue
        table = column.table
        # A bare column with more than one table in scope is ambiguous, and
        # guessing which one it belongs to would put usage on the wrong table.
        resolved = aliases.get(table, table) if table else only_table
        if resolved:
            columns[(resolved, column.name)] += 1


def _count_joins(tree, aliases, joins):
    conditions = []
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is not None:
            conditions.extend([on] + list(on.find_all(exp.EQ)))
    # `WHERE a.id = b.id` is a join too, and older SQL writes them there.
    for where in tree.find_all(exp.Where):
        conditions.extend(where.find_all(exp.EQ))

    for condition in conditions:
        pair = _column_pair(condition, aliases)
        if pair:
            joins[pair] += 1


#: The aggregates worth proposing as a measure, mapped to what cube calls
#: them. Others exist -- `stddev`, `percentile_cont` -- but a measure nobody
#: recognises is worse than no measure, and these five are what a dashboard
#: is actually made of.
AGGREGATES = {
    "sum": "sum",
    "count": "count",
    "avg": "avg",
    "min": "min",
    "max": "max",
}


#: Wrappers to look through on the way to an aggregate. Real SQL almost never
#: writes `SUM(amount)` bare -- it writes `ROUND(SUM(amount))` or
#: `COALESCE(SUM(amount), 0)`, and treating those as "not an aggregate" found
#: one measure in a hundred and twenty queries that were full of them.
#:
#: Only presentation and null-handling belong here. Arithmetic does not:
#: `SUM(amount) * 1.2` is a different number from `SUM(amount)`, and
#: proposing the second as a definition of the first is exactly the confident
#: wrong answer a metric layer cannot afford.
UNWRAP = {"round", "coalesce", "cast", "trycast", "nullif"}


def _aggregate_in(expression):
    """
    The single aggregate inside a projection, or None.

    None when there is no aggregate, when there is more than one -- a ratio
    like `SUM(a) / SUM(b)` is its own metric and not either half of itself --
    or when reaching it means passing through something that changes the
    value.
    """
    found = [node for node in expression.walk() if type(node).__name__.lower() in AGGREGATES]
    if len(found) != 1:
        return None

    node = expression
    while True:
        name = type(node).__name__.lower()
        if name in AGGREGATES:
            return node
        if name not in UNWRAP or node.this is None:
            return None
        node = node.this


def _measure_name(projection, function_name, column_name):
    """
    What to call it.

    An alias is a name a person chose while writing the query, which beats
    anything derived: `SUM(amount) AS gross_revenue` is somebody telling us
    what the number is called. Failing that, compose one that at least says
    what it does.
    """
    alias = projection.alias if isinstance(projection, exp.Alias) else None
    if alias and alias != PARAMETER_TOKEN:
        return alias
    if column_name:
        return "{}_{}".format(function_name, column_name)
    return function_name


def _count_measures(tree, aliases, measures):
    """
    Aggregates in the select list, as proposed measures.

    Only where one table is in scope. `SUM(amount)` across a three-way join
    is a number about the join, not about a table, and filing it under
    whichever table happened to be first would be a definition nobody could
    trust -- which is the one thing a metric layer cannot afford.
    """
    scope = set(aliases.values())
    if len(scope) != 1:
        return
    table = next(iter(scope))

    select = tree.find(exp.Select)
    if select is None:
        return

    for projection in select.expressions:
        body = projection.this if isinstance(projection, exp.Alias) else projection
        function = _aggregate_in(body)
        if function is None:
            continue
        kind = AGGREGATES[type(function).__name__.lower()]

        inner = function.this
        if isinstance(inner, exp.Column):
            column_name = inner.name
        elif isinstance(inner, exp.Star) or inner is None:
            column_name = None
        else:
            # An expression rather than a column -- `SUM(price * qty)`. Real,
            # but it is a definition we cannot check against a column, so it
            # is left for a person to write rather than guessed at.
            continue
        if column_name == PARAMETER_TOKEN:
            continue

        measures[(table, _measure_name(projection, kind, column_name), kind, column_name or "*")] += 1


def mine(sql, data_source_type=None):
    """
    One query's contribution: the tables it names, the columns it touches, and
    the joins it makes.

    Returns counts rather than writing anything, so this is testable without a
    database and callable over thousands of queries before a single commit.
    """
    if data_source_type in NOT_SQL or not (sql or "").strip():
        return {"tables": Counter(), "columns": Counter(), "joins": Counter(), "measures": Counter()}

    try:
        statements = sqlglot.parse(strip_parameters(sql), read=dialect_for(data_source_type))
    except Exception as error:
        logger.debug("could not parse a saved query while mining: %s", error)
        return {"tables": Counter(), "columns": Counter(), "joins": Counter(), "measures": Counter()}

    tables, columns, joins, measures = Counter(), Counter(), Counter(), Counter()
    for tree in statements:
        if tree is None:
            continue
        aliases = _resolve(tree)
        _count_tables(tree, tables)
        _count_columns(tree, aliases, columns)
        _count_joins(tree, aliases, joins)
        _count_measures(tree, aliases, measures)

    return {"tables": tables, "columns": columns, "joins": joins, "measures": measures}


def mine_all(queries):
    """
    Fold many queries into one picture.

    Counts are per *query*, not per mention: a query joining on the same key
    in five subqueries is one team habit, not five, and counting mentions
    would let one baroque query outvote a department.
    """
    tables, columns, joins, measures = Counter(), Counter(), Counter(), Counter()
    for sql, data_source_type in queries:
        found = mine(sql, data_source_type)
        tables.update(set(found["tables"]))
        columns.update(set(found["columns"]))
        joins.update(set(found["joins"]))
        measures.update(set(found["measures"]))
    return {"tables": tables, "columns": columns, "joins": joins, "measures": measures}

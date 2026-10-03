"""
Per-minute buckets, so "how does now compare to this morning" has an answer.

The raw window is minutes long. A question about a day needs something smaller
than a day of raw events, and the smaller thing is a count per minute per
group: 1,440 rows a day per group, which is small enough to live in Postgres
and survive a restart. The raw window lives in DuckDB and does not survive
much; the rollup is the part anybody keeps.

**The aggregation was never the cost.** A `GROUP BY` over 200,000 rows took
seven milliseconds in DuckDB, and the top 1,000 of 5,000 distinct keys took
four. What costs is parsing, which is why the ingest path does none in Python
and why this runs once a minute rather than per event.

**Cardinality is the thing that kills a rollup.** Grouped by `user_id` on a
ten-million-user stream it is not a rollup, it is the stream again with extra
steps. So a stream declares which columns it groups by, the number of distinct
groups is capped, and everything past the cap lands in one `other` bucket that
the chart shows rather than hides -- because a chart that silently dropped the
long tail would make a total wrong and look right.

**Distinct counts are approximate unless somebody asks otherwise.**
`approx_count_distinct` is a HyperLogLog and costs almost nothing; an exact
distinct over a minute of a busy topic can cost more than everything else here
together. A dashboard counting unique visitors per minute does not need exact,
and the one rollup that does can say so.
"""

#: Distinct groups kept per minute. Past this, into `other`. A thousand is
#: already more lines than any chart can draw; the number exists to bound the
#: table, not to be reached.
MAX_GROUPS = 1000

#: What the overflow bucket is called. Shown on the chart, never hidden: a
#: total missing its long tail is wrong while looking right.
OTHER = "other"

#: The aggregates a measure may ask for. Deliberately short -- each one has to
#: mean the same thing to everybody reading the chart, and `approx_quantile`
#: with a parameter is a 0.8 problem.
AGGREGATES = {
    "count": "count(*)",
    "sum": "sum(CAST({column} AS DOUBLE))",
    "min": "min(CAST({column} AS DOUBLE))",
    "max": "max(CAST({column} AS DOUBLE))",
    "avg": "avg(CAST({column} AS DOUBLE))",
    # HyperLogLog. See the module docstring on why this is the default.
    "approx_distinct": "approx_count_distinct({column})",
    "distinct": "count(DISTINCT {column})",
}


class RollupError(Exception):
    """A rollup definition that cannot be run, said in words."""


def check(group_by, measures, columns):
    """
    Why this rollup cannot be run, or None.

    Checked before any SQL is built, because every one of these would otherwise
    be a DuckDB error in a worker's log rather than a sentence on the stream's
    page -- and the person who can fix it is looking at the page.
    """
    known = {name for name, _kind in columns}
    for column in group_by:
        if column not in known:
            return "There is no column called {!r} on this stream.".format(column)
    if not measures:
        return "A rollup needs at least one measure."
    for measure in measures:
        name = measure.get("name")
        kind = measure.get("kind")
        column = measure.get("column")
        if not name:
            return "Every measure needs a name."
        if kind not in AGGREGATES:
            return "{!r} is not an aggregate SQLDesk knows. Use one of: {}.".format(
                kind, ", ".join(sorted(AGGREGATES))
            )
        if kind != "count":
            if not column:
                return "{} needs a column to aggregate.".format(name)
            if column not in known:
                return "There is no column called {!r} on this stream.".format(column)
    return None


def _aggregate(measure):
    template = AGGREGATES[measure["kind"]]
    return template.format(column='"{}"'.format(measure["column"])) if "{column}" in template else template


def minute_sql(group_by, measures, received_column, since_expression, until_expression=None):
    """
    The query that produces one minute's buckets.

    **Two passes, not one.** The first counts every group so the busiest can be
    found; the second rolls everything outside the top `MAX_GROUPS` into
    `other`. One pass with a `LIMIT` would silently drop the tail, which is the
    exact failure the cap exists to avoid -- the chart would add up to less than
    the stream and give no sign of it.

    `is_other` is a column of its own rather than a value anybody has to spot.
    A group whose value is literally `other` merges with the overflow bucket
    and is flagged as other, which is the safer direction to be wrong in: the
    chart says "this one includes a tail" rather than quietly presenting a tail
    as a group.

    Built as text because a stream's columns are its own and are not known
    until it has been harvested. They are quoted, and `check` has confirmed
    every one against the store's own schema -- nothing here comes from a
    request.
    """
    aggregates = ", ".join('{} AS "{}"'.format(_aggregate(measure), measure["name"]) for measure in measures)
    minute = "date_trunc('minute', {})".format(received_column)

    # An upper bound, when the caller wants exactly one minute. The cap on
    # groups is computed over whatever this window holds, so a query spanning
    # ten minutes would pick the busiest groups *of those ten* and sweep a
    # group that was busy in only one of them into `other`. Bounding the query
    # keeps the cap meaning what it says: the busiest groups of that minute.
    window = "{received} >= {since}".format(received=received_column, since=since_expression)
    if until_expression is not None:
        window += " AND {received} < {until}".format(received=received_column, until=until_expression)

    if not group_by:
        # No grouping: one row a minute, and no tail to cap.
        return (
            "SELECT {minute} AS minute, {aggregates}, false AS is_other "
            "FROM events WHERE {window} "
            "GROUP BY 1 ORDER BY 1"
        ).format(minute=minute, aggregates=aggregates, window=window)

    quoted = ['"{}"'.format(column) for column in group_by]
    keys = ", ".join(quoted)
    # `IS NOT DISTINCT FROM` rather than `=` or `USING`: a group value may be
    # null, and under `=` null never matches itself, so every null-keyed row
    # would be swept into `other` whatever its volume.
    joined = " AND ".join(
        "top.{column} IS NOT DISTINCT FROM windowed.{column}".format(column=column) for column in quoted
    )
    # A marker column, not the nullness of a key. `top."region" IS NULL` reads
    # as "no match" and is true for a *matched* row whose key is null, so a
    # legitimately null group was labelled `other` however busy it was -- which
    # for a field a producer sometimes omits is most of the stream.
    flag = "top.matched IS NULL"
    labels = ", ".join(
        "CASE WHEN {flag} THEN '{other}' ELSE CAST(windowed.{column} AS VARCHAR) END AS {column}".format(
            flag=flag, other=OTHER, column=column
        )
        for column in quoted
    )

    return (
        "WITH windowed AS ("
        " SELECT {minute} AS minute, * EXCLUDE ({received}) FROM events WHERE {window}"
        "), top AS ("
        " SELECT {keys}, true AS matched FROM windowed GROUP BY {keys}"
        " ORDER BY count(*) DESC LIMIT {cap}"
        "), labelled AS ("
        " SELECT windowed.minute, {labels}, {flag} AS is_other,"
        " windowed.* EXCLUDE (minute, {keys})"
        " FROM windowed LEFT JOIN top ON {joined}"
        ") "
        "SELECT minute, {keys}, {aggregates}, bool_or(is_other) AS is_other "
        "FROM labelled GROUP BY minute, {keys} ORDER BY minute, {keys}"
    ).format(
        minute=minute,
        received=received_column,
        window=window,
        keys=keys,
        cap=MAX_GROUPS,
        labels=labels,
        flag=flag,
        joined=joined,
        aggregates=aggregates,
    )

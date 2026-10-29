"""
What a query will cost, before a model runs it.

A model exploring a warehouse writes queries nobody reviewed. Most are cheap;
the expensive ones are expensive in a way that shows up on a bill or on
somebody else's dashboard, and by the time either happens the model has moved
on. So `run_query` can be given a ceiling, and the estimate it is checked
against is **the engine's own** -- not a guess from the SQL.

That restriction is the whole design. A cost model of our own would be a second
opinion about a question the engine answers authoritatively, wrong in ways
nobody could predict, and it would have to be written again for every one of
thirty-five connectors. Here there are two estimates and they are both free:

- **Postgres and its family** give a plan cost from `EXPLAIN (FORMAT JSON)`.
  The number is in arbitrary units -- "cost of a sequential page fetch" is 1.0
  -- so a ceiling is a figure somebody arrives at by looking at their own
  queries, not one we can default usefully. Comparable across queries on one
  database, which is all it needs to be.
- **BigQuery** gives bytes from a dry run, which is exactly what it bills for.

Every other engine is unaffected: no estimate means no refusal. That is
deliberate rather than a gap -- refusing on a number we had to invent would be
worse than not refusing.
"""

import json
import logging

from sqldesk import settings

logger = logging.getLogger(__name__)

#: Engines whose `EXPLAIN (FORMAT JSON)` gives a plan cost. All of them are
#: Postgres or speak its protocol closely enough.
PLAN_COST_TYPES = {"pg", "redshift", "cockroach", "risingwave", "timescaledb", "greenplum"}

#: BigQuery prices by bytes scanned, and a dry run reports them exactly.
BYTES_TYPES = {"bigquery"}


class Estimate:
    """
    What the engine said, and whether it is over the ceiling.

    Carries the unit as well as the number, because "4.2 million" means
    nothing on its own and the two units here are not comparable.
    """

    def __init__(self, amount, unit, ceiling):
        self.amount = amount
        self.unit = unit
        self.ceiling = ceiling

    @property
    def over(self):
        return self.ceiling > 0 and self.amount > self.ceiling

    def refusal(self):
        """
        Why this query was not run, in words a model can act on.

        It says the figure and the ceiling, so the next thing the model writes
        can be narrower rather than another guess -- and it says which unit,
        because a model told "too expensive" has nothing to aim at.
        """
        return (
            "Not run: the engine estimates {} and the limit for AI clients is {}. "
            "Narrow it -- fewer columns, a shorter period, or an aggregate instead of rows -- "
            "and ask again. `explain_query` shows the plan.".format(self.described, self.described_ceiling)
        )

    @property
    def described(self):
        return _describe(self.amount, self.unit)

    @property
    def described_ceiling(self):
        return _describe(self.ceiling, self.unit)


def _describe(amount, unit):
    if unit == "bytes":
        return _bytes(amount)
    return "a plan cost of {:,.0f}".format(amount)


def _bytes(count):
    for suffix, size in (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2)):
        if count >= size:
            return "{:.1f} {} scanned".format(count / size, suffix)
    return "{:,.0f} bytes scanned".format(count)


def ceiling_for(source):
    """The ceiling in this engine's own unit, or 0 for no ceiling."""
    if source.type in PLAN_COST_TYPES:
        return settings.MCP_MAX_QUERY_COST
    if source.type in BYTES_TYPES:
        return settings.MCP_MAX_QUERY_BYTES
    return 0


def estimate(source, sql, run):
    """
    Ask the engine what this will cost. Returns an `Estimate` or None.

    `run` is how to run SQL -- passed in rather than reached for, because the
    caller is the one that knows to do it on a worker rather than in the web
    process.

    None means "no answer", and no answer must never be a refusal. An engine
    that has no estimate, a ceiling nobody set, an EXPLAIN that failed because
    the SQL is wrong: all three end here, and in all three the right next step
    is to let the query run and fail on its own terms rather than to refuse it
    with a reason that is not true.
    """
    ceiling = ceiling_for(source)
    if ceiling <= 0:
        return None

    if source.type in PLAN_COST_TYPES:
        amount = _plan_cost(source, sql, run)
        return Estimate(amount, "cost", ceiling) if amount is not None else None
    if source.type in BYTES_TYPES:
        amount = _dry_run_bytes(source, sql)
        return Estimate(amount, "bytes", ceiling) if amount is not None else None
    return None


def _plan_cost(source, sql, run):
    """
    The plan's total cost, from `EXPLAIN (FORMAT JSON)`.

    JSON rather than parsing the text plan, which varies by version and by
    locale. The caller has already established the SQL is a read -- `EXPLAIN`
    in front of a statement that is not would execute it.
    """
    result, error = run("EXPLAIN (FORMAT JSON) {}".format(sql))
    if error or not result:
        logger.debug("no plan cost for %s: %s", source.name, error)
        return None
    try:
        # `run` hands back a QueryResult row, not the dict this once expected:
        # `.get` on it raised AttributeError, the caller logged "could not
        # estimate", and every query went through uncapped.
        data = getattr(result, "data", result)
        if isinstance(data, str):
            data = json.loads(data)
        rows = (data or {}).get("rows") or []
        if not rows:
            # An EXPLAIN that came back with no plan at all. Said quietly and
            # on purpose: it is an answer we cannot use, not a fault of ours,
            # and a traceback behind every one of them would send somebody
            # looking for a bug in this file.
            logger.debug("an empty plan from %s", source.name)
            return None
        plan = list(rows[0].values())[0]
        if isinstance(plan, str):
            plan = json.loads(plan)
        if isinstance(plan, list):
            plan = plan[0]
        return float(plan["Plan"]["Total Cost"])
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        # A plan we cannot read is not a plan we should refuse on.
        logger.warning("could not read a plan cost from %s", source.name, exc_info=True)
        return None


def _dry_run_bytes(source, sql):
    """
    Bytes BigQuery says it would scan, from a dry run.

    Through the runner's own client, because a dry run is not a query: it
    returns no rows, costs nothing, and is the number BigQuery bills on.
    """
    runner = source.query_runner
    asker = getattr(runner, "dry_run_bytes", None)
    if asker is None:
        # An older runner, or one that has not been taught. Not a refusal.
        logger.debug("%s has no dry run", source.type)
        return None
    try:
        return asker(sql)
    except Exception:
        logger.warning("a BigQuery dry run failed for %s", source.name, exc_info=True)
        return None

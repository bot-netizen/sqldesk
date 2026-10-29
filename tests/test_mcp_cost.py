"""
A ceiling on what a model's query may cost.

The estimate is always **the engine's own**. A cost model of ours would be a
second opinion about a question the engine answers authoritatively, wrong in
ways nobody could predict, and it would need writing again for each of
thirty-five connectors. So: a plan cost from Postgres, bytes from a BigQuery
dry run, and silence everywhere else.

The rule these tests exist to hold is **no answer is never a refusal**. An
engine with no estimate, a ceiling nobody set, an EXPLAIN that failed: all of
them let the query run. Refusing on a number we had to invent would be worse
than running an expensive query.
"""

from unittest import mock

from sqldesk.mcp import cost
from tests import BaseTestCase


def plan(total_cost):
    """What `EXPLAIN (FORMAT JSON)` hands back, as a runner returns it."""
    return {"rows": [{"QUERY PLAN": [{"Plan": {"Total Cost": total_cost}}]}]}, None


class CostTestCase(BaseTestCase):
    def source(self, kind="pg"):
        return self.factory.create_data_source(name="Warehouse", type=kind)


class TestWhichEnginesHaveACeiling(CostTestCase):
    def test_postgres_uses_the_plan_cost_setting(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            self.assertEqual(1000, cost.ceiling_for(self.source("pg")))

    def test_bigquery_uses_the_bytes_setting(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 5_000_000):
            self.assertEqual(5_000_000, cost.ceiling_for(self.source("bigquery")))

    def test_anything_else_has_none(self):
        # Deliberately, not as a gap: there is no estimate to check against.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            self.assertEqual(0, cost.ceiling_for(self.source("mysql")))

    def test_redshift_counts_as_postgres(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            self.assertEqual(1000, cost.ceiling_for(self.source("redshift")))


class TestAPlanCost(CostTestCase):
    def estimate(self, total_cost, ceiling=1000, kind="pg"):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", ceiling):
            return cost.estimate(self.source(kind), "select 1", lambda sql: plan(total_cost))

    def test_under_the_ceiling_is_not_over_it(self):
        found = self.estimate(500)

        self.assertIsNotNone(found)
        self.assertFalse(found.over)

    def test_over_it_is(self):
        self.assertTrue(self.estimate(5000).over)

    def test_exactly_at_it_is_not(self):
        # A ceiling is a limit, not a threshold to be inside of.
        self.assertFalse(self.estimate(1000).over)

    def test_with_no_ceiling_nothing_is_estimated_at_all(self):
        # Not "estimated and allowed": the EXPLAIN is not even run, because
        # running one per query to compare against nothing is a round trip for
        # nobody.
        asked = []

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 0):
            found = cost.estimate(self.source(), "select 1", lambda sql: asked.append(sql) or plan(5000))

        self.assertIsNone(found)
        self.assertEqual([], asked)

    def test_the_explain_asks_for_json(self):
        # Rather than parsing the text plan, which varies by version and by
        # locale.
        asked = []

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            cost.estimate(self.source(), "select 1", lambda sql: asked.append(sql) or plan(1))

        self.assertIn("FORMAT JSON", asked[0])
        self.assertIn("select 1", asked[0])

    def test_a_plan_that_came_back_as_text_is_still_read(self):
        # Some drivers hand the JSON back as a string rather than parsed.
        import json

        text = json.dumps([{"Plan": {"Total Cost": 4000}}])

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            found = cost.estimate(self.source(), "select 1", lambda sql: ({"rows": [{"QUERY PLAN": text}]}, None))

        self.assertTrue(found.over)

    def test_an_explain_that_failed_is_not_a_refusal(self):
        # Usually the engine saying the SQL is wrong. Letting it run means it
        # fails on its own terms, with the engine's own message.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            found = cost.estimate(self.source(), "select 1", lambda sql: (None, ["syntax error"]))

        self.assertIsNone(found)

    def test_an_error_beside_a_readable_plan_is_still_not_a_refusal(self):
        # The error is what counts, not whether rows came back with it. A
        # runner that reports both -- a connection that dropped partway, a
        # statement timeout with a partial plan -- has given us a number we
        # have no reason to trust, and refusing on it would refuse on a plan
        # for a query that never finished being planned.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            found = cost.estimate(
                self.source(),
                "select 1",
                lambda sql: (plan(5000)[0], ["connection reset by peer"]),
            )

        self.assertIsNone(found)

    def test_nor_is_a_plan_we_cannot_read(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            found = cost.estimate(
                self.source(), "select 1", lambda sql: ({"rows": [{"QUERY PLAN": "not a plan"}]}, None)
            )

        self.assertIsNone(found)

    def test_nor_an_empty_result(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            self.assertIsNone(cost.estimate(self.source(), "select 1", lambda sql: ({"rows": []}, None)))

    def test_and_an_empty_plan_is_not_complained_about_either(self):
        # Same shape as the dry run below: without the guard the answer would
        # be the same -- an IndexError the broad `except` catches -- so what is
        # at stake is a warning with a traceback for an engine answer we simply
        # cannot use.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with self.assertNoLogs("sqldesk.mcp.cost", level="WARNING"):
                cost.estimate(self.source(), "select 1", lambda sql: ({"rows": []}, None))


class TestBigQueryBytes(CostTestCase):
    def with_runner(self, source, runner):
        """Hand `cost.estimate` a runner of our choosing."""
        return mock.patch.object(type(source), "query_runner", new_callable=mock.PropertyMock, return_value=runner)

    def test_the_dry_run_is_asked_for(self):
        source = self.source("bigquery")
        asked = []
        runner = mock.Mock()
        runner.dry_run_bytes = lambda sql: asked.append(sql) or 5_000_000

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, runner):
                found = cost.estimate(source, "select 1", lambda sql: plan(1))

        self.assertEqual(["select 1"], asked)
        self.assertTrue(found.over)

    def test_under_the_ceiling_it_is_not_over(self):
        source = self.source("bigquery")
        runner = mock.Mock()
        runner.dry_run_bytes = lambda sql: 500

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, runner):
                found = cost.estimate(source, "select 1", lambda sql: plan(1))

        self.assertFalse(found.over)

    def test_a_runner_with_no_dry_run_is_not_a_refusal(self):
        # An older runner, or one that has not been taught. `spec=[]` is a
        # object with no attributes at all, which is what that looks like.
        source = self.source("bigquery")

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, mock.Mock(spec=[])):
                found = cost.estimate(source, "select 1", lambda sql: plan(1))

        self.assertIsNone(found)

    def test_and_it_does_not_complain_about_it(self):
        # The answer is the same either way -- without the guard the call would
        # raise TypeError and the broad `except` below would catch it and
        # return None -- so what is actually at stake is the log, and the log
        # is worth a test of its own. A runner with no dry run is the normal
        # state of thirty-four of the thirty-five connectors; a warning with a
        # traceback behind every query from one of them is an operator chasing
        # a fault that is not there. It is said at debug, not warning.
        source = self.source("bigquery")

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, mock.Mock(spec=[])):
                with self.assertNoLogs("sqldesk.mcp.cost", level="WARNING"):
                    cost.estimate(source, "select 1", lambda sql: plan(1))

    def test_whereas_a_dry_run_that_broke_is_worth_a_warning(self):
        # The other side of the test above: this one is a fault, and silence
        # about it would mean a BigQuery ceiling that quietly stopped being
        # enforced.
        source = self.source("bigquery")
        runner = mock.Mock()
        runner.dry_run_bytes = mock.Mock(side_effect=RuntimeError("bigquery said no"))

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, runner):
                with self.assertLogs("sqldesk.mcp.cost", level="WARNING") as logs:
                    cost.estimate(source, "select 1", lambda sql: plan(1))

        self.assertIn("dry run failed", logs.output[0])

    def test_nor_is_a_dry_run_that_raised(self):
        source = self.source("bigquery")
        runner = mock.Mock()
        runner.dry_run_bytes = mock.Mock(side_effect=RuntimeError("bigquery said no"))

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, runner):
                found = cost.estimate(source, "select 1", lambda sql: plan(1))

        self.assertIsNone(found)

    def test_a_plan_cost_is_never_used_for_bigquery(self):
        # The units are not comparable, and BigQuery's EXPLAIN is not a plan
        # cost at all. Handing one over would refuse on a number from the
        # wrong engine.
        source = self.source("bigquery")
        runner = mock.Mock()
        runner.dry_run_bytes = lambda sql: 10

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_BYTES", 1_000_000):
            with self.with_runner(source, runner):
                found = cost.estimate(source, "select 1", lambda sql: plan(999_999_999))

        self.assertEqual("bytes", found.unit)
        self.assertFalse(found.over)


class TestTheEstimateItself(CostTestCase):
    """
    `Estimate.over` on its own, rather than through `estimate()`.

    One of its two halves cannot be reached from `estimate()`, which returns
    None before building anything when there is no ceiling. It is kept because
    `Estimate` is the public type here and `over` is the question it answers:
    zero means "no ceiling" in `ceiling_for`, and it has to mean the same thing
    to anything holding one of these.
    """

    def test_a_ceiling_of_zero_is_no_ceiling_rather_than_a_ceiling_of_nothing(self):
        self.assertFalse(cost.Estimate(5, "cost", 0).over)

    def test_a_ceiling_that_was_set_is_one(self):
        self.assertTrue(cost.Estimate(5, "cost", 4).over)

    def test_and_the_unit_is_carried_with_the_number(self):
        # "4.2 million" means nothing on its own and the two units are not
        # comparable, so the number never travels without it.
        self.assertEqual("bytes", cost.Estimate(5, "bytes", 4).unit)


class TestWhatTheRefusalSays(CostTestCase):
    def refusal(self, amount, unit, ceiling):
        return cost.Estimate(amount, unit, ceiling).refusal()

    def test_it_names_the_figure_and_the_limit(self):
        # A model told only "too expensive" has nothing to aim at.
        said = self.refusal(5000, "cost", 1000)

        self.assertIn("5,000", said)
        self.assertIn("1,000", said)

    def test_and_what_to_do_instead(self):
        said = self.refusal(5000, "cost", 1000)

        self.assertIn("Narrow it", said)
        self.assertIn("explain_query", said)

    def test_bytes_are_said_as_bytes(self):
        # "4.2 million" means nothing on its own, and the two units here are
        # not comparable.
        said = self.refusal(5 * 1024**3, "bytes", 1024**3)

        self.assertIn("5.0 GB scanned", said)
        self.assertIn("1.0 GB scanned", said)

    def test_small_byte_counts_are_not_abbreviated_into_nonsense(self):
        self.assertIn("500 bytes scanned", self.refusal(500, "bytes", 100))


class TestWhatTheWorkerReallyHandsBack(CostTestCase):
    """
    `run` is `_on_a_worker`, which returns the QueryResult row the worker
    stored -- not the dict the fakes above return. Until 0.7.7 `_plan_cost`
    called `.get` on that row, the AttributeError was logged as "could not
    estimate", and every query on Postgres or Redshift ran however dear it was.
    """

    def stored(self, source, total_cost):
        return self.factory.create_query_result(data_source=source, data=plan(total_cost)[0])

    def test_an_expensive_plan_from_a_stored_result_is_over(self):
        source = self.source("pg")
        stored = self.stored(source, 5000)

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            estimate = cost.estimate(source, "SELECT * FROM big", lambda statement: (stored, None))

        self.assertIsNotNone(estimate)
        self.assertTrue(estimate.over)

    def test_and_a_cheap_one_is_not(self):
        source = self.source("pg")
        stored = self.stored(source, 10)

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            estimate = cost.estimate(source, "SELECT 1", lambda statement: (stored, None))

        self.assertFalse(estimate.over)

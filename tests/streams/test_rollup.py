"""
Per-minute buckets, and the cap that keeps them from being the stream again.

Run against a real DuckDB store rather than by inspecting SQL strings: the
whole point of these queries is what they produce, and a test that asserted on
their text would pass while returning wrong numbers.
"""

import json
import os
import shutil
import tempfile
from unittest import TestCase

from sqldesk.streams import rollup
from sqldesk.streams.store import RECEIVED, Store


def events(*payloads):
    return [json.dumps(payload).encode("utf-8") for payload in payloads]


class RollupTestCase(TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.store = Store(os.path.join(self.folder, "s.duckdb"))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def run_rollup(self, group_by, measures, since="now() - INTERVAL '1 hour'", until=None):
        sql = rollup.minute_sql(group_by, measures, RECEIVED, since, until)
        described = [row[0] for row in self.store.connection.execute("DESCRIBE {}".format(sql)).fetchall()]
        rows = self.store.connection.execute(sql).fetchall()
        return [dict(zip(described, row)) for row in rows]


class TestCheckingADefinition(RollupTestCase):
    def columns(self):
        return self.store.columns()

    def setUp(self):
        super().setUp()
        self.store.append(events({"region": "eu", "amount": 10, "user": "a"}))

    def test_a_good_one_passes(self):
        self.assertIsNone(
            rollup.check(["region"], [{"name": "total", "kind": "sum", "column": "amount"}], self.columns())
        )

    def test_a_column_the_stream_does_not_have(self):
        # Caught here rather than becoming a DuckDB error in a worker's log:
        # the person who can fix it is looking at the stream's page.
        problem = rollup.check(["nope"], [{"name": "n", "kind": "count"}], self.columns())

        self.assertIn("nope", problem)

    def test_a_measure_on_a_column_the_stream_does_not_have(self):
        problem = rollup.check(["region"], [{"name": "total", "kind": "sum", "column": "nope"}], self.columns())

        self.assertIn("nope", problem)

    def test_an_aggregate_nobody_has_heard_of(self):
        problem = rollup.check(["region"], [{"name": "x", "kind": "median"}], self.columns())

        self.assertIn("median", problem)
        # And what the alternatives are, rather than leaving somebody guessing.
        self.assertIn("sum", problem)

    def test_a_measure_with_no_name(self):
        problem = rollup.check(["region"], [{"kind": "count"}], self.columns())

        self.assertIn("name", problem)

    def test_an_aggregate_that_needs_a_column_and_has_none(self):
        problem = rollup.check(["region"], [{"name": "total", "kind": "sum"}], self.columns())

        # Naming the measure, not reporting a column called None. Asserting
        # only on the word "column" passed either way.
        self.assertEqual("total needs a column to aggregate.", problem)

    def test_count_needs_no_column(self):
        self.assertIsNone(rollup.check(["region"], [{"name": "n", "kind": "count"}], self.columns()))

    def test_a_rollup_with_no_measures_at_all(self):
        problem = rollup.check(["region"], [], self.columns())

        self.assertIn("at least one measure", problem)


class TestWhatItProduces(RollupTestCase):
    def test_a_count_per_minute_per_group(self):
        self.store.append(
            events(
                {"region": "eu", "amount": 10},
                {"region": "eu", "amount": 5},
                {"region": "us", "amount": 7},
            )
        )

        rows = self.run_rollup(["region"], [{"name": "n", "kind": "count"}])

        counts = {row["region"]: row["n"] for row in rows}
        self.assertEqual({"eu": 2, "us": 1}, counts)

    def test_a_sum(self):
        self.store.append(events({"region": "eu", "amount": 10}, {"region": "eu", "amount": 5}))

        rows = self.run_rollup(["region"], [{"name": "total", "kind": "sum", "column": "amount"}])

        self.assertEqual(15.0, rows[0]["total"])

    def test_several_measures_at_once(self):
        self.store.append(events({"region": "eu", "amount": 10}, {"region": "eu", "amount": 5}))

        rows = self.run_rollup(
            ["region"],
            [
                {"name": "n", "kind": "count"},
                {"name": "total", "kind": "sum", "column": "amount"},
                {"name": "biggest", "kind": "max", "column": "amount"},
            ],
        )

        self.assertEqual(2, rows[0]["n"])
        self.assertEqual(15.0, rows[0]["total"])
        self.assertEqual(10.0, rows[0]["biggest"])

    def test_an_approximate_distinct(self):
        # HyperLogLog, and the default for a reason: an exact distinct over a
        # minute of a busy topic can cost more than everything else together.
        self.store.append(events(*[{"region": "eu", "user": "u{}".format(n % 7)} for n in range(50)]))

        rows = self.run_rollup(["region"], [{"name": "people", "kind": "approx_distinct", "column": "user"}])

        self.assertEqual(7, rows[0]["people"])

    def test_and_it_really_is_the_approximate_one(self):
        # The only test here that reads the SQL, because it has to: on any data
        # small enough to test, approximate and exact return the same number.
        # The difference is cost, and cost is not visible in a result.
        sql = rollup.minute_sql(
            ["region"], [{"name": "people", "kind": "approx_distinct", "column": "user"}], RECEIVED, "now()"
        )

        self.assertIn("approx_count_distinct", sql)
        self.assertNotIn("count(DISTINCT", sql)

    def test_and_an_exact_one_when_somebody_asks(self):
        self.store.append(events(*[{"region": "eu", "user": "u{}".format(n % 7)} for n in range(50)]))

        rows = self.run_rollup(["region"], [{"name": "people", "kind": "distinct", "column": "user"}])

        self.assertEqual(7, rows[0]["people"])

    def test_no_grouping_gives_one_row_a_minute(self):
        self.store.append(events({"amount": 1}, {"amount": 2}))

        rows = self.run_rollup([], [{"name": "n", "kind": "count"}])

        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["n"])
        self.assertFalse(rows[0]["is_other"])

    def test_two_group_columns(self):
        self.store.append(
            events(
                {"region": "eu", "kind": "web", "amount": 1},
                {"region": "eu", "kind": "app", "amount": 1},
                {"region": "us", "kind": "web", "amount": 1},
            )
        )

        rows = self.run_rollup(["region", "kind"], [{"name": "n", "kind": "count"}])

        self.assertEqual(3, len(rows))

    def test_events_outside_the_period_are_not_counted(self):
        self.store.append(events({"region": "eu"}))
        self.store.connection.execute("UPDATE events SET {} = {} - INTERVAL '2 hours'".format(RECEIVED, RECEIVED))
        self.store.append(events({"region": "eu"}))

        rows = self.run_rollup(["region"], [{"name": "n", "kind": "count"}])

        # The row count, not the first row's figure: the old event is in a
        # different minute, so its own count is 1 either way and an earlier
        # version of this passed with the period filter deleted.
        self.assertEqual(1, len(rows))
        self.assertEqual(1, sum(row["n"] for row in rows))

    def test_events_in_the_same_minute_land_in_one_bucket(self):
        # Two flushes a moment apart have different `now()` values, so without
        # `date_trunc` they group separately and "per minute" means "per
        # flush". Every other test here uses one flush and could not tell.
        self.store.append(events({"region": "eu"}))
        self.store.append(events({"region": "eu"}))
        self.store.append(events({"region": "eu"}))

        rows = self.run_rollup(["region"], [{"name": "n", "kind": "count"}])

        self.assertEqual(1, len(rows))
        self.assertEqual(3, rows[0]["n"])

    def test_and_so_do_ungrouped_ones(self):
        self.store.append(events({"amount": 1}))
        self.store.append(events({"amount": 2}))

        rows = self.run_rollup([], [{"name": "n", "kind": "count"}])

        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["n"])

    def test_the_ungrouped_query_respects_the_period_too(self):
        # It is a separate branch with its own WHERE, and the grouped test
        # could not reach it.
        self.store.append(events({"amount": 1}))
        self.store.connection.execute("UPDATE events SET {} = {} - INTERVAL '2 hours'".format(RECEIVED, RECEIVED))
        self.store.append(events({"amount": 2}))

        rows = self.run_rollup([], [{"name": "n", "kind": "count"}])

        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["n"])

    def test_a_null_group_value_is_its_own_group_not_the_tail(self):
        # Under `=` or `USING`, null never matches itself, so every null-keyed
        # row would be swept into `other` whatever its volume -- which for a
        # field a producer sometimes omits is most of the stream.
        self.store.append(
            events(
                {"region": "eu", "amount": 1},
                {"region": None, "amount": 1},
                {"region": None, "amount": 1},
            )
        )

        rows = self.run_rollup(["region"], [{"name": "n", "kind": "count"}])

        self.assertEqual([], [row for row in rows if row["is_other"]])
        self.assertEqual({None: 2, "eu": 1}, {row["region"]: row["n"] for row in rows})


class TestTheCardinalityCap(RollupTestCase):
    def fill(self, groups, each=1):
        payloads = []
        for index in range(groups):
            payloads.extend({"user": "u{}".format(index)} for _ in range(each))
        self.store.append(events(*payloads))

    def test_under_the_cap_nothing_is_rolled_up(self):
        self.fill(5)

        rows = self.run_rollup(["user"], [{"name": "n", "kind": "count"}])

        self.assertEqual(5, len(rows))
        self.assertEqual([], [row for row in rows if row["is_other"]])

    def test_past_it_the_tail_goes_into_one_bucket(self):
        # Grouped by `user_id` on a ten-million-user stream a rollup is not a
        # rollup; it is the stream again with extra steps.
        original = rollup.MAX_GROUPS
        rollup.MAX_GROUPS = 3
        try:
            self.fill(10)
            rows = self.run_rollup(["user"], [{"name": "n", "kind": "count"}])
        finally:
            rollup.MAX_GROUPS = original

        self.assertEqual(4, len(rows))
        tail = [row for row in rows if row["is_other"]]
        self.assertEqual(1, len(tail))
        self.assertEqual(rollup.OTHER, tail[0]["user"])

    def test_and_the_tail_keeps_its_events_rather_than_losing_them(self):
        # The failure this cap exists to avoid is a chart that adds up to less
        # than the stream and gives no sign of it.
        original = rollup.MAX_GROUPS
        rollup.MAX_GROUPS = 3
        try:
            self.fill(10)
            rows = self.run_rollup(["user"], [{"name": "n", "kind": "count"}])
        finally:
            rollup.MAX_GROUPS = original

        self.assertEqual(10, sum(row["n"] for row in rows))

    def test_the_busiest_groups_are_the_ones_kept(self):
        original = rollup.MAX_GROUPS
        rollup.MAX_GROUPS = 2
        try:
            self.store.append(events(*([{"user": "busy"}] * 20)))
            self.store.append(events(*([{"user": "medium"}] * 10)))
            self.store.append(events(*([{"user": "quiet"}] * 1)))
            rows = self.run_rollup(["user"], [{"name": "n", "kind": "count"}])
        finally:
            rollup.MAX_GROUPS = original

        kept = {row["user"] for row in rows if not row["is_other"]}
        self.assertEqual({"busy", "medium"}, kept)


class TestOneMinuteAtATime(RollupTestCase):
    """
    The query can be bounded above, and the rollup bounds it.

    The cap on groups is computed over whatever the query reads: the busiest
    `MAX_GROUPS` of that window, with the rest swept into `other`. A query
    spanning ten minutes would therefore pick the busiest groups *of those ten*
    and could sweep a group that was busy in only one of them into the tail --
    so a chart of that minute would show the group missing and the tail larger,
    with nothing to say why.

    The rollup reads the finished minutes it is missing one at a time for this
    reason, which is only worth the extra queries if the bound actually bounds.
    """

    def setUp(self):
        super().setUp()
        self.store.append(events({"region": "eu"}, {"region": "eu"}, {"region": "us"}))
        # Half the rows into the minute before last, half into the last one.
        self.store.connection.execute(
            "UPDATE events SET {} = date_trunc('minute', now()) - INTERVAL '2 minutes' + INTERVAL '30 seconds' "
            "WHERE region = 'us'".format(RECEIVED)
        )
        self.store.connection.execute(
            "UPDATE events SET {} = date_trunc('minute', now()) - INTERVAL '1 minute' + INTERVAL '30 seconds' "
            "WHERE region = 'eu'".format(RECEIVED)
        )

    def test_without_an_upper_bound_both_minutes_come_back(self):
        rows = self.run_rollup(["region"], [{"name": "n", "kind": "count"}])

        self.assertEqual(2, len({row["minute"] for row in rows}))

    def test_and_with_one_only_the_minute_asked_for_does(self):
        rows = self.run_rollup(
            ["region"],
            [{"name": "n", "kind": "count"}],
            since="date_trunc('minute', now()) - INTERVAL '2 minutes'",
            until="date_trunc('minute', now()) - INTERVAL '1 minute'",
        )

        self.assertEqual(1, len({row["minute"] for row in rows}))
        self.assertEqual(["us"], [row["region"] for row in rows])

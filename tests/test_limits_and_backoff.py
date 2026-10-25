"""
What stops a query, a worker or a schedule running away.

Each of these had no ceiling at all, and each one shows up as the same
symptom from the outside: an install that is busy, passing every probe, and
not getting anything done.
"""

import datetime
from unittest import mock

from sqldesk import settings
from sqldesk.models import MAX_SCHEDULE_BACKOFF, should_schedule_next
from sqldesk.settings import dynamic_settings
from sqldesk.tasks.queries.execution import _shape_of
from tests import BaseTestCase


class TestAQueryHasATimeLimit(BaseTestCase):
    """
    The limit was -1: no limit. A query holds a worker for as long as the
    warehouse keeps the connection open, which is hours in the cases that
    matter, and the worker goes on answering its health probe the whole time.
    """

    def test_an_ad_hoc_query_is_given_fifteen_minutes(self):
        # Long enough for an unindexed join over a year of events or a first
        # run against cold storage; short enough that a runaway query is not
        # still holding a worker after lunch.
        self.assertEqual(900, settings.ADHOC_QUERY_TIME_LIMIT)
        self.assertEqual(900, dynamic_settings.query_time_limit(False, 1, 1))

    def test_a_scheduled_one_is_given_half_an_hour(self):
        # Nobody is sitting in front of it, so it may be slow -- but not
        # until somebody notices next week.
        self.assertEqual(1800, settings.SCHEDULED_QUERY_TIME_LIMIT)
        self.assertEqual(1800, dynamic_settings.query_time_limit(True, 1, 1))

    def test_the_old_behaviour_is_still_available(self):
        with mock.patch("sqldesk.settings.ADHOC_QUERY_TIME_LIMIT", -1):
            self.assertEqual(-1, dynamic_settings.query_time_limit(False, 1, 1))


class TestAFinishedJobsRecordIsNotKeptAllDay(BaseTestCase):
    def test_ten_minutes_rather_than_twelve_hours(self):
        # The record exists so the browser that asked can be told the query
        # is done; it then reads the result from Postgres and never asks
        # again. Twelve hours of them was most of what Redis held.
        self.assertEqual(600, settings.JOB_RESULT_TTL)
        self.assertLess(settings.JOB_RESULT_TTL, settings.JOB_EXPIRY_TIME)


class TestTheBackoffOnAFailingScheduleHasACeiling(BaseTestCase):
    """
    The delay was 2**failures minutes with nothing above it, so a warehouse
    down for a day took a five-minute query to a 17-hour delay -- and the
    morning after an outage every dashboard was stale with nothing visibly
    wrong.
    """

    def _due_after(self, failures, minutes):
        """Whether a 5-minute query with `failures` is due `minutes` later."""
        last_run = datetime.datetime(2026, 10, 24, 9, 0)
        now = last_run + datetime.timedelta(minutes=minutes)
        return should_schedule_next(last_run, now, "300", failures=failures)

    def test_a_few_failures_still_back_off(self):
        self.assertFalse(self._due_after(4, 10))  # 5 minutes + 16
        self.assertTrue(self._due_after(4, 30))

    def test_ten_failures_no_longer_mean_seventeen_hours(self):
        self.assertTrue(self._due_after(10, 70))

    def test_the_ceiling_is_an_hour(self):
        self.assertEqual(datetime.timedelta(hours=1), MAX_SCHEDULE_BACKOFF)
        self.assertFalse(self._due_after(20, 55))
        self.assertTrue(self._due_after(20, 70))

    def test_a_failure_count_too_big_to_compute_is_capped_rather_than_fatal(self):
        # 2**100000 minutes raises OverflowError, which used to mean "never
        # run this again".
        self.assertTrue(self._due_after(100000, 70))

    def test_a_cron_schedule_is_capped_the_same_way(self):
        last_run = datetime.datetime(2026, 10, 24, 5, 0)
        due = last_run + datetime.timedelta(days=1, hours=2)

        self.assertTrue(should_schedule_next(last_run, due, None, failures=20, cron="0 5 * * *"))

    def test_and_a_healthy_schedule_is_untouched(self):
        self.assertTrue(self._due_after(0, 6))
        self.assertFalse(self._due_after(0, 4))


class TestWritingAResultDoesNotWalkIt(BaseTestCase):
    """
    The log line said how many bytes the result was, measured by walking every
    object in it and keeping each one's id in a set: 1.9 seconds of a
    2.3-second write on 200,000 rows, spent entirely on logging.
    """

    def test_the_shape_is_rows_and_columns(self):
        data = {"columns": [{"name": "a"}, {"name": "b"}], "rows": [{"a": 1, "b": 2}] * 3}

        self.assertEqual("3 rows x 2 columns", _shape_of(data))

    def test_something_else_entirely_is_not_a_traceback(self):
        self.assertEqual("unknown", _shape_of("a string"))
        self.assertEqual("unknown", _shape_of({"rows": None, "columns": None}))

    def test_a_large_result_is_described_without_being_walked(self):
        data = {"columns": [{"name": "a"}], "rows": [{"a": index} for index in range(50000)]}

        with mock.patch("sys.getsizeof", side_effect=AssertionError("the result was walked")):
            self.assertEqual("50000 rows x 1 columns", _shape_of(data))


class TestThePromqlPanelDoesNotParsePromqlAsSql(BaseTestCase):
    """
    The optimizer kept its own list of eight non-SQL types out of
    thirty-five, so the editor's panel reported a syntax error in a perfectly
    good PromQL query on a Mimir source -- the same gap MCP had, from the
    same cause.
    """

    def test_a_mimir_source_is_not_parsed_as_sql(self):
        from sqldesk.ai.optimizer import analyze, is_sql

        self.assertFalse(is_sql("mimir"))
        self.assertFalse(analyze("sum(rate(http_requests_total[5m])) by (job)", "mimir")["applicable"])

    def test_nor_is_prometheus_itself(self):
        from sqldesk.ai.optimizer import is_sql

        self.assertFalse(is_sql("prometheus"))

    def test_but_postgres_still_is(self):
        from sqldesk.ai.optimizer import is_sql

        self.assertTrue(is_sql("pg"))

    def test_an_unknown_type_is_treated_as_sql_as_before(self):
        from sqldesk.ai.optimizer import is_sql

        self.assertTrue(is_sql("something_nobody_installed"))


class TestAProxyAnsweringInsteadOfPrometheus(BaseTestCase):
    def test_html_with_a_200_is_a_message_rather_than_a_traceback(self):
        from sqldesk.query_runner.prometheus import api_body

        response = mock.Mock(headers={"Content-Type": "text/html"})
        response.json.side_effect = ValueError("Expecting value")

        with self.assertRaises(ValueError) as raised:
            api_body(response, "The query")

        self.assertIn("something in front of prometheus", str(raised.exception).lower())

    def test_and_a_query_reports_it_as_an_error_on_the_query(self):
        from sqldesk.query_runner.prometheus import Prometheus

        response = mock.Mock(ok=True, headers={})
        response.json.side_effect = ValueError("Expecting value")
        with mock.patch("sqldesk.query_runner.prometheus.requests.get", return_value=response):
            data, error = Prometheus({"url": "http://prom:9090"}).run_query("up", None)

        self.assertIsNone(data)
        self.assertIn("not JSON", error)

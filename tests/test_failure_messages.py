"""
Whenever a result is not shown, the page says why. A job whose worker died
used to reach it as status "failed" with an empty message -- which reads as a
query that ran and found nothing.
"""
import datetime
import decimal
from unittest import TestCase
from unittest.mock import MagicMock

from dateutil.relativedelta import relativedelta
from rq.job import JobStatus
from rq.timeouts import JobTimeoutException

from sqldesk.models.types import JSONText
from sqldesk.serializers import NO_REASON, WORKER_DIED, failure_reason, serialize_job
from sqldesk.tasks.queries.execution import (
    OUT_OF_MEMORY,
    TIMEOUT_MESSAGE,
    describe_failure,
)
from sqldesk.utils import json_dumps, json_dumps_result, json_loads


def failed_job(exc_string=None, exc_info=None):
    job = MagicMock()
    job.get_status.return_value = JobStatus.FAILED
    job.is_cancelled = False
    job.is_started = True
    job.started_at = 0
    job.result = None
    job.id = "j1"
    if exc_string is None:
        job.latest_result.return_value = None
    else:
        latest = MagicMock()
        latest.type = latest.Type.FAILED
        latest.exc_string = exc_string
        job.latest_result.return_value = latest
    job._exc_info = exc_info
    return job


class TestWhyAJobFailed(TestCase):
    def test_a_worker_killed_for_memory(self):
        job = failed_job("Work-horse terminated unexpectedly; waitpid returned 9 (signal 9); ")
        self.assertEqual(failure_reason(job), WORKER_DIED)

    def test_a_worker_that_vanished(self):
        job = failed_job(exc_info="Moved to FailedJobRegistry, due to AbandonedJobError, at 2026-11-14")
        self.assertEqual(failure_reason(job), WORKER_DIED)

    def test_a_time_limit(self):
        job = failed_job(
            "Traceback...\nrq.timeouts.JobTimeoutException: Task exceeded maximum timeout value (900 seconds)"
        )
        self.assertIn("time limit", failure_reason(job))

    def test_anything_else_says_its_last_line(self):
        job = failed_job("Traceback (most recent call last):\n  File x\nValueError: something odd")
        self.assertEqual(failure_reason(job), "ValueError: something odd")

    def test_never_nothing(self):
        self.assertEqual(failure_reason(failed_job()), NO_REASON)

    def test_the_page_is_told(self):
        payload = serialize_job(failed_job("Work-horse terminated unexpectedly; waitpid returned 9; "))["job"]
        self.assertEqual(payload["status"], 4)
        self.assertEqual(payload["error"], WORKER_DIED)


class TestARunnerExceptionAlwaysHasWords(TestCase):
    def test_out_of_memory(self):
        self.assertEqual(describe_failure(MemoryError()), OUT_OF_MEMORY)

    def test_time_limit(self):
        self.assertEqual(describe_failure(JobTimeoutException("x")), TIMEOUT_MESSAGE)

    def test_one_with_no_text(self):
        self.assertIn("KeyError", describe_failure(KeyError()))
        self.assertTrue(describe_failure(Exception()))

    def test_its_own_words_when_it_has_some(self):
        self.assertEqual(describe_failure(ValueError("bad")), "bad")


class TestStoringAResult(TestCase):
    rows = [
        {
            "n": 1,
            "price": decimal.Decimal("173665.47"),
            "day": datetime.date(1996, 1, 2),
            "at": datetime.datetime(2026, 11, 14, 9, 30, 1, 123456),
            "utc": datetime.datetime(2026, 11, 14, 9, 30, 1, tzinfo=datetime.timezone.utc),
            "nan": float("nan"),
            "inf": float("inf"),
            "nested": {"x": [float("nan"), decimal.Decimal("1.5")]},
            "text": "naïve ✓",
        }
    ]

    def test_the_same_values_as_json_dumps(self):
        self.assertEqual(json_loads(json_dumps_result(self.rows)), json_loads(json_dumps(self.rows)))

    def test_nan_and_infinity_are_null(self):
        stored = json_loads(json_dumps_result(self.rows))[0]
        self.assertIsNone(stored["nan"])
        self.assertIsNone(stored["inf"])
        self.assertIsNone(stored["nested"]["x"][0])

    def test_what_orjson_refuses_goes_the_old_way(self):
        self.assertEqual(json_loads(json_dumps_result({"big": 2**70})), {"big": 2**70})

    def test_results_are_stored_this_way(self):
        self.assertEqual(JSONText().process_bind_param({"a": float("nan")}, None), '{"a":null}')

    def test_an_interval_with_months_is_written_not_refused(self):
        self.assertEqual(
            json_loads(json_dumps({"v": relativedelta(years=1, months=2, days=3, hours=4)})),
            {"v": "1 year 2 months 3 days, 4:00:00"},
        )
        self.assertEqual(json_loads(json_dumps({"v": relativedelta(days=2)})), {"v": "2 days, 0:00:00"})
        self.assertEqual(json_loads(json_dumps({"v": relativedelta()})), {"v": "0:00:00"})

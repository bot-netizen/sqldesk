"""
A result is read a batch at a time and kept only up to what this instance
keeps for one query. Before, every runner fetchall()ed: a result bigger than
the worker's memory took the worker down, with no message, and the warehouse
kept the query open for a reader that was gone.
"""
from unittest import TestCase
from unittest.mock import patch

from sqldesk.query_runner import fetch_within_budget, mark_truncated
from sqldesk.utils import json_dumps_result


def batches(total, width=100, size=1000):
    rows = [(i, "x" * width) for i in range(total)]
    chunks = [rows[i : i + size] for i in range(0, total, size)]
    chunks.append([])

    def fetchmany(n):
        return chunks.pop(0)

    return fetchmany


def to_row(row):
    return {"id": row[0], "text": row[1]}


class TestFetchWithinBudget(TestCase):
    def test_a_result_inside_the_budget_is_all_kept(self):
        rows, truncated = fetch_within_budget(batches(5000), to_row, budget_bytes=10 * 1024 * 1024)
        self.assertEqual(len(rows), 5000)
        self.assertFalse(truncated)

    def test_a_result_past_the_budget_stops_near_it(self):
        budget = 200 * 1024
        rows, truncated = fetch_within_budget(batches(20000), to_row, budget_bytes=budget)
        self.assertTrue(truncated)
        size = len(json_dumps_result(rows))
        self.assertLess(size, budget * 1.1)
        self.assertGreater(size, budget * 0.8)

    def test_zero_is_no_limit(self):
        rows, truncated = fetch_within_budget(batches(20000), to_row, budget_bytes=0)
        self.assertEqual(len(rows), 20000)
        self.assertFalse(truncated)

    def test_the_instances_limit_by_default(self):
        with patch("sqldesk.settings.QUERY_RESULT_MAX_MB", 0):
            self.assertFalse(fetch_within_budget(batches(3000), to_row)[1])
        with patch("sqldesk.settings.QUERY_RESULT_MAX_MB", 0.1):
            self.assertTrue(fetch_within_budget(batches(3000), to_row)[1])

    def test_a_truncated_result_says_why_and_at_how_much(self):
        with patch("sqldesk.settings.QUERY_RESULT_MAX_MB", 250):
            data = mark_truncated({"columns": [], "rows": []})
        self.assertTrue(data["truncated"])
        self.assertEqual(data["truncation"], {"reason": "size", "limit_mb": 250})

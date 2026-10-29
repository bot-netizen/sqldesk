"""
The tools that are about SQL, asked about a source that does not speak it.

A separate file from `test_mcp.py` so the harness is shared and the subject is
not: these are about `query_language` reaching the tools, not about MCP.
"""

import json
from unittest import mock

from sqldesk import models
from tests.handlers.test_mcp import McpTestCase, rpc


class TestTheToolsAboutSqlRefuseWhatIsNot(McpTestCase):
    def setUp(self):
        super().setUp()
        self.factory.data_source.name = "metrics"
        models.db.session.commit()
        self.worker = mock.patch("sqldesk.mcp._on_a_worker", return_value=({"columns": [], "rows": []}, None))
        self.ran = self.worker.start()
        self.addCleanup(self.worker.stop)

    def _as(self, source_type):
        self.factory.data_source.type = source_type
        models.db.session.commit()

    def call(self, name, sql):
        response = self.post(rpc("tools/call", {"name": name, "arguments": {"sql": sql, "data_source": "metrics"}}))
        return json.loads(response.data)["result"]

    def test_check_sql_does_not_report_findings_about_promql(self):
        self._as("mimir")
        with mock.patch("sqldesk.mcp.analyze") as analyze:
            text = self.call("check_sql", 'sum(rate(http_requests_total{job="api"}[5m])) by (code)')["content"][0][
                "text"
            ]
        self.assertIn("not SQL", text)
        self.assertIn("promql", text)
        # The optimizer is never reached: parsing PromQL as SQL produced
        # findings about a query nobody wrote.
        analyze.assert_not_called()

    def test_explain_query_plans_nothing_on_promql(self):
        self._as("mimir")
        result = self.call("explain_query", "up")
        self.assertTrue(result["isError"])
        self.assertIn("not SQL", result["content"][0]["text"])
        # `EXPLAIN up` would have gone to Mimir as the query.
        self.ran.assert_not_called()

    def test_a_promql_query_runs(self):
        # The point of the whole thing: this used to come back "Only a read
        # (SELECT, WITH, SHOW, DESCRIBE) can be run from here."
        self._as("mimir")
        result = self.call("run_query", 'up{job="api"} + 1')
        self.assertFalse(result.get("isError"), result)
        self.ran.assert_called_once()

    def test_sql_still_gets_both(self):
        self._as("pg")
        self.assertIn("Parsed as postgres", self.call("check_sql", "SELECT 1 FROM orders")["content"][0]["text"])
        self.assertFalse(self.call("explain_query", "SELECT 1 FROM orders").get("isError"))

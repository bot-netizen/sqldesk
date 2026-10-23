import json
from unittest import TestCase
from unittest.mock import Mock, patch

from sqldesk.query_runner import TYPE_INTEGER
from sqldesk.query_runner.clickhouse import ClickHouse, split_multi_query

split_multi_query_samples = [
    # Regular query
    ("SELECT 1", ["SELECT 1"]),
    # Multiple data queries inlined
    ("SELECT 1; SELECT 2;", ["SELECT 1", "SELECT 2"]),
    # Multiline data queries
    (
        """
SELECT 1;
SELECT 2;
""",
        ["SELECT 1", "SELECT 2"],
    ),
    # Commented data queries
    (
        """
-- First query single-line commentary
SELECT 1;

/**
 * Second query multi-line commentary
 */
SELECT 2;

-- Tail single-line commentary

/**
 * Tail multi-line commentary
 */
""",
        [
            "-- First query single-line commentary\nSELECT 1",
            "/**\n * Second query multi-line commentary\n */\nSELECT 2",
        ],
    ),
    # Should skip empty statements
    (
        """
;;;
;
SELECT 1;
""",
        ["SELECT 1"],
    ),
]


class TestClickHouseQueriesSplit(TestCase):
    def test_split(self):
        for sample in split_multi_query_samples:
            query, expected = sample

            self.assertEqual(split_multi_query(query), expected)


simple_query_response = {
    "meta": [
        {"name": "1", "type": "UInt8"},
    ],
    "data": [
        {"1": 1},
    ],
    "rows": 1,
    "statistics": {"elapsed": 0.0001278, "rows_read": 1, "bytes_read": 1},
}


class TestClickHouse(TestCase):
    @patch("requests.post")
    def test_send_single_query(self, post_request):
        query_runner = ClickHouse({"url": "http://clickhouse:8123", "dbname": "system", "timeout": 60})

        response = Mock()
        response.status_code = 200
        response.text = json.dumps(simple_query_response)
        response.json.return_value = simple_query_response
        post_request.return_value = response

        data, error = query_runner.run_query("SELECT 1", None)

        self.assertIsNone(error)
        self.assertEqual(
            data,
            {
                "columns": [
                    {"name": "1", "friendly_name": "1", "type": TYPE_INTEGER},
                ],
                "rows": [
                    {"1": 1},
                ],
            },
        )

        (url,), kwargs = post_request.call_args
        self.assertEqual(url, "http://clickhouse:8123")
        self.assertEqual(kwargs["data"], b"SELECT 1\nFORMAT JSON")
        self.assertEqual("system", kwargs["params"]["database"])
        self.assertEqual("JSON", kwargs["params"]["default_format"])
        self.assertTrue(kwargs["params"]["query_id"].startswith("sqldesk_"))
        self.assertEqual(("default", ""), kwargs["auth"])
        self.assertEqual(kwargs["timeout"], 60)

    @patch("requests.post")
    def test_send_multi_query(self, post_request):
        query_runner = ClickHouse({"url": "http://clickhouse:8123", "dbname": "system", "timeout": 60})

        create_table_response = Mock()
        create_table_response.status_code = 200
        create_table_response.text = ""

        select_response = Mock()
        select_response.status_code = 200
        select_response.text = json.dumps(simple_query_response)
        select_response.json.return_value = simple_query_response

        post_request.side_effect = [create_table_response, select_response]

        data, error = query_runner.run_query(
            """
CREATE
TEMPORARY TABLE test AS
SELECT 1;
SELECT * FROM test;
        """,
            None,
        )

        self.assertIsNone(error)
        self.assertEqual(
            data,
            {
                "columns": [
                    {"name": "1", "friendly_name": "1", "type": TYPE_INTEGER},
                ],
                "rows": [
                    {"1": 1},
                ],
            },
        )

        (url,), kwargs = post_request.call_args_list[0]
        self.assertEqual(url, "http://clickhouse:8123")
        self.assertEqual(
            kwargs["data"],
            b"""CREATE
TEMPORARY TABLE test AS
SELECT 1
FORMAT JSON""",
        )
        self.assert_session_params(kwargs, expected_check="0", expected_timeout=60)

        session_id = kwargs["params"]["session_id"]

        (url,), kwargs = post_request.call_args_list[1]
        self.assertEqual(url, "http://clickhouse:8123")
        self.assertEqual(
            kwargs["data"],
            b"""SELECT * FROM test
FORMAT JSON""",
        )

        self.assert_session_params(kwargs, expected_check="1", expected_timeout=60, expected_id=session_id)

    def assert_session_params(self, kwargs, expected_check, expected_timeout, expected_id=None):
        self.assertEqual(kwargs["params"]["session_check"], expected_check)
        self.assertEqual(kwargs["params"]["session_timeout"], expected_timeout)

        session_id = kwargs["params"]["session_id"]
        self.assertRegex(session_id, r"sqldesk_[a-f0-9]+")

        if expected_id:
            self.assertEqual(kwargs["params"]["session_id"], session_id)

    @patch("requests.post")
    def test_the_password_never_goes_in_the_url(self, post_request):
        """In the query string it rode into exceptions, and from there into the log."""
        runner = ClickHouse({"url": "http://clickhouse:8123", "dbname": "system", "user": "u", "password": "s3cret"})
        response = Mock(status_code=200, ok=True, text=json.dumps(simple_query_response))
        response.json.return_value = simple_query_response
        post_request.return_value = response

        runner.run_query("SELECT 1", None)

        _, kwargs = post_request.call_args
        self.assertNotIn("s3cret", json.dumps(kwargs["params"]))
        self.assertEqual(("u", "s3cret"), kwargs["auth"])

    @patch("requests.post")
    def test_a_connection_error_does_not_carry_it_either(self, post_request):
        import requests

        runner = ClickHouse({"url": "http://clickhouse:8123", "dbname": "system", "password": "s3cret"})
        post_request.side_effect = requests.ConnectionError("http://clickhouse:8123/?password=s3cret refused")

        with self.assertLogs("sqldesk.query_runner.clickhouse", level="WARNING") as logged:
            _, error = runner.run_query("SELECT 1", None)

        self.assertNotIn("s3cret", error)
        self.assertNotIn("s3cret", "\n".join(logged.output))

    @patch("requests.post")
    def test_a_query_past_the_timeout_is_asked_to_stop_on_the_server(self, post_request):
        """ClickHouse answers only when the result is ready, so a client that gives up does not stop it."""
        import requests

        runner = ClickHouse({"url": "http://clickhouse:8123", "dbname": "system", "timeout": 30})
        post_request.side_effect = [requests.ReadTimeout(), Mock(ok=True, text="")]

        _, error = runner.run_query("SELECT sleep(60)", None)

        self.assertIn("did not answer within 30 seconds", error)
        query_id = post_request.call_args_list[0][1]["params"]["query_id"]
        kill = post_request.call_args_list[1][1]["data"].decode()
        self.assertEqual("KILL QUERY WHERE query_id = '{}' ASYNC".format(query_id), kill)

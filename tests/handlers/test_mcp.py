import json
from unittest import mock

from sqldesk import models
from tests import BaseTestCase


def rpc(method, params=None, message_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if message_id is not None:
        body["id"] = message_id
    if params is not None:
        body["params"] = params
    return body


class McpTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.feature = mock.patch("sqldesk.settings.FEATURE_AI", True)
        self.feature.start()
        self.addCleanup(self.feature.stop)

    def post(self, body, api_key=None, user=None):
        user = user or self.factory.user
        headers = {"Authorization": "Bearer {}".format(api_key or user.api_key)}
        return self.client.post("/mcp", data=json.dumps(body), headers=headers, content_type="application/json")


class TestTheHandshake(McpTestCase):
    def test_initialize_names_the_protocol_and_the_server(self):
        response = self.post(rpc("initialize"))
        self.assertEqual(200, response.status_code)
        body = json.loads(response.data)
        self.assertEqual("2.0", body["jsonrpc"])
        self.assertIn("protocolVersion", body["result"])
        self.assertEqual("sqldesk", body["result"]["serverInfo"]["name"])
        self.assertIn("tools", body["result"]["capabilities"])

    def test_a_notification_gets_no_reply_at_all(self):
        # Every client sends notifications/initialized, which has no id.
        response = self.post(rpc("notifications/initialized", message_id=None))
        self.assertEqual(202, response.status_code)
        self.assertEqual(b"", response.data)

    def test_tools_list_describes_what_there_is(self):
        body = json.loads(self.post(rpc("tools/list")).data)
        names = {tool["name"] for tool in body["result"]["tools"]}
        self.assertIn("find_context", names)
        self.assertIn("check_sql", names)
        for tool in body["result"]["tools"]:
            self.assertIn("inputSchema", tool, "a client cannot call a tool it has no schema for")

    def test_an_unknown_method_is_an_error_not_a_crash(self):
        body = json.loads(self.post(rpc("tools/destroy")).data)
        self.assertEqual(-32601, body["error"]["code"])


class TestWhoIsAsking(McpTestCase):
    def test_no_key_is_refused(self):
        response = self.client.post("/mcp", data=json.dumps(rpc("initialize")), content_type="application/json")
        self.assertEqual(401, response.status_code)
        self.assertIn("Bearer", response.headers.get("WWW-Authenticate", ""))

    def test_a_wrong_key_is_refused(self):
        response = self.post(rpc("initialize"), api_key="not-a-key")
        self.assertEqual(401, response.status_code)

    def test_a_disabled_user_is_refused(self):
        user = self.factory.create_user()
        user.disabled_at = models.db.func.now()
        models.db.session.commit()
        self.assertEqual(401, self.post(rpc("initialize"), user=user).status_code)

    def test_the_whole_thing_is_off_when_the_feature_is(self):
        self.feature.stop()
        try:
            self.assertEqual(404, self.post(rpc("initialize")).status_code)
        finally:
            self.feature.start()


class TestTheTools(McpTestCase):
    def _catalogued(self):
        # `self.factory.data_source`, not `create_data_source()`: the latter
        # belongs to no group, so nobody can read it -- which is a different
        # test, below.
        source = self.factory.data_source
        table = models.CatalogTable(
            org=self.factory.org, data_source=source, name="orders", usage_count=9, card="orders(id bigint)"
        )
        models.db.session.add(table)
        models.db.session.flush()
        models.db.session.add(models.CatalogColumn(catalog_table=table, name="amount", type="decimal", usage_count=9))
        models.db.session.commit()
        return source

    def call(self, name, arguments=None):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)

    def test_find_context_answers_with_the_card(self):
        self._catalogued()
        body = self.call("find_context", {"question": "orders"})
        self.assertIn("orders(id bigint)", body["result"]["content"][0]["text"])

    def test_find_context_says_when_the_catalog_is_empty(self):
        body = self.call("find_context", {"question": "anything"})
        self.assertIn("harvest", body["result"]["content"][0]["text"])

    def test_check_sql_finds_what_the_optimizer_finds(self):
        source = self._catalogued()
        body = self.call("check_sql", {"sql": "SELECT * FROM orders a JOIN users b", "data_source": source.name})
        text = body["result"]["content"][0]["text"]
        self.assertIn("CRITICAL", text)

    def test_check_sql_executes_nothing(self):
        # It parses. If it ever runs anything this test is the alarm.
        with mock.patch.object(models.DataSource, "query_runner") as runner:
            self.call("check_sql", {"sql": "DROP TABLE orders"})
            runner.run_query.assert_not_called()

    def test_expand_table_gives_the_columns(self):
        self._catalogued()
        body = self.call("expand_table", {"names": ["orders"]})
        self.assertIn("amount decimal", body["result"]["content"][0]["text"])

    def test_a_missing_argument_is_an_error_with_a_reason(self):
        body = self.call("find_context", {})
        self.assertEqual(-32602, body["error"]["code"])
        self.assertIn("question", body["error"]["message"])

    def test_a_tool_that_breaks_reports_it_rather_than_dropping_the_session(self):
        with mock.patch("sqldesk.mcp.context_for", side_effect=RuntimeError("boom")):
            body = self.call("find_context", {"question": "x"})
        self.assertTrue(body["result"]["isError"])


class TestPermissionsAreTheApplicationsOwn(McpTestCase):
    def test_a_data_source_you_cannot_read_is_not_offered(self):
        other_org = self.factory.create_org(name="Other", slug="other-mcp")
        self.factory.create_data_source(org=other_org, name="theirs")
        mine = self.factory.data_source
        body = json.loads(self.post(rpc("tools/call", {"name": "list_data_sources", "arguments": {}})).data)
        text = body["result"]["content"][0]["text"]
        self.assertIn(mine.name, text)
        self.assertNotIn("theirs", text)

    def test_naming_a_source_you_cannot_read_is_refused_with_the_ones_you_can(self):
        other_org = self.factory.create_org(name="Other", slug="other-mcp-2")
        self.factory.create_data_source(org=other_org, name="theirs")
        body = json.loads(
            self.post(
                rpc("tools/call", {"name": "check_sql", "arguments": {"sql": "SELECT 1", "data_source": "theirs"}})
            ).data
        )
        self.assertEqual(-32602, body["error"]["code"])
        self.assertNotIn("theirs", body["error"]["message"].split("Available:")[0].replace("'theirs'", ""))


class TestTheAudit(McpTestCase):
    """
    An audit that records only what succeeded answers "what did this work do"
    and not "who has been trying". The second is the question somebody asks at
    two in the morning.
    """

    def audit(self, user=None):
        response = self.make_request("get", "/api/mcp/audit", user=user or self.factory.create_admin())
        self.assertEqual(200, response.status_code)
        return response.json

    def test_every_call_leaves_a_row(self):
        self.post(rpc("tools/list"))
        events = self.audit()["events"]
        self.assertEqual(1, len(events))
        self.assertEqual("tools/list", events[0]["method"])
        self.assertEqual("ok", events[0]["outcome"])
        self.assertEqual(self.factory.user.name, events[0]["user"])

    def test_a_rejected_key_is_recorded_with_no_user(self):
        # The row worth having: a key that does not work, tried repeatedly.
        self.client.post("/mcp", data=json.dumps(rpc("initialize")), content_type="application/json")
        events = self.audit()["events"]
        self.assertEqual("refused", events[0]["outcome"])
        self.assertIsNone(events[0]["user"])
        self.assertIsNotNone(events[0]["remote_addr"])

    def test_the_tool_and_the_question_are_kept(self):
        self.post(rpc("tools/call", {"name": "find_context", "arguments": {"question": "revenue by region"}}))
        event = self.audit()["events"][0]
        self.assertEqual("find_context", event["tool"])
        self.assertIn("revenue by region", event["detail"])

    def test_an_enormous_argument_is_summarised_not_stored(self):
        self.post(rpc("tools/call", {"name": "check_sql", "arguments": {"sql": "SELECT " + "x," * 50000}}))
        event = self.audit()["events"][0]
        self.assertLess(len(event["detail"] or ""), 600, "the audit is not a copy of the request")

    def test_a_failing_tool_is_recorded_as_an_error(self):
        with mock.patch("sqldesk.mcp.context_for", side_effect=RuntimeError("boom")):
            self.post(rpc("tools/call", {"name": "find_context", "arguments": {"question": "x"}}))
        self.assertEqual("error", self.audit()["events"][0]["outcome"])

    def test_how_long_it_took_is_recorded(self):
        self.post(rpc("tools/list"))
        self.assertIsNotNone(self.audit()["events"][0]["duration_ms"])

    def test_a_session_is_issued_at_initialize_and_groups_what_follows(self):
        response = self.post(rpc("initialize", {"clientInfo": {"name": "claude-code", "version": "2.1"}}))
        session = response.headers.get("Mcp-Session-Id")
        self.assertIsNotNone(session, "without one, 'who is connected' has nothing to group by")

        self.client.post(
            "/mcp",
            data=json.dumps(rpc("tools/list")),
            headers={"Authorization": "Bearer {}".format(self.factory.user.api_key), "Mcp-Session-Id": session},
            content_type="application/json",
        )
        active = self.audit()["active"]
        self.assertEqual(1, len(active))
        self.assertEqual(session, active[0]["session_id"])
        self.assertEqual(2, active[0]["calls"])
        self.assertEqual("claude-code 2.1", active[0]["client"], "the name arrives with initialize, the oldest row")

    def test_only_an_admin_may_read_it(self):
        # It names every user, every question and every address.
        response = self.make_request("get", "/api/mcp/audit", user=self.factory.user)
        self.assertEqual(403, response.status_code)

    def test_another_orgs_activity_is_not_in_it(self):
        self.post(rpc("tools/list"))
        other = self.factory.create_org(name="Other", slug="other-audit")
        models.db.session.add(models.McpEvent(org=other, method="tools/list", outcome="ok"))
        models.db.session.commit()
        self.assertEqual(1, len(self.audit()["events"]))

    def test_the_audit_never_fails_the_request_it_audits(self):
        # Worse than no audit: the failure looks like the feature being
        # broken. Patched at the row rather than at the session, so this
        # breaks the audit write and nothing else.
        with mock.patch("sqldesk.handlers.mcp.models.McpEvent", side_effect=RuntimeError("full disk")):
            response = self.post(rpc("tools/list"))
        self.assertEqual(200, response.status_code)
        self.assertIn("tools", json.loads(response.data)["result"], "and the answer still came back")

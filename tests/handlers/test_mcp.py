import datetime
import json
from unittest import mock

from sqldesk import mcp, models, settings, utils
from sqldesk.handlers.mcp import MyMcpResource
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
        # Everyone in these tests may use MCP, so each one is about the tool
        # it names rather than about the permission. Who may use MCP at all
        # is TestWhoMayUseMcp's subject.
        default_group = self.factory.default_group
        default_group.permissions = list(default_group.permissions or []) + ["use_mcp"]
        models.db.session.add(default_group)
        models.db.session.commit()

    def post(self, body, api_key=None, user=None):
        user = user or self.factory.user
        headers = {"Authorization": "Bearer {}".format(api_key or user.api_key)}
        return self.client.post("/mcp", data=json.dumps(body), headers=headers, content_type="application/json")


class TestWhoMayUseMcp(McpTestCase):
    """
    A working API key is not permission to use MCP. An administrator hands
    that to a group, and until somebody does, only administrators have it --
    which is what an upgrade leaves behind.
    """

    def _member_of(self, *permissions):
        group = self.factory.create_group(name="Analysts", permissions=list(permissions))
        models.db.session.add(group)
        models.db.session.commit()
        return self.factory.create_user(group_ids=[group.id])

    def test_a_key_belonging_to_somebody_without_the_feature_is_refused(self):
        response = self.post(rpc("tools/list"), user=self._member_of("view_query", "execute_query"))

        self.assertEqual(403, response.status_code)
        self.assertIn("administrator", json.loads(response.data)["error"]["message"])

    def test_and_the_refusal_says_who_it_was(self):
        # The difference between this and an unknown key: an administrator
        # can see who is asking and grant it.
        user = self._member_of("view_query")

        self.post(rpc("tools/list"), user=user)

        event = models.McpEvent.query.one()
        self.assertEqual("refused", event.outcome)
        self.assertEqual("no MCP permission", event.detail)
        self.assertEqual(user.id, event.user_id)

    def test_a_group_that_was_granted_it_may(self):
        granted = self._member_of("view_query", "use_mcp")

        response = self.post(rpc("tools/list"), user=granted)

        self.assertEqual(200, response.status_code)
        self.assertIn("tools", json.loads(response.data)["result"])

    def test_an_administrator_may_without_being_granted_anything(self):
        response = self.post(rpc("tools/list"), user=self.factory.create_admin())

        self.assertEqual(200, response.status_code)


class TestTheHandshake(McpTestCase):
    def test_initialize_names_the_protocol_and_the_server(self):
        response = self.post(rpc("initialize"))
        self.assertEqual(200, response.status_code)
        body = json.loads(response.data)
        self.assertEqual("2.0", body["jsonrpc"])
        self.assertIn("protocolVersion", body["result"])
        self.assertEqual("sqldesk", body["result"]["serverInfo"]["name"])
        self.assertIn("tools", body["result"]["capabilities"])

    def test_the_server_answers_in_the_version_the_client_asked_for(self):
        # A client that speaks an older protocol says so, and gets that version
        # back. Answering in ours regardless is how a handshake fails silently.
        for asked in ("2024-11-05", "2025-03-26", "2025-06-18"):
            response = self.post(rpc("initialize", params={"protocolVersion": asked}))
            self.assertEqual(asked, json.loads(response.data)["result"]["protocolVersion"])

    def test_an_unknown_version_gets_ours_back(self):
        # The client decides whether it can proceed; we say what we speak.
        for asked in ("1999-01-01", "", None):
            params = {"protocolVersion": asked} if asked is not None else {}
            response = self.post(rpc("initialize", params=params))
            self.assertEqual("2025-06-18", json.loads(response.data)["result"]["protocolVersion"])

    def test_the_server_reports_the_version_we_actually_ship(self):
        from sqldesk import __version__

        response = self.post(rpc("initialize"))
        self.assertEqual(__version__, json.loads(response.data)["result"]["serverInfo"]["version"])

    def test_a_body_that_is_not_json_is_a_parse_error(self):
        # -32700, not -32600: the codes are how a client decides whether
        # sending the same thing again could ever work.
        response = self.client.post(
            "/mcp",
            data="{not json",
            headers={"Authorization": "Bearer {}".format(self.factory.user.api_key)},
            content_type="application/json",
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual(-32700, json.loads(response.data)["error"]["code"])

    def test_a_crash_is_an_internal_error_not_a_bad_request(self):
        # Telling a client its request was invalid when the server broke
        # invites it to give up on a request that was fine.
        with mock.patch("sqldesk.handlers.mcp.handle", side_effect=RuntimeError("boom")):
            response = self.post(rpc("tools/list"))

        self.assertEqual(-32603, json.loads(response.data)["error"]["code"])

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


class TestFindingExistingWork(McpTestCase):
    """
    A saved query carries its author's understanding of the data -- which
    join is right, what a status means -- and no amount of schema carries
    that. Often the answer is work somebody already did.
    """

    def call(self, name, arguments=None):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)

    def text(self, name, arguments=None):
        return self.call(name, arguments)["result"]["content"][0]["text"]

    def test_a_query_is_found_by_its_description(self):
        self.factory.create_query(
            name="Weekly numbers",
            description="Revenue by region, the one finance uses",
            data_source=self.factory.data_source,
            is_draft=False,
        )
        models.db.session.commit()
        found = self.text("find_queries", {"question": "revenue region"})
        self.assertIn("Weekly numbers", found)
        self.assertIn("the one finance uses", found, "the description is the useful part")

    def test_a_draft_is_not_somebody_elses_answer(self):
        self.factory.create_query(
            name="wip revenue", description="", data_source=self.factory.data_source, is_draft=True
        )
        models.db.session.commit()
        self.assertIn("No saved query", self.text("find_queries", {"question": "revenue"}))

    def test_a_query_on_a_data_source_you_cannot_read_is_not_offered(self):
        other_org = self.factory.create_org(name="Other", slug="other-fq")
        theirs = self.factory.create_data_source(org=other_org, name="theirs")
        self.factory.create_query(
            name="secret revenue", description="", data_source=theirs, org=other_org, is_draft=False
        )
        models.db.session.commit()
        self.assertNotIn("secret revenue", self.text("find_queries", {"question": "revenue"}))

    def test_a_dashboard_is_found_by_the_words_on_it(self):
        dashboard = self.factory.create_dashboard(name="Finance", is_draft=False)
        models.db.session.add(models.Widget(dashboard=dashboard, width=1, text="## Revenue by region", options={}))
        models.db.session.commit()
        found = self.text("find_dashboards", {"question": "revenue"})
        self.assertIn("Finance", found)
        self.assertIn("/dashboards/{}".format(dashboard.id), found, "the address is the useful part")

    # Charts. A chart's description is written for the chart -- "completed
    # orders only, refunds excluded" -- and is written nowhere else, and its
    # settings say which columns it plots.

    def _weekly(self, **chart):
        query = self.factory.create_query(
            name="Weekly numbers", description="", data_source=self.factory.data_source, is_draft=False
        )
        options = {"globalSeriesType": "line", "columnMapping": {"week": "x", "amount": "y", "region": "series"}}
        args = {"query_rel": query, "type": "CHART", "name": "Orders by week", "options": options}
        args.update(chart)
        return query, self.factory.create_visualization(**args)

    def test_a_query_lists_its_charts_and_what_they_plot(self):
        self._weekly(description="Completed orders only; refunds excluded.")
        models.db.session.commit()

        found = self.text("find_queries", {"question": "weekly"})

        self.assertIn("Orders by week (line chart; x: week; y: amount; grouped by: region)", found)
        self.assertIn("Completed orders only; refunds excluded.", found)

    def test_a_query_is_found_by_its_charts_description(self):
        self._weekly(description="Churn by signup cohort")
        models.db.session.commit()

        self.assertIn("Weekly numbers", self.text("find_queries", {"question": "churn cohort"}))

    def test_a_plain_table_nobody_described_is_not_listed(self):
        query, _ = self._weekly()
        self.factory.create_visualization(query_rel=query, type="TABLE", name="Table", options={})
        models.db.session.commit()

        self.assertNotIn("Table (table)", self.text("find_queries", {"question": "weekly"}))

    def test_a_counter_says_which_column_it_counts(self):
        self._weekly(type="COUNTER", name="Orders today", options={"counterColName": "orders"})
        models.db.session.commit()

        self.assertIn("Orders today (counter; value: orders)", self.text("find_queries", {"question": "weekly"}))

    def test_a_dashboard_lists_its_charts_and_their_queries(self):
        query, chart = self._weekly(description="Completed orders only.")
        dashboard = self.factory.create_dashboard(name="Sales", is_draft=False)
        self.factory.create_widget(dashboard=dashboard, visualization=chart)
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "sales"})

        self.assertIn("Orders by week (line chart; x: week; y: amount; grouped by: region)", found)
        self.assertIn("Completed orders only.", found)
        self.assertIn("from query #{} Weekly numbers".format(query.id), found)

    def test_a_dashboard_is_found_by_its_charts_description(self):
        _, chart = self._weekly(description="Churn by signup cohort")
        dashboard = self.factory.create_dashboard(name="Board", is_draft=False)
        self.factory.create_widget(dashboard=dashboard, visualization=chart)
        models.db.session.commit()

        self.assertIn("Board", self.text("find_dashboards", {"question": "churn"}))

    def test_a_chart_you_cannot_read_says_nothing(self):
        # The dashboard itself is visible, but one panel sits on a data
        # source this user has no access to. On the page it is a locked
        # panel; here it must not be listed, nor make the dashboard match.
        outsiders = self.factory.create_group(name="Outsiders")
        models.db.session.add(outsiders)
        locked = self.factory.create_data_source(name="locked", group=outsiders)
        secret = self.factory.create_query(name="Payroll", description="", data_source=locked, is_draft=False)
        chart = self.factory.create_visualization(
            query_rel=secret, type="CHART", name="Salaries by team", description="Payroll by team"
        )
        dashboard = self.factory.create_dashboard(name="Mixed", is_draft=False)
        self.factory.create_widget(dashboard=dashboard, visualization=chart)
        models.db.session.add(models.Widget(dashboard=dashboard, width=1, text="Company overview", options={}))
        models.db.session.commit()

        self.assertIn("No dashboard matches", self.text("find_dashboards", {"question": "payroll"}))
        found = self.text("find_dashboards", {"question": "company overview"})
        self.assertIn("Mixed", found)
        self.assertNotIn("Salaries", found)
        self.assertNotIn("Payroll", found)


class TestTheAuditCannotBeSwitchedOff(McpTestCase):
    def test_a_long_session_header_does_not_lose_the_row(self):
        # The column holds 64 characters. A longer header made the insert
        # fail -- silently, with the request going ahead -- so a client could
        # turn its own audit trail off with one header.
        headers = {"Authorization": "Bearer {}".format(self.factory.user.api_key), "Mcp-Session-Id": "a" * 65}
        response = self.client.post(
            "/mcp", data=json.dumps(rpc("tools/list")), headers=headers, content_type="application/json"
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, models.McpEvent.query.count())
        self.assertIsNone(models.McpEvent.query.first().session_id)

    def test_a_notification_is_recorded_as_ignored_not_ok(self):
        # A message without an id is a notification: acknowledged, never run.
        self.post(
            rpc(
                "tools/call",
                {"name": "run_query", "arguments": {"sql": "DROP TABLE x", "data_source": "pg"}},
                message_id=None,
            )
        )

        outcomes = [event.outcome for event in models.McpEvent.query.all()]
        self.assertIn("ignored", outcomes)
        self.assertNotIn("ok", outcomes)

    def test_a_question_is_a_sentence_not_a_document(self):
        body = json.loads(
            self.post(rpc("tools/call", {"name": "find_context", "arguments": {"question": "word " * 1000}})).data
        )
        self.assertEqual(-32602, body["error"]["code"])


class TestExplainAndRun(McpTestCase):
    def call(self, name, arguments):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments})).data)

    def test_running_needs_a_named_data_source(self):
        # Guessing which warehouse to run somebody's SQL against is not a
        # thing to do on their behalf.
        body = self.call("run_query", {"sql": "SELECT 1"})
        self.assertEqual(-32602, body["error"]["code"])

    def test_the_editors_own_row_limit_is_applied(self):
        captured = {}

        def fake(user, source, sql, timeout):
            captured["sql"] = sql
            return {"columns": [{"name": "n"}], "rows": [{"n": 1}]}, None

        with mock.patch("sqldesk.mcp._on_a_worker", side_effect=fake):
            self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        self.assertIn("1000", captured["sql"], "the ceiling a person clicking Execute gets")

    def test_it_runs_on_a_worker_and_not_in_the_web_process(self):
        """
        A four-minute query run here would hold a web worker for four
        minutes, and would appear in nobody's list of running queries. The
        queue is what makes it cancellable and attributable.
        """
        finished = mock.Mock(is_finished=True, is_failed=False)
        finished.result = {"columns": [{"name": "n"}], "rows": [{"n": 1}]}

        with mock.patch("sqldesk.tasks.queries.enqueue_query") as enqueue:
            with mock.patch("sqldesk.tasks.Job.fetch", return_value=finished):
                with mock.patch.object(type(self.factory.data_source), "query_runner") as runner:
                    runner.apply_auto_limit.side_effect = lambda sql, _: sql
                    self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})

        self.assertTrue(enqueue.called, "the query has to go on the queue")
        runner.run_query.assert_not_called()
        # And it carries who asked, so the admin's list can say so.
        self.assertTrue(enqueue.call_args[1]["metadata"]["mcp"])

    def test_a_failing_query_reports_the_reason(self):
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(None, ['relation "nope" does not exist'])):
            body = self.call("run_query", {"sql": "SELECT * FROM nope", "data_source": self.factory.data_source.name})
        self.assertTrue(body["result"]["isError"])
        self.assertIn("does not exist", body["result"]["content"][0]["text"])

    def test_explain_returns_the_plan(self):
        plan = {"columns": [{"name": "QUERY PLAN"}], "rows": [{"QUERY PLAN": "Seq Scan on orders"}]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(plan, None)) as worker:
            body = self.call(
                "explain_query", {"sql": "SELECT * FROM orders", "data_source": self.factory.data_source.name}
            )
        self.assertIn("Seq Scan", body["result"]["content"][0]["text"])
        self.assertTrue(worker.call_args[0][2].startswith("EXPLAIN "))

    def test_every_row_the_query_was_allowed_to_return_is_returned(self):
        # The SQL is rewritten to ask for no more than ROW_LIMIT, so anything
        # under it has already been fetched and paid for. Rendering fewer only
        # hid rows somebody had already waited on.
        many = {"columns": [{"name": "n"}], "rows": [{"n": i} for i in range(500)]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(many, None)):
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        text = body["result"]["content"][0]["text"]

        self.assertNotIn("more rows returned", text)
        self.assertIn("499", text)
        self.assertEqual(501, len(text.splitlines()), "a header and 500 rows")

    def test_rows_past_the_ceiling_are_truncated_for_reading_not_silently(self):
        over = {"columns": [{"name": "n"}], "rows": [{"n": i} for i in range(mcp.ROW_LIMIT + 20)]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(over, None)):
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        text = body["result"]["content"][0]["text"]

        self.assertIn("20 more rows returned", text)

    def test_what_the_tool_promises_is_what_it_hands_back(self):
        """
        The description said "up to 1000 rows" while the rendering stopped at
        fifty, because the promise, the SQL rewrite and the rendering were
        three separate numbers and only two of them agreed.
        """
        tool = next(t for t in mcp.TOOLS if t["name"] == "run_query")
        self.assertIn(str(mcp.ROW_LIMIT), tool["description"])

        rows = {"columns": [{"name": "n"}], "rows": [{"n": i} for i in range(mcp.ROW_LIMIT)]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(rows, None)):
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        text = body["result"]["content"][0]["text"]

        self.assertNotIn("more rows returned", text)
        self.assertEqual(mcp.ROW_LIMIT + 1, len(text.splitlines()))

    def test_rows_are_tab_separated_rather_than_json(self):
        # The same rows cost two to three times as much when every key is
        # repeated on every row, and a thousand of them is where that tells.
        rows = {"columns": [{"name": "region"}, {"name": "n"}], "rows": [{"region": "EMEA", "n": 7}]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(rows, None)):
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        text = body["result"]["content"][0]["text"]

        self.assertEqual("region\tn", text.splitlines()[0])
        self.assertEqual("EMEA\t7", text.splitlines()[1])

    def test_the_new_tools_are_advertised(self):
        names = {t["name"] for t in json.loads(self.post(rpc("tools/list")).data)["result"]["tools"]}
        self.assertTrue({"find_queries", "find_dashboards", "explain_query", "run_query"} <= names)

    def test_a_query_the_warehouse_refuses_reports_what_it_said(self):
        """
        A refused query still *finishes* as far as the queue is concerned:
        the job returns a QueryExecutionError rather than raising. Handing
        that to the database as a result id got "can't adapt type
        'QueryExecutionError'", which is a long way from "that table does
        not exist".
        """
        from sqldesk.tasks.queries.execution import QueryExecutionError

        finished = mock.Mock(is_finished=True, is_failed=False)
        finished.result = QueryExecutionError('relation "nope" does not exist\nLINE 1: ...')

        with mock.patch("sqldesk.tasks.queries.enqueue_query"):
            with mock.patch("sqldesk.tasks.Job.fetch", return_value=finished):
                with mock.patch.object(type(self.factory.data_source), "query_runner") as runner:
                    runner.apply_auto_limit.side_effect = lambda sql, _: sql
                    body = self.call(
                        "run_query", {"sql": "SELECT * FROM nope", "data_source": self.factory.data_source.name}
                    )

        self.assertTrue(body["result"]["isError"])
        self.assertIn("does not exist", body["result"]["content"][0]["text"])
        self.assertNotIn("adapt type", body["result"]["content"][0]["text"])

    def test_the_result_is_fetched_by_id_rather_than_used_as_rows(self):
        # The job's result is a query_result id. Using it directly gets an
        # integer where a result should be.
        stored = mock.Mock()
        stored.data = {"columns": [{"name": "n"}], "rows": [{"n": 7}]}
        finished = mock.Mock(is_finished=True, is_failed=False)
        finished.result = 4242

        with mock.patch("sqldesk.tasks.queries.enqueue_query"):
            with mock.patch("sqldesk.tasks.Job.fetch", return_value=finished):
                with mock.patch("sqldesk.models.QueryResult.query") as q:
                    q.get.return_value = stored
                    with mock.patch.object(type(self.factory.data_source), "query_runner") as runner:
                        runner.apply_auto_limit.side_effect = lambda sql, _: sql
                        body = self.call(
                            "run_query", {"sql": "SELECT 7", "data_source": self.factory.data_source.name}
                        )

        q.get.assert_called_once_with(4242)
        self.assertIn("7", body["result"]["content"][0]["text"])


class TestDataSourceGuidance(McpTestCase):
    """
    A sentence about the source applies to every question asked of it, which
    makes it the highest-leverage context there is -- and there was nowhere
    to write one until now.
    """

    def _call(self, tool, arguments):
        response = self.post(rpc("tools/call", params={"name": tool, "arguments": arguments}))
        return json.loads(response.data)["result"]["content"][0]["text"]

    def test_listing_sources_repeats_what_the_admin_wrote(self):
        self.factory.data_source.description = "Finance warehouse. raw_* is untrusted."
        models.db.session.commit()

        self.assertIn("raw_* is untrusted", self._call("list_data_sources", {}))

    def test_a_source_without_one_adds_no_noise(self):
        self.factory.data_source.description = None
        models.db.session.commit()

        listed = self._call("list_data_sources", {})
        self.assertIn(self.factory.data_source.name, listed)
        self.assertNotIn("None", listed)


class TestQueueIsolation(McpTestCase):
    """
    An MCP query goes where the install says.

    By default that is the data source's own queue -- the same one dashboards
    use -- so a model exploring competes with the people waiting for a
    dashboard to load. Naming a queue is how an install stops that.
    """

    def _run(self):
        self.post(
            rpc(
                "tools/call",
                params={
                    "name": "run_query",
                    "arguments": {"sql": "SELECT 1", "data_source": self.factory.data_source.name},
                },
            )
        )

    def test_by_default_it_shares_the_data_sources_queue(self):
        with mock.patch("sqldesk.tasks.queries.enqueue_query") as enqueue:
            enqueue.return_value.id = "job-1"
            with mock.patch.object(settings, "MCP_QUEUE", ""):
                self._run()

        self.assertIsNone(enqueue.call_args[1]["queue_name"])

    def test_a_named_queue_is_used_instead(self):
        with mock.patch("sqldesk.tasks.queries.enqueue_query") as enqueue:
            enqueue.return_value.id = "job-1"
            with mock.patch.object(settings, "MCP_QUEUE", "mcp"):
                self._run()

        self.assertEqual("mcp", enqueue.call_args[1]["queue_name"])


class TestNoMoreThanTheApplicationGives(McpTestCase):
    """
    An MCP client is its user, and gets exactly what that user gets in the
    browser -- not more because the question came in over JSON-RPC.
    """

    def call(self, name, arguments, user=None):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments}), user=user).data)

    def text(self, body):
        return body["result"]["content"][0]["text"]

    def _viewer(self):
        # A group that may look at `viewonly` and nothing else, the way an
        # admin sets up people who read dashboards but do not write SQL.
        group = self.factory.create_group(name="Viewers", permissions=models.Group.DEFAULT_PERMISSIONS + ["use_mcp"])
        source = self.factory.create_data_source(name="viewonly", group=group, view_only=True)
        user = self.factory.create_user(group_ids=[group.id], email="viewer@example.com")
        models.db.session.commit()
        return user, source

    def _hidden(self):
        # The user can read a source of their own, so a refusal below is the
        # filter at work rather than a user who can read nothing at all.
        self.factory.data_source
        # In no group at all: nobody but an admin can read it.
        source = self.factory.create_data_source(name="hidden")
        table = models.CatalogTable(
            org=self.factory.org, data_source=source, name="salaries", usage_count=99, card="salaries(amount)"
        )
        models.db.session.add(table)
        models.db.session.flush()
        models.db.session.add(models.CatalogColumn(catalog_table=table, name="amount", type="decimal", usage_count=9))
        models.db.session.commit()
        return source

    def test_a_view_only_user_cannot_run_sql(self):
        user, source = self._viewer()
        with mock.patch("sqldesk.mcp._on_a_worker") as worker:
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": source.name}, user=user)
        self.assertEqual(-32602, body["error"]["code"])
        self.assertIn("full access", body["error"]["message"])
        worker.assert_not_called()

    def test_a_view_only_user_cannot_explain_either(self):
        # EXPLAIN is SQL of the caller's own, run on the warehouse.
        user, source = self._viewer()
        with mock.patch("sqldesk.mcp._on_a_worker") as worker:
            body = self.call("explain_query", {"sql": "SELECT 1", "data_source": source.name}, user=user)
        self.assertEqual(-32602, body["error"]["code"])
        worker.assert_not_called()

    def test_a_view_only_user_can_still_look(self):
        user, source = self._viewer()
        self.assertIn("viewonly", self.text(self.call("list_data_sources", {}, user=user)))

    def test_the_catalog_of_a_source_you_cannot_read_is_not_searched(self):
        self._hidden()
        text = self.text(self.call("find_context", {"question": "salaries amount"}))
        self.assertNotIn("salaries", text)

    def test_nor_can_its_tables_be_expanded_by_name(self):
        self._hidden()
        body = self.call("expand_table", {"names": ["salaries"]})
        self.assertEqual(-32602, body["error"]["code"])

    def test_a_dashboard_on_a_source_you_cannot_read_is_not_found(self):
        hidden = self._hidden()
        owner = self.factory.create_user(email="owner@example.com")
        query = self.factory.create_query(name="Salaries", data_source=hidden, user=owner)
        dashboard = self.factory.create_dashboard(name="Salaries board", user=owner, is_draft=False)
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query)
        )
        models.db.session.commit()
        self.assertIn("No dashboard", self.text(self.call("find_dashboards", {"question": "salaries"})))

    def test_a_colleagues_dashboard_on_a_shared_source_is_found(self):
        owner = self.factory.create_user(email="colleague@example.com")
        query = self.factory.create_query(name="Revenue", data_source=self.factory.data_source, user=owner)
        dashboard = self.factory.create_dashboard(name="Money", user=owner, is_draft=False)
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query)
        )
        models.db.session.commit()
        text = self.text(self.call("find_dashboards", {"question": "revenue"}))
        self.assertIn("Money", text)
        self.assertIn("1 widgets", text)


class TestARowCeiling(McpTestCase):
    """
    `run_query` returns at most 1,000 rows, whatever the SQL says. It relied on
    the runners' `apply_auto_limit`, which only acts on a statement starting
    with SELECT: a WITH query, an explicit large LIMIT, or anything on Athena
    or Presto brought back every row, into a web worker.
    """

    def setUp(self):
        super().setUp()
        self.factory.data_source.name = "pg"
        models.db.session.commit()
        self.worker = mock.patch("sqldesk.mcp._on_a_worker", return_value=({"columns": [], "rows": []}, None))
        self.ran = self.worker.start()
        self.addCleanup(self.worker.stop)

    def sent(self, sql, source_type="pg"):
        self.factory.data_source.type = source_type
        models.db.session.commit()
        self.post(rpc("tools/call", {"name": "run_query", "arguments": {"sql": sql, "data_source": "pg"}}))
        return self.ran.call_args[0][2]

    def test_a_with_query_is_limited(self):
        self.assertIn("LIMIT 1000", self.sent("WITH x AS (SELECT 1 AS a) SELECT * FROM x"))

    def test_a_larger_limit_is_lowered(self):
        sent = self.sent("SELECT * FROM t LIMIT 10000000")
        self.assertIn("LIMIT 1000", sent)
        self.assertNotIn("10000000", sent)

    def test_a_smaller_one_is_left_as_written(self):
        self.assertEqual("SELECT * FROM t LIMIT 5", self.sent("SELECT * FROM t LIMIT 5"))

    def test_a_union_is_limited_as_a_whole(self):
        self.assertTrue(self.sent("SELECT 1 UNION ALL SELECT 2").rstrip().endswith("LIMIT 1000"))

    def test_sql_server_gets_top_and_keeps_its_order_by(self):
        sent = self.sent("SELECT a FROM t ORDER BY a", source_type="mssql")
        self.assertIn("TOP 1000", sent)
        self.assertIn("ORDER BY a", sent)

    def test_athena_is_limited_too(self):
        self.assertIn("LIMIT 1000", self.sent("SELECT * FROM t", source_type="athena"))


class TestOnlyReadsRunFromHere(McpTestCase):
    """
    Not the security boundary -- the database account's grants are -- but a
    model should not delete anything by accident, and EXPLAIN should never
    run what it was asked only to plan.
    """

    def call(self, name, sql):
        body = self.post(rpc("tools/call", {"name": name, "arguments": {"sql": sql, "data_source": "pg"}}))
        return json.loads(body.data)

    def setUp(self):
        super().setUp()
        self.factory.data_source.name = "pg"
        models.db.session.commit()
        self.worker = mock.patch("sqldesk.mcp._on_a_worker", return_value=({"columns": [], "rows": []}, None))
        self.ran = self.worker.start()
        self.addCleanup(self.worker.stop)

    def assertRefused(self, name, sql):
        body = self.call(name, sql)
        self.assertTrue(body["result"]["isError"], sql)
        self.ran.assert_not_called()
        return body["result"]["content"][0]["text"]

    def test_a_write_is_refused(self):
        self.assertIn("DELETE", self.assertRefused("run_query", "DELETE FROM orders"))

    def _as(self, source_type):
        self.factory.data_source.type = source_type
        models.db.session.commit()

    def test_sql_engines_on_the_plain_runner_class_are_checked_too(self):
        # Athena and Presto are SQL engines built on the plain base class,
        # which the guard used to take for "not SQL" and wave through.
        for source_type, sql in (
            ("athena", "DROP TABLE analytics.orders"),
            ("presto", "INSERT INTO t SELECT 1"),
            ("Cassandra", "DROP KEYSPACE k"),
            ("couchbase", "DELETE FROM bucket"),
        ):
            self._as(source_type)
            self.assertRefused("run_query", sql)

    def test_a_language_the_guard_cannot_read_is_refused(self):
        self._as("azure_kusto")
        self.assertIn("editor", self.assertRefused("run_query", ".drop table T"))

    def test_a_mongodb_read_goes_through(self):
        self._as("mongodb")
        body = self.call("run_query", '{"collection": "orders", "query": {}}')
        self.assertFalse(body["result"].get("isError"), body)
        self.ran.assert_called_once()

    def test_a_mongodb_pipeline_that_writes_is_refused(self):
        # `$out` replaces a collection and `$merge` writes into one, from an
        # ordinary aggregate. MongoDB was waved through as "read-only".
        self._as("mongodb")
        self.assertIn(
            "$out", self.assertRefused("run_query", '{"collection": "x", "aggregate": [{"$out": "orders"}]}')
        )
        self.assertIn(
            "$merge",
            self.assertRefused(
                "run_query",
                '{"collection": "x", "aggregate": [{"$facet": {"a": [{"$merge": {"into": "orders"}}]}}]}',
            ),
        )

    def test_a_json_source_may_get_but_not_post(self):
        self._as("json")
        self.assertIn("POST", self.assertRefused("run_query", "url: https://api.example.com/x\nmethod: post"))
        body = self.call("run_query", "url: https://api.example.com/x")
        self.assertFalse(body["result"].get("isError"), body)

    def test_a_second_statement_needs_no_semicolon_on_sql_server(self):
        # T-SQL runs a batch: sqlglot read `SELECT 1 DELETE FROM t` as one
        # SELECT with an alias, and SQL Server ran both.
        self._as("mssql")
        self.assertIn("DELETE", self.assertRefused("run_query", "SELECT 1 DELETE FROM dbo.orders"))
        self.assertIn("EXEC", self.assertRefused("run_query", "SELECT 1 EXEC xp_cmdshell 'dir'"))
        self.assertIn("WAITFOR", self.assertRefused("run_query", "SELECT 1 WAITFOR DELAY '00:10:00'"))

    def test_a_write_the_parser_cannot_read_is_still_refused(self):
        # MySQL's INTO OUTFILE writes a file on the database host; sqlglot
        # fails to parse it, and the first word is SELECT.
        self._as("mysql")
        self.assertIn("INTO", self.assertRefused("run_query", "SELECT * FROM t INTO OUTFILE '/tmp/x'"))

    def test_words_that_only_look_like_writes_run(self):
        body = self.call(
            "run_query",
            """SELECT update_time, delete_flag, 'delete' AS kind, "insert" FROM updates WHERE created > now()""",
        )
        self.assertFalse(body["result"].get("isError"), body)
        self.ran.assert_called_once()

    def test_a_second_statement_is_refused(self):
        self.assertIn("One statement", self.assertRefused("run_query", "SELECT 1; DROP TABLE orders"))

    def test_a_select_that_deletes_is_refused(self):
        self.assertRefused("run_query", "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone")

    def test_select_into_is_refused(self):
        self.assertRefused("run_query", "SELECT * INTO copy_of_orders FROM orders")

    def test_explain_analyze_is_refused(self):
        # EXPLAIN ANALYZE DELETE deletes.
        self.assertRefused("explain_query", "ANALYZE DELETE FROM orders")

    def test_a_read_runs(self):
        self.assertFalse(self.call("run_query", "SELECT id FROM orders")["result"]["isError"])
        self.assertFalse(self.call("run_query", "SHOW search_path")["result"]["isError"])
        self.assertEqual(2, self.ran.call_count)

    def test_sql_the_parser_cannot_read_is_judged_by_its_first_word(self):
        with mock.patch("sqldesk.mcp.sqlglot.parse", side_effect=ValueError("no")):
            self.assertFalse(self.call("run_query", "select strange syntax")["result"]["isError"])
            self.ran.reset_mock()
            self.assertRefused("run_query", "VACUUM strange syntax")
            self.assertRefused("run_query", "SELECT 1; VACUUM")

    def test_a_python_data_source_is_not_a_models_to_run(self):
        self.factory.data_source.type = "python"
        models.db.session.commit()
        self.assertIn("Python", self.assertRefused("run_query", "print(1)"))


class TestLimits(McpTestCase):
    def test_a_batch_has_a_ceiling(self):
        batch = [rpc("ping", message_id=i) for i in range(11)]
        response = self.post(batch)
        self.assertEqual(400, response.status_code)
        self.assertEqual(-32600, json.loads(response.data)["error"]["code"])

    def test_an_empty_batch_is_not_a_request(self):
        self.assertEqual(400, self.post([]).status_code)

    def test_a_small_batch_is_answered(self):
        body = json.loads(self.post([rpc("ping", message_id=1), rpc("ping", message_id=2)]).data)
        self.assertEqual([1, 2], [reply["id"] for reply in body])

    def test_arguments_must_be_an_object(self):
        body = json.loads(self.post(rpc("tools/call", {"name": "find_context", "arguments": ["x"]})).data)
        self.assertEqual(-32602, body["error"]["code"])

    def test_enormous_sql_is_refused_before_it_is_parsed(self):
        sql = "SELECT 1 -- " + "x" * 200000
        with mock.patch("sqldesk.mcp.analyze") as analyze:
            body = json.loads(self.post(rpc("tools/call", {"name": "check_sql", "arguments": {"sql": sql}})).data)
        self.assertEqual(-32602, body["error"]["code"])
        analyze.assert_not_called()

    def test_expand_table_takes_a_bounded_list(self):
        names = ["t{}".format(i) for i in range(21)]
        body = json.loads(self.post(rpc("tools/call", {"name": "expand_table", "arguments": {"names": names}})).data)
        self.assertEqual(-32602, body["error"]["code"])

    def test_a_request_that_has_used_its_time_queues_nothing(self):
        # A query nobody will wait for would still run, and cost the
        # warehouse for nothing.
        from sqldesk.mcp import _on_a_worker, time_budget

        with mock.patch("sqldesk.tasks.queries.enqueue_query") as enqueue:
            with time_budget(1):
                result, error = _on_a_worker(self.factory.user, self.factory.data_source, "SELECT 1", timeout=45)
        self.assertIsNone(result)
        self.assertIn("used its time", error[0])
        enqueue.assert_not_called()

    def test_the_budget_stays_under_the_web_servers_timeout(self):
        self.assertLess(settings.MCP_TIME_BUDGET, 60)


class TestCsrf(McpTestCase):
    def test_the_endpoint_is_exempt_from_csrf(self):
        """
        CSRF protects cookie sessions. With SQLDESK_ENFORCE_CSRF on -- the
        development compose file sets it -- a Bearer-key call is not a
        session, so it was refused before anybody was identified. The check
        in `sqldesk.security` reads the exempt list by dotted name.
        """
        from sqldesk.security import csrf

        self.assertIn("sqldesk.handlers.mcp.mcp_endpoint", csrf._exempt_views)


class TestTheAuditHasLimits(McpTestCase):
    def test_refusals_past_the_minutes_allowance_are_refused_but_not_written(self):
        with mock.patch.object(settings, "MCP_AUDIT_REFUSALS_PER_MINUTE", 3):
            statuses = [
                self.client.post("/mcp", data=json.dumps(rpc("ping")), content_type="application/json").status_code
                for _ in range(5)
            ]
        self.assertEqual([401] * 5, statuses, "still refused, every time")
        self.assertEqual(3, models.McpEvent.query.filter(models.McpEvent.outcome == "refused").count())

    def test_a_working_key_is_not_held_back_by_somebody_elses_refusals(self):
        with mock.patch.object(settings, "MCP_AUDIT_REFUSALS_PER_MINUTE", 1):
            for _ in range(3):
                self.client.post("/mcp", data=json.dumps(rpc("ping")), content_type="application/json")
            response = self.post(rpc("ping"))
        self.assertEqual(200, response.status_code)

    def test_old_rows_are_pruned_and_recent_ones_kept(self):
        import datetime

        from sqldesk.tasks.queries.maintenance import cleanup_mcp_events

        old = models.McpEvent(org=self.factory.org, method="ping", outcome="ok")
        new = models.McpEvent(org=self.factory.org, method="ping", outcome="ok")
        models.db.session.add_all([old, new])
        models.db.session.flush()
        old.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=200)
        models.db.session.commit()

        with mock.patch.object(settings, "MCP_AUDIT_RETENTION_DAYS", 90):
            self.assertEqual(1, cleanup_mcp_events())
        self.assertEqual([new.id], [e.id for e in models.McpEvent.query.all()])

    def test_zero_keeps_everything(self):
        from sqldesk.tasks.queries.maintenance import cleanup_mcp_events

        with mock.patch.object(settings, "MCP_AUDIT_RETENTION_DAYS", 0):
            self.assertEqual(0, cleanup_mcp_events())


class TestRunningNeedsWhatTheEditorNeeds(McpTestCase):
    def call(self, name, sql="SELECT 1", user=None):
        body = rpc(
            "tools/call", {"name": name, "arguments": {"sql": sql, "data_source": self.factory.data_source.name}}
        )
        return json.loads(self.post(body, user=user).data)

    def test_without_execute_query_nothing_runs(self):
        group = self.factory.create_group(name="Readers", permissions=["view_query", "use_mcp"])
        models.db.session.add(
            models.DataSourceGroup(group=group, data_source=self.factory.data_source, view_only=False)
        )
        reader = self.factory.create_user(group_ids=[group.id], email="reader@example.com")
        models.db.session.commit()
        with mock.patch("sqldesk.mcp._on_a_worker") as worker:
            for tool in ("run_query", "explain_query"):
                body = self.call(tool, user=reader)
                self.assertEqual(-32602, body["error"]["code"], tool)
                self.assertIn("running queries", body["error"]["message"])
        worker.assert_not_called()

    def test_a_paused_source_is_refused_with_its_reason(self):
        self.factory.data_source.pause("migrating")
        models.db.session.commit()
        with mock.patch("sqldesk.mcp._on_a_worker") as worker:
            body = self.call("run_query")
        self.assertIn("paused (migrating)", body["error"]["message"])
        worker.assert_not_called()


class MeasureTestCase(McpTestCase):
    """
    The point of a semantic layer is that agreed meaning comes first. A model
    that reads the schema before it reads the definitions will write its own
    definition of revenue, and the wrong revenue number is still a revenue
    number -- it arrives with all the authority of having been asked for.
    """

    def setUp(self):
        super().setUp()
        self.source = self.factory.data_source
        table = models.CatalogTable(
            org=self.factory.org,
            data_source=self.source,
            name="orders",
            card="orders(id int, amount numeric, region text)",
            usage_count=9,
        )
        models.db.session.add(table)
        models.db.session.commit()

    def call(self, name, arguments=None):
        body = json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)
        return body["result"]["content"][0]["text"]

    def measure(self, name, status=models.MEASURE_APPROVED, **overrides):
        fields = {
            "org": self.factory.org,
            "data_source": self.source,
            "table_name": "orders",
            "name": name,
            "kind": "sum",
            "column_name": "amount",
            "usage_count": 3,
            "status": status,
        }
        fields.update(overrides)
        measure = models.CatalogMeasure(**fields)
        models.db.session.add(measure)
        models.db.session.commit()
        return measure


class TestFindContextLeadsWithAgreedMeasures(MeasureTestCase):
    def test_an_agreed_measure_comes_before_the_schema(self):
        self.measure("gross_revenue", description="Before refunds.")

        text = self.call("find_context", {"question": "orders revenue"})

        self.assertIn("gross_revenue", text)
        self.assertLess(
            text.index("gross_revenue"),
            text.index("orders(id int"),
            "the agreed measure has to be read before the columns, or it is a footnote",
        )

    def test_and_says_what_it_computes(self):
        self.measure("gross_revenue", description="Before refunds.")

        text = self.call("find_context", {"question": "orders revenue"})

        self.assertIn("SUM(amount)", text)
        self.assertIn("Before refunds.", text)

    def test_a_merely_proposed_measure_is_not_offered(self):
        # Mined from somebody's SQL and signed off by nobody. Silence beats a
        # guess about what a number means.
        self.measure("maybe_revenue", status=models.MEASURE_PROPOSED)

        self.assertNotIn("maybe_revenue", self.call("find_context", {"question": "orders revenue"}))

    def test_nor_is_a_denied_one(self):
        self.measure("wrong_revenue", status=models.MEASURE_DENIED)

        self.assertNotIn("wrong_revenue", self.call("find_context", {"question": "orders revenue"}))

    def test_the_ones_most_people_compute_come_first(self):
        # Named so that alphabetical order is the *opposite* of usage order.
        # The first version of this test used `common_total` and `rare_total`,
        # which sort the right way by accident -- it passed with the usage
        # ranking replaced by a sort on the name.
        self.measure("a_rare_total", usage_count=1)
        self.measure("z_common_total", usage_count=40)

        text = self.call("find_context", {"question": "orders revenue"})

        self.assertLess(text.index("z_common_total"), text.index("a_rare_total"))


class TestFindMeasures(MeasureTestCase):
    def test_it_finds_one_by_what_it_is_called(self):
        self.measure("gross_revenue")

        self.assertIn("gross_revenue", self.call("find_measures", {"question": "revenue"}))

    def test_and_by_what_the_curator_wrote_about_it(self):
        # The description is where a curator says what the thing means, and a
        # question will often use those words rather than the column's.
        self.measure("gmv", description="Takings before refunds are deducted.")

        self.assertIn("gmv", self.call("find_measures", {"question": "takings"}))

    def test_with_no_question_it_lists_them_all(self):
        self.measure("gross_revenue")
        self.measure("order_count", kind="count", column_name="id")

        text = self.call("find_measures", {})

        self.assertIn("gross_revenue", text)
        self.assertIn("order_count", text)

    def test_a_proposed_one_is_never_listed(self):
        self.measure("maybe_revenue", status=models.MEASURE_PROPOSED)

        self.assertNotIn("maybe_revenue", self.call("find_measures", {}))

    def test_the_ones_most_people_compute_are_listed_first(self):
        # Alphabetically backwards on purpose: a list truncated at fifty has
        # to drop the measures nobody computes, not the ones late in the
        # alphabet.
        self.measure("a_rare_total", usage_count=1)
        self.measure("z_common_total", usage_count=40)

        text = self.call("find_measures", {"question": "total"})

        self.assertLess(text.index("z_common_total"), text.index("a_rare_total"))

    def test_when_there_are_none_it_says_to_write_the_aggregate_yourself(self):
        text = self.call("find_measures", {"question": "revenue"})

        self.assertIn("No agreed measures", text)
        self.assertIn("yourself", text)

    def test_a_measure_on_a_source_this_person_cannot_read_is_not_shown(self):
        # A measure names a table and a column, which is itself something a
        # group may not be allowed to see.
        other_group = self.factory.create_group(name="Theirs")
        models.db.session.add(other_group)
        models.db.session.commit()
        theirs = self.factory.create_data_source(group=other_group, name="theirs")
        models.db.session.add(
            models.CatalogMeasure(
                org=self.factory.org,
                data_source=theirs,
                table_name="secrets",
                name="their_revenue",
                kind="sum",
                column_name="amount",
                status=models.MEASURE_APPROVED,
            )
        )
        models.db.session.commit()

        self.assertNotIn("their_revenue", self.call("find_measures", {}))

    def test_the_tool_is_offered_to_clients(self):
        body = json.loads(self.post(rpc("tools/list")).data)

        self.assertIn("find_measures", [tool["name"] for tool in body["result"]["tools"]])


class TestVerifiedQueriesComeFirst(McpTestCase):
    """
    A verified query is a person saying "this whole question -- which rows to
    exclude, which join is right -- has been answered correctly". Nothing a
    schema contains comes close, so it has to outrank recency.
    """

    def call(self, name, arguments=None):
        body = json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)
        return body["result"]["content"][0]["text"]

    def query(self, name, text="select 1", updated_days_ago=0):
        """
        A saved query, optionally aged.

        Ageing matters: two queries created in one test share an `updated_at`
        to the microsecond, so the recency tie breaks on physical row order
        and an ordering test passes whatever the ORDER BY says. The first
        version of the test below did exactly that -- it survived the ranking
        being deleted. Written through SQL because `updated_at` carries an
        `onupdate`, which would overwrite an assignment.
        """
        query = self.factory.create_query(name=name, query_text=text, is_draft=False)
        models.db.session.commit()
        if updated_days_ago:
            models.db.session.execute(
                "update queries set updated_at = now() - interval ':days days' where id = :id".replace(
                    ":days", str(int(updated_days_ago))
                ),
                {"id": query.id},
            )
            models.db.session.commit()
        return query

    def verify(self, query, **fields):
        # `query_id` rather than `query_rel`: assigning the relationship
        # dirties the query, and the commit then bumps its `updated_at`. That
        # made the confirmed query the most recent one too, so the ordering
        # tests passed on recency alone and survived the ranking being deleted.
        row = models.CatalogVerifiedQuery(
            org=self.factory.org,
            query_id=query.id,
            verified_by=self.factory.user,
            query_hash=query.query_hash,
            **fields,
        )
        models.db.session.add(row)
        models.db.session.commit()
        return row

    def test_it_outranks_a_more_recent_unverified_one(self):
        confirmed = self.query("revenue by region, checked", updated_days_ago=30)
        self.query("revenue by region, draft attempt")  # today, and nobody has read it
        self.verify(confirmed)

        text = self.call("find_queries", {"question": "revenue by region"})

        self.assertLess(text.index("checked"), text.index("draft attempt"))

    def test_a_confirmation_that_has_gone_stale_does_not_keep_the_top_spot(self):
        # Ranking has to read the hash too, not only the id: a query confirmed
        # a year ago and rewritten last week must take its place by date like
        # anything else.
        stale = self.query("revenue by region, once checked", text="select 1", updated_days_ago=30)
        self.verify(stale)
        stale.query_text = "select 2"
        stale.query_hash = models.utils.gen_query_hash(stale.query_text)
        models.db.session.commit()
        self.query("revenue by region, newer")

        text = self.call("find_queries", {"question": "revenue by region"})

        self.assertLess(text.index("newer"), text.index("once checked"))

    def test_nor_does_another_organisations_confirmation_win_it(self):
        ours = self.query("revenue by region, ours", updated_days_ago=30)
        other = self.factory.create_org()
        models.db.session.add(
            models.CatalogVerifiedQuery(
                org=other,
                query_id=ours.id,
                verified_by=self.factory.user,
                query_hash=ours.query_hash,
            )
        )
        models.db.session.commit()
        self.query("revenue by region, newer")

        text = self.call("find_queries", {"question": "revenue by region"})

        self.assertLess(text.index("newer"), text.index("ours"))

    def test_and_says_so(self):
        self.verify(self.query("revenue by region"))

        self.assertIn("VERIFIED", self.call("find_queries", {"question": "revenue"}))

    def test_an_unverified_one_is_not_labelled(self):
        self.query("revenue by region")

        self.assertNotIn("VERIFIED", self.call("find_queries", {"question": "revenue"}))

    def test_it_names_who_confirmed_it(self):
        self.verify(self.query("revenue by region"))

        self.assertIn(self.factory.user.name, self.call("find_queries", {"question": "revenue"}))

    def test_and_the_question_they_said_it_answers(self):
        # The query's name drifts towards the technical; the question is what
        # somebody would actually type.
        self.verify(self.query("daily_active_v3"), question="How many people used it yesterday?")

        text = self.call("find_queries", {"question": "daily_active_v3"})

        self.assertIn("How many people used it yesterday?", text)

    def test_a_query_edited_since_is_no_longer_verified(self):
        query = self.query("revenue by region", text="select 1")
        self.verify(query)
        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        models.db.session.commit()

        self.assertNotIn("VERIFIED", self.call("find_queries", {"question": "revenue"}))

    def test_and_is_not_described_as_stale_either(self):
        # Same rule as the measures: a model cannot weigh "verified, but the
        # SQL changed" -- it reads the first word. The curator is told, on a
        # page where it can be acted on.
        query = self.query("revenue by region", text="select 1")
        self.verify(query, question="What did we take?")
        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        models.db.session.commit()

        text = self.call("find_queries", {"question": "revenue"})

        self.assertIn("revenue by region", text)
        self.assertNotIn("What did we take?", text)

    def test_another_organisations_confirmation_does_not_label_our_query(self):
        query = self.query("revenue by region")
        other = self.factory.create_org()
        models.db.session.add(
            models.CatalogVerifiedQuery(
                org=other,
                query_id=query.id,
                verified_by=self.factory.user,
                query_hash=query.query_hash,
            )
        )
        models.db.session.commit()

        self.assertNotIn("VERIFIED", self.call("find_queries", {"question": "revenue"}))


class TestSayingTheCatalogIsOld(McpTestCase):
    """
    A stale catalog is dangerous in a way an empty one is not. Every card is
    still there, perfectly formatted, describing last month's warehouse -- and
    a model handed it writes confident SQL against a column that was renamed.
    The error it gets back, if any, is about syntax rather than about the
    catalog being old.
    """

    def call(self, name, arguments=None):
        body = json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)
        return body["result"]["content"][0]["text"]

    def harvested(self, days_ago, source=None, name="orders"):
        source = source or self.factory.data_source
        models.db.session.add(
            models.CatalogTable(
                org=self.factory.org,
                data_source=source,
                name=name,
                card="{}(id int, amount numeric)".format(name),
                usage_count=5,
                harvested_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago),
            )
        )
        models.db.session.commit()
        return source

    def test_a_fresh_catalog_says_nothing(self):
        # A note on every single answer is a note nobody reads by the third.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            self.harvested(0)

            self.assertNotIn("Warning", self.call("find_context", {"question": "orders"}))

    def test_an_old_one_warns_before_the_schema(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            self.harvested(10)

            text = self.call("find_context", {"question": "orders"})

            self.assertIn("has not been harvested", text)
            self.assertLess(text.index("Warning"), text.index("orders(id int"))

    def test_and_says_how_long_and_which_source(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            source = self.harvested(10)

            text = self.call("find_context", {"question": "orders"})

            self.assertIn("10 days", text)
            self.assertIn(source.name, text)

    def test_the_answer_itself_is_still_given(self):
        # A warning that replaced the answer would be worse than no warning.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            self.harvested(10)

            self.assertIn("orders(id int", self.call("find_context", {"question": "orders"}))

    def test_a_question_narrowed_to_a_fresh_source_is_not_warned(self):
        # Warning about a stale source nobody asked about trains people to
        # ignore the warning.
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            fresh = self.factory.create_data_source(name="Fresh", group=self.factory.default_group)
            self.harvested(100)
            self.harvested(0, source=fresh, name="invoices")

            text = self.call("find_context", {"question": "invoices", "data_source": "Fresh"})

            self.assertNotIn("Warning", text)

    def test_a_broken_freshness_check_does_not_cost_the_answer(self):
        with mock.patch("sqldesk.settings.CATALOG_HARVEST_SCHEDULE", 24):
            self.harvested(10)
            with mock.patch("sqldesk.ai.catalog.freshness.stale_sources", side_effect=RuntimeError("no")):
                text = self.call("find_context", {"question": "orders"})

            self.assertIn("orders(id int", text)
            self.assertNotIn("Warning", text)


class TestRefusingAQueryThatCostsTooMuch(McpTestCase):
    """
    A model exploring a warehouse writes queries nobody reviewed. Most are
    cheap; the expensive ones show up on a bill or on somebody else's
    dashboard, and by then the model has moved on.

    The estimate is always the engine's own, and **no answer is never a
    refusal** -- refusing a query for a reason that is not true would be worse
    than running an expensive one.
    """

    def setUp(self):
        super().setUp()
        self.source = self.factory.create_data_source(name="Warehouse", type="pg", group=self.factory.default_group)

    def call(self, sql="select * from orders"):
        body = json.loads(
            self.post(
                rpc("tools/call", {"name": "run_query", "arguments": {"sql": sql, "data_source": "Warehouse"}})
            ).data
        )
        return body["result"]

    def answering(self, plan_cost=None, rows=None):
        """Stand in for the worker that runs EXPLAIN and the query."""

        def run(user, source, statement, timeout=None):
            if "FORMAT JSON" in statement:
                if plan_cost is None:
                    return None, ["no plan"]
                return {"rows": [{"QUERY PLAN": [{"Plan": {"Total Cost": plan_cost}}]}]}, None
            return rows or {"columns": [{"name": "n"}], "rows": [{"n": 1}]}, None

        return mock.patch("sqldesk.mcp._on_a_worker", side_effect=run)

    def test_a_query_over_the_ceiling_is_refused(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with self.answering(plan_cost=50_000):
                result = self.call()

        self.assertTrue(result["isError"])
        self.assertIn("50,000", result["content"][0]["text"])
        self.assertIn("1,000", result["content"][0]["text"])

    def test_and_told_what_to_do_instead(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with self.answering(plan_cost=50_000):
                result = self.call()

        self.assertIn("Narrow it", result["content"][0]["text"])

    def test_one_under_it_runs(self):
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with self.answering(plan_cost=10):
                result = self.call()

        self.assertFalse(result["isError"])

    def test_with_no_ceiling_nothing_is_estimated(self):
        # And no EXPLAIN is run: a round trip per query to compare against
        # nothing is a round trip for nobody.
        statements = []

        def run(user, source, statement, timeout=None):
            statements.append(statement)
            return {"columns": [{"name": "n"}], "rows": [{"n": 1}]}, None

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 0):
            with mock.patch("sqldesk.mcp._on_a_worker", side_effect=run):
                self.call()

        self.assertEqual([], [s for s in statements if "FORMAT JSON" in s])

    def test_an_explain_that_failed_lets_the_query_run(self):
        # Usually the engine saying the SQL is wrong, which it will say again
        # in its own words when the query runs.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with self.answering(plan_cost=None):
                result = self.call()

        self.assertFalse(result["isError"])

    def test_an_estimate_that_broke_lets_the_query_run(self):
        # Not a refusal, and not a 500 either. Whatever went wrong in the
        # estimate -- a runner that raised, a plan shaped in a way nothing
        # here expected -- the query itself is still a query somebody asked
        # for, and refusing it would refuse it for a reason that is not true.
        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with mock.patch("sqldesk.mcp.cost.estimate", side_effect=RuntimeError("the estimate broke")):
                with self.answering(plan_cost=10):
                    result = self.call()

        self.assertFalse(result["isError"])

    def test_an_engine_with_no_estimate_is_unaffected(self):
        mysql = self.factory.create_data_source(name="MySQL", type="mysql", group=self.factory.default_group)
        statements = []

        def run(user, source, statement, timeout=None):
            statements.append(statement)
            return {"columns": [{"name": "n"}], "rows": [{"n": 1}]}, None

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1):
            with mock.patch("sqldesk.mcp._on_a_worker", side_effect=run):
                body = json.loads(
                    self.post(
                        rpc(
                            "tools/call",
                            {"name": "run_query", "arguments": {"sql": "select 1", "data_source": mysql.name}},
                        )
                    ).data
                )

        self.assertFalse(body["result"]["isError"])
        self.assertEqual([], [s for s in statements if "FORMAT JSON" in s])

    def test_the_estimate_is_of_the_query_as_written(self):
        # Not of the auto-limited form: a LIMIT does not make a full scan
        # cheap, and estimating the limited query would let one through on a
        # number that is not the one that matters.
        estimated = []

        def run(user, source, statement, timeout=None):
            if "FORMAT JSON" in statement:
                estimated.append(statement)
                return {"rows": [{"QUERY PLAN": [{"Plan": {"Total Cost": 10}}]}]}, None
            return {"columns": [{"name": "n"}], "rows": [{"n": 1}]}, None

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with mock.patch("sqldesk.mcp._on_a_worker", side_effect=run):
                self.call(sql="select * from orders")

        self.assertNotIn("LIMIT", estimated[0].upper())

    def test_a_refused_query_is_never_run(self):
        ran = []

        def run(user, source, statement, timeout=None):
            if "FORMAT JSON" in statement:
                return {"rows": [{"QUERY PLAN": [{"Plan": {"Total Cost": 50_000}}]}]}, None
            ran.append(statement)
            return {"columns": [], "rows": []}, None

        with mock.patch("sqldesk.settings.MCP_MAX_QUERY_COST", 1000):
            with mock.patch("sqldesk.mcp._on_a_worker", side_effect=run):
                self.call()

        self.assertEqual([], ran)


class TestMyOwnMcpActivity(McpTestCase):
    """
    The My MCP page's endpoint.

    The difference from the audit is the point. The audit names every user,
    every question and every address, which is what it is for. This names
    nobody else and carries **no question, no SQL and no arguments** -- and it
    cannot be asked about another user at all, which is a stronger statement
    than a page that merely does not ask.
    """

    def mine(self, user=None):
        return self.make_request("get", "/api/mcp/mine", user=user or self.factory.user)

    def event(self, user=None, minutes_ago=1, **fields):
        row = models.McpEvent(
            **{
                "org": self.factory.org,
                "user": user if user is not None else self.factory.user,
                "method": "tools/call",
                "tool": "find_context",
                "outcome": "ok",
                "duration_ms": 42,
                **fields,
            }
        )
        models.db.session.add(row)
        models.db.session.flush()
        row.created_at = models.utcnow() - datetime.timedelta(minutes=minutes_ago)
        models.db.session.commit()
        return row

    def test_before_a_first_call_it_says_so(self):
        # The page shows only how to connect: a table of nothing under a
        # heading about activity reads as something being broken.
        response = self.mine()

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["ever_connected"])
        self.assertEqual([], response.json["calls"])

    def test_a_recent_call_counts_as_connected(self):
        # The transport holds no socket open, so "connected" can only mean
        # "recently active".
        self.event(minutes_ago=1)

        response = self.mine()

        self.assertTrue(response.json["connected"])
        self.assertTrue(response.json["ever_connected"])

    def test_an_old_one_does_not(self):
        self.event(minutes_ago=120)

        response = self.mine()

        self.assertFalse(response.json["connected"])
        self.assertTrue(response.json["ever_connected"])
        self.assertIsNotNone(response.json["last_call_at"])

    def test_the_calls_say_what_and_when_and_how_long(self):
        self.event()

        call = self.mine().json["calls"][0]

        self.assertEqual("find_context", call["tool"])
        self.assertEqual("ok", call["outcome"])
        self.assertEqual(42, call["duration_ms"])

    def test_the_newest_call_is_first(self):
        # The page shows the most recent fifty, so the order is also what gets
        # kept when there are more than fifty: oldest-first would show somebody
        # their first fifty calls forever and never their last one.
        self.event(tool="find_context", minutes_ago=30)
        self.event(tool="run_query", minutes_ago=1)

        tools = [call["tool"] for call in self.mine().json["calls"]]

        self.assertEqual(["run_query", "find_context"], tools)

    def test_but_never_the_question_or_the_sql(self):
        # `detail` holds one or the other. This endpoint carries neither, so
        # there is no version of this page that leaks somebody's query.
        self.event(detail="question: what did we take last month")

        body = json.dumps(self.mine().json)

        self.assertNotIn("what did we take", body)
        self.assertNotIn("detail", body)

    def test_nor_the_address_it_came_from(self):
        self.event(remote_addr="203.0.113.7")

        self.assertNotIn("203.0.113.7", json.dumps(self.mine().json))

    def test_somebody_elses_calls_are_not_mine(self):
        other = self.factory.create_user()
        self.event(user=other, tool="run_query")

        response = self.mine()

        self.assertEqual([], response.json["calls"])
        self.assertFalse(response.json["ever_connected"])

    def test_and_cannot_be_asked_for(self):
        # There is no parameter to ask with. The test is that adding one
        # changes nothing, so a future "convenience" has to be a deliberate
        # change to the endpoint rather than a query string somebody tries.
        other = self.factory.create_user()
        self.event(user=other)

        response = self.make_request("get", "/api/mcp/mine?user_id={}".format(other.id), user=self.factory.user)

        self.assertEqual([], response.json["calls"])

    def test_another_organisations_calls_are_not_mine_either(self):
        other_org = self.factory.create_org()
        models.db.session.add(
            models.McpEvent(org=other_org, user=self.factory.user, method="tools/call", outcome="ok")
        )
        models.db.session.commit()

        self.assertEqual([], self.mine().json["calls"])

    def test_it_names_the_clients_that_have_been_calling(self):
        self.event(client="Claude Code 1.2")

        self.assertEqual(["Claude Code 1.2"], self.mine().json["clients"])

    def test_only_the_clients_still_calling_are_named(self):
        # The list sits under "connected", so it answers "what is talking to
        # SQLDesk now". A client somebody uninstalled last month named there
        # would be somebody looking for a machine that is not running.
        self.event(minutes_ago=120, **{"client": "an-old-client 0.1"})
        self.event(minutes_ago=1, **{"client": "claude-code 1.2.3"})

        self.assertEqual(["claude-code 1.2.3"], self.mine().json["clients"])

    def test_the_page_asks_for_a_bounded_number_of_calls(self):
        # A client calls a tool per question and a busy afternoon is thousands.
        # Without the limit the page grows until the browser gives up, and the
        # part anybody reads is the first screen of it.
        for index in range(models.McpEvent.query.count(), MyMcpResource.LIMIT + 5):
            self.event(minutes_ago=index + 1)

        self.assertEqual(MyMcpResource.LIMIT, len(self.mine().json["calls"]))

    def test_somebody_without_the_permission_may_not_look(self):
        # Nothing to see, and offering the page would be offering a page about
        # a feature they do not have.
        self.factory.default_group.permissions = models.Group.DEFAULT_PERMISSIONS
        models.db.session.add(self.factory.default_group)
        models.db.session.commit()

        self.assertEqual(403, self.mine().status_code)

    def test_a_refused_call_of_mine_is_still_mine_to_see(self):
        # Knowing a client was refused is how somebody discovers they need a
        # permission, rather than concluding the server is broken.
        self.event(outcome="refused", method="authenticate", tool=None)

        call = self.mine().json["calls"][0]

        self.assertEqual("refused", call["outcome"])
        self.assertEqual("authenticate", call["method"])


class TestCuratingTheCatalogOverMcp(McpTestCase):
    """
    `update_table`: the first MCP tool that writes.

    Offered only to a personal API key belonging to somebody who may curate the
    catalog. OAuth tokens carry `mcp:read`, and `sqldesk.oauth` said from the
    start that a writing tool would not be reachable with one -- so an agent
    working through an OAuth session never sees it listed, and is refused if
    it calls it anyway.
    """

    def setUp(self):
        super().setUp()
        self.admin = self.factory.create_admin()
        self.table = models.CatalogTable(
            org=self.factory.org, data_source_id=self.factory.data_source.id, name="orders", usage_count=5
        )
        models.db.session.add(self.table)
        models.db.session.commit()

    def call(self, arguments, user=None, api_key=None):
        return self.post(
            rpc("tools/call", {"name": "update_table", "arguments": arguments}), user=user, api_key=api_key
        )

    def listed(self, user=None, api_key=None):
        rv = self.post(rpc("tools/list"), user=user, api_key=api_key)
        return [tool["name"] for tool in rv.json["result"]["tools"]]

    def oauth_token(self, user):
        import secrets

        from sqldesk.oauth import ACCESS_PREFIX

        value = ACCESS_PREFIX + secrets.token_urlsafe(32)
        models.db.session.add(
            models.OAuthToken(
                client_id="test-client",
                org_id=user.org_id,
                user_id=user.id,
                access_token_digest=models._token_digest(value),
                scope=models.OAUTH_SCOPE,
                access_expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
            )
        )
        models.db.session.commit()
        return value

    def test_an_administrators_api_key_is_offered_it(self):
        self.assertIn("update_table", self.listed(user=self.admin))

    def test_somebody_who_may_not_curate_is_not(self):
        self.assertNotIn("update_table", self.listed(user=self.factory.user))

    def test_nor_is_an_oauth_session_even_an_administrators(self):
        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", True):
            token = self.oauth_token(self.admin)
            self.assertNotIn("update_table", self.listed(api_key=token))

    def test_and_calling_it_anyway_through_oauth_is_refused(self):
        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", True):
            token = self.oauth_token(self.admin)
            rv = self.call({"name": "orders", "description": "x"}, api_key=token)

        self.assertIn("error", rv.json)
        self.assertIn("mcp:read", rv.json["error"]["message"])
        models.db.session.refresh(self.table)
        self.assertIsNone(self.table.description)

    def test_it_describes_a_table_and_marks_it_as_written_through_mcp(self):
        rv = self.call({"name": "orders", "description": "One row per order. Key: order_id (UUID)."}, user=self.admin)

        self.assertFalse(rv.json["result"]["isError"])
        models.db.session.refresh(self.table)
        self.assertEqual("One row per order. Key: order_id (UUID).", self.table.description)
        self.assertEqual("mcp", self.table.description_source)

    def test_the_card_an_agent_is_given_carries_the_new_description(self):
        """
        The reported bug: described through MCP, and find_context still did
        not say so. The card is what an agent reads, and only the harvest
        ever wrote it -- a day later at best, never on a paused source.
        """
        self.call({"name": "orders", "description": "One row per order."}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertIn("One row per order.", self.table.card or "")

    def test_and_so_does_the_card_after_the_page_describes_one(self):
        rv = self.make_request(
            "post",
            "/api/catalog/tables/{}".format(self.table.id),
            data={"description": "Typed on the page."},
            user=self.admin,
            org=False,
        )

        self.assertEqual(200, rv.status_code)
        models.db.session.refresh(self.table)
        self.assertIn("Typed on the page.", self.table.card or "")

    def test_clearing_a_description_takes_it_off_the_card_too(self):
        self.call({"name": "orders", "description": "One row per order."}, user=self.admin)
        self.call({"name": "orders", "description": ""}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertNotIn("One row per order.", self.table.card or "")

    def test_it_records_whose_key_wrote_the_description(self):
        """ "mcp" says a machine typed it; it does not say whose key it was."""
        self.call({"name": "orders", "description": "One row per order."}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertEqual(self.admin.id, self.table.described_by_id)
        self.assertIsNotNone(self.table.described_at)

    def test_and_clearing_it_clears_the_author(self):
        self.call({"name": "orders", "description": "One row per order."}, user=self.admin)
        self.call({"name": "orders", "description": ""}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertIsNone(self.table.described_by_id)
        self.assertIsNone(self.table.described_at)

    def test_it_will_not_hide_one(self):
        """
        Hiding a table decides what everybody is offered, and any key that
        may curate could have done it with no review and nothing on a page to
        notice. It stays a decision somebody makes in the Catalog page, with
        the table in front of them.
        """
        rv = self.call({"name": "orders", "hidden": True}, user=self.admin)

        self.assertIn("Admin -> Catalog", rv.json["error"]["message"])
        models.db.session.refresh(self.table)
        self.assertFalse(self.table.hidden)

    def test_and_does_not_offer_it_either(self):
        rv = self.post(rpc("tools/list"), user=self.admin)
        update_table = [tool for tool in rv.json["result"]["tools"] if tool["name"] == "update_table"][0]

        self.assertNotIn("hidden", update_table["inputSchema"]["properties"])

    def test_it_will_not_replace_what_a_person_wrote(self):
        self.table.description = "Orders, excluding the test tenant."
        self.table.description_source = "human"
        models.db.session.commit()

        rv = self.call({"name": "orders", "description": "Orders."}, user=self.admin)

        self.assertTrue(rv.json["result"]["isError"])
        self.assertIn("overwrite", rv.json["result"]["content"][0]["text"])
        models.db.session.refresh(self.table)
        self.assertEqual("Orders, excluding the test tenant.", self.table.description)

    def test_unless_told_to(self):
        self.table.description = "Orders, excluding the test tenant."
        self.table.description_source = "human"
        models.db.session.commit()

        self.call({"name": "orders", "description": "Orders.", "overwrite": True}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertEqual("Orders.", self.table.description)
        self.assertEqual("mcp", self.table.description_source)

    def test_a_refused_hide_leaves_a_persons_words_alone(self):
        self.table.description = "Orders, excluding the test tenant."
        self.table.description_source = "human"
        models.db.session.commit()

        self.call({"name": "orders", "hidden": True}, user=self.admin)

        models.db.session.refresh(self.table)
        self.assertFalse(self.table.hidden)
        self.assertEqual("Orders, excluding the test tenant.", self.table.description)

    def test_a_name_in_two_data_sources_asks_which(self):
        other = self.factory.create_data_source(name="Second", group=self.factory.default_group)
        models.db.session.add(models.CatalogTable(org=self.factory.org, data_source_id=other.id, name="orders"))
        models.db.session.commit()

        rv = self.call({"name": "orders", "description": "x"}, user=self.admin)

        self.assertIn("error", rv.json)
        self.assertIn("data_source", rv.json["error"]["message"])

    def test_nothing_to_change_is_refused_rather_than_a_silent_success(self):
        rv = self.call({"name": "orders"}, user=self.admin)

        self.assertIn("Nothing to change", rv.json["error"]["message"])

    def test_an_unknown_table_says_so(self):
        rv = self.call({"name": "nope", "description": "x"}, user=self.admin)

        self.assertIn("No table called", rv.json["error"]["message"])


class TestSavingAQueryOverMcp(McpTestCase):
    """
    `save_query` and `update_query`: what an agent may do with somebody's
    saved SQL.

    The rule throughout is that nothing an agent writes is shown to anybody
    else as settled. A saved query is a draft; an edit is a draft's edit, with
    a version recorded. Publishing, verifying and approving stay with people.
    """

    def setUp(self):
        super().setUp()
        self.author = self.factory.user

    def call(self, tool, arguments, user=None, api_key=None):
        return self.post(rpc("tools/call", {"name": tool, "arguments": arguments}), user=user, api_key=api_key)

    def listed(self, user=None, api_key=None):
        rv = self.post(rpc("tools/list"), user=user, api_key=api_key)
        return [tool["name"] for tool in rv.json["result"]["tools"]]

    def test_it_is_offered_to_somebody_who_may_create_queries(self):
        self.assertIn("save_query", self.listed(user=self.author))
        self.assertIn("update_query", self.listed(user=self.author))

    def test_a_saved_query_is_a_draft_on_the_right_source(self):
        rv = self.call(
            "save_query",
            {
                "name": "Orders by region",
                "sql": "SELECT region, COUNT(*) FROM orders GROUP BY 1",
                "data_source": self.factory.data_source.name,
                "description": "One row per region.",
            },
        )

        self.assertFalse(rv.json["result"].get("isError"))
        query = models.Query.query.filter(models.Query.name == "Orders by region").one()
        self.assertTrue(query.is_draft)
        self.assertEqual(self.factory.data_source.id, query.data_source_id)
        self.assertEqual(self.author.id, query.user_id)
        self.assertEqual("One row per region.", query.description)

    def test_the_reply_says_where_to_find_it(self):
        rv = self.call(
            "save_query",
            {"name": "Orders", "sql": "SELECT 1", "data_source": self.factory.data_source.name},
        )
        query = models.Query.query.filter(models.Query.name == "Orders").one()

        self.assertIn("queries/{}".format(query.id), rv.json["result"]["content"][0]["text"])

    def test_it_refuses_to_save_something_that_is_not_a_read(self):
        # What is saved is what a person will press Run on.
        rv = self.call(
            "save_query",
            {"name": "Tidy up", "sql": "DELETE FROM orders", "data_source": self.factory.data_source.name},
        )

        self.assertIn("error", rv.json)
        self.assertEqual(0, models.Query.query.filter(models.Query.name == "Tidy up").count())

    def test_it_will_not_save_against_a_source_the_caller_may_only_read(self):
        view_only = self.factory.create_data_source(group=self.factory.default_group, view_only=True)

        rv = self.call(
            "save_query",
            {"name": "Peek", "sql": "SELECT 1", "data_source": view_only.name},
        )

        self.assertIn("error", rv.json)

    def test_editing_a_draft_records_a_version(self):
        query = self.factory.create_query(query_text="SELECT 1", is_draft=True, user=self.author)
        models.db.session.commit()

        rv = self.call("update_query", {"id": query.id, "sql": "SELECT 2"})

        self.assertFalse(rv.json["result"].get("isError"))
        models.db.session.refresh(query)
        self.assertEqual("SELECT 2", query.query_text)
        self.assertEqual(self.author.id, query.last_modified_by_id)
        self.assertTrue(models.Change.query.filter(models.Change.object_id == query.id).count() >= 1)

    def test_but_a_published_query_is_left_alone(self):
        # Other people's dashboards and alerts read it, and nobody would see
        # a diff.
        query = self.factory.create_query(query_text="SELECT 1", is_draft=False, user=self.author)
        models.db.session.commit()

        rv = self.call("update_query", {"id": query.id, "sql": "SELECT 2"})

        self.assertIn("published", rv.json["error"]["message"])
        models.db.session.refresh(query)
        self.assertEqual("SELECT 1", query.query_text)

    def test_and_so_is_somebody_elses_draft(self):
        other = self.factory.create_user()
        query = self.factory.create_query(query_text="SELECT 1", is_draft=True, user=other)
        models.db.session.commit()

        rv = self.call("update_query", {"id": query.id, "sql": "SELECT 2"})

        self.assertIn("somebody else's", rv.json["error"]["message"])

    def test_nothing_to_change_is_refused_rather_than_a_silent_success(self):
        query = self.factory.create_query(is_draft=True, user=self.author)
        models.db.session.commit()

        rv = self.call("update_query", {"id": query.id})

        self.assertIn("Nothing to change", rv.json["error"]["message"])

    def test_an_oauth_session_is_offered_neither(self):
        with mock.patch("sqldesk.settings.MCP_OAUTH_ENABLED", True):
            import secrets

            from sqldesk.oauth import ACCESS_PREFIX

            value = ACCESS_PREFIX + secrets.token_urlsafe(32)
            models.db.session.add(
                models.OAuthToken(
                    client_id="test-client",
                    org_id=self.author.org_id,
                    user_id=self.author.id,
                    access_token_digest=models._token_digest(value),
                    scope=models.OAUTH_SCOPE,
                    access_expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
                )
            )
            models.db.session.commit()

            listed = self.listed(api_key=value)
            rv = self.call("save_query", {"name": "x", "sql": "SELECT 1", "data_source": "x"}, api_key=value)

        self.assertNotIn("save_query", listed)
        self.assertIn("mcp:read", rv.json["error"]["message"])


class TestDrawingAResultOverMcp(McpTestCase):
    """
    `save_visualization` and `save_dashboard`.

    An agent that can write SQL and not show it has done half a job: the
    answer to "how are orders doing" is a chart somebody can put on a wall,
    not a result set in a transcript. The same rule as everything else it
    writes applies -- what comes out is a draft, and publishing stays with a
    person.
    """

    def setUp(self):
        super().setUp()
        self.author = self.factory.user
        self.query = self.factory.create_query(
            query_text="SELECT region, amount FROM orders", is_draft=True, user=self.author
        )
        models.db.session.commit()

    def call(self, tool, arguments, user=None, api_key=None):
        return self.post(rpc("tools/call", {"name": tool, "arguments": arguments}), user=user, api_key=api_key)

    def listed(self, user=None, api_key=None):
        rv = self.post(rpc("tools/list"), user=user, api_key=api_key)
        return [tool["name"] for tool in rv.json["result"]["tools"]]

    def draw(self, **arguments):
        arguments.setdefault("query_id", self.query.id)
        rv = self.call("save_visualization", arguments)
        self.assertNotIn("error", rv.json, rv.json.get("error"))
        self.assertFalse(rv.json["result"].get("isError"), rv.json["result"])
        return models.Visualization.query.order_by(models.Visualization.id.desc()).first()

    def test_both_are_offered_to_somebody_who_may_make_them(self):
        offered = self.listed(user=self.author)

        self.assertIn("save_visualization", offered)
        self.assertIn("save_dashboard", offered)

    def test_a_chart_is_mapped_so_it_renders(self):
        # columnMapping is what getChartData reads; without it the chart draws
        # nothing and the failure is silent.
        visualization = self.draw(kind="chart", x="region", y=["amount"], chart_type="column")

        self.assertEqual("CHART", visualization.type)
        self.assertEqual("column", visualization.options["globalSeriesType"])
        self.assertEqual({"region": "x", "amount": "y"}, visualization.options["columnMapping"])
        self.assertEqual(self.query.id, visualization.query_id)

    def test_a_bar_chart_is_a_column_chart_on_its_side(self):
        # `bar` is not a type of its own in the renderer.
        visualization = self.draw(kind="chart", x="region", y=["amount"], chart_type="bar")

        self.assertEqual("column", visualization.options["globalSeriesType"])
        self.assertTrue(visualization.options["swappedAxes"])

    def test_more_than_one_measure_gets_a_legend(self):
        alone = self.draw(kind="chart", x="region", y=["amount"])
        self.assertFalse(alone.options["legend"]["enabled"])

        several = self.draw(kind="chart", x="region", y=["amount", "tax"])
        self.assertTrue(several.options["legend"]["enabled"])
        self.assertEqual({"region": "x", "amount": "y", "tax": "y"}, several.options["columnMapping"])

    def test_a_pie_always_gets_a_legend(self):
        # On a pie the slices are the categories, so the legend is how anybody
        # reads it -- unlike a single-series bar chart, where it is noise.
        pie = self.draw(kind="chart", x="region", y=["amount"], chart_type="pie")

        self.assertTrue(pie.options["legend"]["enabled"])

    def test_a_series_column_splits_the_chart(self):
        visualization = self.draw(kind="chart", x="region", y=["amount"], series="channel")

        self.assertEqual("series", visualization.options["columnMapping"]["channel"])

    def test_a_counter_and_a_table_need_no_columns_mapping(self):
        counter = self.draw(kind="counter", column="amount")
        self.assertEqual("COUNTER", counter.type)
        self.assertEqual("amount", counter.options["counterColName"])

        table = self.draw(kind="table")
        self.assertEqual("TABLE", table.type)

    def test_a_chart_without_its_columns_is_refused(self):
        rv = self.call("save_visualization", {"query_id": self.query.id, "kind": "chart"})

        self.assertIn("error", rv.json)
        self.assertEqual(0, models.Visualization.query.count())

    def test_it_will_not_draw_a_published_query(self):
        # Its page is read by other people: a chart nobody added appearing on
        # it is the same surprise as its SQL changing.
        published = self.factory.create_query(is_draft=False, user=self.author)
        models.db.session.commit()

        rv = self.call("save_visualization", {"query_id": published.id, "kind": "table"})

        self.assertIn("error", rv.json)
        self.assertIn("published", rv.json["error"]["message"])

    def test_a_dashboard_is_a_draft_with_its_widgets_laid_out(self):
        first = self.draw(kind="counter", column="amount")
        second = self.draw(kind="table")
        third = self.draw(kind="chart", x="region", y=["amount"])

        rv = self.call(
            "save_dashboard",
            {"name": "Orders", "visualizations": [first.id, second.id, third.id]},
        )
        self.assertNotIn("error", rv.json, rv.json.get("error"))

        dashboard = models.Dashboard.query.filter(models.Dashboard.name == "Orders").one()
        self.assertTrue(dashboard.is_draft)
        self.assertEqual(self.author.id, dashboard.user_id)

        # Two to a row, in the order given. Without a position every widget
        # sits at the origin, stacked on top of the others.
        placed = {widget.visualization_id: widget.options["position"] for widget in dashboard.widgets}  # noqa: B020
        self.assertEqual({"col": 0, "row": 0}, {k: placed[first.id][k] for k in ("col", "row")})
        self.assertEqual({"col": 12, "row": 0}, {k: placed[second.id][k] for k in ("col", "row")})
        self.assertEqual({"col": 0, "row": 6}, {k: placed[third.id][k] for k in ("col", "row")})

    def test_the_reply_says_where_to_find_the_dashboard(self):
        visualization = self.draw(kind="table")

        rv = self.call("save_dashboard", {"name": "Orders", "visualizations": [visualization.id]})
        dashboard = models.Dashboard.query.filter(models.Dashboard.name == "Orders").one()

        self.assertIn("dashboards/{}".format(dashboard.id), rv.json["result"]["content"][0]["text"])

    def test_a_bad_id_leaves_no_half_a_dashboard_behind(self):
        visualization = self.draw(kind="table")

        rv = self.call("save_dashboard", {"name": "Orders", "visualizations": [visualization.id, 99999]})

        self.assertIn("error", rv.json)
        self.assertEqual(0, models.Dashboard.query.filter(models.Dashboard.name == "Orders").count())

    def test_it_will_not_show_a_result_the_caller_could_not_have_run(self):
        other = self.factory.create_data_source(group=self.factory.create_group())
        theirs = self.factory.create_query(data_source=other, is_draft=True)
        hidden = self.factory.create_visualization(query_rel=theirs)
        models.db.session.commit()

        rv = self.call("save_dashboard", {"name": "Sneak", "visualizations": [hidden.id]})

        self.assertIn("error", rv.json)
        self.assertEqual(0, models.Dashboard.query.filter(models.Dashboard.name == "Sneak").count())

    def test_an_empty_dashboard_is_refused(self):
        rv = self.call("save_dashboard", {"name": "Nothing", "visualizations": []})

        self.assertIn("error", rv.json)


class TestProposingAMeasureOverMcp(McpTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.factory.create_admin()
        self.table = models.CatalogTable(
            org=self.factory.org, data_source_id=self.factory.data_source.id, name="orders"
        )
        models.db.session.add(self.table)
        models.db.session.commit()

    def call(self, arguments, user=None):
        return self.post(rpc("tools/call", {"name": "propose_measure", "arguments": arguments}), user=user)

    def test_a_proposal_waits_for_a_curator(self):
        rv = self.call(
            {"name": "gross_revenue", "table": "orders", "kind": "sum", "column": "amount"}, user=self.admin
        )

        self.assertIn("until a curator agrees", rv.json["result"]["content"][0]["text"])
        measure = models.CatalogMeasure.query.one()
        self.assertEqual(models.MEASURE_PROPOSED, measure.status)
        self.assertEqual(self.admin.id, measure.proposed_by_id)

    def test_an_agreed_measure_is_not_proposed_over(self):
        models.db.session.add(
            models.CatalogMeasure(
                org=self.factory.org,
                data_source_id=self.factory.data_source.id,
                table_name="orders",
                name="gross_revenue",
                kind="sum",
                column_name="amount",
                status=models.MEASURE_APPROVED,
            )
        )
        models.db.session.commit()

        rv = self.call(
            {"name": "gross_revenue", "table": "orders", "kind": "avg", "column": "amount"}, user=self.admin
        )

        self.assertIn("already agreed", rv.json["result"]["content"][0]["text"])
        self.assertEqual(models.MEASURE_APPROVED, models.CatalogMeasure.query.one().status)
        self.assertEqual("sum", models.CatalogMeasure.query.one().kind)

    def test_a_denied_one_goes_back_on_the_list_rather_than_becoming_true(self):
        models.db.session.add(
            models.CatalogMeasure(
                org=self.factory.org,
                data_source_id=self.factory.data_source.id,
                table_name="orders",
                name="gross_revenue",
                kind="sum",
                column_name="amount",
                status=models.MEASURE_DENIED,
            )
        )
        models.db.session.commit()

        self.call({"name": "gross_revenue", "table": "orders", "kind": "sum", "column": "net"}, user=self.admin)

        measure = models.CatalogMeasure.query.one()
        self.assertEqual(models.MEASURE_PROPOSED, measure.status)
        self.assertEqual("net", measure.column_name)

    def test_a_count_needs_no_column(self):
        rv = self.call({"name": "orders_placed", "table": "orders", "kind": "count"}, user=self.admin)

        self.assertFalse(rv.json["result"].get("isError"))
        # "*", as the harvester stores COUNT(*): the column is declared NOT
        # NULL, and the two have to agree or a mined measure and a proposed
        # one are different rows for the same number.
        self.assertEqual("*", models.CatalogMeasure.query.one().column_name)

    def test_but_a_sum_does(self):
        rv = self.call({"name": "revenue", "table": "orders", "kind": "sum"}, user=self.admin)

        self.assertIn("`column` is required", rv.json["error"]["message"])

    def test_an_invented_kind_is_refused(self):
        rv = self.call({"name": "revenue", "table": "orders", "kind": "median", "column": "amount"}, user=self.admin)

        self.assertIn("`kind` is one of", rv.json["error"]["message"])

    def test_a_table_nobody_has_harvested_says_so(self):
        rv = self.call({"name": "x", "table": "nowhere", "kind": "count"}, user=self.admin)

        self.assertIn("No table called", rv.json["error"]["message"])

    def test_somebody_who_may_not_curate_is_not_offered_it(self):
        rv = self.post(rpc("tools/list"), user=self.factory.user)

        self.assertNotIn("propose_measure", [tool["name"] for tool in rv.json["result"]["tools"]])


class TestTheDailyCapOnWrites(McpTestCase):
    """
    An agent told to describe a warehouse will describe the whole warehouse,
    and a loop getting it wrong will do it just as fast. The cap makes a
    mistake a morning's review rather than a restore.
    """

    def setUp(self):
        super().setUp()
        self.admin = self.factory.create_admin()
        models.db.session.add(
            models.CatalogTable(org=self.factory.org, data_source_id=self.factory.data_source.id, name="orders")
        )
        models.db.session.commit()

    def _wrote(self, count, tool="update_table", outcome="ok", user=None):
        for _ in range(count):
            models.db.session.add(
                models.McpEvent(
                    org=self.factory.org,
                    user=user or self.admin,
                    method="tools/call",
                    tool=tool,
                    outcome=outcome,
                )
            )
        models.db.session.commit()

    def _describe(self):
        return self.post(
            rpc("tools/call", {"name": "update_table", "arguments": {"name": "orders", "description": "One row."}}),
            user=self.admin,
        )

    def test_under_the_cap_a_write_goes_through(self):
        self._wrote(10)

        self.assertFalse(self._describe().json["result"].get("isError"))

    def test_at_the_cap_it_is_refused_and_says_when_it_resets(self):
        self._wrote(50)

        message = self._describe().json["error"]["message"]

        self.assertIn("daily limit", message)
        self.assertIn("midnight", message)

    def test_refused_and_failed_calls_do_not_count_towards_it(self):
        self._wrote(50, outcome="error")
        self._wrote(10, outcome="refused")

        self.assertFalse(self._describe().json["result"].get("isError"))

    def test_reads_do_not_count_towards_it(self):
        self._wrote(60, tool="find_context")

        self.assertFalse(self._describe().json["result"].get("isError"))

    def test_the_cap_is_per_person(self):
        other = self.factory.create_admin()
        self._wrote(50, user=other)

        self.assertFalse(self._describe().json["result"].get("isError"))

    def test_an_install_may_turn_it_off(self):
        self._wrote(80)

        with mock.patch("sqldesk.settings.MCP_WRITES_PER_DAY", 0):
            self.assertFalse(self._describe().json["result"].get("isError"))


class TestWhatTheAuditSaysAboutAWrite(McpTestCase):
    """
    "update_table ok" did not answer the question anybody brings to an audit
    of an agent's writes, which is what that table used to say.
    """

    def setUp(self):
        super().setUp()
        self.admin = self.factory.create_admin()
        self.table = models.CatalogTable(
            org=self.factory.org,
            data_source_id=self.factory.data_source.id,
            name="orders",
            description="What it was before.",
            description_source="mcp",
        )
        models.db.session.add(self.table)
        models.db.session.commit()

    def _detail(self):
        row = (
            models.McpEvent.query.filter(models.McpEvent.tool.isnot(None)).order_by(models.McpEvent.id.desc()).first()
        )
        return row.detail or ""

    def test_it_records_the_before_and_the_after(self):
        self.post(
            rpc(
                "tools/call",
                {"name": "update_table", "arguments": {"name": "orders", "description": "What it says now."}},
            ),
            user=self.admin,
        )

        detail = self._detail()
        self.assertIn("What it was before.", detail)
        self.assertIn("What it says now.", detail)
        self.assertIn("orders", detail)

    def test_a_saved_query_is_recorded_by_id_and_name(self):
        self.post(
            rpc(
                "tools/call",
                {
                    "name": "save_query",
                    "arguments": {
                        "name": "Orders by region",
                        "sql": "SELECT 1",
                        "data_source": self.factory.data_source.name,
                    },
                },
            ),
            user=self.admin,
        )

        detail = self._detail()
        self.assertIn("saved query", detail)
        self.assertIn("Orders by region", detail)

    def test_and_a_read_still_records_the_question_rather_than_a_write(self):
        self.post(
            rpc("tools/call", {"name": "find_context", "arguments": {"question": "what are orders"}}),
            user=self.admin,
        )

        self.assertIn("what are orders", self._detail())


class TestWhatAnAnswerCosts(McpTestCase):
    """
    Measured on a real catalog on 2026-10-25, one question to `find_dashboards`
    cost 1,346 tokens: eight dashboards, twelve chart lines each, and the whole
    thing again as `structuredContent`. The semantic catalog that makes an
    agent correct costs 153. These hold the answers to the shape that made
    that difference.
    """

    def call(self, name, arguments=None):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)["result"]

    def text(self, name, arguments=None):
        return self.call(name, arguments)["content"][0]["text"]

    def board_showing_one_query_several_ways(self, name, views=5):
        dashboard = self.factory.create_dashboard(name=name)
        query = self.factory.create_query(
            name="Revenue per minute", description="revenue by region", data_source=self.factory.data_source
        )
        for kind in ("CHART", "COUNTER", "TABLE", "BOXPLOT", "PIVOT")[:views]:
            visualization = self.factory.create_visualization(query_rel=query, type=kind, name=kind.title())
            self.factory.create_widget(dashboard=dashboard, visualization=visualization)
        return dashboard, query

    def test_no_tool_repeats_its_answer_as_structured_content(self):
        """
        It was sent with no `outputSchema` declared anywhere, so no client
        could rely on it, and it repeated about 90% of the text's bytes.
        """
        self.factory.create_query(
            name="Revenue by region", description="revenue by region", data_source=self.factory.data_source
        )
        models.db.session.commit()
        for name, arguments in (
            ("find_queries", {"question": "revenue"}),
            ("find_measures", {"question": "revenue"}),
            ("find_dashboards", {"question": "revenue"}),
            ("list_data_sources", {}),
        ):
            with self.subTest(name):
                self.assertNotIn("structuredContent", self.call(name, arguments))

    def test_panels_showing_the_same_query_are_one_line(self):
        self.board_showing_one_query_several_ways("Revenue board")
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "revenue"})

        self.assertIn("Revenue board", found)
        # Four, not five: a plain table nobody described says nothing the
        # query does not already say, and _worth_listing drops it.
        self.assertIn("+3 more views of it", found, "panels of one query are one line and a count")
        self.assertEqual(1, found.count("from query #"), "one line per query, not per panel")

    def test_only_a_few_boards_are_described_and_the_rest_are_counted(self):
        for n in range(7):
            self.board_showing_one_query_several_ways("Revenue board {}".format(n), views=1)
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "revenue"})

        described = found.count("— /dashboards/")
        self.assertEqual(4, described, "four boards described")
        self.assertIn("3 more match", found, "and the rest counted, with how to ask for them")
        self.assertIn("Ask for one by name", found)

    def test_the_tool_list_stays_lean(self):
        """
        It is sent on every turn whether a tool is called or not, so it is the
        one thing here whose size is paid again and again. The nine a reader
        is offered measured 4,348 bytes before the prose was trimmed; the
        budget below is what that became, with room to add a tool without
        rewriting this.
        """
        listed = json.loads(self.post(rpc("tools/list", {})).data)["result"]["tools"]

        self.assertTrue(listed)
        for tool in listed:
            with self.subTest(tool["name"]):
                self.assertLessEqual(
                    len(tool["description"]),
                    340,
                    "a tool description earns its place on every turn: say what it does, when to "
                    "reach for it, and the one constraint that is not obvious",
                )

        # The read-only nine, whatever else this caller is also offered.
        reading = {
            "list_data_sources",
            "find_context",
            "find_queries",
            "find_dashboards",
            "find_measures",
            "expand_table",
            "check_sql",
            "explain_query",
            "run_query",
        }
        offered = [tool for tool in listed if tool["name"] in reading]
        self.assertEqual(len(reading), len(offered), "a read tool went missing")
        self.assertLessEqual(len(json.dumps(offered, separators=(",", ":"))), 3800)


class TestWhichDashboardsAreDescribed(McpTestCase):
    """
    Four boards are described and the rest are counted, so which four is the
    whole question. Ordered by when they were last touched, a board somebody
    read and confirmed falls behind four nobody has checked -- into a count,
    where an agent cannot see that it exists.
    """

    def call(self, name, arguments=None):
        return json.loads(self.post(rpc("tools/call", {"name": name, "arguments": arguments or {}})).data)["result"]

    def text(self, name, arguments=None):
        return self.call(name, arguments)["content"][0]["text"]

    def board(self, name, verified=False, panels=1):
        dashboard = self.factory.create_dashboard(name=name)
        query = self.factory.create_query(
            name=name + " query", description="revenue by region", data_source=self.factory.data_source
        )
        for n in range(panels):
            visualization = self.factory.create_visualization(query_rel=query, type="CHART", name="Chart {}".format(n))
            self.factory.create_widget(dashboard=dashboard, visualization=visualization)
        if verified:
            dashboard.verified_at = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            dashboard.verified_note = "checked against finance"
            models.db.session.add(dashboard)
        return dashboard

    def test_a_verified_board_is_described_even_behind_newer_ones(self):
        self.board("Revenue, checked", verified=True)
        for n in range(6):
            self.board("Revenue draft {}".format(n))
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "revenue"})

        self.assertIn("Revenue, checked", found)
        self.assertIn("[VERIFIED]", found)
        self.assertIn("checked against finance", found)

    def test_the_boards_that_did_not_fit_are_named_not_only_counted(self):
        for n in range(7):
            self.board("Revenue board {}".format(n))
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "revenue"})

        self.assertIn("3 more match:", found)
        self.assertIn("Ask for one by name", found)
        named = [
            name
            for name in (
                "Revenue board 0",
                "Revenue board 1",
                "Revenue board 2",
                "Revenue board 3",
                "Revenue board 4",
                "Revenue board 5",
                "Revenue board 6",
            )
            if name in found
        ]
        self.assertEqual(7, len(named), "every board is either described or named in the tail")

    def test_a_panel_is_described_by_the_words_written_on_it(self):
        """
        Not by a sibling's words: a counter and a line chart of one query are
        one line, and the line has to say what the panel it describes shows.
        """
        dashboard = self.factory.create_dashboard(name="Revenue board")
        query = self.factory.create_query(
            name="Revenue", description="revenue by region", data_source=self.factory.data_source
        )
        plain = self.factory.create_visualization(query_rel=query, type="CHART", name="Plain", description="")
        described = self.factory.create_visualization(
            query_rel=query, type="COUNTER", name="Counted", description="completed orders only"
        )
        self.factory.create_widget(dashboard=dashboard, visualization=plain)
        self.factory.create_widget(dashboard=dashboard, visualization=described)
        models.db.session.commit()

        found = self.text("find_dashboards", {"question": "revenue"})

        self.assertIn("completed orders only", found)
        line = next(one for one in found.splitlines() if "completed orders only" in one)
        self.assertIn("counter", line.lower(), "the description belongs to the counter, so the line is the counter's")


class TestAlertsOverMcp(McpTestCase):
    """
    Debugging an alert is almost always one of four questions: why did it
    fire, is it flapping, why did it *not* fire, and was anybody told. Before
    0.7.9 an alert kept only its current state, so a tool here could have
    answered "it is triggered" and almost nothing else. The fire history is
    what makes the other three answerable, and this is what reads it.
    """

    def call(self, name, arguments=None, user=None):
        body = rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return json.loads(self.post(body, user=user).data)

    def text(self, name, arguments=None, user=None):
        return self.call(name, arguments, user=user)["result"]["content"][0]["text"]

    def an_alert(self, **kwargs):
        options = {"column": "orders", "op": "<", "value": 100}
        options.update(kwargs.pop("options", {}))
        query = kwargs.pop("query", None) or self.factory.create_query(
            name="Orders per hour", data_source=self.factory.data_source
        )
        alert = self.factory.create_alert(query_rel=query, options=options, **kwargs)
        models.db.session.commit()
        return alert

    def fire(self, alert, state, value=None, notified=True, minutes_ago=0):
        row = models.AlertFire(
            alert_id=alert.id,
            state=state,
            value=None if value is None else str(value),
            notified=notified,
            created_at=utils.utcnow() - datetime.timedelta(minutes=minutes_ago),
        )
        models.db.session.add(row)
        models.db.session.commit()
        return row

    def with_result(self, query, rows, retrieved_at=None):
        result = self.factory.create_query_result(
            data={"columns": [{"name": "orders"}], "rows": rows},
            retrieved_at=retrieved_at or utils.utcnow(),
            data_source=query.data_source,
        )
        query.latest_query_data = result
        models.db.session.add(query)
        models.db.session.commit()
        return result

    # --- find_alerts -----------------------------------------------------

    def test_an_alert_is_found_by_its_name(self):
        self.an_alert(name="Orders have dried up")

        self.assertIn("Orders have dried up", self.text("find_alerts", {"question": "dried up"}))

    def test_and_by_the_name_of_the_query_behind_it(self):
        # Alerts are often named for the threshold while the subject somebody
        # asks about is in the query's name.
        self.an_alert(name="Below 100")

        self.assertIn("Below 100", self.text("find_alerts", {"question": "orders per hour"}))

    def test_the_condition_comes_back_as_words_rather_than_option_keys(self):
        self.an_alert(name="Quiet", options={"column": "orders", "op": "<", "value": 100})

        found = self.text("find_alerts", {"question": "quiet"})

        self.assertIn("orders < 100", found)

    def test_a_selector_is_shown_because_it_changes_what_is_measured(self):
        self.an_alert(name="Peak", options={"column": "latency", "op": ">", "value": 2, "selector": "max"})

        self.assertIn("max(latency) > 2", self.text("find_alerts", {"question": "peak"}))

    def test_a_spelled_out_operator_reads_as_a_symbol(self):
        # The model has accepted both forms for years; only one of them reads.
        self.an_alert(name="Legacy", options={"column": "orders", "op": "less than", "value": 100})

        self.assertIn("orders < 100", self.text("find_alerts", {"question": "legacy"}))

    def test_the_fire_count_is_the_point_of_the_line(self):
        alert = self.an_alert(name="Flapper")
        for minutes in (10, 40, 70):
            self.fire(alert, models.Alert.TRIGGERED_STATE, value=412, minutes_ago=minutes)

        self.assertIn("3 fires in 24h", self.text("find_alerts", {"question": "flapper"}))

    def test_a_fire_older_than_the_window_is_not_counted(self):
        alert = self.an_alert(name="Quiet lately")
        self.fire(alert, models.Alert.TRIGGERED_STATE, value=1, minutes_ago=60 * 25)

        self.assertNotIn("fire in 24h", self.text("find_alerts", {"question": "quiet lately"}))

    def test_muted_is_said_on_the_line(self):
        # An alert evaluating and telling nobody looks identical to a quiet
        # one, which is exactly the confusion worth spending a word on.
        self.an_alert(name="Hushed", options={"column": "orders", "op": "<", "value": 1, "muted": True})

        self.assertIn("MUTED", self.text("find_alerts", {"question": "hushed"}))

    def test_an_alert_on_a_source_this_key_cannot_read_is_not_found(self):
        other = self.factory.create_data_source(name="locked", group=self.factory.create_group(name="Locked"))
        self.an_alert(name="Secret threshold", query=self.factory.create_query(name="Private", data_source=other))

        self.assertIn("No alerts match", self.text("find_alerts", {"question": "secret threshold"}))

    def test_nothing_matching_says_so_rather_than_answering_emptily(self):
        self.assertIn("No alerts match", self.text("find_alerts", {"question": "payroll"}))

    # --- explain_alert ---------------------------------------------------

    def test_explain_gives_the_condition_and_the_query(self):
        alert = self.an_alert(name="Orders low")

        said = self.text("explain_alert", {"id": alert.id})

        self.assertIn("Condition: orders < 100", said)
        self.assertIn("Orders per hour", said)

    def test_the_history_carries_the_value_each_change_was_decided_on(self):
        alert = self.an_alert(name="Orders low")
        self.fire(alert, models.Alert.TRIGGERED_STATE, value=412, minutes_ago=30)

        said = self.text("explain_alert", {"id": alert.id})

        self.assertIn("triggered at 412", said)

    def test_a_change_nobody_was_told_about_says_so(self):
        # The difference between "we missed the message" and "no message was
        # ever sent", which is the first thing somebody asks.
        alert = self.an_alert(name="Silent")
        self.fire(alert, models.Alert.TRIGGERED_STATE, value=7, notified=False, minutes_ago=5)

        self.assertIn("nobody notified", self.text("explain_alert", {"id": alert.id}))

    def test_the_history_is_capped_so_a_month_of_flapping_cannot_fill_a_window(self):
        alert = self.an_alert(name="Noisy")
        for minute in range(30):
            self.fire(alert, models.Alert.TRIGGERED_STATE, value=minute, minutes_ago=minute)

        said = self.text("explain_alert", {"id": alert.id})

        # Twenty lines of history, and a line saying there is more.
        self.assertEqual(20, said.count("triggered at"))
        self.assertIn("there may be more", said)

    def test_the_current_value_comes_from_the_querys_last_run(self):
        alert = self.an_alert(name="Orders low")
        self.with_result(alert.query_rel, [{"orders": 412}])

        self.assertIn("orders = 412", self.text("explain_alert", {"id": alert.id}))

    def test_a_stale_result_is_refused_as_the_current_value(self):
        # A threshold checked against a result three days old reads as an
        # answer and sends somebody to the threshold when the real fault is
        # that nothing has run.
        alert = self.an_alert(name="Orders low")
        self.with_result(alert.query_rel, [{"orders": 412}], retrieved_at=utils.utcnow() - datetime.timedelta(days=3))

        said = self.text("explain_alert", {"id": alert.id})

        self.assertIn("too old to read as the current value", said)
        self.assertIn("3 days ago", said)

    def test_a_query_that_has_never_run_says_so(self):
        alert = self.an_alert(name="Brand new")

        self.assertIn("never run", self.text("explain_alert", {"id": alert.id}))

    def test_a_column_the_query_no_longer_returns_is_named(self):
        # The alert cannot evaluate at all, and the reason is in the query's
        # columns rather than in the threshold.
        alert = self.an_alert(name="Renamed")
        self.with_result(alert.query_rel, [{"order_count": 412}])

        self.assertIn("no longer returns a column called orders", self.text("explain_alert", {"id": alert.id}))

    def test_nobody_subscribed_is_worth_saying(self):
        alert = self.an_alert(name="Shouting into a void")

        self.assertIn("nobody is subscribed", self.text("explain_alert", {"id": alert.id}))

    def test_a_destination_is_named_with_the_kind_it_is(self):
        # "Slack" and "email" are different answers to "was anybody told",
        # because one of them wakes a channel up.
        alert = self.an_alert(name="Orders low")
        self.factory.create_alert_subscription(alert=alert, user=self.factory.user)
        models.db.session.commit()

        self.assertIn("(slack)", self.text("explain_alert", {"id": alert.id}))

    def test_a_subscription_with_no_destination_is_mail_to_that_person(self):
        alert = self.an_alert(name="Orders low")
        self.factory.create_alert_subscription(alert=alert, user=self.factory.user, destination=None)
        models.db.session.commit()

        said = self.text("explain_alert", {"id": alert.id})

        self.assertIn("email to {}".format(self.factory.user.email), said)

    def test_rearm_is_explained_because_it_looks_like_the_condition_clearing(self):
        alert = self.an_alert(name="Throttled")
        alert.rearm = 3600
        models.db.session.add(alert)
        models.db.session.commit()

        self.assertIn("Rearm: 3600", self.text("explain_alert", {"id": alert.id}))

    def test_an_alert_this_key_cannot_read_is_refused_without_confirming_it_exists(self):
        other = self.factory.create_data_source(name="locked", group=self.factory.create_group(name="Locked"))
        alert = self.an_alert(query=self.factory.create_query(name="Private", data_source=other))

        said = self.call("explain_alert", {"id": alert.id})

        # The same answer as for an id that does not exist: saying which would
        # confirm an alert exists to somebody who may not see it.
        self.assertIn("No alert #{}".format(alert.id), said["error"]["message"])

    def test_an_id_that_does_not_exist_is_refused_the_same_way(self):
        said = self.call("explain_alert", {"id": 999999})

        self.assertIn("No alert #999999", said["error"]["message"])

    def test_both_tools_are_offered_without_any_write_permission(self):
        # They read; they join the nine that an OAuth session may call.
        offered = json.loads(self.post(rpc("tools/list")).data)["result"]["tools"]
        names = [tool["name"] for tool in offered]

        self.assertIn("find_alerts", names)
        self.assertIn("explain_alert", names)

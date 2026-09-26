import json
from unittest import mock

from sqldesk import models, settings
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

    def test_rows_are_truncated_for_reading_not_silently(self):
        many = {"columns": [{"name": "n"}], "rows": [{"n": i} for i in range(500)]}
        with mock.patch("sqldesk.mcp._on_a_worker", return_value=(many, None)):
            body = self.call("run_query", {"sql": "SELECT 1", "data_source": self.factory.data_source.name})
        text = body["result"]["content"][0]["text"]
        self.assertIn("450 more rows returned", text)

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
        group = self.factory.create_group(name="Viewers")
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

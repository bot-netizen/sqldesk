"""
Sharing a dashboard to Slack.

Driven against a stub of Slack's Web API rather than mocks of our own
functions, so the parts most likely to be wrong are the parts under test: the
three-step upload, the pagination, and the translation of Slack's terse error
identifiers into sentences somebody can act on.
"""

import json
from unittest import mock

from sqldesk import models, settings, slack
from sqldesk.models import db
from tests import BaseTestCase


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("{}".format(self.status_code))


class FakeSlack:
    """
    Slack, as far as this feature is concerned.

    Records what it was asked, so a test can assert on the message that would
    have been posted rather than only on the fact that something was.
    """

    def __init__(self, **answers):
        self.answers = {
            "auth.test": {"ok": True, "team": "Acme", "user": "sqldesk", "team_id": "T1"},
            "conversations.list": {
                "ok": True,
                "channels": [
                    {"id": "C1", "name": "general", "is_private": False, "is_member": True},
                    {"id": "C2", "name": "secrets", "is_private": True, "is_member": True},
                ],
            },
            "files.getUploadURLExternal": {"ok": True, "upload_url": "https://files.slack/upload", "file_id": "F1"},
            "files.completeUploadExternal": {"ok": True},
            "chat.postMessage": {"ok": True, "channel": "C1", "ts": "1.0"},
        }
        self.answers.update(answers)
        self.calls = []

    def __call__(self, url, **kwargs):
        if url.startswith("https://files.slack/"):
            self.calls.append(("upload-bytes", kwargs.get("data")))
            return FakeResponse({}, 200)
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, kwargs.get("data") or {}))
        answer = self.answers.get(method, {"ok": False, "error": "unknown_method"})
        if isinstance(answer, FakeResponse):
            return answer
        return FakeResponse(answer)

    def asked(self, method):
        return [payload for name, payload in self.calls if name == method]

    def posted(self):
        sent = self.asked("chat.postMessage")
        return json.loads(sent[0]["blocks"]) if sent else None


class SlackTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.slack = FakeSlack()
        patch = mock.patch("sqldesk.slack.requests.post", self.slack)
        patch.start()
        self.addCleanup(patch.stop)
        # Sending needs a renderer: `send_dashboards` is not even offered as a
        # permission without one, because there is nothing to send without a
        # picture. The tests that assert the *absence* of a renderer say so
        # for themselves.
        rendering = mock.patch.multiple(
            settings,
            FEATURE_ALERT_SCREENSHOTS=True,
            SCREENSHOT_URL="http://screenshots:3000",
        )
        rendering.start()
        self.addCleanup(rendering.stop)

    def installed(self, token="xoxb-real"):
        workspace = models.SlackWorkspace(org=self.factory.org, bot_token=token, team_name="Acme", app_name="sqldesk")
        db.session.add(workspace)
        db.session.commit()
        return workspace

    def sender(self):
        group = self.factory.create_group(
            name="Senders", permissions=models.Group.DEFAULT_PERMISSIONS + ["send_dashboards"]
        )
        db.session.add(group)
        db.session.commit()
        return self.factory.create_user(group_ids=[group.id, self.factory.default_group.id])


class TestTheClient(SlackTestCase):
    def test_a_good_token_says_which_workspace(self):
        who, error = slack.check("xoxb-real")

        self.assertIsNone(error)
        self.assertEqual("Acme", who["team"])

    def test_the_token_travels_in_a_header_not_the_body(self):
        # A form body is the thing most likely to be logged by something in
        # between.
        slack.check("xoxb-real")

        self.assertNotIn("xoxb-real", json.dumps(self.slack.asked("auth.test")))

    def test_a_revoked_token_is_explained_rather_than_echoed(self):
        self.slack.answers["auth.test"] = {"ok": False, "error": "token_revoked"}

        _who, error = slack.check("xoxb-old")

        self.assertIn("revoked", error)
        self.assertNotIn("token_revoked", error)

    def test_an_error_nobody_anticipated_still_names_itself(self):
        # Better a terse identifier than "something went wrong".
        self.slack.answers["auth.test"] = {"ok": False, "error": "some_new_thing"}

        _who, error = slack.check("xoxb-real")

        self.assertIn("some_new_thing", error)

    def test_a_network_failure_is_a_sentence(self):
        import requests

        with mock.patch("sqldesk.slack.requests.post", side_effect=requests.ConnectionError("down")):
            _who, error = slack.check("xoxb-real")

        self.assertIn("Could not reach Slack", error)

    def test_a_non_json_answer_does_not_raise(self):
        self.slack.answers["auth.test"] = FakeResponse(None, 502)

        _who, error = slack.check("xoxb-real")

        self.assertIn("not JSON", error)

    def test_rate_limiting_says_to_wait(self):
        self.slack.answers["auth.test"] = FakeResponse({"ok": False, "error": "ratelimited"}, 429)

        _who, error = slack.check("xoxb-real")

        self.assertIn("rate-limiting", error)

    def test_channels_come_back_public_first_then_private(self):
        found, error = slack.channels("xoxb-real")

        self.assertIsNone(error)
        self.assertEqual(["general", "secrets"], [c["name"] for c in found])
        self.assertTrue(found[1]["private"])

    def test_channels_follows_slacks_pagination(self):
        pages = [
            {
                "ok": True,
                "channels": [{"id": "C1", "name": "one", "is_private": False, "is_member": True}],
                "response_metadata": {"next_cursor": "more"},
            },
            {"ok": True, "channels": [{"id": "C2", "name": "two", "is_private": False, "is_member": True}]},
        ]

        def answer(url, **kwargs):
            if url.endswith("conversations.list"):
                return FakeResponse(pages.pop(0))
            return FakeResponse({"ok": True})

        with mock.patch("sqldesk.slack.requests.post", answer):
            found, error = slack.channels("xoxb-real")

        self.assertIsNone(error)
        self.assertEqual(["one", "two"], [c["name"] for c in found])

    def test_archived_channels_are_not_asked_for(self):
        slack.channels("xoxb-real")

        self.assertEqual("true", self.slack.asked("conversations.list")[0]["exclude_archived"])

    def test_uploading_is_three_calls_in_order(self):
        # `files.upload` was one call and is being switched off; this is what
        # replaced it, and getting the order wrong fails only at runtime.
        file_id, error = slack.upload("xoxb-real", "d.png", b"PNGDATA")

        self.assertIsNone(error)
        self.assertEqual("F1", file_id)
        self.assertEqual(
            ["files.getUploadURLExternal", "upload-bytes", "files.completeUploadExternal"],
            [name for name, _payload in self.slack.calls],
        )

    def test_it_tells_slack_the_length_it_will_send(self):
        slack.upload("xoxb-real", "d.png", b"PNGDATA")

        self.assertEqual(7, self.slack.asked("files.getUploadURLExternal")[0]["length"])

    def test_an_upload_slack_will_not_accept_is_reported(self):
        self.slack.answers["files.getUploadURLExternal"] = {"ok": False, "error": "upload_limit_reached"}

        file_id, error = slack.upload("xoxb-real", "d.png", b"PNGDATA")

        self.assertIsNone(file_id)
        self.assertIn("file storage limit", error)

    def test_a_missing_upload_url_is_not_an_exception(self):
        self.slack.answers["files.getUploadURLExternal"] = {"ok": True}

        file_id, error = slack.upload("xoxb-real", "d.png", b"PNGDATA")

        self.assertIsNone(file_id)
        self.assertIn("somewhere to upload", error)

    def test_the_message_carries_the_picture_by_file_id(self):
        # Not a URL: an uploaded file has no publicly fetchable one, which is
        # the whole reason it was uploaded rather than linked.
        slack.post("xoxb-real", "C1", "look", file_id="F1", button={"text": "Open", "url": "http://x/"})

        blocks = self.slack.posted()
        image = [b for b in blocks if b["type"] == "image"][0]
        self.assertEqual({"id": "F1"}, image["slack_file"])

    def test_and_a_button_that_goes_somewhere(self):
        slack.post("xoxb-real", "C1", "look", file_id="F1", button={"text": "Open", "url": "http://x/d/1"})

        actions = [b for b in self.slack.posted() if b["type"] == "actions"][0]
        self.assertEqual("http://x/d/1", actions["elements"][0]["url"])

    def test_the_fallback_text_is_always_sent(self):
        # Without it a phone banner shows an empty message.
        slack.post("xoxb-real", "C1", "revenue is up", file_id="F1")

        self.assertEqual("revenue is up", self.slack.asked("chat.postMessage")[0]["text"])

    def test_links_in_the_message_are_not_unfurled(self):
        # The picture is the message. A second preview under it is noise.
        slack.post("xoxb-real", "C1", "look")

        sent = self.slack.asked("chat.postMessage")[0]
        self.assertEqual("false", sent["unfurl_links"])

    def test_a_channel_the_app_is_not_in_says_to_invite_it(self):
        self.slack.answers["chat.postMessage"] = {"ok": False, "error": "not_in_channel"}

        _posted, error = slack.post("xoxb-real", "C9", "look")

        self.assertIn("Invite it", error)


class TestSettingUpSlack(SlackTestCase):
    def save(self, token="xoxb-real", user=None):
        return self.make_request(
            "post", "/api/settings/slack", data={"bot_token": token}, user=user or self.factory.create_admin()
        )

    def test_an_administrator_pastes_a_token(self):
        response = self.save()

        self.assertEqual(200, response.status_code)
        self.assertEqual("Acme", response.json["team_name"])
        self.assertEqual(1, models.SlackWorkspace.query.count())

    def test_the_token_is_checked_with_slack_before_it_is_stored(self):
        # So a wrong one is refused while somebody is still looking at the
        # field, rather than the first time a dashboard fails to send.
        self.slack.answers["auth.test"] = {"ok": False, "error": "invalid_auth"}

        response = self.save(token="xoxb-wrong")

        self.assertEqual(400, response.status_code)
        self.assertIn("rejected the token", response.json["message"])
        self.assertEqual(0, models.SlackWorkspace.query.count())

    def test_it_is_stored_encrypted(self):
        self.save(token="xoxb-secret-value")

        stored = db.session.execute("select encrypted_bot_token from slack_workspaces").scalar()
        self.assertNotIn("xoxb-secret-value", stored)
        self.assertEqual("xoxb-secret-value", models.SlackWorkspace.query.one().bot_token)

    def test_the_token_is_never_sent_back(self):
        # Not even partially. A bot token posts as the app in every channel the
        # app is in and does not expire; there is no version of showing it that
        # is worth the risk.
        self.save(token="xoxb-secret-value")

        response = self.make_request("get", "/api/settings/slack", user=self.factory.create_admin())

        self.assertNotIn("xoxb", json.dumps(response.json))
        self.assertTrue(response.json["configured"])

    def test_pasting_a_second_token_replaces_the_first(self):
        self.save(token="xoxb-one")

        self.save(token="xoxb-two")

        self.assertEqual(1, models.SlackWorkspace.query.count())
        self.assertEqual("xoxb-two", models.SlackWorkspace.query.one().bot_token)

    def test_nothing_configured_says_so_rather_than_erroring(self):
        response = self.make_request("get", "/api/settings/slack", user=self.factory.create_admin())

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["configured"])

    def test_disconnecting_removes_it(self):
        self.save()

        response = self.make_request("delete", "/api/settings/slack", user=self.factory.create_admin())

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, models.SlackWorkspace.query.count())

    def test_somebody_who_is_not_an_administrator_may_not_look_or_change_it(self):
        self.assertEqual(403, self.make_request("get", "/api/settings/slack", user=self.factory.user).status_code)
        self.assertEqual(403, self.save(user=self.factory.user).status_code)

    def test_a_blank_token_is_refused_without_asking_slack(self):
        response = self.save(token="   ")

        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.slack.asked("auth.test"))


class TestListingChannels(SlackTestCase):
    def test_somebody_who_may_send_gets_the_list(self):
        self.installed()

        response = self.make_request("get", "/api/slack/channels", user=self.sender())

        self.assertEqual(200, response.status_code)
        self.assertEqual(["general", "secrets"], [c["name"] for c in response.json["channels"]])

    def test_somebody_who_may_not_send_does_not(self):
        self.installed()

        response = self.make_request("get", "/api/slack/channels", user=self.factory.user)

        self.assertEqual(403, response.status_code)

    def test_with_slack_not_set_up_it_says_what_to_do(self):
        response = self.make_request("get", "/api/slack/channels", user=self.sender())

        self.assertEqual(400, response.status_code)
        self.assertIn("administrator", response.json["message"])

    def test_a_revoked_token_is_remembered_where_settings_can_show_it(self):
        # From here a revoked token looks exactly like a working one until
        # something is sent, so the failure needs somewhere to live other than
        # a worker's log.
        workspace = self.installed()
        self.slack.answers["conversations.list"] = {"ok": False, "error": "token_revoked"}

        self.make_request("get", "/api/slack/channels", user=self.sender())

        db.session.refresh(workspace)
        self.assertIn("revoked", workspace.last_error)
        self.assertFalse(workspace.working)

    def test_and_a_working_one_clears_it(self):
        workspace = self.installed()
        workspace.last_error = "something old"
        db.session.commit()

        self.make_request("get", "/api/slack/channels", user=self.sender())

        db.session.refresh(workspace)
        self.assertIsNone(workspace.last_error)


class TestSendingADashboard(SlackTestCase):
    def setUp(self):
        super().setUp()
        self.installed()
        self.dashboard = self.factory.create_dashboard(name="Revenue")
        db.session.commit()
        self.drawn = mock.patch("sqldesk.screenshots.capture", return_value=b"PNGDATA")
        self.drawn.start()
        self.addCleanup(self.drawn.stop)

    def widgets(self, count):
        for index in range(count):
            query = self.factory.create_query()
            visualization = self.factory.create_visualization(query_rel=query)
            self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()

    def send(self, user=None, **body):
        payload = {"channel": "C1", "text": "revenue is up"}
        payload.update(body)
        return self.make_request(
            "post",
            "/api/dashboards/{}/share/slack".format(self.dashboard.id),
            data=payload,
            user=user or self.sender(),
        )

    def test_it_arrives_with_the_picture_and_a_button(self):
        self.widgets(2)

        response = self.send()

        self.assertEqual(200, response.status_code, response.json)
        kinds = [block["type"] for block in self.slack.posted()]
        self.assertIn("image", kinds)
        self.assertIn("actions", kinds)

    def test_the_senders_words_are_in_it(self):
        self.widgets(1)

        self.send(text="look at Q3")

        self.assertIn("look at Q3", json.dumps(self.slack.posted()))

    def test_and_so_is_who_sent_it(self):
        # A dashboard arriving in a channel from nobody is a dashboard nobody
        # can ask about.
        self.widgets(1)
        sender = self.sender()

        self.send(user=sender)

        self.assertIn(sender.name, json.dumps(self.slack.posted()))

    def test_the_picture_is_uploaded_rather_than_linked(self):
        # Which is the whole reason this works on a VPN: Slack never reaches in.
        self.widgets(1)

        self.send()

        self.assertEqual(1, len(self.slack.asked("files.getUploadURLExternal")))

    def test_a_dashboard_too_big_for_one_page_is_refused_before_anything_is_drawn(self):
        # Eight seconds of rendering to be told no is eight seconds wasted, and
        # the answer does not depend on the picture.
        self.widgets(14)

        response = self.send()

        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.slack.asked("files.getUploadURLExternal"))

    def test_somebody_without_the_permission_may_not_send(self):
        self.widgets(1)

        response = self.send(user=self.factory.user)

        self.assertEqual(403, response.status_code)
        self.assertEqual([], self.slack.asked("chat.postMessage"))

    def test_nor_may_somebody_who_cannot_see_the_dashboard(self):
        # Sending a dashboard's contents to a channel is at least as much
        # access as opening it.
        self.widgets(1)
        other_group = self.factory.create_group(name="Theirs")
        db.session.add(other_group)
        db.session.commit()
        theirs = self.factory.create_data_source(group=other_group, name="theirs")
        query = self.factory.create_query(data_source=theirs)
        visualization = self.factory.create_visualization(query_rel=query)
        hidden = self.factory.create_dashboard(name="Theirs")
        self.factory.create_widget(dashboard=hidden, visualization=visualization)
        db.session.commit()

        response = self.make_request(
            "post",
            "/api/dashboards/{}/share/slack".format(hidden.id),
            data={"channel": "C1"},
            user=self.sender(),
        )

        self.assertEqual(403, response.status_code)

    def test_with_no_channel_it_says_to_pick_one(self):
        self.widgets(1)

        self.assertEqual(400, self.send(channel="").status_code)

    def test_a_failed_upload_does_not_post_a_message_without_the_picture(self):
        # A message saying "look at this dashboard" with no dashboard in it is
        # worse than no message.
        self.widgets(1)
        self.slack.answers["files.getUploadURLExternal"] = {"ok": False, "error": "upload_limit_reached"}

        response = self.send()

        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.slack.asked("chat.postMessage"))

    def test_a_failed_post_is_reported_to_the_person_who_pressed_send(self):
        self.widgets(1)
        self.slack.answers["chat.postMessage"] = {"ok": False, "error": "not_in_channel"}

        response = self.send()

        self.assertEqual(400, response.status_code)
        self.assertIn("Invite it", response.json["message"])

    def test_with_no_renderer_nobody_may_send_at_all(self):
        # Not a message about a missing renderer: `send_dashboards` is not
        # granted without one, so the button is never offered and the endpoint
        # refuses as a permission. That is why there is no "no renderer" branch
        # in the handler -- it would be unreachable.
        self.widgets(1)

        with mock.patch.multiple(settings, FEATURE_ALERT_SCREENSHOTS=True, SCREENSHOT_URL=""):
            response = self.send()

        self.assertEqual(403, response.status_code)
        self.assertEqual([], self.slack.asked("chat.postMessage"))

    def test_a_render_that_comes_back_empty_is_not_sent(self):
        self.widgets(1)

        with mock.patch("sqldesk.screenshots.capture", return_value=None):
            response = self.send()

        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.slack.asked("chat.postMessage"))


class TestWhereTheButtonGoes(SlackTestCase):
    def setUp(self):
        super().setUp()
        self.installed()
        self.dashboard = self.factory.create_dashboard(name="Revenue")
        query = self.factory.create_query()
        visualization = self.factory.create_visualization(query_rel=query)
        self.factory.create_widget(dashboard=self.dashboard, visualization=visualization)
        db.session.commit()
        drawn = mock.patch("sqldesk.screenshots.capture", return_value=b"PNGDATA")
        drawn.start()
        self.addCleanup(drawn.stop)

    def button_url(self):
        actions = [b for b in self.slack.posted() if b["type"] == "actions"][0]
        return actions["elements"][0]["url"]

    def send(self):
        return self.make_request(
            "post",
            "/api/dashboards/{}/share/slack".format(self.dashboard.id),
            data={"channel": "C1"},
            user=self.sender(),
        )

    def test_the_public_link_where_there_is_one(self):
        # So anybody in the channel can open it without an account here.
        models.db.session.add(models.ApiKey(org=self.factory.org, object=self.dashboard, api_key="abc123"))
        db.session.commit()

        self.send()

        self.assertIn("/public/dashboards/abc123", self.button_url())

    def test_the_dashboards_own_address_where_there_is_not(self):
        # The honest fallback: a link people sign in to, rather than one half
        # the channel cannot use and nobody told them about.
        self.send()

        self.assertIn("/dashboards/", self.button_url())
        self.assertNotIn("/public/", self.button_url())

    def test_and_where_the_organisation_has_turned_public_links_off(self):
        models.db.session.add(models.ApiKey(org=self.factory.org, object=self.dashboard, api_key="abc123"))
        db.session.commit()
        self.factory.org.set_setting("disable_public_urls", True)
        db.session.add(self.factory.org)
        db.session.commit()

        self.send()

        self.assertNotIn("/public/", self.button_url())


class TestAnAlertThroughTheSlackApp(SlackTestCase):
    """
    The reason this destination exists: an incoming webhook cannot upload a
    file, so an alert sent that way says a threshold was crossed and shows
    nothing -- which for an alert on a chart is most of the information
    missing.
    """

    def setUp(self):
        super().setUp()
        from sqldesk.destinations.slack_app import SlackApp

        self.destination = SlackApp({"channel": "C1"})
        # The alert's body templates render the result that fired it, so the
        # query needs one and the alert needs a column to look at.
        result = self.factory.create_query_result(
            data={"rows": [{"value": 1}], "columns": [{"name": "value", "type": "INTEGER"}]}
        )
        self.query = self.factory.create_query(latest_query_data_id=result.id)
        self.alert = self.factory.create_alert(
            query_rel=self.query,
            options={"selector": "first", "op": "equals", "column": "value", "value": "1"},
        )
        db.session.commit()

    def notify(self, state="triggered", pictures=None, options=None):
        self.destination.options = options if options is not None else {"channel": "C1"}
        self.destination.notify(
            self.alert,
            self.query,
            self.factory.user,
            state,
            None,
            "https://sqldesk.example.com",
            {"screenshots": pictures or []},
            self.destination.options,
        )

    def picture(self, name="dashboard-1.png", title="Revenue"):
        return {"filename": name, "image": b"PNGDATA", "title": title}

    def test_the_message_carries_the_picture(self):
        self.installed()

        self.notify(pictures=[self.picture()])

        kinds = [block["type"] for block in self.slack.posted()]
        self.assertIn("image", kinds)

    def test_and_a_button_to_the_query(self):
        self.installed()

        self.notify(pictures=[self.picture()])

        actions = [b for b in self.slack.posted() if b["type"] == "actions"][0]
        self.assertIn("/queries/{}".format(self.query.id), actions["elements"][0]["url"])

    def test_a_triggered_alert_says_what_the_number_was(self):
        # It used to say "<name> just triggered", which is the one thing the
        # arrival of the message had already said. Since 0.8 the headline
        # carries the reading and the line it crossed -- see
        # sqldesk/alerting.py, shared with the webhook destination.
        self.installed()

        self.notify()

        posted = json.dumps(self.slack.posted())
        self.assertIn(self.alert.name, posted)
        self.assertIn(str(self.alert.options["value"]), posted)

    def test_and_one_that_recovered_says_that(self):
        self.installed()

        self.notify(state="ok")

        self.assertIn("went back to normal", json.dumps(self.slack.posted()))

    def test_a_custom_body_is_sent_exactly_as_written(self):
        # It is not ours to append to.
        self.installed()
        self.alert.options = dict(self.alert.options or {}, custom_body="Revenue is below plan.")
        db.session.commit()

        self.notify()

        self.assertIn("Revenue is below plan.", json.dumps(self.slack.posted()))

    def test_several_pictures_arrive_as_several_messages(self):
        # A Slack message carries one image block, and an alert told to attach
        # three dashboards should send three rather than silently send one.
        self.installed()

        self.notify(pictures=[self.picture("a.png"), self.picture("b.png"), self.picture("c.png")])

        self.assertEqual(3, len(self.slack.asked("chat.postMessage")))

    def test_a_picture_that_will_not_upload_does_not_stop_the_alert(self):
        # The threshold was still crossed, and somebody still needs to know.
        self.installed()
        self.slack.answers["files.getUploadURLExternal"] = {"ok": False, "error": "upload_limit_reached"}

        self.notify(pictures=[self.picture()])

        self.assertEqual(1, len(self.slack.asked("chat.postMessage")))

    def test_but_it_says_the_picture_is_missing(self):
        # An alert about a chart arriving with no chart and no explanation
        # reads as the alert being broken.
        self.installed()
        self.slack.answers["files.getUploadURLExternal"] = {"ok": False, "error": "upload_limit_reached"}

        self.notify(pictures=[self.picture(title="Revenue")])

        self.assertIn("could not be attached", json.dumps(self.slack.posted()))

    def test_with_no_workspace_connected_nothing_is_sent(self):
        # And it is said once in the log with what to do, rather than an alert
        # firing into nothing every five minutes.
        self.notify(pictures=[self.picture()])

        self.assertEqual([], self.slack.asked("chat.postMessage"))

    def test_with_no_channel_nothing_is_sent(self):
        self.installed()

        self.notify(options={"channel": "  "})

        self.assertEqual([], self.slack.asked("chat.postMessage"))

    def test_a_refusal_is_remembered_where_settings_can_show_it(self):
        workspace = self.installed()
        self.slack.answers["chat.postMessage"] = {"ok": False, "error": "not_in_channel"}

        self.notify()

        db.session.refresh(workspace)
        self.assertIn("Invite it", workspace.last_error)

    def test_and_a_successful_send_clears_it(self):
        workspace = self.installed()
        workspace.last_error = "something from last time"
        db.session.commit()

        self.notify()

        db.session.refresh(workspace)
        self.assertIsNone(workspace.last_error)

    def test_it_takes_no_token_of_its_own(self):
        """
        The token is the organisation's, entered once by an administrator and
        stored encrypted. A destination carrying its own would mean a bot token
        in a form field on a page anybody with alert permissions can reach.
        """
        from sqldesk.destinations.slack_app import SlackApp

        schema = SlackApp.configuration_schema()

        self.assertEqual(["channel"], list(schema["properties"]))
        self.assertNotIn("secret", schema)

    def test_the_webhook_destination_still_exists(self):
        # Replacing it would break every alert already using it, for a feature
        # not everybody wants.
        from sqldesk.destinations import destinations

        self.assertIn("slack", destinations)
        self.assertIn("slack_app", destinations)

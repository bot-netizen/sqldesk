from unittest import mock

import requests

from sqldesk import models, render_pass, screenshots
from sqldesk.models import db
from tests import BaseTestCase

RENDERER = "http://screenshots:3000"


def _on(**overrides):
    """Turn the feature on for one test."""
    settings = {"FEATURE_ALERT_SCREENSHOTS": True, "SCREENSHOT_URL": RENDERER}
    settings.update(overrides)
    return mock.patch.multiple("sqldesk.screenshots.settings", **settings)


class TestEnabled(BaseTestCase):
    def test_off_unless_a_renderer_is_named(self):
        # The flag alone is not enough: with nowhere to send the request there
        # is nothing to turn on, and an install that never sets this behaves
        # exactly as it did before the feature existed.
        with mock.patch.multiple("sqldesk.screenshots.settings", FEATURE_ALERT_SCREENSHOTS=True, SCREENSHOT_URL=""):
            self.assertFalse(screenshots.enabled())

    def test_off_when_the_flag_is_off(self):
        with mock.patch.multiple(
            "sqldesk.screenshots.settings", FEATURE_ALERT_SCREENSHOTS=False, SCREENSHOT_URL=RENDERER
        ):
            self.assertFalse(screenshots.enabled())

    def test_on_when_both_are_set(self):
        with _on():
            self.assertTrue(screenshots.enabled())


class TestCapture(BaseTestCase):
    def _query(self, **kwargs):
        query = self.factory.create_query(**kwargs)
        db.session.commit()
        return query

    def test_asks_the_renderer_for_the_embed_page(self):
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(INTERNAL_BASE_URL="http://server:5000"), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query, self.factory.user)

        body = post.call_args[1]["json"]
        self.assertIn(f"/embed/query/{query.id}/visualization/", body["url"])
        self.assertIn("screenshot=1", body["url"])

    def test_shows_the_renderer_its_token(self):
        # The renderer fetches pages for whoever asks; the token is how it
        # knows the worker is asking.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(SCREENSHOT_TOKEN="only-the-worker-knows"), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())
            screenshots.capture(screenshots.QUERY, query, self.factory.user)

        self.assertEqual("only-the-worker-knows", post.call_args[1]["headers"]["X-Screenshot-Token"])

    def test_sends_a_pass_as_a_header_and_never_the_query_own_key(self):
        # In the header rather than the URL, because two services would
        # otherwise write a working credential into their logs -- and a pass
        # rather than the query's own key, which does not expire and opens
        # that query for as long as it exists.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query, self.factory.user)

        body = post.call_args[1]["json"]
        self.assertTrue(body["headers"]["Authorization"].startswith(f"Key {render_pass.PREFIX}"))
        self.assertNotIn(query.api_key, body["url"])
        self.assertNotIn(query.api_key, body["headers"]["Authorization"])

    def test_waits_for_the_page_to_say_it_has_drawn(self):
        # Without this the usual result is a photograph of a spinner.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query, self.factory.user)

        self.assertEqual(post.call_args[1]["json"]["wait_for"], screenshots.READY_SELECTOR)

    def test_draws_the_chart_rather_than_the_table(self):
        # A table is what a query has when nobody has made a visualization;
        # somebody attaching a query to an alert means the chart they built.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="TABLE")
        chart = self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query, self.factory.user)

        self.assertIn(f"/visualization/{chart.id}?", post.call_args[1]["json"]["url"])

    def test_a_dashboard_nobody_has_shared_is_drawn_anyway(self):
        # It used to need a public link, so attaching a dashboard to an alert
        # meant first making it readable by anyone who had the token. A pass
        # is good for this dashboard for five minutes and nothing else.
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            self.assertEqual(b"PNG", screenshots.capture(screenshots.DASHBOARD, dashboard, self.factory.user))

        # And still no public link, which is the whole point.
        self.assertIsNone(models.ApiKey.get_by_object(dashboard))

    def test_a_dashboard_is_drawn_whole_through_a_pass(self):
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.DASHBOARD, dashboard, self.factory.user)

        body = post.call_args[1]["json"]
        self.assertIn(render_pass.PREFIX, body["url"])
        # A dashboard is usually taller than a window.
        self.assertTrue(body["full_page"])


class TestDrawnTheWayItsSenderSeesIt(BaseTestCase):
    """
    A Slack picture of a dashboard showed eight tiles where the same person's
    Export as image showed eighteen: the export is the dashboard on their
    2800px screen, the renderer had a 1400px window of its own. The width
    their browser last reported goes with every picture sent in their name.
    """

    def _send(self, kind, obj, viewer):
        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())
            screenshots.capture(kind, obj, viewer)
        return post.call_args[1]["json"]

    def test_a_dashboard_is_drawn_at_the_senders_width_and_in_their_zone(self):
        dashboard = self.factory.create_dashboard()
        user = self.factory.user
        user.details = {**(user.details or {}), "screen": {"width": 2780, "time_zone": "America/Toronto"}}
        db.session.commit()

        body = self._send(screenshots.DASHBOARD, dashboard, user)

        # The window is wider than the dashboard by the frame drawn round it,
        # so the dashboard itself is exactly as wide as it was on the screen.
        self.assertEqual(body["width"], 2780 + screenshots.FRAME_WIDTH)
        self.assertEqual(body["time_zone"], "America/Toronto")

    def test_somebody_who_never_reported_a_screen_gets_the_renderers_window(self):
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        body = self._send(screenshots.DASHBOARD, dashboard, self.factory.user)

        self.assertNotIn("width", body)
        self.assertNotIn("time_zone", body)

    def test_a_query_keeps_the_renderers_window_but_takes_the_zone(self):
        query = self.factory.create_query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        user = self.factory.user
        user.details = {**(user.details or {}), "screen": {"width": 2780, "time_zone": "Europe/London"}}
        db.session.commit()

        body = self._send(screenshots.QUERY, query, user)

        self.assertNotIn("width", body)
        self.assertEqual(body["time_zone"], "Europe/London")

    def test_nonsense_is_never_passed_on(self):
        dashboard = self.factory.create_dashboard()
        user = self.factory.user
        user.details = {**(user.details or {}), "screen": {"width": 99999, "time_zone": "Mars/Olympus"}}
        db.session.commit()

        body = self._send(screenshots.DASHBOARD, dashboard, user)

        self.assertNotIn("width", body)
        self.assertNotIn("time_zone", body)


class TestScreenValues(BaseTestCase):
    def test_widths(self):
        self.assertEqual(screenshots.clean_screen_width(1400), 1400)
        self.assertEqual(screenshots.clean_screen_width(1399.6), 1400)
        self.assertIsNone(screenshots.clean_screen_width(screenshots.MIN_SCREEN_WIDTH - 1))
        self.assertIsNone(screenshots.clean_screen_width(screenshots.MAX_SCREEN_WIDTH + 1))
        self.assertIsNone(screenshots.clean_screen_width("1400"))
        self.assertIsNone(screenshots.clean_screen_width(True))
        self.assertIsNone(screenshots.clean_screen_width(None))

    def test_time_zones(self):
        self.assertEqual(screenshots.clean_time_zone("America/Toronto"), "America/Toronto")
        self.assertEqual(screenshots.clean_time_zone("UTC"), "UTC")
        self.assertIsNone(screenshots.clean_time_zone("America/Nowhere"))
        self.assertIsNone(screenshots.clean_time_zone("../../etc/passwd"))
        self.assertIsNone(screenshots.clean_time_zone(None))

    def test_a_user_with_no_details(self):
        user = mock.Mock(details=None)
        self.assertEqual(screenshots.screen_of(user), (None, None))


class TestTableOrders(BaseTestCase):
    """
    A table sorted by its header on screen was exported sorted and sent to
    Slack in the query's order. The order on screen is kept, per dashboard,
    for the pictures sent in that person's name.
    """

    ORDER = {"12": [{"name": "slot_requests", "direction": "descend"}]}

    def test_keeps_only_well_formed_orders(self):
        orders = screenshots.clean_table_orders(
            {
                "12": [{"name": "slot_requests", "direction": "descend", "extra": 1}],
                "13": [{"name": "x", "direction": "sideways"}],
                "not-a-widget": [{"name": "x", "direction": "ascend"}],
                "14": "slot_requests",
            }
        )
        self.assertEqual(orders, {"12": [{"name": "slot_requests", "direction": "descend"}]})
        self.assertEqual(screenshots.clean_table_orders(None), {})

    def test_remembers_one_dashboard_without_touching_another(self):
        user = self.factory.user
        screenshots.remember_table_orders(user, 4, self.ORDER)
        screenshots.remember_table_orders(user, 5, {"20": [{"name": "a", "direction": "ascend"}]})
        db.session.commit()

        self.assertEqual(screenshots.table_orders_of(user, mock.Mock(id=4)), self.ORDER)
        self.assertEqual(screenshots.table_orders_of(user, mock.Mock(id=5))["20"][0]["name"], "a")

    def test_nothing_sorted_forgets_the_dashboard(self):
        user = self.factory.user
        screenshots.remember_table_orders(user, 4, self.ORDER)

        self.assertTrue(screenshots.remember_table_orders(user, 4, {}))
        self.assertEqual(screenshots.table_orders_of(user, mock.Mock(id=4)), {})

    def test_the_same_order_again_changes_nothing(self):
        user = self.factory.user
        screenshots.remember_table_orders(user, 4, self.ORDER)
        self.assertFalse(screenshots.remember_table_orders(user, 4, self.ORDER))

    def test_keeps_the_most_recent_dashboards_only(self):
        user = self.factory.user
        for dashboard_id in range(1, screenshots.MAX_SORTED_DASHBOARDS + 6):
            screenshots.remember_table_orders(user, dashboard_id, self.ORDER)

        self.assertEqual(len(user.details["table_orders"]), screenshots.MAX_SORTED_DASHBOARDS)
        self.assertEqual(screenshots.table_orders_of(user, mock.Mock(id=1)), {})
        self.assertEqual(
            screenshots.table_orders_of(user, mock.Mock(id=screenshots.MAX_SORTED_DASHBOARDS + 5)), self.ORDER
        )


class TestCaptureNeverRaises(BaseTestCase):
    """
    A picture is a nice-to-have. An alert is not.

    Every one of these used to be a way for a screenshot to become the reason
    a threshold breach went unreported, which is the one outcome this feature
    must never cause.
    """

    def _query_with_chart(self):
        query = self.factory.create_query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()
        return query

    def test_a_renderer_that_is_not_there(self):
        query = self._query_with_chart()
        with _on(), mock.patch("sqldesk.screenshots.requests.post", side_effect=requests.ConnectionError("refused")):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query, self.factory.user))

    def test_a_renderer_that_takes_too_long(self):
        query = self._query_with_chart()
        with _on(), mock.patch("sqldesk.screenshots.requests.post", side_effect=requests.Timeout("slow")):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query, self.factory.user))

    def test_a_renderer_that_returns_an_error(self):
        query = self._query_with_chart()
        failing = mock.Mock()
        failing.raise_for_status.side_effect = requests.HTTPError("502")
        with _on(), mock.patch("sqldesk.screenshots.requests.post", return_value=failing):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query, self.factory.user))

    def test_a_renderer_that_returns_nothing(self):
        query = self._query_with_chart()
        empty = mock.Mock(content=b"", raise_for_status=mock.Mock())
        with _on(), mock.patch("sqldesk.screenshots.requests.post", return_value=empty):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query, self.factory.user))

    def test_a_query_with_nothing_to_draw(self):
        query = self.factory.create_query()
        db.session.commit()
        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query, self.factory.user))
        post.assert_not_called()


class TestForAlert(BaseTestCase):
    def _alert_with(self, attachments):
        query = self.factory.create_query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        alert = self.factory.create_alert(query_rel=query)
        alert.options = dict(alert.options or {}, attachments=attachments)
        db.session.commit()
        return alert, query

    def test_nothing_at_all_when_the_feature_is_off(self):
        alert, query = self._alert_with([{"type": "query", "id": 1}])
        with mock.patch("sqldesk.screenshots.requests.post") as post:
            self.assertEqual(screenshots.for_alert(alert), [])
        post.assert_not_called()

    def test_takes_the_name_from_the_object_not_the_alert(self):
        # The name saved on the alert goes stale the moment anybody renames
        # the dashboard, and a picture labelled with last month's name is
        # worse than one labelled with none.
        alert, query = self._alert_with([])
        alert.options["attachments"] = [{"type": "query", "id": query.id, "name": "what it used to be called"}]
        query.name = "what it is called now"
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            images = screenshots.for_alert(alert)

        self.assertEqual(images[0]["title"], "what it is called now")

    def test_draws_each_attachment(self):
        alert, query = self._alert_with([{"type": "query", "id": None}])
        alert.options["attachments"] = [{"type": "query", "id": query.id}]
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            images = screenshots.for_alert(alert)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["filename"], f"query-{query.id}.png")
        self.assertEqual(images[0]["image"], b"PNG")
        # Named, so the email can say what each picture is of.
        self.assertEqual(images[0]["title"], query.name)
        self.assertEqual(images[0]["kind"], "query")

    def test_never_more_than_the_cap(self):
        # An alert carrying twenty dashboards takes minutes to send and
        # arrives as something nobody opens.
        alert, query = self._alert_with([{"type": "query", "id": None}])
        alert.options["attachments"] = [{"type": "query", "id": query.id}] * 20
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            images = screenshots.for_alert(alert)

        self.assertEqual(len(images), 5)

    def test_one_that_fails_does_not_lose_the_others(self):
        alert, query = self._alert_with([])
        other = self.factory.create_query()
        self.factory.create_visualization(query_rel=other, type="CHART")
        alert.options["attachments"] = [
            {"type": "query", "id": 9999999},  # deleted since it was attached
            {"type": "query", "id": other.id},
        ]
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            images = screenshots.for_alert(alert)

        self.assertEqual([i["filename"] for i in images], [f"query-{other.id}.png"])

    def test_an_alert_with_no_attachments_asks_for_nothing(self):
        alert, _ = self._alert_with([])
        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            self.assertEqual(screenshots.for_alert(alert), [])
        post.assert_not_called()

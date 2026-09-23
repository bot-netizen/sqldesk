from unittest import mock

import requests

from sqldesk import models, screenshots
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

            screenshots.capture(screenshots.QUERY, query)

        body = post.call_args[1]["json"]
        self.assertIn(f"/embed/query/{query.id}/visualization/", body["url"])
        self.assertIn("screenshot=1", body["url"])

    def test_sends_the_key_as_a_header_not_in_the_url(self):
        # Two services would otherwise write a working credential into their
        # logs.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query)

        body = post.call_args[1]["json"]
        self.assertEqual(body["headers"]["Authorization"], f"Key {query.api_key}")
        self.assertNotIn(query.api_key, body["url"])

    def test_waits_for_the_page_to_say_it_has_drawn(self):
        # Without this the usual result is a photograph of a spinner.
        query = self._query()
        self.factory.create_visualization(query_rel=query, type="CHART")
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.QUERY, query)

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

            screenshots.capture(screenshots.QUERY, query)

        self.assertIn(f"/visualization/{chart.id}?", post.call_args[1]["json"]["url"])

    def test_a_dashboard_nobody_has_shared_is_not_drawn(self):
        # And no link is created for it: making a dashboard publicly reachable
        # is the owner's decision, not a side effect of attaching it.
        dashboard = self.factory.create_dashboard()
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            self.assertIsNone(screenshots.capture(screenshots.DASHBOARD, dashboard))

        post.assert_not_called()
        self.assertIsNone(models.ApiKey.get_by_object(dashboard))

    def test_a_shared_dashboard_is_drawn_whole(self):
        dashboard = self.factory.create_dashboard()
        key = models.ApiKey.create_for_object(dashboard, self.factory.user)
        db.session.commit()

        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            post.return_value = mock.Mock(content=b"PNG", raise_for_status=mock.Mock())

            screenshots.capture(screenshots.DASHBOARD, dashboard)

        body = post.call_args[1]["json"]
        self.assertIn(key.api_key, body["url"])
        # A dashboard is usually taller than a window.
        self.assertTrue(body["full_page"])


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
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query))

    def test_a_renderer_that_takes_too_long(self):
        query = self._query_with_chart()
        with _on(), mock.patch("sqldesk.screenshots.requests.post", side_effect=requests.Timeout("slow")):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query))

    def test_a_renderer_that_returns_an_error(self):
        query = self._query_with_chart()
        failing = mock.Mock()
        failing.raise_for_status.side_effect = requests.HTTPError("502")
        with _on(), mock.patch("sqldesk.screenshots.requests.post", return_value=failing):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query))

    def test_a_renderer_that_returns_nothing(self):
        query = self._query_with_chart()
        empty = mock.Mock(content=b"", raise_for_status=mock.Mock())
        with _on(), mock.patch("sqldesk.screenshots.requests.post", return_value=empty):
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query))

    def test_a_query_with_nothing_to_draw(self):
        query = self.factory.create_query()
        db.session.commit()
        with _on(), mock.patch("sqldesk.screenshots.requests.post") as post:
            self.assertIsNone(screenshots.capture(screenshots.QUERY, query))
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

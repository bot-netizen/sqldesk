from sqldesk import models
from tests import BaseTestCase


class TestAnIdThatMatchesNothing(BaseTestCase):
    """A mistyped or deleted id came back as a 500, which reads as the server broken."""

    def test_is_a_404_not_a_500(self):
        for method, path, body in (
            ("delete", "/api/widgets/999999", None),
            ("post", "/api/widgets/999999", {"options": {}, "text": ""}),
            ("post", "/api/dashboards/999999", {"name": "x", "version": 1}),
        ):
            with self.subTest(path):
                rv = self.make_request(method, path, data=body)
                self.assertEqual(404, rv.status_code, rv.data[:200])


class WidgetAPITest(BaseTestCase):
    def create_widget(self, dashboard, visualization, width=1):
        data = {
            "visualization_id": visualization.id,
            "dashboard_id": dashboard.id,
            "options": {},
            "width": width,
        }

        rv = self.make_request("post", "/api/widgets", data=data)

        return rv

    def test_create_widget(self):
        dashboard = self.factory.create_dashboard()
        vis = self.factory.create_visualization()

        rv = self.create_widget(dashboard, vis)
        self.assertEqual(rv.status_code, 200)

    def test_wont_create_widget_for_visualization_you_dont_have_access_to(self):
        dashboard = self.factory.create_dashboard()
        vis = self.factory.create_visualization()
        ds = self.factory.create_data_source(group=self.factory.create_group())
        vis.query_rel.data_source = ds

        models.db.session.add(vis.query_rel)

        data = {
            "visualization_id": vis.id,
            "dashboard_id": dashboard.id,
            "options": {},
            "width": 1,
        }

        rv = self.make_request("post", "/api/widgets", data=data)
        self.assertEqual(rv.status_code, 403)

    def test_create_text_widget(self):
        dashboard = self.factory.create_dashboard()

        data = {
            "visualization_id": None,
            "text": "Sample text.",
            "dashboard_id": dashboard.id,
            "options": {},
            "width": 2,
        }

        rv = self.make_request("post", "/api/widgets", data=data)

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["text"], "Sample text.")

    def test_create_text_widget_without_mentioning_a_visualization_at_all(self):
        """
        The browser always sends `visualization_id: null`, so this only ever
        bit whoever wrote against the API themselves -- and it bit them with a
        500 and a traceback in the log for a request that is simply a textbox.
        """
        dashboard = self.factory.create_dashboard()

        rv = self.make_request(
            "post",
            "/api/widgets",
            data={"text": "No visualization here.", "dashboard_id": dashboard.id, "options": {}, "width": 1},
        )

        self.assertEqual(200, rv.status_code, rv.data[:200])
        self.assertEqual("No visualization here.", rv.json["text"])
        self.assertIsNone(rv.json.get("visualization"))

    def test_delete_widget(self):
        widget = self.factory.create_widget()

        rv = self.make_request("delete", "/api/widgets/{0}".format(widget.id))

        self.assertEqual(rv.status_code, 200)
        dashboard = models.Dashboard.get_by_slug_and_org(widget.dashboard.slug, widget.dashboard.org)
        self.assertEqual(dashboard.widgets.count(), 0)

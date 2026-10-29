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


class TestAWidgetWithTabs(BaseTestCase):
    """
    One widget drawing its query several ways.

    A query returning region, channel, product and a sum has three charts in
    it, not one, and before this each of those had to be its own widget. That
    is three fetches and three parses of the same result -- the dashboard cost
    that was measured -- and three boxes to arrange. A tabbed widget fetches
    once and draws whichever tab is in front.

    The rule that makes it both cheap and safe is that every tab is a
    visualization of the widget's own query.
    """

    def setUp(self):
        super().setUp()
        self.dashboard = self.factory.create_dashboard()
        self.query = self.factory.create_query()
        self.primary = self.factory.create_visualization(query_rel=self.query)
        self.by_channel = self.factory.create_visualization(query_rel=self.query, name="By channel")
        self.by_product = self.factory.create_visualization(query_rel=self.query, name="By product")
        models.db.session.commit()

    def create(self, tabs=None, visualization=None):
        rv = self.make_request(
            "post",
            "/api/widgets",
            data={
                "visualization_id": (visualization or self.primary).id,
                "dashboard_id": self.dashboard.id,
                "options": {} if tabs is None else {"tabs": tabs},
                "width": 1,
            },
        )
        self.assertEqual(200, rv.status_code, rv.data[:300])
        return rv.json

    def saved_tabs(self, widget_json):
        return models.Widget.query.get(widget_json["id"]).options.get("tabs")

    def test_tabs_on_the_same_query_are_kept_in_order(self):
        widget = self.create(tabs=[self.by_product.id, self.by_channel.id])

        self.assertEqual([self.by_product.id, self.by_channel.id], self.saved_tabs(widget))

    def test_a_widget_with_no_tabs_carries_no_tab_key_at_all(self):
        # The ordinary widget is untouched by this existing.
        widget = self.create()

        self.assertNotIn("tabs", models.Widget.query.get(widget["id"]).options)
        self.assertEqual([], widget["tab_visualizations"])

    def test_a_visualization_of_another_query_is_dropped(self):
        # The rule that makes a tab free: every tab draws the result already
        # fetched for this widget. One from another query would have to fetch,
        # and would show data this widget's access was never checked against.
        other = self.factory.create_visualization(query_rel=self.factory.create_query())
        models.db.session.commit()

        widget = self.create(tabs=[self.by_channel.id, other.id])

        self.assertEqual([self.by_channel.id], self.saved_tabs(widget))

    def test_the_widgets_own_visualization_is_not_also_a_tab(self):
        # It is always the first tab; naming it would draw it twice.
        widget = self.create(tabs=[self.primary.id, self.by_channel.id])

        self.assertEqual([self.by_channel.id], self.saved_tabs(widget))

    def test_the_same_tab_twice_is_one_tab(self):
        widget = self.create(tabs=[self.by_channel.id, self.by_channel.id])

        self.assertEqual([self.by_channel.id], self.saved_tabs(widget))

    def test_rubbish_in_the_list_is_dropped_rather_than_refused(self):
        # The list is cosmetic and the widget still draws. A dashboard that
        # will not save because of one bad id in a blob helps nobody.
        widget = self.create(tabs=["seven", None, True, 999999, self.by_channel.id])

        self.assertEqual([self.by_channel.id], self.saved_tabs(widget))

    def test_tabs_that_are_not_a_list_are_ignored(self):
        widget = self.create(tabs={"not": "a list"})

        self.assertNotIn("tabs", models.Widget.query.get(widget["id"]).options)

    def test_more_tabs_than_a_strip_can_carry_are_cut(self):
        from sqldesk.handlers.widgets import MAX_WIDGET_TABS

        extra = [self.factory.create_visualization(query_rel=self.query) for _ in range(MAX_WIDGET_TABS + 2)]
        models.db.session.commit()

        widget = self.create(tabs=[one.id for one in extra])

        # The widget's own visualization is the first tab, so the stored list
        # is one shorter than the limit.
        self.assertEqual(MAX_WIDGET_TABS - 1, len(self.saved_tabs(widget)))

    def test_a_textbox_has_no_query_to_draw_and_so_no_tabs(self):
        rv = self.make_request(
            "post",
            "/api/widgets",
            data={
                "dashboard_id": self.dashboard.id,
                "text": "a note",
                "options": {"tabs": [self.by_channel.id]},
                "width": 1,
            },
        )

        self.assertEqual(200, rv.status_code, rv.data[:300])
        self.assertNotIn("tabs", models.Widget.query.get(rv.json["id"]).options)

    def test_tabs_can_be_changed_after_the_widget_exists(self):
        widget = self.create(tabs=[self.by_channel.id])

        rv = self.make_request(
            "post",
            "/api/widgets/{}".format(widget["id"]),
            data={"text": "", "options": {"tabs": [self.by_product.id]}},
        )

        self.assertEqual(200, rv.status_code, rv.data[:300])
        self.assertEqual([self.by_product.id], self.saved_tabs(widget))

    def test_an_update_is_checked_the_same_way_a_create_is(self):
        other = self.factory.create_visualization(query_rel=self.factory.create_query())
        models.db.session.commit()
        widget = self.create(tabs=[self.by_channel.id])

        self.make_request(
            "post",
            "/api/widgets/{}".format(widget["id"]),
            data={"text": "", "options": {"tabs": [other.id]}},
        )

        self.assertEqual(None, self.saved_tabs(widget))

    def test_tabs_removed_by_an_update_leave_nothing_behind(self):
        widget = self.create(tabs=[self.by_channel.id])

        self.make_request(
            "post",
            "/api/widgets/{}".format(widget["id"]),
            data={"text": "", "options": {}},
        )

        self.assertNotIn("tabs", models.Widget.query.get(widget["id"]).options)

    def test_an_update_keeps_the_rest_of_the_options(self):
        widget = self.create(tabs=[self.by_channel.id])

        self.make_request(
            "post",
            "/api/widgets/{}".format(widget["id"]),
            data={"text": "", "options": {"tabs": [self.by_channel.id], "position": {"row": 3}}},
        )

        saved = models.Widget.query.get(widget["id"]).options
        self.assertEqual({"row": 3}, saved["position"])
        self.assertEqual([self.by_channel.id], saved["tabs"])


class TestWhatATabbedWidgetSends(BaseTestCase):
    """
    What the dashboard payload carries for a tabbed widget.

    A dashboard is already the heaviest thing the application sends, so a tab
    costs a name, a type and its options -- and not another copy of the query
    it shares with the widget.
    """

    def setUp(self):
        super().setUp()
        self.query = self.factory.create_query()
        self.primary = self.factory.create_visualization(query_rel=self.query)
        self.second = self.factory.create_visualization(query_rel=self.query, name="By channel")
        self.third = self.factory.create_visualization(query_rel=self.query, name="By product")
        self.dashboard = self.factory.create_dashboard()
        self.widget = self.factory.create_widget(
            dashboard=self.dashboard,
            visualization=self.primary,
            options={"tabs": [self.third.id, self.second.id]},
        )
        models.db.session.commit()

    def serialized(self):
        from sqldesk.serializers import serialize_widget

        return serialize_widget(models.Widget.query.get(self.widget.id))

    def test_the_tabs_arrive_in_the_saved_order(self):
        names = [one["name"] for one in self.serialized()["tab_visualizations"]]

        self.assertEqual(["By product", "By channel"], names)

    def test_a_tab_does_not_repeat_the_query_it_shares(self):
        for one in self.serialized()["tab_visualizations"]:
            self.assertNotIn("query", one)

    def test_a_tab_carries_what_it_takes_to_draw(self):
        tab = self.serialized()["tab_visualizations"][0]

        self.assertEqual({"id", "type", "name", "description", "options", "updated_at", "created_at"}, set(tab))

    def test_a_deleted_visualization_is_skipped_rather_than_left_as_a_hole(self):
        models.db.session.delete(self.third)
        models.db.session.commit()

        names = [one["name"] for one in self.serialized()["tab_visualizations"]]

        self.assertEqual(["By channel"], names)

from tealdash.models import Dashboard
from tests import BaseTestCase


class TestDashboardContentCounts(BaseTestCase):
    def test_returns_empty_dict_for_no_ids(self):
        self.assertEqual(Dashboard.content_counts([]), {})

    def test_counts_panels_and_distinct_queries(self):
        dashboard = self.factory.create_dashboard()
        query = self.factory.create_query()

        # Two panels charting the SAME query, plus one charting another.
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query)
        )
        self.factory.create_widget(
            dashboard=dashboard, visualization=self.factory.create_visualization(query_rel=query)
        )
        self.factory.create_widget(dashboard=dashboard, visualization=self.factory.create_visualization())

        counts = Dashboard.content_counts([dashboard.id])

        self.assertEqual(counts[dashboard.id]["widget_count"], 3)
        # Three panels, two distinct queries: the point of the column is how
        # many queries the dashboard costs to refresh, not how many panels.
        self.assertEqual(counts[dashboard.id]["query_count"], 2)

    def test_text_widgets_count_as_panels_but_not_queries(self):
        dashboard = self.factory.create_dashboard()
        self.factory.create_widget(dashboard=dashboard, visualization=None, text="a textbox")

        counts = Dashboard.content_counts([dashboard.id])

        self.assertEqual(counts[dashboard.id]["widget_count"], 1)
        self.assertEqual(counts[dashboard.id]["query_count"], 0)

    def test_keeps_dashboards_separate(self):
        first = self.factory.create_dashboard()
        second = self.factory.create_dashboard()
        self.factory.create_widget(dashboard=first)
        self.factory.create_widget(dashboard=second)
        self.factory.create_widget(dashboard=second)

        counts = Dashboard.content_counts([first.id, second.id])

        self.assertEqual(counts[first.id]["widget_count"], 1)
        self.assertEqual(counts[second.id]["widget_count"], 2)

    def test_omits_dashboards_with_no_widgets(self):
        # An empty dashboard produces no row, so callers must default to 0
        # rather than assume every id is present.
        empty = self.factory.create_dashboard()
        self.assertNotIn(empty.id, Dashboard.content_counts([empty.id]))

from sqldesk.models import QueryResult, result_row_count
from tests import BaseTestCase


class TestRowCountOf(BaseTestCase):
    def test_counts_rows(self):
        self.assertEqual(result_row_count({"columns": [], "rows": [{"a": 1}, {"a": 2}]}), 2)

    def test_empty_result_is_zero_not_none(self):
        # An empty result genuinely returned zero rows; that is not "unknown".
        self.assertEqual(result_row_count({"columns": [], "rows": []}), 0)

    def test_unknown_shapes_are_none(self):
        # None rather than 0, so the UI can say unknown instead of asserting
        # a query returned nothing.
        self.assertIsNone(result_row_count(None))
        self.assertIsNone(result_row_count("a json string"))
        self.assertIsNone(result_row_count({"columns": []}))
        self.assertIsNone(result_row_count({"rows": None}))

    def test_store_result_persists_the_count(self):
        data_source = self.factory.create_data_source()
        result = QueryResult.store_result(
            data_source.org_id,
            data_source,
            "hash",
            "select 1",
            {"columns": [{"name": "a"}], "rows": [{"a": 1}, {"a": 2}, {"a": 3}]},
            1.0,
            self.factory.create_query().created_at,
        )
        self.assertEqual(result.row_count, 3)

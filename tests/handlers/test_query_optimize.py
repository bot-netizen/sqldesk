from sqldesk import models
from tests import BaseTestCase


class TestQueryOptimize(BaseTestCase):
    """
    Stateless on purpose: the editor sends whatever is in it, saved or not,
    because the query you want checked is usually the one you have not saved.
    """

    def test_it_finds_things_in_unsaved_sql(self):
        response = self.make_request(
            "post", "/api/queries/optimize", data={"query": "SELECT * FROM orders"}, user=self.factory.user
        )
        self.assertEqual(200, response.status_code)
        rules = {f["rule"] for f in response.json["findings"]}
        self.assertIn("select_star", rules)
        self.assertIn("no_predicate", rules)

    def test_the_data_source_decides_the_dialect(self):
        response = self.make_request(
            "post",
            "/api/queries/optimize",
            data={"query": "SELECT id FROM orders LIMIT 1", "data_source_id": self.factory.data_source.id},
            user=self.factory.user,
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json["applicable"])

    def test_a_data_source_you_cannot_see_is_refused(self):
        # Nothing is executed, but the dialect and the findings describe that
        # source, so it is gated the same way reading it is.
        other_org = self.factory.create_org(name="Other", slug="other-opt")
        other_source = self.factory.create_data_source(org=other_org)
        response = self.make_request(
            "post",
            "/api/queries/optimize",
            data={"query": "SELECT 1", "data_source_id": other_source.id},
            user=self.factory.user,
        )
        self.assertIn(response.status_code, (403, 404))

    def test_half_written_sql_is_reported_not_an_error(self):
        response = self.make_request(
            "post", "/api/queries/optimize", data={"query": "SELECT FROM WHERE"}, user=self.factory.user
        )
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json["applicable"])

    def test_it_needs_no_model_configured(self):
        # The deterministic half works on an instance with no AI at all, which
        # is the point of shipping it first.
        self.assertIsNone(models.AIProvider.get_for_org(self.factory.org))
        response = self.make_request(
            "post", "/api/queries/optimize", data={"query": "SELECT * FROM t"}, user=self.factory.user
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json["applicable"])

    def test_anonymous_callers_get_nothing(self):
        response = self.make_request("post", "/api/queries/optimize", data={"query": "SELECT 1"}, user=False)
        self.assertIn(response.status_code, (302, 401, 404))

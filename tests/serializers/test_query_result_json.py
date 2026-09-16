import json

from tealdash.serializers import serialize_query_result, serialize_query_result_json
from tealdash.utils import json_dumps
from tests import BaseTestCase


class QueryResultJsonTest(BaseTestCase):
    """The splicing path must be indistinguishable from encoding the dict.

    It exists only to avoid decoding and re-encoding a payload that is already
    JSON on disk, so any difference in the bytes it produces is a bug, not an
    optimisation.
    """

    def _result(self, data):
        # JSONText encodes on write, so the factory takes the object, not text.
        return self.factory.create_query_result(data=data)

    def test_matches_the_dict_encoding_byte_for_byte(self):
        data = {
            "columns": [{"name": "id", "friendly_name": "id", "type": "integer"}],
            "rows": [{"id": 1}, {"id": 2}],
        }
        qr = self._result(data)

        spliced = serialize_query_result_json(qr, is_api_user=False)
        encoded = json_dumps({"query_result": serialize_query_result(qr, False)})

        self.assertEqual(json.loads(spliced), json.loads(encoded))

    def test_payload_survives_intact(self):
        data = {"columns": [], "rows": [{"n": i} for i in range(50)]}
        qr = self._result(data)

        parsed = json.loads(serialize_query_result_json(qr, is_api_user=False))
        self.assertEqual(parsed["query_result"]["data"], data)

    def test_api_user_gets_only_the_public_keys(self):
        qr = self._result({"columns": [], "rows": []})

        parsed = json.loads(serialize_query_result_json(qr, is_api_user=True))
        self.assertEqual(set(parsed["query_result"].keys()), {"data", "retrieved_at"})

    def test_payload_containing_the_slot_marker_is_not_corrupted(self):
        # The marker is spliced with a single replace, so a payload that happens
        # to contain the marker text must not be able to displace it.
        marker = "tealdash-payload"
        data = {"columns": [], "rows": [{"note": marker}]}
        qr = self._result(data)

        parsed = json.loads(serialize_query_result_json(qr, is_api_user=False))
        self.assertEqual(parsed["query_result"]["data"]["rows"][0]["note"], marker)

    def test_missing_payload_serialises_as_null(self):
        qr = self.factory.create_query_result(data=None)

        parsed = json.loads(serialize_query_result_json(qr, is_api_user=False))
        self.assertIsNone(parsed["query_result"]["data"])

    def test_does_not_load_the_deferred_column(self):
        # The whole point: reading the raw text must not trigger the lazy load
        # that would decode the payload.
        from sqlalchemy import inspect

        from tealdash.models import QueryResult, db

        qr = self._result({"columns": [], "rows": [{"n": 1}]})
        db.session.commit()
        db.session.expunge_all()

        loaded = QueryResult.get_by_id_and_org_deferred_data(qr.id, qr.org)
        self.assertIn("data", inspect(loaded).unloaded)

        serialize_query_result_json(loaded, is_api_user=False)
        self.assertIn("data", inspect(loaded).unloaded)

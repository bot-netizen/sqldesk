import datetime

from sqldesk import models
from sqldesk.utils import gen_query_hash, utcnow
from tests import BaseTestCase


class QueryResultTest(BaseTestCase):
    def test_get_latest_returns_none_if_not_found(self):
        found_query_result = models.QueryResult.get_latest(self.factory.data_source, "SELECT 1", 60)
        self.assertIsNone(found_query_result)

    def test_get_latest_returns_when_found(self):
        qr = self.factory.create_query_result()
        found_query_result = models.QueryResult.get_latest(qr.data_source, qr.query_text, 60)

        self.assertEqual(qr, found_query_result)

    def test_get_latest_doesnt_return_query_from_different_data_source(self):
        qr = self.factory.create_query_result()
        data_source = self.factory.create_data_source()
        found_query_result = models.QueryResult.get_latest(data_source, qr.query_text, 60)

        self.assertIsNone(found_query_result)

    def test_get_latest_doesnt_return_if_ttl_expired(self):
        yesterday = utcnow() - datetime.timedelta(days=1)
        qr = self.factory.create_query_result(retrieved_at=yesterday)

        found_query_result = models.QueryResult.get_latest(qr.data_source, qr.query_text, max_age=60)

        self.assertIsNone(found_query_result)

    def test_get_latest_returns_if_ttl_not_expired(self):
        yesterday = utcnow() - datetime.timedelta(seconds=30)
        qr = self.factory.create_query_result(retrieved_at=yesterday)

        found_query_result = models.QueryResult.get_latest(qr.data_source, qr.query_text, max_age=120)

        self.assertEqual(found_query_result, qr)

    def test_get_latest_returns_the_most_recent_result(self):
        yesterday = utcnow() - datetime.timedelta(seconds=30)
        self.factory.create_query_result(retrieved_at=yesterday)
        qr = self.factory.create_query_result()

        found_query_result = models.QueryResult.get_latest(qr.data_source, qr.query_text, 60)

        self.assertEqual(found_query_result.id, qr.id)

    def test_get_latest_returns_the_last_cached_result_for_negative_ttl(self):
        yesterday = utcnow() + datetime.timedelta(days=-100)
        self.factory.create_query_result(retrieved_at=yesterday)

        yesterday = utcnow() + datetime.timedelta(days=-1)
        qr = self.factory.create_query_result(retrieved_at=yesterday)
        found_query_result = models.QueryResult.get_latest(qr.data_source, qr.query_text, -1)

        self.assertEqual(found_query_result.id, qr.id)

    def test_store_result_does_not_modify_query_update_at(self):
        original_updated_at = utcnow() - datetime.timedelta(hours=1)
        query = self.factory.create_query(updated_at=original_updated_at)

        models.QueryResult.store_result(
            query.org_id,
            query.data_source,
            query.query_hash,
            query.query_text,
            {},
            0,
            utcnow(),
        )

        self.assertEqual(original_updated_at, query.updated_at)


class LatestIdsTest(BaseTestCase):
    """
    `latest_ids` answers for several query hashes at once, which is what a
    live dashboard's check-in needs. It has to give the same answers as
    `get_latest` does one at a time, because that is the contract it replaced.
    """

    def _result(self, text, **kwargs):
        return self.factory.create_query_result(query_text=text, query_hash=gen_query_hash(text), **kwargs)

    def test_finds_the_newest_for_each_hash(self):
        old = self._result("SELECT 1", retrieved_at=utcnow() - datetime.timedelta(seconds=30))
        new = self._result("SELECT 1")
        other = self._result("SELECT 2")

        found = models.QueryResult.latest_ids(
            self.factory.data_source.id, [gen_query_hash("SELECT 1"), gen_query_hash("SELECT 2")]
        )

        self.assertEqual(found[gen_query_hash("SELECT 1")], new.id)
        self.assertNotEqual(found[gen_query_hash("SELECT 1")], old.id)
        self.assertEqual(found[gen_query_hash("SELECT 2")], other.id)

    def test_a_hash_with_no_result_is_absent_rather_than_none(self):
        found = models.QueryResult.latest_ids(self.factory.data_source.id, [gen_query_hash("SELECT 1")])
        self.assertEqual(found, {})

    def test_asks_nothing_when_given_nothing(self):
        self.assertEqual(models.QueryResult.latest_ids(self.factory.data_source.id, []), {})
        self.assertEqual(models.QueryResult.latest_ids(self.factory.data_source.id, [None, ""]), {})

    def test_does_not_cross_data_sources(self):
        self._result("SELECT 1")
        other_source = self.factory.create_data_source()

        found = models.QueryResult.latest_ids(other_source.id, [gen_query_hash("SELECT 1")])

        self.assertEqual(found, {})

    def test_an_age_leaves_out_what_is_too_old(self):
        self._result("SELECT 1", retrieved_at=utcnow() - datetime.timedelta(seconds=300))
        fresh = self._result("SELECT 2")

        found = models.QueryResult.latest_ids(
            self.factory.data_source.id,
            [gen_query_hash("SELECT 1"), gen_query_hash("SELECT 2")],
            max_age=60,
        )

        self.assertEqual(found, {gen_query_hash("SELECT 2"): fresh.id})

    def test_agrees_with_get_latest_one_hash_at_a_time(self):
        for text, age in [("SELECT 1", 0), ("SELECT 1", 30), ("SELECT 2", 0), ("SELECT 3", 900)]:
            self._result(text, retrieved_at=utcnow() - datetime.timedelta(seconds=age))

        hashes = [gen_query_hash(t) for t in ("SELECT 1", "SELECT 2", "SELECT 3", "SELECT 4")]
        for max_age in (-1, 60, 3600):
            batched = models.QueryResult.latest_ids(self.factory.data_source.id, hashes, max_age=max_age)
            one_by_one = {}
            for text in ("SELECT 1", "SELECT 2", "SELECT 3", "SELECT 4"):
                found = models.QueryResult.get_latest(self.factory.data_source, text, max_age=max_age)
                if found:
                    one_by_one[gen_query_hash(text)] = found.id
            self.assertEqual(batched, one_by_one, "disagreed at max_age={}".format(max_age))

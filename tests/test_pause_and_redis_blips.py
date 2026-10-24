"""
Two places where a Redis that is restarting used to change what the product
does, rather than what it remembers.
"""

from unittest import mock

from redis.exceptions import ConnectionError as RedisConnectionError

from sqldesk import models
from sqldesk.models import db
from tests import BaseTestCase


class TestAPausedDataSourceStaysPaused(BaseTestCase):
    """
    Pausing a data source is what somebody does when the warehouse is
    overloaded or being migrated. It lived only in Redis, so it lasted until
    the next Redis restart -- after which every scheduled query ran against
    that warehouse again, and nothing said so.
    """

    def test_a_pause_outlives_redis(self):
        source = self.factory.create_data_source()
        source.pause("Migrating the cluster.")
        db.session.commit()

        with mock.patch("sqldesk.models.redis_connection") as redis:
            redis.exists.return_value = False
            redis.get.return_value = None

            self.assertTrue(source.paused)
            self.assertEqual("Migrating the cluster.", source.pause_reason)

    def test_resuming_outlives_it_too(self):
        source = self.factory.create_data_source()
        source.pause("Migrating.")
        db.session.commit()
        source.resume()
        db.session.commit()

        with mock.patch("sqldesk.models.redis_connection") as redis:
            redis.exists.return_value = False

            self.assertFalse(source.paused)

    def test_a_pause_made_before_this_version_is_still_honoured(self):
        # Only Redis knows about it, which is where it used to live.
        source = self.factory.create_data_source()

        with mock.patch("sqldesk.models.redis_connection") as redis:
            redis.exists.return_value = True
            redis.get.return_value = "Paused last week."

            self.assertTrue(source.paused)
            self.assertEqual("Paused last week.", source.pause_reason)

    def test_a_redis_that_is_down_does_not_make_a_source_look_paused(self):
        source = self.factory.create_data_source()

        with mock.patch("sqldesk.models.redis_connection") as redis:
            redis.exists.side_effect = RedisConnectionError("no connection")

            self.assertFalse(source.paused)

    def test_nor_does_it_stop_somebody_pausing_one(self):
        source = self.factory.create_data_source()

        with mock.patch("sqldesk.models.redis_connection") as redis:
            redis.set.side_effect = RedisConnectionError("no connection")
            source.pause("Because.")
        db.session.commit()

        self.assertTrue(source.paused)

    def test_the_api_records_the_pause_where_a_restart_cannot_reach_it(self):
        source = self.factory.create_data_source()
        admin = self.factory.create_admin()

        response = self.make_request(
            "post", "/api/data_sources/{}/pause".format(source.id), data={"reason": "Overloaded."}, user=admin
        )

        self.assertEqual(200, response.status_code)
        db.session.expire_all()
        self.assertIsNotNone(models.DataSource.query.get(source.id).paused_at)

    def test_and_clears_it_the_same_way(self):
        source = self.factory.create_data_source()
        admin = self.factory.create_admin()
        source.pause("Overloaded.")
        db.session.commit()

        self.make_request("delete", "/api/data_sources/{}/pause".format(source.id), user=admin)

        db.session.expire_all()
        self.assertIsNone(models.DataSource.query.get(source.id).paused_at)


class TestARedisBlipDoesNotFailARequest(BaseTestCase):
    """
    "Last seen" is written on every request from a signed-in person, and
    nothing depends on the answer -- but a Redis that was restarting, full or
    read-only failed the write before the handler ran, so every signed-in
    request became a 500 over a cache the product treats as optional.
    """

    def test_a_failed_write_is_logged_and_the_request_goes_on(self):
        with mock.patch("sqldesk.models.users.redis_connection") as redis:
            redis.hset.side_effect = RedisConnectionError("no connection")
            response = self.make_request("get", "/api/queries", user=self.factory.user)

        self.assertEqual(200, response.status_code)

    def test_and_the_write_still_happens_when_redis_is_there(self):
        with mock.patch("sqldesk.models.users.redis_connection") as redis:
            response = self.make_request("get", "/api/queries", user=self.factory.user)

        self.assertEqual(200, response.status_code)
        redis.hset.assert_called()

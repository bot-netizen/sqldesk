"""
Choosing which of a cluster's topics can be queried.

This is the access decision on a Kafka cluster. The data source permission is
per cluster, so whatever somebody enables here is what everybody with access to
that cluster can then query -- which is why it is behind a permission of its
own rather than something any reader can do.
"""

from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.streams import watching
from tests import BaseTestCase


class TopicTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.factory.create_data_source(
            name="Cluster",
            type="kafka_stream",
            options={"brokers": "broker:9092"},
            group=self.factory.default_group,
        )
        db.session.commit()

    def allowed(self, user=None):
        """Hold the permission open; the feature is gated on the SDK."""
        return mock.patch("sqldesk.features.can", lambda *a, **k: True)

    def topics(self, listed):
        return mock.patch("sqldesk.streams.consumer.list_topics", lambda *a, **k: listed)


class TestListingWhatAClusterHas(TopicTestCase):
    def test_it_says_which_are_already_enabled(self):
        db.session.add(models.Stream(org=self.source.org, data_source=self.source, topic="orders"))
        db.session.commit()
        listed = [{"name": "orders", "partitions": 3}, {"name": "payments", "partitions": 1}]

        with self.allowed(), self.topics(listed):
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))

        self.assertEqual(200, rv.status_code)
        by_name = {topic["name"]: topic for topic in rv.json["topics"]}
        self.assertTrue(by_name["orders"]["enabled"])
        self.assertFalse(by_name["payments"]["enabled"])

    def test_without_the_permission_it_refuses(self):
        # Topic names leak the shape of a business, so the list itself is worth
        # not handing to everybody.
        with mock.patch("sqldesk.features.can", lambda *a, **k: False):
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))

        self.assertEqual(403, rv.status_code)

    def test_a_data_source_that_is_not_a_cluster_is_refused(self):
        other = self.factory.create_data_source(name="Warehouse", type="pg", group=self.factory.default_group)
        db.session.commit()

        with self.allowed():
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(other.id))

        self.assertEqual(400, rv.status_code)

    def test_a_broker_that_will_not_answer_says_so(self):
        def refuse(*a, **k):
            raise Exception("no route to host")

        with self.allowed(), mock.patch("sqldesk.streams.consumer.list_topics", refuse):
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))

        self.assertEqual(502, rv.status_code)
        self.assertIn("no route to host", rv.json["message"])


class TestEnablingATopic(TopicTestCase):
    def enable(self, topic="orders", **body):
        return self.make_request("post", "/api/data_sources/{}/topics/{}".format(self.source.id, topic), data=body)

    def test_enabling_one_creates_its_stream(self):
        with self.allowed():
            rv = self.enable()

        self.assertEqual(200, rv.status_code)
        self.assertEqual("orders", rv.json["topic"])
        self.assertEqual(1, models.Stream.query.filter(models.Stream.topic == "orders").count())

    def test_enabling_it_twice_does_not_make_two(self):
        with self.allowed():
            self.enable()
            rv = self.enable(row_budget=1000)

        self.assertEqual(200, rv.status_code)
        self.assertEqual(1, models.Stream.query.count())
        self.assertEqual(1000, models.Stream.query.first().row_budget)

    def test_a_budget_has_to_be_a_whole_number(self):
        with self.allowed():
            rv = self.enable(row_budget=-5)

        self.assertEqual(400, rv.status_code)

    def test_pinning_is_an_administrators_decision(self):
        # A pin keeps a worker and a disk busy with nobody watching.
        with self.allowed():
            rv = self.enable(pinned=True)

        self.assertEqual(403, rv.status_code)

    def test_but_an_administrator_may(self):
        admin = self.factory.create_admin()

        with self.allowed():
            rv = self.make_request(
                "post",
                "/api/data_sources/{}/topics/orders".format(self.source.id),
                data={"pinned": True},
                user=admin,
            )

        self.assertEqual(200, rv.status_code)
        self.assertTrue(models.Stream.query.first().pinned)

    def test_without_the_permission_nothing_is_enabled(self):
        with mock.patch("sqldesk.features.can", lambda *a, **k: False):
            rv = self.enable()

        self.assertEqual(403, rv.status_code)
        self.assertEqual(0, models.Stream.query.count())


class TestTurningOneOff(TopicTestCase):
    def test_it_goes_and_so_does_its_window(self):
        import os

        with self.allowed():
            self.make_request("post", "/api/data_sources/{}/topics/orders".format(self.source.id), data={})
            stream = models.Stream.query.first()
            path = stream.store_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(b"x")

            rv = self.make_request("delete", "/api/data_sources/{}/topics/orders".format(self.source.id))

        self.assertEqual(200, rv.status_code)
        self.assertEqual(0, models.Stream.query.count())
        # Keeping a file for a topic nobody can query is disk nothing reclaims.
        self.assertFalse(os.path.exists(path))

    def test_one_that_is_not_enabled_is_a_404(self):
        with self.allowed():
            rv = self.make_request("delete", "/api/data_sources/{}/topics/nope".format(self.source.id))

        self.assertEqual(404, rv.status_code)


class TestWatchingOne(TopicTestCase):
    """
    Starting a stream takes a slot and needs the permission. Watching one that
    is already running needs neither -- which is what makes sharing a live
    board work without handing the permission to everybody who might open it.
    """

    def setUp(self):
        super().setUp()
        from sqldesk import redis_connection
        from sqldesk.streams import slots

        redis_connection.delete(slots.SLOTS_KEY, slots.LOCK_KEY)
        self.stream = models.Stream(org=self.source.org, data_source=self.source, topic="orders")
        db.session.add(self.stream)
        db.session.commit()

    def watch(self, user=None):
        return self.make_request("post", "/api/streams/{}/watch".format(self.stream.id), user=user)

    def test_starting_one_takes_a_slot_and_records_who(self):
        from sqldesk.streams import slots

        with self.allowed():
            rv = self.watch()

        self.assertEqual(200, rv.status_code)
        self.assertEqual("running", rv.json["state"])
        self.assertIn(self.stream.id, slots.held())
        self.assertEqual(self.factory.user.name, rv.json["started_by"])

    def test_starting_needs_the_permission(self):
        with mock.patch("sqldesk.features.can", lambda *a, **k: False):
            rv = self.watch()

        self.assertEqual(403, rv.status_code)

    def test_but_joining_one_already_running_does_not(self):
        other = self.factory.create_user()
        with self.allowed():
            self.watch()

        with mock.patch("sqldesk.features.can", lambda *a, **k: False):
            rv = self.watch(user=other)

        self.assertEqual(200, rv.status_code)
        self.assertEqual(2, rv.json["watchers"])

    def test_past_the_limit_it_says_so_rather_than_failing_quietly(self):
        from sqldesk.streams import slots

        slots.acquire(999, owner="somebody")

        with self.allowed(), mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
            rv = self.watch()

        self.assertEqual(429, rv.status_code)
        self.assertIn("in use", rv.json["message"])

    def test_leaving_stops_counting_you(self):
        with self.allowed():
            self.watch()
            rv = self.make_request("delete", "/api/streams/{}/watch".format(self.stream.id))

        self.assertEqual(200, rv.status_code)
        from sqldesk.streams import watching

        self.assertEqual(0, watching.watchers(self.stream.id))

    def test_another_organisations_stream_is_not_yours_to_watch(self):
        elsewhere = self.factory.create_org()
        theirs = models.Stream(
            org=elsewhere,
            data_source=self.factory.create_data_source(org=elsewhere, type="kafka_stream"),
            topic="theirs",
        )
        db.session.add(theirs)
        db.session.commit()

        with self.allowed():
            rv = self.make_request("post", "/api/streams/{}/watch".format(theirs.id))

        self.assertEqual(404, rv.status_code)


class TestWhatIsRunning(TopicTestCase):
    def test_it_lists_the_running_ones_and_the_room_left(self):
        from sqldesk import redis_connection
        from sqldesk.streams import slots, watching

        redis_connection.delete(slots.SLOTS_KEY, slots.LOCK_KEY)
        stream = models.Stream(org=self.source.org, data_source=self.source, topic="orders")
        db.session.add(stream)
        db.session.commit()
        watching.check_in(stream.id, "ada")
        slots.acquire(stream.id, owner="ada")

        rv = self.make_request("get", "/api/streams/running")

        self.assertEqual(200, rv.status_code)
        self.assertEqual(["orders"], [one["topic"] for one in rv.json["streams"]])
        self.assertEqual(1, rv.json["slots"]["used"])

    def test_a_cold_stream_is_not_in_it(self):
        # The page answers "what is consuming", and a cold stream is not.
        db.session.add(models.Stream(org=self.source.org, data_source=self.source, topic="quiet"))
        db.session.commit()

        rv = self.make_request("get", "/api/streams/running")

        self.assertEqual([], rv.json["streams"])

    def test_but_only_for_the_clusters_they_can_read(self):
        """A topic's name, columns and errors are the cluster's data."""
        from sqldesk import redis_connection
        from sqldesk.streams import slots, watching

        redis_connection.delete(slots.SLOTS_KEY, slots.LOCK_KEY)
        restricted = self.factory.create_group(name="Payments team")
        theirs = self.factory.create_data_source(
            name="Payments cluster", type="kafka_stream", options={"brokers": "b:9092"}, group=restricted
        )
        ours = models.Stream(org=self.source.org, data_source=self.source, topic="orders")
        hidden = models.Stream(org=self.source.org, data_source=theirs, topic="card_numbers")
        db.session.add_all([ours, hidden])
        db.session.commit()
        for stream in (ours, hidden):
            watching.check_in(stream.id, "ada")
            slots.acquire(stream.id, owner="ada")

        rv = self.make_request("get", "/api/streams/running", user=self.factory.create_user())

        self.assertEqual(["orders"], [one["topic"] for one in rv.json["streams"]])
        # The slots are shared, so the count stays whole.
        self.assertEqual(2, rv.json["slots"]["used"])

    def test_everybody_may_read_it(self):
        # "All the slots are in use" is only actionable if you can see what is
        # using them and who to ask.
        rv = self.make_request("get", "/api/streams/running", user=self.factory.create_user())

        self.assertEqual(200, rv.status_code)


class TestRunningSqlAgainstTheWindows(TopicTestCase):
    """
    The stream query endpoint, which is deliberately not the ordinary one.

    The ordinary path enqueues a job because a warehouse query can take four
    minutes. A stream query reads a local file and returns in milliseconds, and
    runs every couple of seconds while somebody watches -- a round trip through
    Redis and a worker per refresh would cost more than the query. Nothing is
    stored either way: no result row, no query, nothing.
    """

    def ask(self, sql, source=None):
        return self.make_request(
            "post",
            "/api/data_sources/{}/stream_query".format((source or self.source).id),
            data={"query": sql},
        )

    def leave(self, sql, source=None):
        return self.make_request(
            "delete",
            "/api/data_sources/{}/stream_query".format((source or self.source).id),
            data={"query": sql},
        )

    def test_stopping_says_so_rather_than_waiting_to_be_timed_out(self):
        """
        The other half of running one, and for a while it did not exist.

        Pressing Stop ended the page's own polling and told the server nothing,
        so the consumer ran on until the check-in expired and every status read
        still said "consuming" against a stream somebody had just stopped.
        """
        stream = models.Stream(org=self.source.org, data_source=self.source, topic="orders")
        db.session.add(stream)
        db.session.commit()
        watching.check_in(stream.id, self.factory.user.id)
        self.assertEqual(watching.state(stream), watching.RUNNING)

        rv = self.leave("select * from orders")

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["left"], [stream.id])
        self.assertNotEqual(watching.state(stream), watching.RUNNING)

    def test_and_leaves_alone_a_topic_the_query_never_named(self):
        # A slot is a topic, not a viewer: stopping one query must not stop a
        # stream somebody else is reading through another.
        named = models.Stream(org=self.source.org, data_source=self.source, topic="orders")
        other = models.Stream(org=self.source.org, data_source=self.source, topic="payments")
        db.session.add_all([named, other])
        db.session.commit()
        watching.check_in(named.id, self.factory.user.id)
        watching.check_in(other.id, self.factory.user.id)

        rv = self.leave("select * from orders")

        self.assertEqual(rv.json["left"], [named.id])
        self.assertEqual(watching.state(other), watching.RUNNING)

    def test_stopping_something_that_was_never_started_is_not_an_error(self):
        # A page unmounting, a tab closing, a double press: all of them land
        # here and none of them is a fault.
        rv = self.leave("select * from orders")

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["left"], [])

    def test_an_install_with_no_kafka_client_says_so_rather_than_failing(self):
        # What an install looks like after somebody drops the optional
        # dependency group: the rows are here and nothing can read them. A 503
        # with a sentence beats a 500 with a traceback.
        #
        # The runner is taken away explicitly rather than relying on this image
        # not having it. The first version of this test asserted the absence
        # and passed locally for that reason alone -- then failed in CI, where
        # the client *is* installed, which is the one place it had never run.
        with mock.patch.object(models.DataSource, "query_runner", new_callable=mock.PropertyMock, return_value=None):
            rv = self.ask("select 1")

        self.assertEqual(503, rv.status_code)
        self.assertIn("not installed", rv.json["message"])

    def test_an_empty_query_is_refused(self):
        rv = self.make_request(
            "post", "/api/data_sources/{}/stream_query".format(self.source.id), data={"query": "   "}
        )

        self.assertEqual(400, rv.status_code)

    def test_a_data_source_that_is_not_a_cluster_is_refused(self):
        other = self.factory.create_data_source(name="Warehouse", type="pg", group=self.factory.default_group)
        db.session.commit()

        self.assertEqual(400, self.ask("select 1", source=other).status_code)

    def test_nothing_is_written_down(self):
        # The window is what a consumer saw while somebody watched; a copy of
        # it in Postgres would be the one thing this feature is not. True
        # whether the query ran or was refused, which is what makes it worth
        # asserting here rather than only where a broker is running.
        before = models.QueryResult.query.count()

        self.ask("select 1")

        self.assertEqual(before, models.QueryResult.query.count())
        self.assertEqual(0, models.Query.query.count())


class TestHowATopicIsRead(TopicTestCase):
    """
    The consumer group, saving the position and where a cold start begins.

    Lag monitoring alarmed on SQLDesk because every stream joined a group it
    never committed under. The default is now no group the broker can see; a
    name, saving and the start point are each somebody's choice.
    """

    def enable(self, topic="orders", **body):
        return self.make_request("post", "/api/data_sources/{}/topics/{}".format(self.source.id, topic), data=body)

    def stream(self):
        return models.Stream.query.filter(models.Stream.topic == "orders").one()

    def test_by_default_there_is_no_group_nothing_is_saved_and_it_starts_at_the_end(self):
        with self.allowed():
            rv = self.enable()

        self.assertEqual(200, rv.status_code)
        stream = self.stream()
        self.assertIsNone(stream.consumer_group)
        self.assertFalse(stream.save_position)
        self.assertEqual("latest", stream.start_from)

    def test_a_name_is_kept_and_reported_back(self):
        with self.allowed():
            rv = self.enable(consumer_group="analytics-sqldesk.orders")

        self.assertEqual(200, rv.status_code)
        self.assertEqual("analytics-sqldesk.orders", self.stream().consumer_group)
        self.assertEqual("analytics-sqldesk.orders", rv.json["consumer_group"])

    def test_a_blank_name_means_no_group(self):
        with self.allowed():
            self.enable(consumer_group="analytics-sqldesk")
            self.enable(consumer_group="   ")

        self.assertIsNone(self.stream().consumer_group)

    def test_a_name_kafka_would_refuse_is_refused_here_first(self):
        with self.allowed():
            rv = self.enable(consumer_group="has spaces/and slashes")

        self.assertEqual(400, rv.status_code)
        self.assertIn("letters, digits", rv.json["message"])

    def test_saving_the_position_needs_a_group_to_save_it_under(self):
        with self.allowed():
            rv = self.enable(save_position=True)

        self.assertEqual(400, rv.status_code)
        self.assertIn("consumer group name", rv.json["message"])

    def test_with_a_group_it_may_be_saved(self):
        with self.allowed():
            rv = self.enable(consumer_group="analytics-sqldesk", save_position=True)

        self.assertEqual(200, rv.status_code)
        self.assertTrue(self.stream().save_position)

    def test_starting_where_it_left_off_needs_a_saved_position(self):
        with self.allowed():
            rv = self.enable(consumer_group="analytics-sqldesk", start_from="saved")

        self.assertEqual(400, rv.status_code)
        self.assertIn("saved", rv.json["message"])

    def test_and_with_one_it_may(self):
        with self.allowed():
            rv = self.enable(consumer_group="analytics-sqldesk", save_position=True, start_from="saved")

        self.assertEqual(200, rv.status_code)
        self.assertEqual("saved", self.stream().start_from)

    def test_earliest_needs_nothing_else(self):
        with self.allowed():
            rv = self.enable(start_from="earliest")

        self.assertEqual(200, rv.status_code)
        self.assertEqual("earliest", self.stream().start_from)

    def test_an_unknown_start_point_is_refused(self):
        with self.allowed():
            rv = self.enable(start_from="yesterday")

        self.assertEqual(400, rv.status_code)

    def test_clearing_the_name_while_saving_is_refused_rather_than_guessed_at(self):
        # Silently turning saving off would lose the setting; keeping it would
        # leave a saved position with nowhere to save to.
        with self.allowed():
            self.enable(consumer_group="analytics-sqldesk", save_position=True)
            rv = self.enable(consumer_group="")

        self.assertEqual(400, rv.status_code)
        self.assertEqual("analytics-sqldesk", self.stream().consumer_group)

    def test_the_topic_list_says_how_each_enabled_topic_is_read(self):
        with self.allowed():
            self.enable(consumer_group="analytics-sqldesk", save_position=True)
        listed = [{"name": "orders", "partitions": 3}, {"name": "payments", "partitions": 1}]

        with self.allowed(), self.topics(listed):
            rv = self.make_request("get", "/api/data_sources/{}/topics".format(self.source.id))

        by_name = {topic["name"]: topic for topic in rv.json["topics"]}
        self.assertEqual("analytics-sqldesk", by_name["orders"]["consumer_group"])
        self.assertTrue(by_name["orders"]["save_position"])
        # And one not yet enabled shows the defaults it would get.
        self.assertIsNone(by_name["payments"]["consumer_group"])
        self.assertFalse(by_name["payments"]["save_position"])
        self.assertEqual("latest", by_name["payments"]["start_from"])

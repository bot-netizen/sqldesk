"""
A stream's own settings, and the list the Streams page reads.

The field all of this exists for is the sentence that says *why* a stream is
quiet. Three different situations look identical on an empty chart -- nobody
has looked at it lately, the consumer stopped with an error, or the topic
genuinely has nothing on it -- and only one of them is somebody's problem. A
page that just said "0 events" would send people to the broker for a paused
consumer.
"""

import datetime
import json
import shutil
import tempfile
import unittest
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.streams.store import Store
from sqldesk.utils import utcnow
from tests import BaseTestCase


def events(*payloads):
    return [json.dumps(payload).encode("utf-8") for payload in payloads]


class StreamHandlerTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

    def stream(self, topic="events", group=None, **fields):
        # The default group unless a test says otherwise. The factory attaches
        # a data source to no group at all when none is named, which makes one
        # nobody can read -- not a useful default for testing who may read a
        # stream.
        source = self.factory.create_data_source(
            name="Topic " + topic,
            type="duckdb",
            group=group or self.factory.default_group,
            options={"brokers": "b:9092", "topic": topic},
        )
        stream = models.Stream(org=self.factory.org, data_source=source, topic=topic, **fields)
        db.session.add(stream)
        db.session.commit()
        return stream

    def filled(self, stream, *payloads):
        store = Store(stream.store_path())
        self.addCleanup(store.close)
        store.append(events(*payloads))
        store.close()
        return stream


class TestTheListThePageReads(StreamHandlerTestCase):
    def listed(self, user=None):
        return self.make_request("get", "/api/streams", user=user or self.factory.create_admin())

    def test_an_administrator_sees_every_stream(self):
        self.stream("one", pinned=True)
        self.stream("two")

        response = self.listed()

        self.assertEqual(200, response.status_code)
        self.assertEqual(["one", "two"], [row["topic"] for row in response.json["streams"]])

    def test_somebody_who_is_not_an_administrator_may_not(self):
        # The page it feeds carries the pin and the budgets; a reader who may
        # use one stream has no business knowing what else is configured.
        self.stream()

        self.assertEqual(403, self.listed(user=self.factory.user).status_code)

    def test_another_organisations_streams_are_not_listed(self):
        self.stream("ours", pinned=True)
        other = self.factory.create_org()
        theirs_source = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        db.session.add(models.Stream(org=other, data_source=theirs_source, topic="theirs"))
        db.session.commit()

        self.assertEqual(["ours"], [row["topic"] for row in self.listed().json["streams"]])

    def test_a_paused_stream_says_it_is_paused_and_will_come_back(self):
        self.stream(last_viewed_at=utcnow() - datetime.timedelta(hours=1))

        row = self.listed().json["streams"][0]

        self.assertFalse(row["active"])
        self.assertIn("Paused", row["quiet"])

    def test_a_broken_one_says_what_the_broker_said(self):
        self.stream(pinned=True, last_error="The broker refused the credentials.")

        row = self.listed().json["streams"][0]

        self.assertEqual("The broker refused the credentials.", row["quiet"])

    def test_a_working_one_says_nothing_at_all(self):
        self.stream(pinned=True, rows=5000, window_seconds=600)

        row = self.listed().json["streams"][0]

        self.assertTrue(row["active"])
        self.assertIsNone(row["quiet"])

    def test_it_carries_the_line_the_chart_shows(self):
        # Built on the server so the page and a chart cannot word the same fact
        # two ways.
        self.stream(pinned=True, rows=4_900_000, window_seconds=360)

        self.assertEqual("last 6 minutes · 4.9M events", self.listed().json["streams"][0]["describes"])

    def test_and_says_when_it_is_sampling(self):
        self.stream(pinned=True, rows=10, sample_rate=20, window_seconds=300)

        row = self.listed().json["streams"][0]

        self.assertTrue(row["sampled"])
        self.assertEqual(20, row["sample_rate"])


class TestOneStream(StreamHandlerTestCase):
    def get(self, stream, user=None):
        return self.make_request(
            "get",
            "/api/data_sources/{}/stream".format(stream.data_source_id),
            user=user or self.factory.create_admin(),
        )

    def post(self, stream, user=None, **body):
        return self.make_request(
            "post",
            "/api/data_sources/{}/stream".format(stream.data_source_id),
            data=body,
            user=user or self.factory.create_admin(),
        )

    def test_anybody_who_may_read_the_data_source_may_read_the_stream(self):
        # A stream is a data source, and who may read it is already decided.
        stream = self.stream()

        self.assertEqual(200, self.get(stream, user=self.factory.user).status_code)

    def test_but_not_somebody_outside_its_group(self):
        other_group = self.factory.create_group(name="Theirs")
        db.session.add(other_group)
        db.session.commit()
        stream = self.stream(group=other_group)

        self.assertEqual(403, self.get(stream, user=self.factory.user).status_code)

    def test_a_data_source_that_is_not_a_stream_says_so(self):
        source = self.factory.create_data_source(name="Ordinary", type="pg")

        response = self.make_request(
            "get", "/api/data_sources/{}/stream".format(source.id), user=self.factory.create_admin()
        )

        self.assertEqual(404, response.status_code)
        self.assertIn("No such stream", response.json["message"])

    def test_on_a_cluster_with_several_topics_the_one_named_is_the_one_changed(self):
        """
        It took the cluster's first stream, so Pin on `payments` pinned
        whichever row Postgres returned first and said "Saved" for payments.
        """
        orders = self.stream(topic="orders")
        payments = models.Stream(org=self.factory.org, data_source=orders.data_source, topic="payments")
        db.session.add(payments)
        db.session.commit()

        rv = self.make_request(
            "post",
            "/api/data_sources/{}/stream/{}".format(orders.data_source_id, payments.id),
            data={"pinned": True},
            user=self.factory.create_admin(),
        )

        self.assertEqual(200, rv.status_code)
        db.session.refresh(orders)
        db.session.refresh(payments)
        self.assertEqual((False, True), (orders.pinned, payments.pinned))

    def test_and_without_saying_which_it_refuses_to_guess(self):
        orders = self.stream(topic="orders")
        db.session.add(models.Stream(org=self.factory.org, data_source=orders.data_source, topic="payments"))
        db.session.commit()

        rv = self.post(orders, pinned=True)

        self.assertEqual(400, rv.status_code)
        db.session.refresh(orders)
        self.assertFalse(orders.pinned)

    def test_pinning_it(self):
        stream = self.stream()

        response = self.post(stream, pinned=True)

        self.assertTrue(response.json["pinned"])
        self.assertTrue(response.json["active"])

    def test_only_an_administrator_may_pin(self):
        # A pin burns a worker and a disk indefinitely.
        stream = self.stream()

        self.assertEqual(403, self.post(stream, user=self.factory.user, pinned=True).status_code)

    def test_the_budgets_can_be_overridden_per_stream(self):
        stream = self.stream()

        response = self.post(stream, row_budget=600, events_per_second=50)

        self.assertEqual(600, response.json["row_budget"])
        self.assertEqual(50, response.json["events_per_second"])

    def test_and_zero_means_use_the_installs_own(self):
        from sqldesk import settings

        stream = self.stream(row_budget=600)

        response = self.post(stream, row_budget=0)

        self.assertEqual(settings.STREAM_ROW_BUDGET, response.json["row_budget"])

    def test_settling_the_columns_freezes_the_schema(self):
        # Which is what stops a chart changing shape because a producer shipped
        # a field.
        stream = self.stream()

        response = self.post(stream, columns=[{"name": "region", "type": "VARCHAR"}])

        self.assertEqual("frozen", response.json["schema_state"])
        self.assertEqual([{"name": "region", "type": "VARCHAR"}], response.json["columns"])

    def test_an_empty_schema_is_refused(self):
        stream = self.stream()

        self.assertEqual(400, self.post(stream, columns=[]).status_code)

    def test_a_rollup_is_checked_against_the_real_columns(self):
        # The alternative is a definition that looks accepted and then fails in
        # a worker once a minute with nobody reading the log.
        stream = self.filled(self.stream(), {"region": "eu", "amount": 1})

        response = self.post(stream, group_by=["nope"], measures=[{"name": "n", "kind": "count"}])

        self.assertEqual(400, response.status_code)
        self.assertIn("nope", response.json["message"])

    def test_a_good_rollup_is_accepted(self):
        stream = self.filled(self.stream(), {"region": "eu", "amount": 1})

        response = self.post(
            stream, group_by=["region"], measures=[{"name": "total", "kind": "sum", "column": "amount"}]
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(["region"], response.json["group_by"])

    def test_one_can_be_defined_before_the_first_event_arrives(self):
        # The store's columns are the truth, but a stream that has never
        # consumed has none -- and refusing would mean setting it up twice.
        stream = self.stream(columns=[{"name": "region", "type": "VARCHAR"}])

        response = self.post(stream, group_by=["region"], measures=[{"name": "n", "kind": "count"}])

        self.assertEqual(200, response.status_code)

    def test_fixing_a_refused_definition_clears_the_complaint(self):
        stream = self.filled(self.stream(last_error="There is no column called 'nope'."), {"region": "eu"})

        self.post(stream, group_by=["region"], measures=[{"name": "n", "kind": "count"}])

        db.session.refresh(stream)
        self.assertIsNone(stream.last_error)


class TestTheRollupEndpoint(StreamHandlerTestCase):
    def rows_for(self, stream, **params):
        query = "&".join("{}={}".format(key, value) for key, value in params.items())
        return self.make_request(
            "get",
            "/api/data_sources/{}/stream/rollup{}".format(stream.data_source_id, "?" + query if query else ""),
            user=self.factory.create_admin(),
        )

    def bucket(self, stream, minute=None, **fields):
        row = models.StreamRollup(
            stream_id=stream.id,
            minute=minute or utcnow() - datetime.timedelta(minutes=5),
            group_key={"region": "eu"},
            values={"n": 3},
            **fields,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_the_buckets_come_back_with_their_groups(self):
        stream = self.stream()
        self.bucket(stream)

        response = self.rows_for(stream)

        self.assertEqual(200, response.status_code)
        self.assertEqual({"region": "eu"}, response.json["rows"][0]["group"])
        self.assertEqual({"n": 3}, response.json["rows"][0]["values"])

    def test_the_capped_tail_is_flagged_rather_than_hidden(self):
        # A chart that hid it would make a total wrong and look right.
        stream = self.stream()
        self.bucket(stream, is_other=True)

        self.assertTrue(self.rows_for(stream).json["rows"][0]["is_other"])

    def test_and_so_is_the_sample_rate(self):
        # So a chart can say a count is an estimate rather than quietly
        # multiplying it.
        stream = self.stream()
        self.bucket(stream, sample_rate=20)

        self.assertEqual(20, self.rows_for(stream).json["rows"][0]["sample_rate"])

    def test_buckets_outside_the_period_are_not_returned(self):
        stream = self.stream()
        self.bucket(stream, minute=utcnow() - datetime.timedelta(hours=10))

        self.assertEqual([], self.rows_for(stream, minutes=60).json["rows"])

    def test_the_period_is_capped_at_two_days(self):
        # A chart asking for a year would be asking Postgres for a table scan.
        stream = self.stream()

        self.assertEqual(60 * 48, self.rows_for(stream, minutes=999999).json["minutes"])


def _kafka_runner_available():
    from sqldesk.query_runner import get_query_runner

    return get_query_runner("kafka_stream", {}) is not None


WHY_NOT_KAFKA = (
    "the kafka_stream runner is not registered here -- confluent-kafka is in "
    "the optional all_ds group, so rebuild the image to run this"
)


@unittest.skipUnless(_kafka_runner_available(), WHY_NOT_KAFKA)
class TestARunnerFindsItsStream(BaseTestCase):
    """
    A Kafka data source's runner has to find the window belonging to it.

    A runner is normally told nothing about the row it came from, and this one
    looked for `data_source_id` in its own configuration -- which nothing ever
    put there. So `_stream()` returned None for every data source built through
    the application, and every query answered "This data source has no stream
    yet" however long it had been consuming. Nothing noticed because the tests
    construct the runner by hand, with that key supplied.
    """

    def source(self):
        return self.factory.create_data_source(
            name="Orders topic",
            type="kafka_stream",
            options={"brokers": "broker:9092", "topic": "orders"},
        )

    def test_the_runner_is_told_which_data_source_it_is_for(self):
        source = self.source()
        stream = models.Stream(org=source.org, data_source=source, topic="orders")
        models.db.session.add(stream)
        models.db.session.commit()

        found = source.query_runner._streams()

        self.assertEqual([stream.id], [one.id for one in found])

    def test_and_every_enabled_topic_comes_back(self):
        # A cluster has as many streams as it has enabled topics.
        source = self.source()
        for topic in ("orders", "payments"):
            models.db.session.add(models.Stream(org=source.org, data_source=source, topic=topic))
        models.db.session.commit()

        self.assertEqual(["orders", "payments"], [one.topic for one in source.query_runner._streams()])

    def test_and_a_cluster_with_no_topics_enabled_has_none(self):
        source = self.source()
        models.db.session.commit()

        self.assertEqual([], source.query_runner._streams())

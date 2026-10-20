"""
How `Broker` decides where to start and whether the broker ever sees a group.

These stand a small fake in for `confluent_kafka` with its real offset
constants, so they run without librdkafka and without a broker. What a fake
cannot show -- that librdkafka really keeps an unjoined group off the broker's
list -- is in `test_broker.py`, against a real one.
"""

from types import SimpleNamespace
from unittest import TestCase, mock

from sqldesk.streams import consumer

# The values librdkafka uses, so a test cannot pass by comparing two fakes.
OFFSET_BEGINNING = -2
OFFSET_END = -1
OFFSET_STORED = -1000


class TopicPartition:
    def __init__(self, topic, partition, offset=-1001):
        self.topic, self.partition, self.offset = topic, partition, offset

    def __repr__(self):
        return "TP({}, {})".format(self.partition, self.offset)


#: What the fake broker says about a topic. Tests change it.
TOPICS = {"partitions": {0: object(), 1: object(), 2: object()}, "missing": False, "error": None}


class FakeConsumer:
    def __init__(self, config):
        self.config = config
        self.subscribed = None
        self.on_assign = None
        self.assigned = None
        self.commits = 0

    def list_topics(self, topic, timeout=None):
        if TOPICS["missing"]:
            return SimpleNamespace(topics={})
        return SimpleNamespace(topics={topic: SimpleNamespace(partitions=TOPICS["partitions"], error=TOPICS["error"])})

    def subscribe(self, topics, on_assign=None):
        self.subscribed = topics
        self.on_assign = on_assign

    def assign(self, partitions):
        self.assigned = {tp.partition: tp.offset for tp in partitions}

    def assignment(self):
        return [TopicPartition("t", p, o) for p, o in (self.assigned or {}).items()]

    def position(self, partitions):
        return [TopicPartition("t", tp.partition, 500 + tp.partition) for tp in partitions]

    def commit(self, asynchronous=True):
        self.commits += 1

    def close(self):
        pass


fake_confluent = SimpleNamespace(
    Consumer=FakeConsumer,
    TopicPartition=TopicPartition,
    OFFSET_BEGINNING=OFFSET_BEGINNING,
    OFFSET_END=OFFSET_END,
    OFFSET_STORED=OFFSET_STORED,
)


class BrokerTestCase(TestCase):
    def setUp(self):
        patch = mock.patch.object(consumer, "confluent", fake_confluent)
        patch.start()
        self.addCleanup(patch.stop)
        saved = dict(TOPICS)
        self.addCleanup(lambda: TOPICS.update(saved))

    def opened(self, **kwargs):
        broker = consumer.Broker(brokers="b:9092", topic="orders", group="g", **kwargs)
        broker.open()
        return broker


class TestTheBrokerNeverSeesAnUnnamedGroup(BrokerTestCase):
    def test_by_default_it_assigns_rather_than_joining(self):
        # Joining is what puts a group on the broker, and an unnamed group that
        # joins and never commits is exactly what lag monitoring alarmed on.
        broker = self.opened()

        self.assertIsNone(broker._consumer.subscribed)
        self.assertEqual({0, 1, 2}, set(broker._consumer.assigned))

    def test_and_starts_every_partition_at_the_end(self):
        broker = self.opened()

        self.assertEqual({0: OFFSET_END, 1: OFFSET_END, 2: OFFSET_END}, broker._consumer.assigned)

    def test_it_never_commits_without_a_named_group(self):
        # Even if somebody asks: there is no group to commit under.
        broker = self.opened(commit=True)

        self.assertFalse(broker.commit_position())
        self.assertEqual(0, broker._consumer.commits)

    def test_a_group_id_is_still_set_because_the_client_insists(self):
        broker = self.opened()

        self.assertEqual("g", broker._consumer.config["group.id"])

    def test_nothing_is_ever_committed_automatically(self):
        broker = self.opened(join=True, commit=True)

        self.assertFalse(broker._consumer.config["enable.auto.commit"])


class TestANamedGroup(BrokerTestCase):
    def test_joins(self):
        broker = self.opened(join=True)

        self.assertEqual(["orders"], broker._consumer.subscribed)

    def test_and_places_whatever_the_group_hands_it(self):
        broker = self.opened(join=True)
        handed = [TopicPartition("orders", 0), TopicPartition("orders", 2)]

        broker._consumer.on_assign(broker._consumer, handed)

        self.assertEqual({0: OFFSET_END, 2: OFFSET_END}, broker._consumer.assigned)

    def test_commits_after_a_flush_only_when_saving(self):
        saving = self.opened(join=True, commit=True)
        not_saving = self.opened(join=True, commit=False)

        self.assertTrue(saving.commit_position())
        self.assertFalse(not_saving.commit_position())
        self.assertEqual(1, saving._consumer.commits)
        self.assertEqual(0, not_saving._consumer.commits)


class TestWhereAColdStartBegins(BrokerTestCase):
    def test_earliest_begins_at_the_beginning(self):
        broker = self.opened(start_from="earliest")

        self.assertEqual({OFFSET_BEGINNING}, set(broker._consumer.assigned.values()))

    def test_and_says_so_to_librdkafka_for_a_partition_with_no_offset(self):
        broker = self.opened(start_from="earliest")

        self.assertEqual("earliest", broker._consumer.config["auto.offset.reset"])

    def test_saved_uses_the_committed_offset_when_saving(self):
        broker = self.opened(join=True, commit=True, start_from="saved")
        broker._consumer.on_assign(broker._consumer, [TopicPartition("orders", 0)])

        self.assertEqual({0: OFFSET_STORED}, broker._consumer.assigned)

    def test_saved_without_saving_falls_back_to_the_end_rather_than_a_stale_offset(self):
        # The API refuses this combination; this is the belt to that brace.
        broker = self.opened(start_from="saved")

        self.assertEqual({OFFSET_END}, set(broker._consumer.assigned.values()))


class TestAHandOverCarriesOn(BrokerTestCase):
    def test_a_resumed_partition_starts_where_the_last_job_stopped(self):
        broker = self.opened(resume={0: 120, 1: 45})

        self.assertEqual({0: 120, 1: 45, 2: OFFSET_END}, broker._consumer.assigned)

    def test_even_when_the_topic_is_set_to_start_from_the_beginning(self):
        # Without this, "earliest" would replay the whole topic at every
        # hand-over -- every few minutes.
        broker = self.opened(start_from="earliest", resume={0: 120})

        self.assertEqual(120, broker._consumer.assigned[0])
        self.assertEqual(OFFSET_BEGINNING, broker._consumer.assigned[1])

    def test_and_for_a_named_group_too(self):
        broker = self.opened(join=True, resume={2: 9})
        broker._consumer.on_assign(broker._consumer, [TopicPartition("orders", 2)])

        self.assertEqual({2: 9}, broker._consumer.assigned)

    def test_closing_records_where_it_got_to_for_the_next_job(self):
        broker = self.opened()

        broker.close()

        self.assertEqual({0: 500, 1: 501, 2: 502}, broker.last_positions)

    def test_a_logical_offset_is_never_handed_on(self):
        # "The end" is a promise about the future, not a place in the log.
        broker = self.opened()
        broker._consumer.position = lambda parts: [TopicPartition("t", 0, OFFSET_END), TopicPartition("t", 1, 7)]

        self.assertEqual({1: 7}, broker.positions())


class TestATopicThatIsNotThere(BrokerTestCase):
    """
    Assigned to zero partitions, a consumer reads nothing and says nothing --
    which is exactly what a quiet topic looks like. So a typo, a deleted topic
    or a missing ACL has to be an error the stream's page can show instead.
    """

    def test_a_missing_topic_is_an_error_not_a_quiet_stream(self):
        TOPICS["missing"] = True

        with self.assertRaises(RuntimeError) as raised:
            self.opened()
        self.assertIn("no topic called 'orders'", str(raised.exception))

    def test_so_is_one_the_broker_will_not_describe(self):
        TOPICS["error"] = "TOPIC_AUTHORIZATION_FAILED"

        with self.assertRaises(RuntimeError) as raised:
            self.opened()
        self.assertIn("TOPIC_AUTHORIZATION_FAILED", str(raised.exception))

    def test_and_one_with_no_partitions(self):
        TOPICS["partitions"] = {}

        with self.assertRaises(RuntimeError):
            self.opened()

    def test_a_named_group_is_checked_too(self):
        TOPICS["missing"] = True

        with self.assertRaises(RuntimeError):
            self.opened(join=True)

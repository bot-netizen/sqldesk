"""
The jobs that run streams: starting consumers, and the rollup.

The lock is the part worth the most attention. Two consumers on one stream would
both write the same DuckDB file and both count the same events, and the window
would be wrong in a way nobody could see from the chart.
"""

import datetime
import json
import shutil
import tempfile
from unittest import mock

from sqldesk import models, redis_connection
from sqldesk.models import db
from sqldesk.streams.store import Store
from sqldesk.tasks import streams as tasks
from sqldesk.utils import utcnow
from tests import BaseTestCase


def events(*payloads):
    return [json.dumps(payload).encode("utf-8") for payload in payloads]


class StreamTaskTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

    def stream(self, topic="events", **fields):
        source = self.factory.create_data_source(
            name="Topic " + topic, type="duckdb", options={"brokers": "localhost:9092", "topic": topic}
        )
        stream = models.Stream(org=self.factory.org, data_source=source, topic=topic, **fields)
        db.session.add(stream)
        db.session.commit()
        return stream


class TestStartingConsumers(StreamTaskTestCase):
    def test_one_is_started_for_an_active_stream(self):
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks.consume_stream, "delay") as started:
            self.assertEqual(1, tasks.supervise_streams())

        started.assert_called_once_with(stream.id)

    def test_and_none_for_a_stream_nobody_is_watching(self):
        # A stream's cost is continuous, unlike a query's, so an unwatched one
        # is the only thing here that costs money while doing nothing.
        self.stream(last_viewed_at=utcnow() - datetime.timedelta(hours=1))

        with mock.patch.object(tasks.consume_stream, "delay") as started:
            self.assertEqual(0, tasks.supervise_streams())

        started.assert_not_called()

    def test_a_stream_already_being_consumed_is_not_queued_again(self):
        # Two consumers on one stream would both write the same DuckDB file and
        # both count the same events, and the window would be wrong in a way
        # nobody could see from the chart. The job's own claim is what makes
        # that impossible; this only keeps the queue readable.
        stream = self.stream(pinned=True)
        tasks._claim(stream.id)

        with mock.patch.object(tasks.consume_stream, "delay") as started:
            self.assertEqual(0, tasks.supervise_streams())

        started.assert_not_called()

    def test_and_is_once_its_consumer_has_finished(self):
        stream = self.stream(pinned=True)
        tasks._claim(stream.id)
        tasks._release(stream.id)

        with mock.patch.object(tasks.consume_stream, "delay"):
            self.assertEqual(1, tasks.supervise_streams())

    def test_with_no_redis_nothing_is_queued(self):
        """
        The safe answer when Redis cannot be asked is "it is already consumed".

        A stream that is not consumed is an empty chart, which somebody notices
        and can act on. A flood of jobs that all refuse is a queue nobody can
        read.
        """
        self.stream(pinned=True)

        with mock.patch.object(redis_connection, "exists", side_effect=RuntimeError("down")):
            with mock.patch.object(tasks.consume_stream, "delay") as started:
                self.assertEqual(0, tasks.supervise_streams())

        started.assert_not_called()

    def test_and_the_job_itself_refuses_without_redis(self):
        # The claim is the thing that actually prevents two consumers, so it
        # has to fail closed.
        stream = self.stream(pinned=True)

        with mock.patch.object(redis_connection, "set", side_effect=RuntimeError("down")):
            with mock.patch.object(tasks, "consume") as consumed:
                tasks.consume_stream(stream.id)

        consumed.assert_not_called()

    def test_streams_in_every_organisation_are_started(self):
        ours = self.stream("ours", pinned=True)
        other = self.factory.create_org()
        theirs_source = self.factory.create_data_source(org=other, name="Theirs", type="duckdb")
        theirs = models.Stream(org=other, data_source=theirs_source, topic="theirs", pinned=True)
        db.session.add(theirs)
        db.session.commit()

        with mock.patch.object(tasks.consume_stream, "delay") as started:
            tasks.supervise_streams()

        self.assertEqual({ours.id, theirs.id}, {call.args[0] for call in started.call_args_list})


class TestOneConsumerJob(StreamTaskTestCase):
    def test_a_stream_another_worker_holds_is_left_alone(self):
        # The claim is in the job, because the job is also what re-enqueues
        # itself and nothing outside it knows when that happens.
        stream = self.stream(pinned=True)
        tasks._claim(stream.id)

        with mock.patch.object(tasks, "consume") as consumed:
            tasks.consume_stream(stream.id)

        consumed.assert_not_called()
        # And the lock it did not take is not released either.
        self.assertIsNotNone(redis_connection.get(tasks._lock_key(stream.id)))

    def test_a_consumer_hands_over_to_a_successor_when_its_time_is_up(self):
        """
        Waiting for the supervisor's next minute would leave up to a minute of
        the topic unconsumed after every job, which on a window measured in
        minutes is a visible hole in the chart.
        """
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks, "consume"):
            with mock.patch.object(tasks.consume_stream, "delay") as again:
                tasks.consume_stream(stream.id)

        again.assert_called_once_with(stream.id)

    def test_but_not_when_its_stream_has_gone_quiet(self):
        stream = self.stream(last_viewed_at=utcnow() - datetime.timedelta(seconds=30))

        def go_quiet(*_args, **_kwargs):
            stream.last_viewed_at = utcnow() - datetime.timedelta(hours=1)
            db.session.commit()

        with mock.patch.object(tasks, "consume", side_effect=go_quiet):
            with mock.patch.object(tasks.consume_stream, "delay") as again:
                tasks.consume_stream(stream.id)

        again.assert_not_called()

    def test_nor_when_it_stopped_with_an_error(self):
        # A consumer that failed should not spin: the supervisor will try again
        # in a minute, which is slow enough to be visible and fast enough to
        # recover.
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks, "consume", side_effect=RuntimeError("no")):
            with mock.patch.object(tasks.consume_stream, "delay") as again:
                tasks.consume_stream(stream.id)

        again.assert_not_called()

    def test_an_inactive_stream_returns_at_once_and_releases_the_lock(self):
        stream = self.stream(last_viewed_at=utcnow() - datetime.timedelta(hours=1))

        with mock.patch.object(tasks, "consume") as consumed:
            tasks.consume_stream(stream.id)

        consumed.assert_not_called()
        self.assertIsNone(redis_connection.get(tasks._lock_key(stream.id)))

    def test_a_stream_that_has_been_deleted_is_not_an_error(self):
        # The supervisor and the job are a minute apart, and a data source can
        # be deleted in between.
        tasks.consume_stream(999999)

    def test_a_failure_is_recorded_where_the_page_can_read_it(self):
        # A consumer that stopped with an error and one that stopped because
        # nobody is watching look identical on a chart, and only one of them is
        # a problem.
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks, "consume", side_effect=RuntimeError("the broker refused us")):
            tasks.consume_stream(stream.id)

        db.session.refresh(stream)
        self.assertIn("the broker refused us", stream.last_error)

    def test_and_the_lock_is_released_even_then(self):
        # Otherwise one failure keeps a stream unconsumed until the lock expires.
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks, "consume", side_effect=RuntimeError("no")):
            tasks.consume_stream(stream.id)

        self.assertIsNone(redis_connection.get(tasks._lock_key(stream.id)))

    def test_a_successful_run_clears_an_earlier_error(self):
        stream = self.stream(pinned=True, last_error="something from last time")

        with mock.patch.object(tasks, "consume"):
            tasks.consume_stream(stream.id)

        db.session.refresh(stream)
        self.assertIsNone(stream.last_error)

    def test_the_broker_is_built_from_the_data_sources_own_options(self):
        stream = self.stream(pinned=True)
        stream.data_source.options["security_protocol"] = "SASL_SSL"
        stream.data_source.options["sasl_username"] = "someone"
        db.session.commit()

        with mock.patch.object(tasks, "consume") as consumed:
            with mock.patch.object(tasks, "Broker") as broker:
                tasks.consume_stream(stream.id)

        self.assertTrue(consumed.called)
        options = broker.call_args.kwargs["options"]
        self.assertEqual("SASL_SSL", options["security.protocol"])
        self.assertEqual("someone", options["sasl.username"])

    def test_the_consumer_group_is_the_streams_own(self):
        # One group per stream, so the broker balances partitions for it alone.
        stream = self.stream(pinned=True)

        with mock.patch.object(tasks, "consume"):
            with mock.patch.object(tasks, "Broker") as broker:
                tasks.consume_stream(stream.id)

        self.assertEqual("sqldesk-stream-{}".format(stream.id), broker.call_args.kwargs["group"])


class TestTheRollup(StreamTaskTestCase):
    def filled(self, minutes_ago=1, **fields):
        stream = self.stream(group_by=["region"], measures=[{"name": "n", "kind": "count"}], **fields)
        store = Store(stream.store_path())
        self.addCleanup(store.close)
        store.append(events({"region": "eu"}, {"region": "eu"}, {"region": "us"}))
        # Into the middle of the minute that has just finished, because the one
        # in progress is deliberately not rolled up.
        #
        # Computed from the minute boundary rather than by subtracting a fixed
        # 90 seconds: that lands two minutes back whenever the clock's second
        # is under thirty, which is outside the period the rollup reads -- a
        # flake that passed alone and failed in the full suite roughly half the
        # time, depending on nothing but when it happened to run.
        store.connection.execute(
            "UPDATE events SET _received_at = date_trunc('minute', now()) "
            "- INTERVAL '{} minutes' + INTERVAL '30 seconds'".format(minutes_ago)
        )
        store.close()
        return stream

    def test_a_finished_minute_becomes_buckets(self):
        stream = self.filled()

        tasks.roll_up_streams()

        rows = {
            row.group_key["region"]: row.values["n"]
            for row in models.StreamRollup.query.filter_by(stream_id=stream.id)
        }
        self.assertEqual({"eu": 2, "us": 1}, rows)

    def test_the_minute_in_progress_is_left_alone(self):
        """
        A bucket written while its minute is still filling is wrong until it is
        rewritten, and nothing rewrites it.
        """
        stream = self.stream(group_by=["region"], measures=[{"name": "n", "kind": "count"}])
        store = Store(stream.store_path())
        self.addCleanup(store.close)
        store.append(events({"region": "eu"}))

        tasks.roll_up_streams()

        self.assertEqual(0, models.StreamRollup.query.filter_by(stream_id=stream.id).count())

    def test_a_stream_with_no_measures_is_skipped(self):
        self.stream()

        self.assertEqual(0, tasks.roll_up_streams())

    def test_a_bad_definition_is_said_on_the_page_rather_than_raised(self):
        stream = self.filled()
        stream.group_by = ["no_such_column"]
        db.session.commit()

        tasks.roll_up_streams()

        db.session.refresh(stream)
        self.assertIn("no_such_column", stream.last_error)
        self.assertEqual(0, models.StreamRollup.query.filter_by(stream_id=stream.id).count())

    def test_the_sample_rate_is_recorded_with_the_bucket(self):
        # So a count can be scaled back up honestly rather than quietly
        # multiplied, and so a chart can say it is an estimate.
        stream = self.filled(sample_rate=20)

        tasks.roll_up_streams()

        rows = models.StreamRollup.query.filter_by(stream_id=stream.id).all()
        self.assertTrue(rows)
        self.assertTrue(all(row.sample_rate == 20 for row in rows))

    def test_running_twice_does_not_double_the_buckets(self):
        stream = self.filled()

        tasks.roll_up_streams()
        tasks.roll_up_streams()

        self.assertEqual(2, models.StreamRollup.query.filter_by(stream_id=stream.id).count())

    def test_old_buckets_are_dropped(self):
        stream = self.filled()
        tasks.roll_up_streams()
        models.db.session.execute(
            "UPDATE stream_rollups SET minute = minute - INTERVAL '2 days' WHERE stream_id = :id",
            {"id": stream.id},
        )
        db.session.commit()

        tasks.roll_up_streams()

        # Asserting on the aged rows specifically: the same run also rolls the
        # finished minute up again from the store, so a total count would be
        # back to two either way.
        aged = models.db.session.execute(
            "SELECT count(*) FROM stream_rollups WHERE minute < now() - INTERVAL '2 hours'"
        ).scalar()
        self.assertEqual(0, aged)
        self.assertGreater(models.StreamRollup.query.filter_by(stream_id=stream.id).count(), 0)

    def test_a_minute_a_late_run_missed_is_still_rolled_up(self):
        """
        The rollup used to read `now() - 1 minute` and nothing else.

        A run that arrived late therefore read the wrong minute, and nothing
        ever went back for the one it skipped: by the time anybody noticed,
        the raw events had aged out of the window and that minute had no
        buckets and never would. The task is scheduled once a minute, so a
        worker busy for ninety seconds was enough to leave a hole in the
        history.

        It was also why `test_one_streams_failure_does_not_lose_the_others`
        was intermittent in CI. The clock crossing a minute boundary
        mid-test is the same event as a late run, and that test does twice
        the setup, so it crossed roughly one run in three.
        """
        stream = self.filled(minutes_ago=3)

        tasks.roll_up_streams()

        self.assertGreater(models.StreamRollup.query.filter_by(stream_id=stream.id).count(), 0)

    def test_but_never_the_minute_still_filling(self):
        # A bucket written while its minute is still going is wrong until it
        # is rewritten, and nothing rewrites it.
        #
        # Asserted on the minute list as well as on the result: the loop over
        # rows refuses the current minute too, so a test that only counted
        # buckets would pass with the window left wide open and would never
        # notice the query being run for a minute that cannot produce one.
        stream = self.filled(minutes_ago=0)

        self.assertEqual([], tasks._minutes_to_roll(Store(stream.store_path(), read_only=True), stream))
        tasks.roll_up_streams()

        self.assertEqual(0, models.StreamRollup.query.filter_by(stream_id=stream.id).count())

    def test_the_catch_up_reaches_back_only_so_far(self):
        # A quiet topic's window can hold a long stretch of history, and
        # re-reading all of it once a minute would be a sweep nobody asked
        # for. The bound is on how far back a *late* run catches up, not on
        # what is kept.
        stream = self.filled(minutes_ago=1)
        store = Store(stream.store_path())
        self.addCleanup(store.close)
        store.append(events(*[{"region": "eu"} for _ in range(30)]))
        # One row per minute, going back thirty.
        store.connection.execute(
            "UPDATE events SET _received_at = date_trunc('minute', now()) "
            "- INTERVAL '1 minute' * (rowid % 30 + 1) + INTERVAL '30 seconds'"
        )
        store.close()

        minutes = tasks._minutes_to_roll(Store(stream.store_path(), read_only=True), stream)

        self.assertEqual(tasks.CATCHUP_MINUTES, len(minutes))

    def test_a_minute_already_rolled_up_is_not_read_again(self):
        # The catch-up reads every finished minute the window holds, which on
        # a quiet topic is a long stretch. Doing that every minute would be
        # work nobody asked for.
        stream = self.filled(minutes_ago=3)
        tasks.roll_up_streams()
        before = models.StreamRollup.query.filter_by(stream_id=stream.id).count()

        self.assertEqual([], tasks._minutes_to_roll(Store(stream.store_path(), read_only=True), stream))
        tasks.roll_up_streams()

        self.assertEqual(before, models.StreamRollup.query.filter_by(stream_id=stream.id).count())

    def test_one_streams_failure_does_not_lose_the_others(self):
        broken = self.filled()
        broken.group_by = ["no_such_column"]
        working = self.filled(topic="other")
        db.session.commit()

        tasks.roll_up_streams()

        self.assertGreater(models.StreamRollup.query.filter_by(stream_id=working.id).count(), 0)
        self.assertIsNotNone(models.Stream.query.get(broken.id).last_error)


class TestSlotsAndStates(BaseTestCase):
    """
    The supervisor starts what somebody is watching, and only as many as the
    install allows.

    A refusal is written on the stream rather than only logged: a person
    looking at an empty chart deserves "all the slots are in use" rather than
    silence, and the page reads it from there.
    """

    def setUp(self):
        super().setUp()
        from sqldesk import redis_connection
        from sqldesk.streams import slots

        redis_connection.delete(slots.SLOTS_KEY, slots.LOCK_KEY)

    def stream(self, topic="orders"):
        from sqldesk import models

        source = self.factory.create_data_source(name="Cluster " + topic, type="kafka_stream")
        stream = models.Stream(org=source.org, data_source=source, topic=topic, last_viewed_at=utcnow())
        models.db.session.add(stream)
        models.db.session.commit()
        return stream

    def watch(self, stream):
        from sqldesk.streams import watching

        watching.check_in(stream.id, "ada")

    def test_a_watched_stream_is_started_and_takes_a_slot(self):
        from sqldesk.streams import slots
        from sqldesk.tasks import streams as tasks

        stream = self.stream()
        self.watch(stream)

        with mock.patch.object(tasks.consume_stream, "delay") as delayed:
            self.assertEqual(1, tasks.supervise_streams())

        delayed.assert_called_once_with(stream.id)
        self.assertIn(stream.id, slots.held())

    def test_a_paused_stream_is_not_started(self):
        # Seen a minute ago, nobody watching now. Its window is kept and
        # nothing consumes.
        from sqldesk.tasks import streams as tasks

        self.stream()

        with mock.patch.object(tasks.consume_stream, "delay") as delayed:
            self.assertEqual(0, tasks.supervise_streams())

        delayed.assert_not_called()

    def test_past_the_limit_the_stream_says_why(self):
        from sqldesk import models
        from sqldesk.tasks import streams as tasks

        first, second = self.stream("orders"), self.stream("payments")
        self.watch(first)
        self.watch(second)

        with mock.patch("sqldesk.settings.STREAM_MAX_CONCURRENT", 1):
            with mock.patch.object(tasks.consume_stream, "delay"):
                tasks.supervise_streams()

        refused = [s for s in (first, second) if s.last_error]
        self.assertEqual(1, len(refused))
        self.assertIn("in use", refused[0].last_error)
        models.db.session.rollback()

    def test_and_stops_saying_so_once_a_slot_is_free(self):
        from sqldesk.tasks import streams as tasks

        stream = self.stream()
        self.watch(stream)
        stream.last_error = "All 1 streaming slots are in use. Stop one, or wait for one to finish."
        from sqldesk import models

        models.db.session.commit()

        with mock.patch.object(tasks.consume_stream, "delay"):
            tasks.supervise_streams()

        self.assertIsNone(stream.last_error)

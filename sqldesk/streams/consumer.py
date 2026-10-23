"""
The loop: collect raw bytes for a second, hand them to DuckDB, repeat.

What it does **not** do is the design. It does not decode JSON, it does not
queue anything it cannot write, and it does not replay a backlog. Avro and
Protobuf are the exception they have to be: `decode` turns them into JSON lines
after sampling, and JSON itself passes through untouched.

**Never buffer the overflow.** An unbounded queue in front of a slow writer is
the crash, not the protection against it -- it turns a topic doing more than the
ceiling into a worker that runs out of memory half an hour later, somewhere
else, for reasons nobody can trace back. The one-second flush is the bound:
whatever arrives in a second is either written or sampled away within that
second, and nothing accumulates between flushes.

**Start at the end, unless told otherwise.** The window is "now". Replaying an
hour of backlog to fill five minutes is waste, and worse than waste -- it would
stamp hour-old events with an arrival time of now and draw a chart that is a
lie. So a cold start begins at the end by default; a topic can be set to start
from the beginning or from a saved position, and a hand-over between jobs
carries on from where the last one stopped.

**Invisible to the broker by default.** No consumer group is joined and nothing
is committed unless somebody names a group for the topic, because a group that
joins and never commits is exactly what lag monitoring alarms on.

Kafka itself is behind `Broker`, which is the only part that needs a broker to
exercise. Everything above it -- the sampling decision, the flush, the window,
the rate, the ceilings -- is driven in tests by a fake that returns bytes.
"""

import base64
import binascii
import logging
import time

from sqldesk import models, settings
from sqldesk.query_runner import deferred
from sqldesk.streams import decode, window
from sqldesk.streams.store import Store
from sqldesk.utils import utcnow

logger = logging.getLogger(__name__)

#: Imported when a stream is actually consumed, not at startup. `confluent_kafka`
#: is librdkafka behind a C extension, and most installs have no streams at all
#: -- the same reason every other data source's SDK is deferred.
confluent = deferred("confluent_kafka")
# A submodule of its own: `import confluent_kafka` does not bring `admin` with
# it, so reaching for `confluent.admin` raises AttributeError at the point of
# use -- which is how listing a cluster's topics came to be written and never
# to have run.
confluent_admin = deferred("confluent_kafka.admin")

#: How long to wait for messages in one `consume` call. Shorter than the flush
#: so a quiet topic still comes back and lets the loop do its housekeeping.
POLL_SECONDS = 0.5

#: Messages asked for in one call. Large enough that a busy topic is a few
#: calls a second rather than thousands; the flush, not this, is what bounds
#: memory.
BATCH = 10_000


class Broker:
    """
    The only part that talks to Kafka.

    A thin wrapper rather than a subclass, so the loop above can be handed
    something else in a test and nothing has to pretend to be librdkafka.
    """

    def __init__(
        self,
        brokers,
        topic,
        group,
        options=None,
        join=False,
        commit=False,
        start_from="latest",
        resume=None,
    ):
        self.brokers = brokers
        self.topic = topic
        #: Always set, because librdkafka refuses to build a consumer without
        #: one. Whether the broker ever *sees* it is `join`'s decision.
        self.group = group
        self.options = options or {}
        #: Join the group, rather than assigning every partition to ourselves.
        #: Only when somebody named one: joining is what makes a group appear
        #: on the broker, and an unnamed one appearing is what lag monitoring
        #: alarms on.
        self.join = bool(join)
        #: Commit offsets after each flush. Needs `join`.
        self.commit = bool(commit) and self.join
        self.start_from = start_from
        #: `{partition: offset}` the previous job reached. Present on a
        #: hand-over and absent on a cold start, which is how the two are told
        #: apart -- see `streams/handover.py`.
        self.resume = {int(p): int(o) for p, o in (resume or {}).items()}
        #: Where this consumer had got to when it closed, for the next job.
        self.last_positions = {}
        self._consumer = None

    def open(self):
        """
        Connect, and be at the right offset before the first poll.

        Positioned at assignment rather than by polling once and then seeking:
        the old way threw the first poll away, which was right only while every
        start meant "the end". Starting from a saved position or from the
        beginning, the first message *is* the one that was wanted.
        """
        config = {
            "bootstrap.servers": self.brokers,
            "group.id": self.group,
            # What librdkafka does when it is asked for a committed offset and
            # the group has none -- which is only ever the `saved` start.
            "auto.offset.reset": "earliest" if self.start_from == "earliest" else "latest",
            # Committed by hand after a flush, so a committed offset only ever
            # covers events that are in the window.
            "enable.auto.commit": False,
        }
        config.update(self.options)
        self._consumer = confluent.Consumer(config)

        # Asked first, in both modes, so a topic that is not there is an error
        # somebody can read. Assigned to zero partitions, a consumer reads
        # nothing and reports nothing -- exactly what a quiet topic looks like,
        # so a typo, a deleted topic or a missing ACL would have been
        # indistinguishable from a slow afternoon.
        partitions = self._partitions()
        if self.join:
            self._consumer.subscribe([self.topic], on_assign=self._place)
        else:
            self._consumer.assign([self._at(partition) for partition in partitions])
        return self

    def _partitions(self):
        metadata = self._consumer.list_topics(self.topic, timeout=10)
        described = (metadata.topics or {}).get(self.topic)
        if described is None:
            raise RuntimeError("The broker has no topic called {!r}.".format(self.topic))
        if getattr(described, "error", None) is not None:
            raise RuntimeError("The broker would not describe {!r}: {}".format(self.topic, described.error))
        partitions = sorted((described.partitions or {}).keys())
        if not partitions:
            raise RuntimeError("{!r} has no partitions this consumer can read.".format(self.topic))
        return partitions

    def _offset_for(self, partition):
        """Where one partition starts: a hand-over first, then the setting."""
        if partition in self.resume:
            return self.resume[partition]
        if self.start_from == "saved" and self.commit:
            return confluent.OFFSET_STORED
        if self.start_from == "earliest":
            return confluent.OFFSET_BEGINNING
        return confluent.OFFSET_END

    def _at(self, partition):
        return confluent.TopicPartition(self.topic, partition, self._offset_for(partition))

    def _place(self, consumer, assigned):
        """`on_assign`: put each partition the group hands us where it belongs."""
        consumer.assign([self._at(partition.partition) for partition in assigned])

    def commit_position(self):
        """After a flush: record how far the window now reaches. Only when asked."""
        if not self.commit or self._consumer is None:
            return False
        try:
            self._consumer.commit(asynchronous=False)
            return True
        except Exception:
            # Nothing consumed since the last commit raises "no offset to
            # commit", which is not a problem; anything else is worth a line.
            logger.debug("stream %s: nothing committed", self.topic, exc_info=True)
            return False

    def positions(self):
        """`{partition: next offset}` for every partition that has one."""
        if self._consumer is None:
            return {}
        try:
            reached = self._consumer.position(self._consumer.assignment())
        except Exception:
            return {}
        # A negative offset is a logical one -- "the end", "nothing yet" -- and
        # handing it to the next job would be handing it a promise, not a place.
        return {tp.partition: tp.offset for tp in reached if tp.offset is not None and tp.offset >= 0}

    def poll(self, limit=BATCH, timeout=POLL_SECONDS):
        """
        Raw `(key, value)` byte pairs. Never decoded, never parsed.

        A message the broker reports an error for is dropped here rather than
        raised: a partition that has gone away is the broker's business and
        recovers on its own, and a consumer that died for one is a consumer
        somebody has to restart.
        """
        messages = self._consumer.consume(num_messages=limit, timeout=timeout)
        pairs = []
        for message in messages or []:
            if message.error():
                logger.debug("stream %s: %s", self.topic, message.error())
                continue
            pairs.append((message.key(), message.value()))
        return pairs

    def seek_to_end(self):
        """
        Start from now, discarding whatever position the group held.

        Done by assignment rather than by configuration, because
        `auto.offset.reset` only applies when there is *no* committed offset --
        and a group that has run before has one.
        """
        assigned = self._consumer.assignment()
        if not assigned:
            # Assignment arrives with the first poll, so a caller that has not
            # polled yet has nothing to seek. Not an error: the next start
            # will.
            return False
        for partition in assigned:
            try:
                self._consumer.seek(confluent.TopicPartition(partition.topic, partition.partition, -1))
            except Exception:
                logger.warning("could not seek %s to the end", partition, exc_info=True)
        return True

    def close(self):
        if self._consumer is not None:
            self.last_positions = self.positions()
            self._consumer.close()
            self._consumer = None


def describe_topic(options, topic=None, seconds=5):
    """
    Whether the broker will let us in and, if one is named, the topic exists.

    Returns None when all is well, and otherwise something a person can act on.
    Called when somebody saves the data source, which is the moment to find
    out: the alternative is a stream that looks configured and quietly consumes
    nothing until somebody opens a dashboard and finds it empty.

    Deliberately not a rate measurement. The plan's idea of sniffing the topic
    to report "~48,000 events/sec, so you will see a 1-in-10 sample" is worth
    having, but it means holding a connection open for ten seconds inside a
    request that saves a form -- and the rate is measured properly on the first
    flush anyway, which is where the page reads it from. This answers the
    question that cannot wait: will it connect at all.
    """
    brokers = (options or {}).get("brokers")
    topic = topic or (options or {}).get("topic")
    if not brokers:
        return "No bootstrap servers given."

    try:
        found = _metadata(options, seconds)
    except Exception as error:
        return "Could not reach the broker at {}: {}".format(brokers, error)

    # No topic named: the question was only whether the cluster answers, which
    # is what saving a cluster data source asks.
    if not topic:
        return None
    if topic not in (found.topics or {}):
        return "The broker has no topic called {!r}.".format(topic)
    partitions = len(found.topics[topic].partitions or {})
    if not partitions:
        return "The topic {!r} has no partitions.".format(topic)
    return None


def _metadata(options, seconds=5):
    admin = confluent_admin.AdminClient({"bootstrap.servers": (options or {}).get("brokers"), **_security(options)})
    return admin.list_topics(timeout=seconds)


def list_topics(options, seconds=5):
    """
    Every topic the cluster will tell us about.

    Metadata only -- no consumer, no messages, and fast enough to answer a page
    load. Internal topics are left out: `__consumer_offsets` and its kind are
    Kafka's own bookkeeping, and offering them as something to analyse is an
    invitation to a confusing afternoon.
    """
    found = _metadata(options, seconds)
    topics = []
    for name, described in (found.topics or {}).items():
        if name.startswith("_"):
            continue
        topics.append(
            {
                "name": name,
                "partitions": len(described.partitions or {}),
                # A topic the cluster is reporting an error for -- not
                # authorised, under-replicated -- is still worth listing, with
                # the reason, rather than silently missing.
                "problem": str(described.error) if described.error else None,
            }
        )
    return sorted(topics, key=lambda topic: topic["name"])


def _pem(value):
    """
    A certificate or key as librdkafka wants it: PEM text.

    The form uploads files base64-encoded; something configured through the
    API may already be PEM. Both are accepted, so a certificate pasted in as
    text is not silently turned into nonsense by decoding it.
    """
    text = value.strip() if isinstance(value, str) else ""
    if text.startswith("-----BEGIN"):
        return text
    try:
        return base64.b64decode(text, validate=False).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("A certificate or key here has to be a PEM file.")


def _security(options):
    """
    The librdkafka settings a broker needs to let us in.

    Every connection SQLDesk makes to Kafka -- the stream consumer, analysing a
    topic, listing a cluster's topics -- is built from this, so a broker that
    needs a certificate gets it everywhere at once.

    Certificates are handed over as PEM text rather than as files. librdkafka
    accepts both, and text has no lifetime: a consumer runs for minutes and
    hands over to another job, and a temporary file would have had to outlive
    one and be cleaned up after the other.
    """
    options = options or {}
    chosen = {}
    protocol = options.get("security_protocol")
    if protocol and protocol != "PLAINTEXT":
        chosen["security.protocol"] = protocol
    for key, setting in (
        ("sasl_mechanism", "sasl.mechanism"),
        ("sasl_username", "sasl.username"),
        ("sasl_password", "sasl.password"),
        ("ssl_key_password", "ssl.key.password"),
    ):
        value = options.get(key)
        if value:
            chosen[setting] = value
    for key, setting in (
        ("ssl_ca_File", "ssl.ca.pem"),
        ("ssl_certificate_File", "ssl.certificate.pem"),
        ("ssl_key_File", "ssl.key.pem"),
    ):
        value = options.get(key)
        if value:
            chosen[setting] = _pem(value)
    # On by default, as librdkafka has it. Off for a broker reached by an
    # address its certificate does not name -- an IP, an internal alias --
    # which still checks the certificate is the CA's, just not whose it is.
    if options.get("ssl_verify_hostname") is False:
        chosen["ssl.endpoint.identification.algorithm"] = "none"
    return chosen


class Flush:
    """What one second of a topic came to. Returned so a caller can log it."""

    def __init__(self, received=0, kept=0, stored=0, malformed=0, sampled_at=1):
        self.received = received
        self.kept = kept
        self.stored = stored
        self.malformed = malformed
        self.sampled_at = sampled_at

    @property
    def dropped(self):
        return self.received - self.kept

    def __repr__(self):
        return "<Flush received={} stored={} malformed={} 1-in-{}>".format(
            self.received, self.stored, self.malformed, self.sampled_at
        )


#: Consecutive failed flushes before a consumer gives up and says why.
MAX_FAILED_FLUSHES = 30

#: How much one flush moves the measured rate. A second's count is noisy -- a
#: producer batching, a poll that came back early -- and the sample rate it
#: decides is shown on every chart, so it should not jump about with it.
SMOOTHING = 0.3


def _received_rate(stream, count, now):
    """
    Messages a second arriving on the topic, before any sampling.

    This flush's count over the time since the last one, smoothed against the
    rate measured before. The first flush of a run, or one after a gap, has
    nothing recent to smooth against and is taken as it is.
    """
    last = stream.last_flush_at
    elapsed = (now - last).total_seconds() if last else 0
    if elapsed <= 0 or elapsed > 60:
        return count / (float(settings.STREAM_FLUSH_SECONDS) or 1.0)
    instant = count / elapsed
    previous = stream.observed_rate or 0
    if not previous:
        return instant
    return SMOOTHING * instant + (1 - SMOOTHING) * previous


def flush_once(stream, store, messages, now=None, decoder=None):
    """
    One flush: sample, decode, write, trim, and update what the page reads.

    Takes the messages rather than fetching them, which is what makes the whole
    of this testable without a broker -- and makes the ordering explicit. The
    sampling decision comes first, because the point of sampling is to not do
    the work -- and decoding Avro or Protobuf is the most work there is here.
    """
    now = now or utcnow()
    rate = stream.sample_rate or 1

    kept = [
        value
        for position, (key, value) in enumerate(messages)
        if value is not None and window.keeps(key, rate, position=position)
    ]

    undecodable = 0
    if decoder is not None:
        if getattr(decoder, "refresh", None) and decoder.refresh():
            # Read differently from now on, so what is in the window is in the
            # wrong shape: its columns came from the old reading, and every
            # new row would be nulls under them.
            store.reset()
            stream.columns = None
            stream.schema_state = models.SCHEMA_INFERRED
            stream.malformed = 0
        decoded = decoder.decode(kept)
        kept, undecodable = decoded.lines, decoded.failed
        if decoded.problem:
            stream.last_error = decoded.problem
        elif kept and decode.is_problem(stream.last_error):
            # Something read this time, so the reason nothing did is over.
            # Only our own sentence: a slot or a stopped consumer is somebody
            # else's to clear.
            stream.last_error = None

    stored, malformed = store.append(kept)
    malformed += undecodable

    # Measured, then used. The window for the *next* flush follows from the rate
    # this one observed, which is the only honest order: a window chosen from a
    # rate nobody has measured is a guess with a number on it.
    #
    # The topic's rate is what *arrived*, before sampling. It used to be
    # estimated as the rows stored over the last minute times the current
    # sample rate -- but most of those rows were kept at an earlier, lower
    # rate, so once a topic went over the ceiling the estimate fed on itself:
    # at twice the ceiling the rate climbed past 100 within half a minute,
    # stored almost nothing, collapsed back to 1 and did it again.
    received = _received_rate(stream, len(messages), now)
    stream.observed_rate = received
    stream.sample_rate = window.sample_rate_for(received, stream.ceiling)
    stream.window_seconds = window.window_for(stream.budget, received / stream.sample_rate)
    store.truncate(stream.window_seconds)
    stream.rows = store.rows()
    stream.malformed = (stream.malformed or 0) + malformed
    stream.last_flush_at = now
    if not stream.columns:
        stream.columns = [{"name": name, "type": kind} for name, kind in store.columns()]

    models.db.session.add(stream)
    models.db.session.commit()

    return Flush(received=len(messages), kept=len(kept), stored=stored, malformed=malformed, sampled_at=rate)


def consume(stream, broker, should_continue, now=None, decoder=None):
    """
    Run until `should_continue()` says otherwise.

    `should_continue` rather than a loop condition of its own, so the thing that
    decides -- is anybody watching, has an administrator paused it, is the
    worker shutting down -- stays outside and this stays testable.
    """
    store = Store(stream.store_path())
    try:
        # Positioned by `open` itself: at the end, the beginning, a saved
        # offset, or wherever the previous job got to on a hand-over. It used
        # to poll once and throw that poll away before seeking to the end --
        # right while every start meant "the end", and a lost message as soon
        # as one did not.
        broker.open()

        failures = 0
        while should_continue():
            started = time.monotonic()
            collected = []
            # At least one poll per flush, then as many more as the interval
            # allows. A plain `while elapsed < interval` polls zero times when
            # the interval is small or the clock is coarse, so the loop spun
            # flushing nothing while the topic piled up behind it.
            while True:
                collected.extend(broker.poll())
                if not should_continue():
                    break
                if time.monotonic() - started >= settings.STREAM_FLUSH_SECONDS:
                    break
            try:
                flush_once(stream, store, collected, now=now, decoder=decoder)
                failures = 0
            except decode.SchemaError:
                # The uploaded schema no longer loads: nothing will read until
                # somebody fixes it, and the reason belongs on the page.
                raise
            except Exception:
                # One bad second is dropped and counted, not the end of the
                # consumer: a message DuckDB cannot insert, or a reader holding
                # the window a moment too long, used to stop it -- with no
                # hand-over, and again on every restart while the message was
                # there. Thirty in a row is something actually wrong.
                failures += 1
                logger.warning("stream %s: a flush failed (%s in a row)", stream.id, failures, exc_info=True)
                models.db.session.rollback()
                if failures >= MAX_FAILED_FLUSHES:
                    raise
                stream.malformed = (stream.malformed or 0) + len(collected)
                models.db.session.commit()
            # After the flush and never before it, so a committed offset only
            # ever covers events that are already in the window -- or, after
            # a failed flush, events that were counted and dropped, so a poison
            # message is passed rather than read again for ever.
            broker.commit_position()
            # The window is a file and DuckDB gives it to one process at a
            # time. Held open for the whole run -- minutes -- this consumer
            # locked out every reader: the Streams page quietly fell back to
            # the schema stored on the row, and a query against the stream
            # failed outright with a conflicting lock. Closed after each flush,
            # the lock is held for the moment it is written and the seconds in
            # between belong to whoever wants to read. The next flush reopens
            # it; `Store.connection` is lazy.
            store.close()
    finally:
        broker.close()
        store.close()

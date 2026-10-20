"""
What a topic looks like, before anybody commits to keeping it.

Somebody choosing which topics to enable needs three things, and none of them
can be guessed from the name: what the messages contain, how fast they arrive,
and what that means for how much history a window will hold. Enabling a topic
blind and finding out an hour later that it is JSON we cannot parse, or that it
is so fast everything will be sampled, is the experience this exists to avoid.

**It reads the last few messages, not the next few.** Watching the end of a
topic for three seconds tells you nothing about a topic that produces once a
minute -- which is most of them -- so this seeks *backwards* from the high
water mark and reads what is already there. The rate comes from the timestamps
on those messages, which is the rate they were actually produced at rather than
the rate they happened to arrive while somebody had a page open.

Python parses the sample. The rule about not decoding messages in Python is
about the ingest path, where it runs for every event for ever; this runs once,
over at most a few hundred, because somebody pressed a button.
"""

import json
import logging
import math

from sqldesk import settings
from sqldesk.query_runner import deferred
from sqldesk.streams.consumer import _security
from sqldesk.streams.window import window_for

confluent = deferred("confluent_kafka")

logger = logging.getLogger(__name__)

#: How many messages to read. Enough to see the shape of a union type without
#: making somebody wait.
SAMPLE = 500

#: How long to wait for them. A broker that cannot answer in this is a broker
#: whose topics are not worth offering yet.
SECONDS = 5


def analyse(options, topic, sample=SAMPLE, seconds=SECONDS, decoder=None):
    """
    Read the end of a topic and say what is there.

    Read the way it would be stored: through `decoder`, so an Avro topic is
    described by its fields rather than as five hundred malformed messages.
    Returns a dict, or raises with something a person can act on.
    """
    consumer = confluent.Consumer(
        {
            "bootstrap.servers": (options or {}).get("brokers"),
            # Its own group, and nothing is committed: analysing a topic must
            # not move the position of the consumer that reads it for real.
            "group.id": "sqldesk-analyse",
            "enable.auto.commit": False,
            **_security(options),
        }
    )
    try:
        assignment = _last_messages(consumer, topic, sample, seconds)
    finally:
        consumer.close()
    return _describe(assignment, topic, options, decoder=decoder)


def _last_messages(consumer, topic, sample, seconds):
    """Seek back from the high water mark and read what is already there."""
    metadata = consumer.list_topics(topic, timeout=seconds)
    described = (metadata.topics or {}).get(topic)
    if described is None or described.error:
        raise Exception("The broker has no topic called {!r}.".format(topic))
    partitions = sorted(described.partitions or {})
    if not partitions:
        raise Exception("The topic {!r} has no partitions.".format(topic))

    # Spread the sample over the partitions rather than taking it all from the
    # first: a topic keyed by customer puts quite different messages in each.
    each = max(1, sample // len(partitions))
    wanted = []
    for partition in partitions:
        low, high = consumer.get_watermark_offsets(
            confluent.TopicPartition(topic, partition), timeout=seconds, cached=False
        )
        if high <= low:
            continue
        wanted.append(confluent.TopicPartition(topic, partition, max(low, high - each)))
    if not wanted:
        return []

    consumer.assign(wanted)
    collected = []
    deadline = seconds
    while len(collected) < sample:
        batch = consumer.consume(num_messages=min(sample - len(collected), 100), timeout=deadline)
        if not batch:
            break
        for message in batch:
            if message.error():
                continue
            collected.append((message.value(), message.timestamp()))
    return collected


def _describe(messages, topic, options, decoder=None):
    """Columns, rate, and what a window of them would hold."""
    columns, malformed = {}, 0
    times = []
    for _raw, timestamp in messages:
        kind, when = timestamp or (0, 0)
        if when:
            times.append(when)

    values = [raw for raw, _timestamp in messages if raw is not None]
    found, problem = {}, None
    if decoder is not None:
        decoded = decoder.decode(values)
        values, malformed = decoded.lines, decoded.failed
        found, problem = decoded.kinds, decoded.problem

    for raw in values:
        try:
            parsed = json.loads(raw)
        except Exception:
            malformed += 1
            continue
        if not isinstance(parsed, dict):
            # A message that is not an object has no columns to offer, and one
            # of them would otherwise collapse the whole schema to a single
            # JSON column.
            malformed += 1
            continue
        for name, value in parsed.items():
            columns.setdefault(name, _kind(value))

    rate = _rate(times)
    budget = (options or {}).get("row_budget") or settings.STREAM_ROW_BUDGET
    ceiling = (options or {}).get("events_per_second") or settings.STREAM_EVENTS_PER_SECOND
    return {
        "topic": topic,
        "read": len(messages),
        "malformed": malformed,
        # What was on the topic, by kind -- {"Avro": 480, "JSON": 20} -- and,
        # when nothing could be read, the sentence saying why.
        "formats": found,
        "problem": problem,
        "columns": [{"name": name, "type": kind} for name, kind in sorted(columns.items())],
        "events_per_second": round(rate, 2),
        # `window_for(row_budget, events_per_second)`, in that order. These were
        # the other way round, so the preview divided the *rate* by the budget
        # and clamped -- which is the floor for anything short of five million
        # events a second. Every topic was previewed as "5 minutes of history"
        # whatever its rate, and the figure looked precomputed because in
        # effect it was. The consumer always had it right, so the window a
        # stream actually kept was never wrong; only the number somebody read
        # before deciding.
        "window_seconds": window_for(budget, rate) if rate else 0,
        "row_budget": budget,
        "ceiling": ceiling,
        "sampled": bool(ceiling and rate > ceiling),
        "sample_rate": max(1, math.ceil(rate / ceiling)) if ceiling and rate > ceiling else 1,
    }


def _rate(times):
    """
    Messages a second, from the timestamps on the sample.

    The rate they were produced at, not the rate they arrived while somebody
    had a page open -- which for a topic that produces in bursts are very
    different numbers.
    """
    if len(times) < 2:
        return 0.0
    span = (max(times) - min(times)) / 1000.0
    if span <= 0:
        # Every message in the same millisecond: a burst, and dividing by zero
        # to describe it would be worse than saying nothing.
        return 0.0
    return (len(times) - 1) / span


def _kind(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"

"""
Where one consuming job leaves off, for the job that takes over.

Consumption is a chain of jobs: each runs for its time and enqueues a successor.
Every one of them used to seek to the end when it started, so each hand-over
dropped whatever arrived between the two -- a small hole in the chart every few
minutes. And once a topic can be set to start from the *beginning*, the same
seek would replay the whole topic at every hand-over.

So a job that is handing over writes its positions here, and its successor takes
them. A cold start finds nothing and applies the topic's own start setting; that
is how the two are told apart. Nothing about it reaches the broker.

Short-lived on purpose. A successor is enqueued at once, so if nobody has taken
the positions within a minute there is no successor, and the next start is a
cold one -- which must not inherit a position from however long ago it was.
"""

import json
import logging

from sqldesk import redis_connection

logger = logging.getLogger(__name__)

#: Long enough for a successor to be picked up; short enough that a stream
#: started again later begins from its setting, not from a stale position.
SECONDS = 60


def _key(stream_id):
    return "sqldesk:stream:{}:handover".format(stream_id)


def give(stream_id, positions):
    """Leave `{partition: offset}` for the next job. Nothing to leave, nothing written."""
    if not positions:
        return False
    try:
        redis_connection.set(_key(stream_id), json.dumps({str(p): int(o) for p, o in positions.items()}), ex=SECONDS)
        return True
    except Exception:
        # Losing a hand-over costs a cold start, not a stream. Worth a line.
        logger.warning("could not hand over stream %s", stream_id, exc_info=True)
        return False


def take(stream_id):
    """The positions the last job left, once. `{}` on a cold start."""
    try:
        pipe = redis_connection.pipeline()
        pipe.get(_key(stream_id))
        pipe.delete(_key(stream_id))
        raw, _deleted = pipe.execute()
    except Exception:
        logger.warning("could not read the hand-over for stream %s", stream_id, exc_info=True)
        return {}
    if not raw:
        return {}
    try:
        return {int(p): int(o) for p, o in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError):
        return {}

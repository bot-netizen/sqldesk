"""
Spark, when a cell wants a cluster instead of this container's memory.

Spark Connect rather than a submitted job: the cluster runs a Connect server,
this process is a client, and `spark` in a cell is a handle to a session over
there. That keeps the notebook's shape exactly as it is -- a cell runs, its
variables persist, stop still stops -- while the work happens on YARN.

**`spark` is built on first use, never on session start.** Opening a notebook
attaches nothing (design §4.4), and a Python cell that only reshapes a
dataframe should not pay for a cluster session it never touches. So what goes
into the namespace is a handle that builds the real session the first time
somebody reaches through it -- and a cell that never mentions `spark` never
opens one.

**A Spark DataFrame is a plan, not rows.** It becomes this cell's handoff by
being collected, which is the one moment the cluster's result has to fit in
this container -- so it is bounded, and a result over the bound is refused
with a sentence rather than silently cut down to size. A notebook that quietly
showed you the first million rows of a billion would be worse than one that
said no.
"""

import logging
import os

logger = logging.getLogger(__name__)

#: Where the cluster's Connect server is, e.g. sc://spark-gateway:15002.
#: Empty means this executor has no Spark, and `spark` is not in the namespace
#: at all -- a cell that mentions it gets a NameError naming it, which is
#: clearer than a handle that fails on every attribute.
REMOTE = os.environ.get("EXECUTOR_SPARK_REMOTE", "")

#: Rows a Spark DataFrame may bring back to this container when it becomes a
#: cell's handoff. The whole dataset stays on the cluster; this is the part
#: that crosses, and it is bounded by the memory of one container rather than
#: by the cluster's.
COLLECT_ROWS = int(os.environ.get("EXECUTOR_SPARK_COLLECT_ROWS", "1000000"))


class TooMuchToCollect(Exception):
    """A cluster result too large to bring back. Carries the sentence."""


def configured():
    return bool(REMOTE)


class Handle:
    """
    `spark`, as a cell sees it -- the real session, built on first reach.

    Deliberately not a subclass or a copy of anything in pyspark: it forwards
    attribute access and nothing else, so whatever a version of Spark offers is
    what a cell gets, and this file does not have to track it.
    """

    def __init__(self, remote=None):
        self._remote = remote or REMOTE
        self._built = None

    def session(self):
        if self._built is None:
            from pyspark.sql import SparkSession

            logger.info("opening a Spark Connect session on %s", self._remote)
            self._built = SparkSession.builder.remote(self._remote).getOrCreate()
        return self._built

    @property
    def attached(self):
        return self._built is not None

    def stop(self):
        if self._built is not None:
            try:
                self._built.stop()
            finally:
                self._built = None

    def __getattr__(self, name):
        # Only reached for names this object does not have, so the underscored
        # attributes above never come through here and cannot recurse.
        return getattr(self.session(), name)

    def __repr__(self):
        return "<spark {} {}>".format(self._remote, "attached" if self.attached else "not attached yet")


def is_a_spark_frame(value):
    """
    Whether this is a Spark DataFrame, without importing pyspark to find out.

    By what it can do rather than what it is: `toPandas` and `limit` together
    are not a combination anything else in a notebook has, and asking this way
    means a container with no pyspark installed answers False instantly rather
    than raising on the import.
    """
    return hasattr(value, "toPandas") and hasattr(value, "limit") and not hasattr(value, "iloc")


def collect(frame, limit=None):
    """
    A Spark DataFrame as pandas, or a refusal saying what to do instead.

    One row over the limit is fetched on purpose: it is how we tell "exactly
    the limit" from "more than we will carry", without counting the whole
    dataset on the cluster first.
    """
    limit = COLLECT_ROWS if limit is None else limit
    collected = frame.limit(limit + 1).toPandas()
    if len(collected) > limit:
        raise TooMuchToCollect(
            "This cell's result has more than {:,} rows, which is the most that can come back from the "
            "cluster. Aggregate or filter it in Spark before returning it.".format(limit)
        )
    return collected

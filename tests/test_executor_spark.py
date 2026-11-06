"""
Spark in the executor: the handle that waits, and the result that is bounded.

pyspark is not installed here -- it belongs to the Spark build of the executor
image, not to SQLDesk's own. So these use a stand-in with the shape Spark's
DataFrame has, and test the two things that are ours rather than Spark's:

**The session opens on first use and not before.** Opening a notebook attaches
nothing (design §4.4), and a Python cell that only reshapes a dataframe should
not pay for a cluster session it never touches.

**A cluster result is bounded on the way back.** A Spark DataFrame is a plan;
making it a cell's handoff means collecting it, and that is the one moment the
cluster's answer has to fit in one container. Over the bound it is refused,
not truncated -- a notebook that quietly showed the first million rows of a
billion would be worse than one that said no.
"""

import os
import sys
import unittest
from unittest import mock

EXECUTOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "executor")
if EXECUTOR not in sys.path:
    sys.path.insert(0, EXECUTOR)

import spark as spark_module  # noqa: E402


class FakeFrame:
    """A Spark DataFrame's shape: a plan you can limit and collect."""

    def __init__(self, rows):
        self.rows = rows
        self.limited_to = None

    def limit(self, n):
        self.limited_to = n
        return FakeFrame(self.rows[:n])

    def toPandas(self):  # noqa: N802 -- Spark's own spelling
        import pandas

        return pandas.DataFrame({"n": self.rows})


class TestTheHandle(unittest.TestCase):
    def test_nothing_is_opened_until_something_is_asked_of_it(self):
        handle = spark_module.Handle("sc://cluster:15002")

        self.assertFalse(handle.attached)
        self.assertIn("not attached yet", repr(handle))

    def test_the_first_reach_builds_the_session_and_the_second_reuses_it(self):
        handle = spark_module.Handle("sc://cluster:15002")
        built = mock.Mock(range=mock.Mock(return_value="a frame"))

        with mock.patch.object(handle, "session", wraps=lambda: built) as session:
            self.assertEqual("a frame", handle.range(5))
            self.assertEqual("a frame", handle.range(5))

        self.assertEqual(2, session.call_count, "each reach goes through the session")

    def test_it_forwards_whatever_this_version_of_spark_has(self):
        """
        Not a copy of Spark's API: a cell gets whatever the installed version
        offers, and this file does not have to track it.
        """
        handle = spark_module.Handle("sc://cluster:15002")
        handle._built = mock.Mock(something_new_in_spark_5=lambda: "yes")

        self.assertEqual("yes", handle.something_new_in_spark_5())

    def test_stopping_lets_the_session_go(self):
        handle = spark_module.Handle("sc://cluster:15002")
        session = mock.Mock()
        handle._built = session

        handle.stop()

        session.stop.assert_called_once()
        self.assertFalse(handle.attached)

    def test_an_executor_with_no_cluster_says_so(self):
        with mock.patch.object(spark_module, "REMOTE", ""):
            self.assertFalse(spark_module.configured())
        with mock.patch.object(spark_module, "REMOTE", "sc://cluster:15002"):
            self.assertTrue(spark_module.configured())


class TestRecognisingAFrame(unittest.TestCase):
    def test_a_spark_frame_is_recognised_by_what_it_can_do(self):
        self.assertTrue(spark_module.is_a_spark_frame(FakeFrame([1, 2])))

    def test_a_pandas_frame_is_not_mistaken_for_one(self):
        """
        pandas has `toPandas`-adjacent habits and would be collected twice if
        this were sloppy. `iloc` is the tell.
        """
        import pandas

        self.assertFalse(spark_module.is_a_spark_frame(pandas.DataFrame({"a": [1]})))

    def test_an_ordinary_value_is_not(self):
        for value in (None, 42, "a string", [1, 2, 3], {"a": 1}):
            with self.subTest(value=value):
                self.assertFalse(spark_module.is_a_spark_frame(value))


class TestComingHome(unittest.TestCase):
    def test_a_result_within_the_bound_comes_back_whole(self):
        frame = FakeFrame(list(range(10)))

        collected = spark_module.collect(frame, limit=100)

        self.assertEqual(10, len(collected))

    def test_one_more_than_the_limit_is_fetched_so_the_two_cases_differ(self):
        """
        How "exactly the limit" is told from "more than we will carry", without
        counting the whole dataset on the cluster first.
        """
        frame = FakeFrame(list(range(5)))

        spark_module.collect(frame, limit=5)

        self.assertEqual(6, frame.limited_to, "with only `limit` rows asked for, a full result looks like a short one")

    def test_exactly_the_limit_is_allowed(self):
        frame = FakeFrame(list(range(5)))

        self.assertEqual(5, len(spark_module.collect(frame, limit=5)))

    def test_more_than_the_limit_is_refused_with_what_to_do_instead(self):
        frame = FakeFrame(list(range(50)))

        with self.assertRaises(spark_module.TooMuchToCollect) as caught:
            spark_module.collect(frame, limit=5)

        said = str(caught.exception)
        self.assertIn("5", said)
        self.assertIn("Aggregate", said, "a refusal that does not say what to do is a dead end")


class TestWhatACellSees(unittest.TestCase):
    """The namespace, which is where all of this meets somebody's code."""

    def run_cell(self, code, configured):
        import runner

        namespace = {"__name__": "__notebook__", "__builtins__": __builtins__}
        with mock.patch.object(spark_module, "REMOTE", "sc://cluster:15002" if configured else ""):
            if spark_module.configured():
                namespace["spark"] = spark_module.Handle()
            return runner.run_cell(namespace, code, None)

    def test_without_a_cluster_spark_is_not_there_at_all(self):
        """
        Absent rather than a handle that fails on every attribute: a NameError
        naming `spark` is clearer than a connection error from a cell that
        should never have had one.
        """
        answer = self.run_cell("spark", configured=False)

        self.assertFalse(answer["ok"])
        self.assertIn("NameError", answer["error"])

    def test_with_a_cluster_it_is_there_and_still_unopened(self):
        answer = self.run_cell("repr(spark)", configured=True)

        self.assertTrue(answer["ok"], answer)
        self.assertIn("not attached yet", answer["value"])

import datetime

from sqldesk import notebooks
from tests import BaseTestCase


class Cell:
    """A cell as the staleness walk sees it: a name, an id and a last run."""

    def __init__(self, name, ran_at=None, id=None):
        self.name = name
        self.id = id if id is not None else name
        self.last_run_at = ran_at


def at(minute):
    return datetime.datetime(2026, 10, 29, 12, minute, tzinfo=datetime.timezone.utc)


class TestWhatACellMayBeCalled(BaseTestCase):
    """
    The name is a table name in SQL and a variable in Python at the same time,
    so it has to be legal as both without quoting in either.
    """

    def test_an_ordinary_name_is_fine(self):
        for name in ("orders", "orders_by_region", "_scratch", "q1", "A"):
            with self.subTest(name=name):
                self.assertIsNone(notebooks.name_problem(name))

    def test_a_name_is_required_and_says_why(self):
        for name in ("", "   ", None):
            with self.subTest(name=name):
                problem = notebooks.name_problem(name)
                self.assertIsNotNone(problem)
                self.assertIn("refer", problem)

    def test_a_name_starting_with_a_digit_is_refused(self):
        # Legal nowhere: not a bare SQL relation, not a Python identifier.
        self.assertIsNotNone(notebooks.name_problem("1st_pass"))

    def test_spaces_hyphens_and_punctuation_are_refused(self):
        for name in ("by region", "by-region", "orders!", "orders.raw", "o'brien"):
            with self.subTest(name=name):
                self.assertIsNotNone(notebooks.name_problem(name))

    def test_a_name_already_in_the_notebook_is_refused_by_name(self):
        problem = notebooks.name_problem("orders", taken={"orders", "refunds"})

        self.assertIn("orders", problem)

    def test_the_same_name_is_fine_in_another_notebook(self):
        self.assertIsNone(notebooks.name_problem("orders", taken={"refunds"}))

    def test_a_name_too_long_to_read_in_a_reference_is_refused(self):
        self.assertIsNone(notebooks.name_problem("a" * notebooks.MAX_NAME))
        self.assertIsNotNone(notebooks.name_problem("a" * (notebooks.MAX_NAME + 1)))


class TestStaleness(BaseTestCase):
    """
    The one thing Zeppelin never had.

    A session means a number can be computed from an input that has since
    moved, and nothing on the page would say so.
    """

    def test_a_cell_whose_input_ran_later_is_stale(self):
        source = Cell("source", ran_at=at(10))
        derived = Cell("derived", ran_at=at(5))

        stale = notebooks.staleness([source, derived], {"derived": ["source"]})

        self.assertEqual({"derived": ["source"]}, stale)

    def test_a_cell_whose_input_ran_earlier_is_not(self):
        source = Cell("source", ran_at=at(5))
        derived = Cell("derived", ran_at=at(10))

        self.assertEqual({}, notebooks.staleness([source, derived], {"derived": ["source"]}))

    def test_a_cell_that_has_never_run_is_unrun_rather_than_stale(self):
        # Nobody is being misled by a cell with no number on it.
        source = Cell("source", ran_at=at(10))
        derived = Cell("derived", ran_at=None)

        self.assertEqual({}, notebooks.staleness([source, derived], {"derived": ["source"]}))

    def test_an_input_that_has_never_run_cannot_have_run_since(self):
        source = Cell("source", ran_at=None)
        derived = Cell("derived", ran_at=at(10))

        self.assertEqual({}, notebooks.staleness([source, derived], {"derived": ["source"]}))

    def test_every_input_that_moved_is_named_not_just_the_first(self):
        a = Cell("a", ran_at=at(20))
        b = Cell("b", ran_at=at(20))
        c = Cell("c", ran_at=at(5))

        stale = notebooks.staleness([a, b, c], {"c": ["a", "b"]})

        self.assertEqual(["a", "b"], sorted(stale["c"]))

    def test_a_cell_reading_nothing_is_never_stale(self):
        a = Cell("a", ran_at=at(5))

        self.assertEqual({}, notebooks.staleness([a], {}))


class TestStalenessCarries(BaseTestCase):
    """
    A to B to C. Re-running A has to mark C as well.

    Stopping at direct inputs marks B and leaves C looking trustworthy, which
    is both the worst outcome and the hardest to notice by eye.
    """

    def chain(self, a_ran, b_ran, c_ran):
        cells = [Cell("a", ran_at=a_ran), Cell("b", ran_at=b_ran), Cell("c", ran_at=c_ran)]
        return notebooks.staleness(cells, {"b": ["a"], "c": ["b"]})

    def test_re_running_the_first_marks_the_whole_chain(self):
        stale = self.chain(a_ran=at(30), b_ran=at(10), c_ran=at(20))

        self.assertIn("b", stale)
        self.assertIn("c", stale)

    def test_c_is_marked_even_though_b_itself_has_not_re_run(self):
        # c read b at 20 and b last ran at 10, so by the direct rule c is
        # fine. It is not: b is built on an a that has moved.
        stale = self.chain(a_ran=at(30), b_ran=at(10), c_ran=at(20))

        self.assertEqual(["b"], stale["c"])

    def test_a_chain_that_was_run_in_order_is_clean(self):
        self.assertEqual({}, self.chain(a_ran=at(10), b_ran=at(20), c_ran=at(30)))

    def test_a_reference_that_loops_does_not_hang(self):
        # Should not be constructible. Must not take the page down if it is.
        a = Cell("a", ran_at=at(10))
        b = Cell("b", ran_at=at(10))

        notebooks.staleness([a, b], {"a": ["b"], "b": ["a"]})

    def test_a_cell_referring_to_itself_does_not_hang(self):
        a = Cell("a", ran_at=at(10))

        notebooks.staleness([a], {"a": ["a"]})


class TestAnInputThatIsGone(BaseTestCase):
    """
    Deleted and changed need different answers.

    A cell whose input has changed is showing an old number. A cell whose
    input was deleted is showing a number that cannot be reproduced at all --
    re-running fails rather than refreshing it.
    """

    def test_a_deleted_input_is_reported_as_missing(self):
        derived = Cell("derived", ran_at=at(10))

        gone = notebooks.missing_inputs([derived], {"derived": ["source"]})

        self.assertEqual({"derived": ["source"]}, gone)

    def test_a_deleted_input_is_not_reported_as_staleness(self):
        derived = Cell("derived", ran_at=at(10))

        self.assertEqual({}, notebooks.staleness([derived], {"derived": ["source"]}))

    def test_an_unrun_cell_has_nothing_to_be_missing(self):
        derived = Cell("derived", ran_at=None)

        self.assertEqual({}, notebooks.missing_inputs([derived], {"derived": ["source"]}))

    def test_inputs_that_still_exist_are_not_reported(self):
        source = Cell("source", ran_at=at(5))
        derived = Cell("derived", ran_at=at(10))

        self.assertEqual({}, notebooks.missing_inputs([source, derived], {"derived": ["source"]}))

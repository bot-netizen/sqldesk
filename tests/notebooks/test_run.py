"""
Running a cell: the split store in practice, and the refusals said in advance.

The claim worth testing here is the one the whole design rests on. A SQL cell
writes **twice** -- everything into the notebook's own file for the next cell,
a truncated slice into `query_results` for the page -- and the next cell can
then read the whole thing, not the slice. If that is not true, a notebook is a
dashboard with extra steps.

The other half is §4.9: a cell says why it cannot run *before* it runs.
Zeppelin's failure mode is finding the limits by hitting them, so each refusal
is checked for the sentence a person can act on, not for a boolean.
"""

import shutil
import tempfile
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.notebooks import run as runner
from sqldesk.notebooks.store import Store
from sqldesk.query_runner import TYPE_INTEGER, TYPE_STRING
from tests import BaseTestCase


def result(rows, columns=None):
    """What a query runner hands back."""
    columns = columns or [
        {"name": "id", "friendly_name": "id", "type": TYPE_INTEGER},
        {"name": "city", "friendly_name": "city", "type": TYPE_STRING},
    ]
    return {"columns": columns, "rows": rows}


def answering(data, error=None):
    """A data source that returns this, without a warehouse anywhere near it."""
    return mock.Mock(return_value=(data, error))


class NotebookTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.notebook = models.Notebook(org=self.factory.org, user=self.factory.user, name="Quarter", is_draft=True)
        db.session.add(self.notebook)
        db.session.flush()

    def cell(self, name, source, position=0, data_source=None, kind=models.NotebookCell.SQL, ran=False):
        cell = models.NotebookCell(
            notebook=self.notebook,
            name=name,
            source=source,
            position=position,
            kind=kind,
            data_source=data_source,
        )
        if ran:
            cell.last_run_at = models.db.func.now()
        db.session.add(cell)
        db.session.flush()
        return cell

    def store(self):
        return Store(self.notebook.store_path(), read_only=True)


class TestWhatACellReads(BaseTestCase):
    """
    Which names in a statement are cell references. Narrow on purpose: every
    other identifier is a column, an alias or a function.
    """

    def test_from_and_join_are_references(self):
        found = runner.references("SELECT * FROM orders JOIN cities ON true", ["orders", "cities"])

        self.assertEqual(["orders", "cities"], found)

    def test_a_name_this_notebook_does_not_have_is_not_a_reference(self):
        self.assertEqual([], runner.references("SELECT * FROM public.sales", ["orders"]))

    def test_a_column_or_alias_is_not_a_reference(self):
        found = runner.references("SELECT orders AS cities FROM orders", ["orders", "cities"])

        self.assertEqual(["orders"], found)

    def test_case_does_not_matter_but_the_cells_own_spelling_is_returned(self):
        self.assertEqual(["Orders"], runner.references("select * from ORDERS", ["Orders"]))

    def test_a_cell_read_twice_is_listed_once(self):
        found = runner.references("SELECT * FROM orders UNION SELECT * FROM orders", ["orders"])

        self.assertEqual(["orders"], found)

    def test_a_quoted_name_is_still_a_reference(self):
        self.assertEqual(["orders"], runner.references('SELECT * FROM "orders"', ["orders"]))


class TestWhyItCannotRun(NotebookTestCase):
    def test_a_cell_with_a_data_source_and_sql_can_run(self):
        cell = self.cell("orders", "SELECT 1", data_source=self.factory.data_source)

        self.assertIsNone(runner.why_it_cannot_run(cell))

    def test_an_empty_cell_says_so(self):
        cell = self.cell("orders", "   ", data_source=self.factory.data_source)

        self.assertIn("no SQL", runner.why_it_cannot_run(cell))

    def test_a_cell_cannot_query_a_warehouse_and_read_a_cell_at_once(self):
        """
        The limit that belongs in the product rather than being discovered: a
        warehouse has never heard of cell `orders`, and we are not pushing the
        rows into it to pretend otherwise.
        """
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        second = self.cell("summary", "SELECT count(*) FROM orders", position=1, data_source=self.factory.data_source)

        problem = runner.why_it_cannot_run(second)

        self.assertIn("orders", problem)
        self.assertIn("not both", problem)

    def test_a_cell_with_no_data_source_and_no_reference_says_what_it_could_read(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        second = self.cell("summary", "SELECT 1", position=1)

        problem = runner.why_it_cannot_run(second)

        self.assertIn("orders", problem, "it should name what there is to read")

    def test_the_first_cell_with_no_data_source_says_there_is_nothing_above_it(self):
        cell = self.cell("summary", "SELECT 1")

        self.assertIn("no cell above it", runner.why_it_cannot_run(cell))

    def test_reading_a_cell_that_has_never_run_says_which_one(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source)
        second = self.cell("summary", "SELECT count(*) FROM orders", position=1)

        problem = runner.why_it_cannot_run(second)

        self.assertIn("orders", problem)
        self.assertIn("not run yet", problem)

    def test_a_cell_only_reads_what_is_above_it(self):
        """Position, not existence: a notebook is read downwards."""
        first = self.cell("summary", "SELECT count(*) FROM orders", position=0)
        self.cell("orders", "SELECT 1", position=1, data_source=self.factory.data_source, ran=True)

        self.assertIn("no cell above it", runner.why_it_cannot_run(first))

    def test_a_python_cell_without_an_interpreter_says_what_is_missing(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        code = self.cell("shaped", "df.head()", position=1, kind=models.NotebookCell.PYTHON)

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", ""):
            problem = runner.why_it_cannot_run(code)

        self.assertIn("interpreter", problem)

    def test_a_python_cell_with_an_interpreter_and_data_above_it_can_run(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        code = self.cell("shaped", "df.head()", position=1, kind=models.NotebookCell.PYTHON)

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", "http://executor:5000"):
            self.assertIsNone(runner.why_it_cannot_run(code))

    def test_a_python_cell_with_nothing_above_it_is_told_it_cannot_query(self):
        code = self.cell("shaped", "df.head()", kind=models.NotebookCell.PYTHON)

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", "http://executor:5000"):
            problem = runner.why_it_cannot_run(code)

        self.assertIn("cannot query", problem)


class TestTheNameOfTheRefusal(NotebookTestCase):
    """
    Each refusal carries a name as well as a sentence.

    The page needs the name for one case it cannot get right otherwise: the
    sentence describes the cell as *saved*, and a cell saves when its editor
    loses focus, so somebody who has just typed into an empty cell must not be
    told it is empty. Matching on English would be the alternative.
    """

    def test_an_empty_cell_is_named_empty(self):
        cell = self.cell("orders", "   ", data_source=self.factory.data_source)

        self.assertEqual(runner.EMPTY, runner.what_stops_it(cell)[0])

    def test_a_cell_reading_an_unrun_cell_is_named_for_that(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source)
        second = self.cell("summary", "SELECT count(*) FROM orders", position=1)

        self.assertEqual(runner.UNRUN_INPUT, runner.what_stops_it(second)[0])

    def test_a_cell_with_a_data_source_and_a_reference_is_named_for_that(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        second = self.cell("summary", "SELECT count(*) FROM orders", position=1, data_source=self.factory.data_source)

        self.assertEqual(runner.BOTH_SOURCES, runner.what_stops_it(second)[0])

    def test_a_python_cell_without_an_interpreter_is_named_for_that(self):
        self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source, ran=True)
        code = self.cell("shaped", "orders.head()", position=1, kind=models.NotebookCell.PYTHON)

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", ""):
            self.assertEqual(runner.NO_INTERPRETER, runner.what_stops_it(code)[0])

    def test_a_runnable_cell_is_stopped_by_nothing(self):
        cell = self.cell("orders", "SELECT 1", data_source=self.factory.data_source)

        self.assertIsNone(runner.what_stops_it(cell))

    def test_the_sentence_is_the_same_one_why_it_cannot_run_gives(self):
        """One source of truth; the other is a view of it."""
        cell = self.cell("orders", "   ", data_source=self.factory.data_source)

        self.assertEqual(runner.why_it_cannot_run(cell), runner.what_stops_it(cell)[1])


class TestRunningASqlCell(NotebookTestCase):
    def test_the_whole_result_is_handed_on_and_a_slice_is_displayed(self):
        """
        The split, in one test. 2,500 rows fetched; the handoff has all of
        them, `query_results` has the first 10, and the run says 2,500 -- so
        the page can say "first 10 of 2,500" rather than implying ten was all.
        """
        rows = [{"id": n, "city": "Toronto"} for n in range(2500)]
        cell = self.cell("orders", "SELECT * FROM big", data_source=self.factory.data_source)

        with mock.patch("sqldesk.settings.NOTEBOOK_DISPLAY_ROWS", 10):
            record = runner.run_sql_cell(cell, self.factory.user, run_query=answering(result(rows)))

        self.assertEqual(models.NotebookRun.OK, record.state)
        self.assertEqual(2500, record.rows)
        store = self.store()
        try:
            self.assertEqual(2500, store.row_count("orders"), "the next cell would only see the slice")
        finally:
            store.close()
        self.assertEqual(10, len(cell.latest_result.data["rows"]))

    def test_the_next_cell_reads_the_whole_handoff(self):
        """
        What the split is for. The second cell sums 2,500 rows that were never
        all in Postgres and never all in Python.
        """
        rows = [{"id": n, "city": "Toronto"} for n in range(2500)]
        first = self.cell("orders", "SELECT * FROM big", position=0, data_source=self.factory.data_source)
        with mock.patch("sqldesk.settings.NOTEBOOK_DISPLAY_ROWS", 10):
            runner.run_sql_cell(first, self.factory.user, run_query=answering(result(rows)))
        second = self.cell("summary", "SELECT count(*) AS n, sum(id) AS total FROM orders", position=1)

        record = runner.run_sql_cell(second, self.factory.user)

        self.assertEqual(models.NotebookRun.OK, record.state)
        self.assertEqual([2500], [row["n"] for row in second.latest_result.data["rows"]])
        self.assertEqual(sum(range(2500)), second.latest_result.data["rows"][0]["total"])

    def test_the_run_records_which_cells_it_read(self):
        """Provenance: what makes staleness answerable later."""
        first = self.cell("orders", "SELECT 1", position=0, data_source=self.factory.data_source)
        runner.run_sql_cell(first, self.factory.user, run_query=answering(result([{"id": 1, "city": "A"}])))
        second = self.cell("summary", "SELECT count(*) AS n FROM orders", position=1)

        record = runner.run_sql_cell(second, self.factory.user)

        self.assertEqual(["orders"], record.inputs)

    def test_a_cells_result_carries_the_data_source_the_data_came_from(self):
        """
        Not decoration. Permission on a stored result follows its data source,
        so a cell that read an earlier cell has to carry that cell's origin --
        otherwise a result assembled in the notebook would answer to nothing.
        """
        source = self.factory.data_source
        first = self.cell("orders", "SELECT 1", position=0, data_source=source)
        runner.run_sql_cell(first, self.factory.user, run_query=answering(result([{"id": 1, "city": "A"}])))
        second = self.cell("summary", "SELECT count(*) AS n FROM orders", position=1)
        third = self.cell("again", "SELECT n FROM summary", position=2)

        runner.run_sql_cell(second, self.factory.user)
        runner.run_sql_cell(third, self.factory.user)

        self.assertEqual(source.id, second.latest_result.data_source_id)
        self.assertEqual(source.id, third.latest_result.data_source_id, "two hops from the warehouse")

    def test_a_cell_that_cannot_run_leaves_no_trace_of_having_tried(self):
        cell = self.cell("summary", "SELECT 1")

        with self.assertRaises(runner.CannotRun):
            runner.run_sql_cell(cell, self.factory.user)

        self.assertEqual(0, models.NotebookRun.query.count())
        self.assertIsNone(cell.last_run_at)

    def test_a_failed_query_is_recorded_and_the_cell_keeps_its_last_good_run(self):
        cell = self.cell("orders", "SELECT * FROM nope", data_source=self.factory.data_source)
        runner.run_sql_cell(cell, self.factory.user, run_query=answering(result([{"id": 1, "city": "A"}])))
        first_result = cell.latest_result_id

        record = runner.run_sql_cell(
            cell, self.factory.user, run_query=answering(None, "relation nope does not exist")
        )

        self.assertEqual(models.NotebookRun.FAILED, record.state)
        self.assertIn("nope", record.error)
        self.assertEqual(first_result, cell.latest_result_id, "a failure replaced what was on the page")

    def test_re_running_replaces_the_handoff_rather_than_adding_to_it(self):
        cell = self.cell("orders", "SELECT * FROM big", data_source=self.factory.data_source)
        runner.run_sql_cell(cell, self.factory.user, run_query=answering(result([{"id": 1, "city": "A"}])))

        runner.run_sql_cell(
            cell,
            self.factory.user,
            run_query=answering(result([{"id": 2, "city": "B"}, {"id": 3, "city": "C"}])),
        )

        store = self.store()
        try:
            self.assertEqual(2, store.row_count("orders"))
        finally:
            store.close()

    def test_a_query_that_returns_nothing_is_a_failure_not_an_empty_handoff(self):
        """
        A runner answering `None` means it did not produce a result set. Writing
        an empty table would make the next cell's zero look like an answer.
        """
        cell = self.cell("orders", "CREATE TABLE x (a int)", data_source=self.factory.data_source)

        record = runner.run_sql_cell(cell, self.factory.user, run_query=answering(None, None))

        self.assertEqual(models.NotebookRun.FAILED, record.state)
        self.assertIn("nothing to hand on", record.error)

    def test_the_timing_and_row_count_are_recorded(self):
        cell = self.cell("orders", "SELECT 1", data_source=self.factory.data_source)

        record = runner.run_sql_cell(cell, self.factory.user, run_query=answering(result([{"id": 1, "city": "A"}])))

        self.assertIsNotNone(record.started_at)
        self.assertIsNotNone(record.finished_at)
        self.assertIsNotNone(record.runtime)
        self.assertEqual(1, record.rows)


class TestTheAuditSeesACellRun(NotebookTestCase):
    """
    The other half of the audit's view of notebooks.

    `tests/test_audit.py` checks the page names a cell run correctly given the
    event; this checks the event is written at all, which is the half that was
    missing. Notebooks and the audit are both new and were built without
    reference to each other, so an install whose people worked in notebooks
    saw an empty audit while the page promised "where the month went".
    """

    def executions(self):
        return models.Event.query.filter(models.Event.action == "execute_query").all()

    def a_run(self, name="orders", source="SELECT 1"):
        cell = self.cell(name, source, data_source=self.factory.data_source)
        runner.run_sql_cell(cell, self.factory.user, run_query=answering(result([{"id": 1}])))
        db.session.flush()
        return cell

    def test_a_sql_cell_against_a_warehouse_records_one(self):
        self.a_run()

        events = self.executions()

        self.assertEqual(1, len(events))
        self.assertEqual("notebook", events[0].additional_properties["query_id"])
        self.assertEqual(str(self.factory.data_source.id), str(events[0].object_id))

    def test_it_says_which_notebook_and_which_cell(self):
        cell = self.a_run()

        properties = self.executions()[0].additional_properties

        self.assertEqual(cell.notebook_id, properties["notebook_id"])
        self.assertEqual("orders", properties["cell"])

    def test_it_is_attributed_to_whoever_ran_it(self):
        self.a_run()

        self.assertEqual(self.factory.user.id, self.executions()[0].user_id)

    def test_a_cell_reading_earlier_cells_records_nothing(self):
        """
        No warehouse was touched. Counting it would inflate a month with work
        that never left the notebook's own store.
        """
        self.a_run()
        reading = self.cell("counted", "SELECT count(*) AS n FROM orders", position=1)

        runner.run_sql_cell(reading, self.factory.user)
        db.session.flush()

        # The one from `a_run`, and not a second.
        self.assertEqual(1, len(self.executions()))

    def test_a_cell_that_fails_is_still_counted(self):
        """
        The editor counts an execution when somebody asks, not when it
        succeeds -- a month of failing queries is a month of work asked for,
        and an audit that hid them would be the wrong shape.
        """
        cell = self.cell("broken", "SELECT nonsense", data_source=self.factory.data_source)

        runner.run_sql_cell(cell, self.factory.user, run_query=answering(None, "no such column"))
        db.session.flush()

        self.assertEqual(1, len(self.executions()))

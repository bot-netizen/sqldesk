"""
Running a cell on a worker: the pool slot, and what a refusal looks like.

The claim worth holding here is the one that is easy to lose: a SQL cell in a
notebook is a query against a warehouse, and the warehouse's connection limit
does not get larger because somebody typed it into a notebook instead of the
query editor. A Python cell takes no slot at all -- it runs on the interpreter
and touches no data source.
"""

import shutil
import tempfile
from unittest import mock

from sqldesk import models, pools
from sqldesk.models import db
from sqldesk.notebooks import run as cell_runner
from sqldesk.tasks.notebooks import run_cell, run_due_notebooks, run_notebook
from tests import BaseTestCase


class CellJobTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.notebook = models.Notebook(org=self.factory.org, user=self.factory.user, name="Quarter")
        db.session.add(self.notebook)
        db.session.flush()

    def a_cell(self, kind=models.NotebookCell.SQL, source="SELECT 1", data_source=None, name="orders"):
        cell = models.NotebookCell(
            notebook=self.notebook,
            name=name,
            source=source,
            position=0,
            kind=kind,
            data_source=data_source,
        )
        db.session.add(cell)
        db.session.commit()
        return cell


class TestThePoolSlot(CellJobTestCase):
    def test_a_sql_cell_takes_a_slot_and_gives_it_back(self):
        source = self.factory.data_source
        cell = self.a_cell(data_source=source)
        pool = pools.pool_for(source)

        with mock.patch.object(cell_runner, "run_sql_cell") as ran:
            ran.return_value = _ok()
            during = {}

            def note(*args, **kwargs):
                during["held"] = dict(pools.held(pool))
                return _ok()

            ran.side_effect = note
            run_cell(cell.id, self.factory.user.id)

        self.assertEqual(1, len(during["held"]), "the cell ran without taking a slot")
        self.assertEqual({}, dict(pools.held(pool)), "the slot was not given back")

    def test_a_python_cell_takes_no_slot(self):
        cell = self.a_cell(kind=models.NotebookCell.PYTHON, source="1 + 1", name="code")

        with mock.patch.object(cell_runner, "run_python_cell") as ran:
            ran.return_value = _ok()
            run_cell(cell.id, self.factory.user.id)

        self.assertEqual({}, dict(pools.held("ds:{}".format(self.factory.data_source.id))))

    def test_a_full_pool_is_reported_in_the_pools_own_words(self):
        source = self.factory.data_source
        cell = self.a_cell(data_source=source)

        with mock.patch.object(pools, "acquire", return_value="All 8 slots on warehouse are in use."):
            with mock.patch.object(cell_runner, "run_sql_cell") as ran:
                answer = run_cell(cell.id, self.factory.user.id)

        self.assertEqual({"error": "All 8 slots on warehouse are in use."}, answer)
        ran.assert_not_called()

    def test_a_refused_slot_is_not_released_as_though_it_were_held(self):
        """
        Releasing a slot we never took would hand somebody else's slot back.
        """
        source = self.factory.data_source
        cell = self.a_cell(data_source=source)

        with mock.patch.object(pools, "acquire", return_value="no room"):
            with mock.patch.object(pools, "release") as released:
                run_cell(cell.id, self.factory.user.id)

        released.assert_not_called()

    def test_the_slot_is_given_back_when_the_cell_fails(self):
        source = self.factory.data_source
        cell = self.a_cell(data_source=source)
        pool = pools.pool_for(source)

        with mock.patch.object(cell_runner, "run_sql_cell", side_effect=RuntimeError("boom")):
            answer = run_cell(cell.id, self.factory.user.id)

        self.assertEqual({"error": "boom"}, answer)
        self.assertEqual({}, dict(pools.held(pool)), "a failed cell kept its slot")


class TestWhatTheJobReports(CellJobTestCase):
    def test_a_cell_that_cannot_run_is_a_sentence_not_a_crash(self):
        """
        "This cell cannot run yet" is not an exception. Raising would make
        every refusal look like a crash in the logs.
        """
        cell = self.a_cell(name="summary", source="SELECT 1")

        answer = run_cell(cell.id, self.factory.user.id)

        self.assertIn("no data source", answer["error"])

    def test_a_deleted_cell_is_said_plainly(self):
        cell = self.a_cell(data_source=self.factory.data_source)
        cell_id = cell.id
        db.session.delete(cell)
        db.session.commit()

        answer = run_cell(cell_id, self.factory.user.id)

        self.assertEqual({"error": "That cell has been deleted."}, answer)

    def test_a_good_run_reports_the_result_to_show(self):
        cell = self.a_cell(data_source=self.factory.data_source)
        record = _ok()

        with mock.patch.object(cell_runner, "run_sql_cell", return_value=record):
            with mock.patch.object(models.db.session, "commit"):
                cell.latest_result_id = 4242
                answer = run_cell(cell.id, self.factory.user.id)

        self.assertEqual(4242, answer, "serialize_job reads the return value as the result id")

    def test_a_failed_run_reports_the_error_the_cell_recorded(self):
        cell = self.a_cell(data_source=self.factory.data_source)
        record = _ok()
        record.state = models.NotebookRun.FAILED
        record.error = "relation nope does not exist"

        with mock.patch.object(cell_runner, "run_sql_cell", return_value=record):
            answer = run_cell(cell.id, self.factory.user.id)

        self.assertEqual("relation nope does not exist", answer["error"])


def _ok():
    record = models.NotebookRun(state=models.NotebookRun.OK)
    record.id = 1
    return record


class TestRunningTheWholeNotebook(CellJobTestCase):
    """
    Run all, and the rule that makes it trustworthy: it stops.

    A notebook is a chain. If cell two failed, cell three reads what cell two
    did not produce -- and running it anyway would either refuse or, worse,
    succeed against cell two's *previous* output and put a number on the
    screen computed from data that no longer matches the cell above it.
    """

    def chain(self, how_many=3):
        cells = []
        for n in range(how_many):
            cell = models.NotebookCell(
                notebook=self.notebook,
                name="cell_{}".format(n),
                source="SELECT 1",
                position=n,
                kind=models.NotebookCell.SQL,
                data_source=self.factory.data_source if n == 0 else None,
            )
            db.session.add(cell)
            cells.append(cell)
        db.session.commit()
        return cells

    def test_it_runs_every_cell_in_order(self):
        self.chain(3)
        seen = []

        with mock.patch("sqldesk.tasks.notebooks._run") as ran:
            ran.side_effect = lambda cell, user: (seen.append(cell.name), _ok())[1]
            answer = run_notebook(self.notebook.id, self.factory.user.id)

        self.assertEqual(["cell_0", "cell_1", "cell_2"], seen)
        self.assertEqual({"ran": 3}, answer)

    def test_it_stops_at_the_first_failure_and_says_which_cell(self):
        self.chain(3)
        seen = []

        def fail_on_the_second(cell, user):
            seen.append(cell.name)
            if cell.name == "cell_1":
                record = models.NotebookRun(state=models.NotebookRun.FAILED, error="no such column")
                record.id = 2
                return record
            return _ok()

        with mock.patch("sqldesk.tasks.notebooks._run", side_effect=fail_on_the_second):
            answer = run_notebook(self.notebook.id, self.factory.user.id)

        self.assertEqual(["cell_0", "cell_1"], seen, "it carried on past a failure")
        self.assertIn("cell_1", answer["error"])
        self.assertIn("no such column", answer["error"])

    def test_how_many_got_through_before_it_stopped(self):
        """
        So the page can say "two of five ran" rather than only that something
        went wrong -- the first two results are real and on the screen.
        """
        self.chain(5)

        def fail_on_the_third(cell, user):
            if cell.name == "cell_2":
                record = models.NotebookRun(state=models.NotebookRun.FAILED, error="boom")
                record.id = 3
                return record
            return _ok()

        with mock.patch("sqldesk.tasks.notebooks._run", side_effect=fail_on_the_third):
            answer = run_notebook(self.notebook.id, self.factory.user.id)

        self.assertEqual(2, answer["ran"])

    def test_a_refusal_stops_it_as_a_failure_does(self):
        self.chain(3)

        with mock.patch("sqldesk.tasks.notebooks._run") as ran:
            ran.side_effect = cell_runner.CannotRun("This cell has no SQL in it yet.")
            answer = run_notebook(self.notebook.id, self.factory.user.id)

        self.assertIn("cell_0", answer["error"])
        self.assertEqual(0, answer["ran"])

    def test_a_deleted_notebook_is_a_sentence_rather_than_a_crash(self):
        notebook_id = self.notebook.id
        db.session.delete(self.notebook)
        db.session.commit()

        answer = run_notebook(notebook_id, self.factory.user.id)

        self.assertIn("deleted", answer["error"])

    def test_each_sql_cell_takes_a_slot_on_the_same_terms_as_a_single_run(self):
        """
        The warehouse's connection limit does not get larger because a
        notebook is running itself rather than a person pressing Run.
        """
        cells = self.chain(2)
        cells[1].data_source = self.factory.data_source
        db.session.commit()
        pool = pools.pool_for(self.factory.data_source)
        held = []

        with mock.patch("sqldesk.tasks.notebooks._run") as ran:
            ran.side_effect = lambda cell, user: (held.append(len(dict(pools.held(pool)))), _ok())[1]
            run_notebook(self.notebook.id, self.factory.user.id)

        self.assertEqual([1, 1], held, "a cell ran without taking a slot")
        self.assertEqual({}, dict(pools.held(pool)), "a slot was not given back")


class TestStartingTheNotebooksThatAreDue(CellJobTestCase):
    """
    The periodic check that starts scheduled notebooks.

    It enqueues rather than runs: each notebook is its own job, so one slow
    notebook does not hold up every other notebook's schedule.
    """

    def scheduled(self, cron="0 6 * * *", last=None, draft=False):
        notebook = models.Notebook(
            org=self.factory.org,
            user=self.factory.user,
            name="Nightly",
            is_draft=draft,
            schedule=cron,
            last_scheduled_at=last,
        )
        db.session.add(notebook)
        db.session.commit()
        return notebook

    def test_it_enqueues_a_notebook_whose_slot_has_come_round(self):
        notebook = self.scheduled()

        with mock.patch("sqldesk.tasks.notebooks.run_notebook.delay") as delayed:
            answer = run_due_notebooks()

        delayed.assert_called_once_with(notebook.id, self.factory.user.id)
        self.assertEqual([notebook.id], answer["started"])

    def test_it_stamps_the_notebook_at_enqueue_not_at_finish(self):
        """
        Otherwise a notebook taking longer than its interval is enqueued
        again on the next check, and again, until the queue is nothing but
        that notebook.
        """
        notebook = self.scheduled()

        with mock.patch("sqldesk.tasks.notebooks.run_notebook.delay"):
            run_due_notebooks()

        self.assertIsNotNone(models.Notebook.query.get(notebook.id).last_scheduled_at)

    def test_a_second_check_does_not_start_it_again(self):
        self.scheduled()

        with mock.patch("sqldesk.tasks.notebooks.run_notebook.delay") as delayed:
            run_due_notebooks()
            run_due_notebooks()

        self.assertEqual(1, delayed.call_count)

    def test_a_draft_is_left_alone(self):
        self.scheduled(draft=True)

        with mock.patch("sqldesk.tasks.notebooks.run_notebook.delay") as delayed:
            run_due_notebooks()

        delayed.assert_not_called()

    def test_one_notebook_failing_to_enqueue_does_not_stop_the_rest(self):
        first = self.scheduled()
        second = self.scheduled()

        def refuse_the_first(notebook_id, user_id):
            if notebook_id == first.id:
                raise RuntimeError("redis said no")

        with mock.patch("sqldesk.tasks.notebooks.run_notebook.delay", side_effect=refuse_the_first):
            answer = run_due_notebooks()

        self.assertEqual([second.id], answer["started"])
        # And the one that could not be enqueued is not stamped, so the next
        # check tries it again rather than skipping its slot.
        self.assertIsNone(models.Notebook.query.get(first.id).last_scheduled_at)


class TestBackingOffAFailingNotebook(CellJobTestCase):
    def a_notebook_with_cells(self):
        notebook = models.Notebook(
            org=self.factory.org, user=self.factory.user, name="Nightly", is_draft=False, schedule="0 6 * * *"
        )
        db.session.add(notebook)
        db.session.flush()
        db.session.add(
            models.NotebookCell(
                notebook=notebook,
                name="orders",
                source="SELECT 1",
                position=0,
                kind=models.NotebookCell.SQL,
                data_source=self.factory.data_source,
            )
        )
        db.session.commit()
        return notebook

    def test_a_failed_run_counts_against_the_schedule(self):
        notebook = self.a_notebook_with_cells()

        def fail(cell, user):
            record = models.NotebookRun(state=models.NotebookRun.FAILED, error="boom")
            record.id = 1
            return record

        with mock.patch("sqldesk.tasks.notebooks._run", side_effect=fail):
            run_notebook(notebook.id, self.factory.user.id)

        self.assertEqual(1, models.Notebook.query.get(notebook.id).schedule_failures)

    def test_a_run_that_works_clears_the_count(self):
        notebook = self.a_notebook_with_cells()
        notebook.schedule_failures = 5
        db.session.add(notebook)
        db.session.commit()

        with mock.patch("sqldesk.tasks.notebooks._run", return_value=_ok()):
            run_notebook(notebook.id, self.factory.user.id)

        self.assertEqual(0, models.Notebook.query.get(notebook.id).schedule_failures)

"""
A Python cell: what is shipped, what comes back, and what it cannot do.

Two kinds of test here, and both are worth having.

Most of them drive a stand-in interpreter, because what is being checked is
SQLDesk's side: that only the cells a cell mentions are shipped, that a
dataframe becomes a handoff and text does not, that a lost session is reopened
rather than reported, and that a cell says in advance when it cannot run.

The last class wires the **real** executor to the **real** store and runs
pandas on the other side of it. That is the one that would have caught a
Parquet written one way and read another, or types quietly flattened in
between -- neither of which a stand-in can fail on, because a stand-in agrees
with whatever we wrote.
"""

import json
import os
import shutil
import sys
import tempfile
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.notebooks import interpreter
from sqldesk.notebooks import run as runner
from sqldesk.notebooks.store import Store
from sqldesk.query_runner import TYPE_DATETIME, TYPE_INTEGER, TYPE_STRING
from tests import BaseTestCase

EXECUTOR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "executor")
if EXECUTOR not in sys.path:
    sys.path.insert(0, EXECUTOR)


def columns(*pairs):
    return [{"name": name, "friendly_name": name, "type": kind} for name, kind in pairs]


class Stand_in:
    """
    An interpreter that records what it was asked and answers what it is told.

    Deliberately not a Mock: the sequence matters here -- ship, then run, then
    fetch -- and a recorded list of calls says whether that happened in that
    order far more plainly than three assert_called_with.
    """

    def __init__(self, answers=None, frame=None, fail_first_with=None):
        self.calls = []
        self.shipped = []
        self.answers = list(answers or [{"ok": True, "stdout": "", "value": "42", "result_id": None}])
        self.frame = frame
        self.fail_first_with = fail_first_with
        self.sessions = 0

    def session_for(self, notebook, create=True):
        if not create:
            return "session-1" if self.sessions else None
        self.sessions += 1
        self.calls.append(("session_for", self.sessions))
        return "session-{}".format(self.sessions)

    def detach(self, notebook):
        self.calls.append(("detach", None))
        self.sessions = 0

    def ship(self, notebook, session_id, store, names):
        self.calls.append(("ship", tuple(names)))
        self.shipped.append(tuple(names))
        if self.fail_first_with and len(self.shipped) == 1:
            raise self.fail_first_with

    def run(self, session_id, code):
        self.calls.append(("run", code))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def fetch(self, session_id, result_id, into):
        self.calls.append(("fetch", result_id))
        shutil.copyfile(self.frame, into)
        return into


class PythonCellTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        for target, value in (("UPLOAD_ROOT", self.root), ("NOTEBOOK_EXECUTOR_URL", "http://executor:5000")):
            patch = mock.patch("sqldesk.settings.{}".format(target), value)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        self.notebook = models.Notebook(org=self.factory.org, user=self.factory.user, name="Quarter")
        db.session.add(self.notebook)
        db.session.flush()

    def cell(self, name, source, position=0, kind=models.NotebookCell.PYTHON, data_source=None):
        cell = models.NotebookCell(
            notebook=self.notebook,
            name=name,
            source=source,
            position=position,
            kind=kind,
            data_source=data_source,
        )
        db.session.add(cell)
        db.session.flush()
        return cell

    def a_sql_cell_that_ran(self, name, rows, position=0, cols=None):
        """A SQL cell with a handoff already in the store, as its run leaves it."""
        cell = self.cell(
            name, "SELECT 1", position=position, kind=models.NotebookCell.SQL, data_source=self.factory.data_source
        )
        store = Store(self.notebook.store_path())
        try:
            store.hand_off(name, cols or columns(("id", TYPE_INTEGER), ("city", TYPE_STRING)), rows)
        finally:
            store.close()
        cell.last_run_at = models.db.func.now()
        cell.options = {"produced": runner.TABLE}
        db.session.add(cell)
        db.session.flush()
        return cell

    def parquet(self, rows, declaration="id INTEGER, city VARCHAR"):
        """A Parquet file, as the interpreter would hand one back."""
        import duckdb

        path = os.path.join(self.root, "from-interpreter.parquet")
        connection = duckdb.connect()
        try:
            quoted = ", ".join('"{}" {}'.format(*one.strip().split(" ", 1)) for one in declaration.split(","))
            connection.execute("CREATE TABLE out ({})".format(quoted))
            for row in rows:
                connection.execute("INSERT INTO out VALUES ({})".format(", ".join("?" for _ in row)), list(row))
            connection.execute("COPY out TO ? (FORMAT PARQUET)", [path])
        finally:
            connection.close()
        return path


class TestWhatIsShipped(PythonCellTestCase):
    def test_only_the_cells_the_code_mentions_are_shipped(self):
        """
        A notebook whose first cell fetched four million rows should not send
        them to the interpreter for a cell that never looks at them.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}], position=0)
        self.a_sql_cell_that_ran("weather", [{"id": 1, "city": "Ottawa"}], position=1)
        code = self.cell("shaped", "orders.head()", position=2)
        stand_in = Stand_in()

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual([("orders",)], stand_in.shipped)

    def test_a_name_that_merely_contains_a_cells_name_is_not_a_reference(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}], position=0)
        code = self.cell("shaped", "orders_total = 1\norders_total", position=1)
        stand_in = Stand_in()

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual([()], stand_in.shipped, "it shipped a cell the code does not use")

    def test_a_name_inside_a_longer_token_is_not_a_reference(self):
        """
        The leading word boundary, which the greedy character class does not
        make redundant: without it, `'1orders'` yields `orders`, because the
        match simply starts after the digit. A string or a column name is
        exactly where that spelling turns up.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}], position=0)
        code = self.cell("shaped", "label = '1orders'\nlabel", position=1)
        stand_in = Stand_in()

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual([()], stand_in.shipped, "a digit-prefixed token was read as a reference")

    def test_the_inputs_are_recorded_on_the_run_for_staleness(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}], position=0)
        code = self.cell("shaped", "orders.head()", position=1)

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: Stand_in())

        self.assertEqual(["orders"], record.inputs)

    def test_ship_then_run_then_fetch_in_that_order(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}], position=0)
        code = self.cell("shaped", "orders.head(1)", position=1)
        stand_in = Stand_in(
            answers=[{"ok": True, "stdout": "", "value": None, "result_id": "a" * 32}],
            frame=self.parquet([(1, "Toronto")]),
        )

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual(["session_for", "ship", "run", "fetch"], [name for name, _ in stand_in.calls])


class TestWhatComesBack(PythonCellTestCase):
    def test_a_dataframe_becomes_this_cells_handoff(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}, {"id": 2, "city": "Ottawa"}])
        code = self.cell("shaped", "orders.head(1)", position=1)
        stand_in = Stand_in(
            answers=[{"ok": True, "stdout": "", "value": None, "result_id": "b" * 32}],
            frame=self.parquet([(1, "Toronto")]),
        )

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual(models.NotebookRun.OK, record.state)
        self.assertEqual(runner.TABLE, code.options["produced"])
        store = Store(self.notebook.store_path(), read_only=True)
        try:
            self.assertEqual(1, store.row_count("shaped"))
        finally:
            store.close()

    def test_a_later_sql_cell_can_read_what_python_produced(self):
        """
        The chain closing: SQL to the warehouse, Python over its result, SQL
        again over Python's. All of it in one DuckDB file.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "orders.head(1)", position=1)
        stand_in = Stand_in(
            answers=[{"ok": True, "stdout": "", "value": None, "result_id": "c" * 32}],
            frame=self.parquet([(7, "Montreal"), (8, "Halifax")]),
        )
        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)
        after = self.cell("counted", "SELECT count(*) AS n FROM shaped", position=2, kind=models.NotebookCell.SQL)

        record = runner.run_sql_cell(after, self.factory.user)

        self.assertEqual(models.NotebookRun.OK, record.state)
        self.assertEqual(2, after.latest_result.data["rows"][0]["n"])

    def test_text_is_shown_but_cannot_be_read_by_a_later_cell(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "print('looked at it')\n42", position=1)
        stand_in = Stand_in(answers=[{"ok": True, "stdout": "looked at it\n", "value": "42", "result_id": None}])

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual(runner.TEXT, code.options["produced"])
        self.assertIn("looked at it", code.latest_result.data["rows"][0]["output"])
        self.assertIn("42", code.latest_result.data["rows"][0]["output"])
        after = self.cell("counted", "SELECT * FROM shaped", position=2, kind=models.NotebookCell.SQL)
        self.assertIn("produced text rather than a table", runner.why_it_cannot_run(after))

    def test_a_cell_that_failed_keeps_what_it_printed_first(self):
        """
        The print before the exception is usually the whole diagnosis.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "print('got this far')\norders.nope", position=1)
        stand_in = Stand_in(
            answers=[
                {
                    "ok": False,
                    "error": "AttributeError: 'DataFrame' object has no attribute 'nope'",
                    "stdout": "got this far\n",
                }
            ]
        )

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual(models.NotebookRun.FAILED, record.state)
        self.assertIn("AttributeError", record.error)
        self.assertIn("got this far", record.error)
        self.assertIsNone(code.last_run_at, "a failed cell was marked as having run")


class TestWhereAResultsPermissionComesFrom(PythonCellTestCase):
    """
    Permission on a stored result is read through its data source, so every
    cell's result has to carry one -- including the cells that have no lineage
    at all.
    """

    def test_a_cell_that_reads_a_cell_carries_that_cells_origin(self):
        source = self.factory.data_source
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "orders.head()", position=1)

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: Stand_in())

        self.assertEqual(source.id, code.latest_result.data_source_id)

    def test_a_cell_that_reads_nothing_falls_back_to_the_one_above_it(self):
        """
        `total = 1 + 1` holds none of the warehouse's data, so attributing it
        there is more restrictive than the truth -- and that is the safe
        direction: null would make `QueryResult.groups` raise, turning a
        permission question into a 500.
        """
        source = self.factory.data_source
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("alone", "total = 1 + 1\ntotal", position=1)

        runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: Stand_in())

        self.assertEqual(source.id, code.latest_result.data_source_id)


class TestWhenTheSessionIsGone(PythonCellTestCase):
    def test_a_reaped_session_is_reopened_rather_than_reported(self):
        """
        The interpreter ends idle sessions, and it is allowed to: every input
        is another cell's output, so a fresh session with the inputs shipped
        again is the same notebook. Only the variables a cell assigned itself
        are lost, which is what re-running the cell does anyway.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "orders.head()", position=1)
        stand_in = Stand_in(fail_first_with=interpreter.Gone("that session is finished"))

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=lambda: stand_in)

        self.assertEqual(models.NotebookRun.OK, record.state)
        self.assertEqual(
            ["session_for", "ship", "detach", "session_for", "ship", "run"],
            [name for name, _ in stand_in.calls],
        )

    def test_a_second_loss_is_reported_rather_than_retried_for_ever(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "orders.head()", position=1)

        class AlwaysGone(Stand_in):
            def ship(self, notebook, session_id, store, names):
                self.calls.append(("ship", tuple(names)))
                raise interpreter.Gone("that session is finished")

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=AlwaysGone)

        self.assertEqual(models.NotebookRun.FAILED, record.state)


class TestWhatAPythonCellCannotDo(PythonCellTestCase):
    def test_without_an_interpreter_the_cell_says_so_before_running(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "orders.head()", position=1)

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", ""):
            problem = runner.why_it_cannot_run(code)
            with self.assertRaises(runner.CannotRun):
                runner.run_python_cell(code, self.factory.user)

        self.assertIn("interpreter", problem)

    def test_a_python_cell_with_nothing_above_it_is_told_it_cannot_query(self):
        code = self.cell("shaped", "orders.head()")

        self.assertIn("cannot query", runner.why_it_cannot_run(code))

    def test_reading_a_cell_that_has_not_run_says_which(self):
        self.cell("orders", "SELECT 1", position=0, kind=models.NotebookCell.SQL, data_source=self.factory.data_source)
        code = self.cell("shaped", "orders.head()", position=1)

        self.assertIn("orders", runner.why_it_cannot_run(code))
        self.assertIn("not run yet", runner.why_it_cannot_run(code))

    def test_an_empty_python_cell_says_so(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("shaped", "   ", position=1)

        self.assertIn("no code", runner.why_it_cannot_run(code))


class TestAgainstTheRealInterpreter(PythonCellTestCase):
    """
    The store on one side, the executor on the other, pandas in the middle.

    Everything above this agrees with whatever SQLDesk wrote, because it is a
    stand-in. This is the only class that can fail on a Parquet file written
    one way and read another.
    """

    def setUp(self):
        super().setUp()
        try:
            import pandas  # noqa: F401
            import service
        except ImportError as e:  # pragma: no cover
            self.skipTest("the interpreter needs pandas and flask: {}".format(e))
        service.TOKEN = ""
        service.MEMORY_MB = 0
        service.app.config["TESTING"] = True
        self.service = service
        self.addCleanup(self.end_every_session)

    def end_every_session(self):
        for session in list(self.service._sessions.values()):
            self.service._sessions.pop(session.id, None)
            session.close()

    def real_interpreter(self):
        """
        A real `Interpreter`, with its one HTTP call routed to the executor's
        own test client instead of the network.

        Everything above `_call` -- the session in Redis, the Parquet export,
        the retry when a session is gone -- is the real code. Only the socket
        is not there.
        """
        client = self.service.app.test_client()

        class Routed(interpreter.Interpreter):
            def _call(inner, method, path, timeout, **kwargs):
                answer = client.open(path, method=method, **_as_werkzeug(kwargs))
                if answer.status_code == 404:
                    raise interpreter.Gone("that session is finished")
                return _LikeRequests(answer)

        return Routed(url="http://executor:5000", token="")

    def test_a_cell_reshapes_its_input_and_the_next_cell_reads_the_result(self):
        self.a_sql_cell_that_ran(
            "orders",
            [{"id": 1, "city": "Toronto"}, {"id": 2, "city": "Toronto"}, {"id": 3, "city": "Ottawa"}],
        )
        code = self.cell("by_city", "orders.groupby('city', as_index=False).size()", position=1)

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=self.real_interpreter)

        self.assertEqual(models.NotebookRun.OK, record.state, record.error)
        self.assertEqual(runner.TABLE, code.options["produced"])
        after = self.cell(
            "biggest",
            "SELECT city FROM by_city ORDER BY size DESC LIMIT 1",
            position=2,
            kind=models.NotebookCell.SQL,
        )
        runner.run_sql_cell(after, self.factory.user)
        self.assertEqual("Toronto", after.latest_result.data["rows"][0]["city"])

    def test_a_timestamp_survives_the_round_trip(self):
        """
        Parquet on both sides, so no string format is agreed anywhere -- and
        DuckDB writes and reads it natively, with no pyarrow in either image.
        """
        self.a_sql_cell_that_ran(
            "events",
            [{"id": 1, "at": "2026-10-30T09:00:00+00:00"}],
            cols=columns(("id", TYPE_INTEGER), ("at", TYPE_DATETIME)),
        )
        code = self.cell("same", "events", position=1)

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=self.real_interpreter)

        self.assertEqual(models.NotebookRun.OK, record.state, record.error)
        store = Store(self.notebook.store_path(), read_only=True)
        try:
            declared = store.connection.execute(
                "SELECT data_type FROM duckdb_columns() WHERE table_name = 'same' AND column_name = 'at'"
            ).fetchone()
        finally:
            store.close()
        self.assertIn("TIMESTAMP", declared[0])

    def test_a_real_error_comes_back_as_the_cells_error(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("broken", "orders.no_such_column_at_all", position=1)

        record = runner.run_python_cell(code, self.factory.user, interpreter_for=self.real_interpreter)

        self.assertEqual(models.NotebookRun.FAILED, record.state)
        self.assertIn("AttributeError", record.error)

    def test_variables_persist_across_two_cells_of_the_same_notebook(self):
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        first = self.cell("kept", "kept_value = len(orders)\nprint(kept_value)", position=1)
        second = self.cell("read_back", "kept_value * 10", position=2)

        runner.run_python_cell(first, self.factory.user, interpreter_for=self.real_interpreter)
        runner.run_python_cell(second, self.factory.user, interpreter_for=self.real_interpreter)

        self.assertIn("10", second.latest_result.data["rows"][0]["output"])

    def test_nothing_in_the_notebooks_directory_is_left_behind(self):
        """
        The directory a cell's SQL is sealed into, so an exported input or a
        fetched result left there is readable by the next cell.
        """
        self.a_sql_cell_that_ran("orders", [{"id": 1, "city": "Toronto"}])
        code = self.cell("by_city", "orders.groupby('city', as_index=False).size()", position=1)

        runner.run_python_cell(code, self.factory.user, interpreter_for=self.real_interpreter)

        left = sorted(os.listdir(self.notebook.directory()))
        self.assertEqual([], [name for name in left if name.endswith(".parquet") or "ship-" in name], left)


def _as_werkzeug(kwargs):
    """`requests` keyword arguments as the test client's."""
    sent = {}
    if "json" in kwargs:
        sent["data"] = json.dumps(kwargs["json"])
        sent["content_type"] = "application/json"
    if "data" in kwargs:
        sent["data"] = kwargs["data"]
    return sent


class _LikeRequests:
    """A werkzeug test response wearing the two attributes `Interpreter` reads."""

    def __init__(self, answer):
        self._answer = answer
        self.status_code = answer.status_code
        self.content = answer.get_data()

    def json(self):
        return self._answer.get_json()

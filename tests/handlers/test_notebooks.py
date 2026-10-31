"""
The notebook API: who may see what, and what the page is told in advance.

Three things are worth a test rather than a glance.

**A draft is the author's own.** The same promise queries and dashboards make,
and the one that is easy to lose when a list query is written in a hurry.

**A cell carries the sentence saying why it cannot run.** Worked out on the
server, because the rules need the install's settings and the other cells'
state -- so if the page had to re-derive them the two would drift.

**A data source's permission is not something a notebook can route around.**
A SQL cell is a query. Whoever may not query that warehouse may not put it in
a cell either.
"""

import shutil
import tempfile
from unittest import mock

from sqldesk import models
from sqldesk.models import db
from sqldesk.notebooks.store import Store
from tests import BaseTestCase


class NotebookApiTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        patch = mock.patch("sqldesk.settings.UPLOAD_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        allowed = mock.patch("sqldesk.features.can", return_value=True)
        allowed.start()
        self.addCleanup(allowed.stop)

    def a_notebook(self, user=None, is_draft=False, name="Quarter"):
        notebook = models.Notebook(org=self.factory.org, user=user or self.factory.user, name=name, is_draft=is_draft)
        db.session.add(notebook)
        db.session.commit()
        return notebook

    def a_cell(
        self,
        notebook,
        name="orders",
        source="SELECT 1",
        position=0,
        kind=models.NotebookCell.SQL,
        data_source=None,
        ran=False,
    ):
        cell = models.NotebookCell(
            notebook=notebook,
            name=name,
            source=source,
            position=position,
            kind=kind,
            data_source=data_source,
        )
        if ran:
            cell.last_run_at = db.func.now()
            cell.options = {"produced": "table"}
        db.session.add(cell)
        db.session.commit()
        return cell


class TestTheList(NotebookApiTestCase):
    def test_a_published_notebook_is_in_the_list(self):
        self.a_notebook()

        answer = self.make_request("get", "/api/notebooks", user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertEqual(1, len(answer.json["results"]))

    def test_somebody_elses_draft_is_not(self):
        other = self.factory.create_user()
        self.a_notebook(user=other, is_draft=True)

        answer = self.make_request("get", "/api/notebooks", user=self.factory.user)

        self.assertEqual([], answer.json["results"], "a draft showed up in somebody else's list")

    def test_your_own_draft_is(self):
        self.a_notebook(is_draft=True)

        answer = self.make_request("get", "/api/notebooks", user=self.factory.user)

        self.assertEqual(1, len(answer.json["results"]))

    def test_an_archived_notebook_is_not(self):
        notebook = self.a_notebook()
        notebook.is_archived = True
        db.session.add(notebook)
        db.session.commit()

        answer = self.make_request("get", "/api/notebooks", user=self.factory.user)

        self.assertEqual([], answer.json["results"])

    def test_creating_one_gives_back_a_draft_with_no_cells(self):
        answer = self.make_request("post", "/api/notebooks", data={"name": "Churn"}, user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertEqual("Churn", answer.json["name"])
        self.assertTrue(answer.json["is_draft"])
        self.assertEqual([], answer.json["cells"])


class TestOpeningOne(NotebookApiTestCase):
    def test_opening_it_attaches_no_interpreter(self):
        """
        Design §4.4. A Spark session takes 30-60 seconds to come up; if opening
        a notebook paid that, none of this would feel like a BI tool.
        """
        notebook = self.a_notebook()
        self.a_cell(notebook, kind=models.NotebookCell.PYTHON, source="1 + 1")

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", "http://executor:5000"):
            with mock.patch("sqldesk.notebooks.interpreter.Interpreter.session_for") as session_for:
                session_for.return_value = None
                answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertEqual({"configured": True, "attached": False}, answer.json["interpreter"])
        session_for.assert_called_once()
        self.assertEqual(False, session_for.call_args.kwargs.get("create"), "opening it created a session")

    def test_without_an_executor_the_page_is_told_there_is_none(self):
        notebook = self.a_notebook()

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", ""):
            answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual({"configured": False, "attached": False}, answer.json["interpreter"])

    def test_each_cell_carries_why_it_cannot_run(self):
        notebook = self.a_notebook()
        self.a_cell(notebook, name="summary", source="SELECT 1", position=0)

        answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        cell = answer.json["cells"][0]
        self.assertIn("no data source", cell["cannot_run"])

    def test_a_runnable_cell_says_nothing_is_wrong(self):
        notebook = self.a_notebook()
        self.a_cell(notebook, source="SELECT 1", data_source=self.factory.data_source)

        answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertIsNone(answer.json["cells"][0]["cannot_run"])

    def test_somebody_elses_draft_is_a_404_not_a_403(self):
        """
        A 403 would confirm it exists, which is the thing a draft is supposed
        not to do.
        """
        other = self.factory.create_user()
        notebook = self.a_notebook(user=other, is_draft=True)

        answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual(404, answer.status_code)

    def test_a_notebook_in_another_org_is_a_404(self):
        other_org = self.factory.create_org()
        other_user = self.factory.create_user(org=other_org)
        notebook = models.Notebook(org=other_org, user=other_user, name="Theirs", is_draft=False)
        db.session.add(notebook)
        db.session.commit()

        answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual(404, answer.status_code)


class TestCells(NotebookApiTestCase):
    def test_a_new_cell_is_named_and_appended(self):
        notebook = self.a_notebook()
        self.a_cell(notebook, name="first", position=0)

        answer = self.make_request(
            "post", "/api/notebooks/{}/cells".format(notebook.id), data={}, user=self.factory.user
        )

        self.assertEqual(200, answer.status_code)
        self.assertEqual("cell_1", answer.json["name"])
        self.assertEqual(1, answer.json["position"], "it was not appended")

    def test_a_python_cell_cannot_be_given_a_data_source(self):
        """
        Decided 2026-10-04 and enforced rather than assumed: a code cell reads
        an earlier cell's output and nothing else.
        """
        notebook = self.a_notebook()

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells".format(notebook.id),
            data={"kind": "python", "data_source_id": self.factory.data_source.id},
            user=self.factory.user,
        )

        self.assertEqual(200, answer.status_code)
        self.assertIsNone(answer.json["data_source_id"])

    def test_a_name_another_cell_has_is_refused_with_the_reason(self):
        notebook = self.a_notebook()
        self.a_cell(notebook, name="orders")

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells".format(notebook.id),
            data={"name": "orders"},
            user=self.factory.user,
        )

        self.assertEqual(400, answer.status_code)
        self.assertIn("already has a cell called orders", answer.json["message"])

    def test_a_name_that_is_not_a_relation_is_refused(self):
        notebook = self.a_notebook()

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells".format(notebook.id),
            data={"name": "1st pass"},
            user=self.factory.user,
        )

        self.assertEqual(400, answer.status_code)

    def test_a_data_source_this_user_cannot_query_is_refused(self):
        """
        A SQL cell is a query. A notebook is not a way round the data source's
        own permission.
        """
        notebook = self.a_notebook()
        source = self.factory.create_data_source(group=self.factory.create_group())

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells".format(notebook.id),
            data={"data_source_id": source.id},
            user=self.factory.user,
        )

        self.assertEqual(403, answer.status_code)

    def test_renaming_a_cell_moves_its_handoff(self):
        from sqldesk.notebooks.store import Store
        from sqldesk.query_runner import TYPE_INTEGER

        notebook = self.a_notebook()
        cell = self.a_cell(notebook, name="orders", data_source=self.factory.data_source, ran=True)
        store = Store(notebook.store_path())
        try:
            store.hand_off("orders", [{"name": "id", "friendly_name": "id", "type": TYPE_INTEGER}], [{"id": 1}])
        finally:
            store.close()

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells/{}".format(notebook.id, cell.id),
            data={"name": "sales"},
            user=self.factory.user,
        )

        self.assertEqual(200, answer.status_code)
        reader = Store(notebook.store_path(), read_only=True)
        try:
            self.assertEqual(["sales"], reader.names(), "the handoff was left under the old name")
        finally:
            reader.close()

    def test_deleting_a_cell_takes_its_handoff_with_it(self):
        from sqldesk.notebooks.store import Store
        from sqldesk.query_runner import TYPE_INTEGER

        notebook = self.a_notebook()
        cell = self.a_cell(notebook, name="orders", data_source=self.factory.data_source, ran=True)
        store = Store(notebook.store_path())
        try:
            store.hand_off("orders", [{"name": "id", "friendly_name": "id", "type": TYPE_INTEGER}], [{"id": 1}])
        finally:
            store.close()

        answer = self.make_request(
            "delete", "/api/notebooks/{}/cells/{}".format(notebook.id, cell.id), user=self.factory.user
        )

        self.assertEqual(200, answer.status_code)
        reader = Store(notebook.store_path(), read_only=True)
        try:
            self.assertEqual([], reader.names())
        finally:
            reader.close()

    def test_a_cell_of_another_notebook_is_a_404(self):
        mine = self.a_notebook(name="Mine")
        theirs = self.a_notebook(name="Theirs")
        cell = self.a_cell(theirs, name="orders")

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells/{}".format(mine.id, cell.id),
            data={"source": "SELECT 2"},
            user=self.factory.user,
        )

        self.assertEqual(404, answer.status_code)


class TestRunning(NotebookApiTestCase):
    def test_running_a_cell_enqueues_a_job(self):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, source="SELECT 1", data_source=self.factory.data_source)

        with mock.patch("sqldesk.handlers.notebooks.run_cell.delay") as delayed:
            delayed.return_value = _AJob()
            answer = self.make_request(
                "post",
                "/api/notebooks/{}/cells/{}/run".format(notebook.id, cell.id),
                data={},
                user=self.factory.user,
            )

        self.assertEqual(200, answer.status_code)
        delayed.assert_called_once_with(cell.id, self.factory.user.id)

    def test_a_cell_that_cannot_run_is_refused_without_queueing_anything(self):
        """
        Told immediately rather than after a round trip through a worker -- and
        with the same sentence the cell was already showing.
        """
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, name="summary", source="SELECT 1")

        with mock.patch("sqldesk.handlers.notebooks.run_cell.delay") as delayed:
            answer = self.make_request(
                "post",
                "/api/notebooks/{}/cells/{}/run".format(notebook.id, cell.id),
                data={},
                user=self.factory.user,
            )

        self.assertEqual(400, answer.status_code)
        self.assertIn("no data source", answer.json["message"])
        delayed.assert_not_called()

    def test_stopping_without_an_interpreter_is_not_an_error(self):
        notebook = self.a_notebook()

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", ""):
            answer = self.make_request(
                "post", "/api/notebooks/{}/stop".format(notebook.id), data={}, user=self.factory.user
            )

        self.assertEqual(200, answer.status_code)
        self.assertFalse(answer.json["stopped"])

    def test_detaching_lets_the_interpreter_go(self):
        notebook = self.a_notebook()

        with mock.patch("sqldesk.settings.NOTEBOOK_EXECUTOR_URL", "http://executor:5000"):
            with mock.patch("sqldesk.notebooks.interpreter.Interpreter.detach") as detach:
                detach.return_value = "session-1"
                answer = self.make_request(
                    "delete", "/api/notebooks/{}/session".format(notebook.id), user=self.factory.user
                )

        self.assertEqual(200, answer.status_code)
        self.assertTrue(answer.json["detached"])


class TestArchiving(NotebookApiTestCase):
    def test_archiving_throws_the_handoff_away_and_keeps_the_notebook(self):
        """
        The handoff is disposable by construction -- re-running re-materialises
        it -- so an archived notebook has no reason to hold a DuckDB file. What
        is on the page is in Postgres and stays.
        """
        from sqldesk.notebooks.store import Store
        from sqldesk.query_runner import TYPE_INTEGER

        notebook = self.a_notebook()
        self.a_cell(notebook, name="orders", data_source=self.factory.data_source, ran=True)
        store = Store(notebook.store_path())
        try:
            store.hand_off("orders", [{"name": "id", "friendly_name": "id", "type": TYPE_INTEGER}], [{"id": 1}])
        finally:
            store.close()
        import os

        self.assertTrue(os.path.exists(notebook.store_path()))

        answer = self.make_request("delete", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual(200, answer.status_code)
        self.assertTrue(answer.json["is_archived"])
        self.assertFalse(os.path.exists(notebook.store_path()), "the store outlived the notebook")
        self.assertEqual(1, models.NotebookCell.query.filter_by(notebook_id=notebook.id).count())

    def test_somebody_who_cannot_edit_it_cannot_archive_it(self):
        other = self.factory.create_user()
        notebook = self.a_notebook(user=other)

        answer = self.make_request("delete", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertEqual(403, answer.status_code)


class _AJob:
    """Just enough of an RQ job for `serialize_job`."""

    id = "a-job-id"
    is_started = False
    is_cancelled = False
    result = None
    meta = {}

    def get_status(self):
        from rq.job import JobStatus

        return JobStatus.QUEUED

    def save_meta(self):
        return None


class TestWhatTheResultEndpointSays(NotebookApiTestCase):
    """
    The per-cell result, which the page fetches once per cell rather than
    inlined into the notebook.

    Two of its fields are not in the stored result and are read from the run
    record instead: how many rows were handed on (so the page can say "first
    1,000 of 4.2 million" rather than implying a thousand was all of it), and
    what the cell printed on its way there.
    """

    def a_cell_with_a_result(self, rows=None, handed_on=None, printed=None, state=None):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, kind=models.NotebookCell.PYTHON, source="orders.head(1)", ran=True)
        # A real data source, not None: `query_results.data_source_id` is NOT
        # NULL, which is why a cell's result records the warehouse its chain
        # started at even when the cell itself is Python.
        cell.latest_result = models.QueryResult.store_result(
            self.factory.org.id,
            self.factory.data_source,
            "hash",
            "orders.head(1)",
            {"columns": [{"name": "id"}], "rows": rows if rows is not None else [{"id": 1}]},
            0.1,
            db.func.now(),
        )
        db.session.add(
            models.NotebookRun(
                notebook=notebook,
                cell=cell,
                user=self.factory.user,
                state=state or models.NotebookRun.OK,
                rows=handed_on,
                printed=printed,
            )
        )
        db.session.add(cell)
        db.session.commit()
        return notebook, cell

    def fetch(self, notebook, cell, user=None):
        return self.make_request(
            "get",
            "/api/notebooks/{}/cells/{}/result".format(notebook.id, cell.id),
            user=user or self.factory.user,
        )

    def test_it_carries_what_the_cell_printed(self):
        notebook, cell = self.a_cell_with_a_result(printed="rows: 42")

        answer = self.fetch(notebook, cell)

        self.assertEqual(200, answer.status_code)
        self.assertEqual("rows: 42", answer.json["printed"])

    def test_it_carries_the_number_of_rows_handed_on(self):
        notebook, cell = self.a_cell_with_a_result(handed_on=4200000)

        answer = self.fetch(notebook, cell)

        self.assertEqual(4200000, answer.json["handed_on"])

    def test_both_are_null_when_there_is_no_successful_run_to_read_them_from(self):
        notebook, cell = self.a_cell_with_a_result(printed="never got here", state=models.NotebookRun.FAILED)

        answer = self.fetch(notebook, cell)

        self.assertIsNone(answer.json["printed"])
        self.assertIsNone(answer.json["handed_on"])

    def test_the_rows_themselves_are_still_there(self):
        notebook, cell = self.a_cell_with_a_result(rows=[{"id": 7}])

        answer = self.fetch(notebook, cell)

        self.assertEqual([{"id": 7}], answer.json["data"]["rows"])

    def test_a_cell_that_has_produced_nothing_is_a_404_rather_than_an_empty_result(self):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, kind=models.NotebookCell.PYTHON)

        answer = self.fetch(notebook, cell)

        self.assertEqual(404, answer.status_code)


class TestACellsTitle(NotebookApiTestCase):
    """
    What a person calls a step, as against the name other cells are written
    against.

    The two are separate on purpose: renaming `name` breaks every cell that
    refers to it, where a title is prose and breaks nothing. The contents list
    needs the second one -- `cell_1 … cell_30` is a list nobody reads.
    """

    def set_title(self, cell, title):
        return self.make_request(
            "post",
            "/api/notebooks/{}/cells/{}".format(cell.notebook_id, cell.id),
            data={"title": title},
            user=self.factory.user,
        )

    def test_a_cell_starts_without_one(self):
        notebook = self.a_notebook()
        self.a_cell(notebook)

        answer = self.make_request("get", "/api/notebooks/{}".format(notebook.id), user=self.factory.user)

        self.assertIsNone(answer.json["cells"][0]["title"])

    def test_it_can_be_given_one(self):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook)

        answer = self.set_title(cell, "Orders, cleaned")

        self.assertEqual(200, answer.status_code)
        self.assertEqual("Orders, cleaned", answer.json["title"])

    def test_clearing_it_leaves_no_title_rather_than_an_empty_one(self):
        """
        The page falls back to the name when there is no title, and "" is not
        no title -- it is a title that draws as a blank line in the contents.
        """
        notebook = self.a_notebook()
        cell = self.a_cell(notebook)
        self.set_title(cell, "Orders, cleaned")

        answer = self.set_title(cell, "   ")

        self.assertIsNone(answer.json["title"])

    def test_it_does_not_touch_the_name_other_cells_are_written_against(self):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, name="orders")

        self.set_title(cell, "Orders, cleaned")

        self.assertEqual("orders", models.NotebookCell.query.get(cell.id).name)

    def test_two_cells_may_share_a_title_though_not_a_name(self):
        """A title is prose; nothing resolves a reference through it."""
        notebook = self.a_notebook()
        first = self.a_cell(notebook, name="orders", position=0)
        second = self.a_cell(notebook, name="refunds", position=1)

        self.set_title(first, "Takings")
        answer = self.set_title(second, "Takings")

        self.assertEqual(200, answer.status_code)
        self.assertEqual("Takings", answer.json["title"])

    def test_a_new_cell_may_be_created_with_one(self):
        notebook = self.a_notebook()

        answer = self.make_request(
            "post",
            "/api/notebooks/{}/cells".format(notebook.id),
            data={"kind": "sql", "title": "Orders, cleaned"},
            user=self.factory.user,
        )

        self.assertEqual("Orders, cleaned", answer.json["title"])


class TestRunningTheWholeNotebook(NotebookApiTestCase):
    """
    Run all, as one job on a worker.

    Not a loop in the browser: a chain run from the page stops the moment
    somebody closes the tab, halfway through, leaving a notebook whose first
    four cells are new and whose last six are old — which looks exactly like a
    notebook that ran.
    """

    def run_all(self, notebook, user=None):
        return self.make_request(
            "post", "/api/notebooks/{}/run".format(notebook.id), data={}, user=user or self.factory.user
        )

    def test_it_enqueues_one_job_for_the_notebook(self):
        notebook = self.a_notebook()
        self.a_cell(notebook, source="SELECT 1", data_source=self.factory.data_source)
        self.a_cell(notebook, name="summary", source="SELECT 1 FROM orders", position=1)

        with mock.patch("sqldesk.handlers.notebooks.run_notebook.delay") as delayed:
            delayed.return_value = _AJob()
            answer = self.run_all(notebook)

        self.assertEqual(200, answer.status_code)
        delayed.assert_called_once_with(notebook.id, self.factory.user.id)

    def test_an_empty_notebook_is_refused_rather_than_queued(self):
        notebook = self.a_notebook()

        with mock.patch("sqldesk.handlers.notebooks.run_notebook.delay") as delayed:
            answer = self.run_all(notebook)

        self.assertEqual(400, answer.status_code)
        delayed.assert_not_called()

    def test_a_first_cell_that_cannot_run_stops_it_before_the_queue(self):
        """
        The common mistake — a first cell with no data source and nothing above
        it to read — is a sentence, not a job that fails a second later.
        """
        notebook = self.a_notebook()
        self.a_cell(notebook, name="summary", source="SELECT 1")

        with mock.patch("sqldesk.handlers.notebooks.run_notebook.delay") as delayed:
            answer = self.run_all(notebook)

        self.assertEqual(400, answer.status_code)
        self.assertIn("nothing below it", answer.json["message"])
        delayed.assert_not_called()

    def test_a_later_cell_waiting_on_the_one_above_does_not_stop_it(self):
        """
        A later cell that cannot run *yet* is usually one waiting for the cell
        above it. Refusing the whole notebook for that would make Run all
        unusable on exactly the notebooks it exists for.
        """
        notebook = self.a_notebook()
        self.a_cell(notebook, name="orders", source="SELECT 1", data_source=self.factory.data_source)
        self.a_cell(notebook, name="summary", source="SELECT count(*) FROM orders", position=1)

        with mock.patch("sqldesk.handlers.notebooks.run_notebook.delay") as delayed:
            delayed.return_value = _AJob()
            answer = self.run_all(notebook)

        self.assertEqual(200, answer.status_code)
        delayed.assert_called_once()

    def test_somebody_who_may_not_edit_it_is_refused(self):
        notebook = self.a_notebook(user=self.factory.create_user())
        self.a_cell(notebook, source="SELECT 1", data_source=self.factory.data_source)

        with mock.patch("sqldesk.handlers.notebooks.run_notebook.delay") as delayed:
            answer = self.run_all(notebook)

        self.assertIn(answer.status_code, (403, 404))
        delayed.assert_not_called()


class TestDownloadingACellsOutput(NotebookApiTestCase):
    """
    A result taken out of here, for somebody moving data rather than looking
    at it.

    The claim worth testing: it is the **whole** handoff, not the truncated
    slice `query_results` holds for the page. A download that quietly handed
    over a thousand rows of four million would be wrong in the way that is
    hardest to notice — it would look right.
    """

    def a_cell_that_ran(self, rows, produced="table"):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook, name="orders", data_source=self.factory.data_source, ran=True)
        cell.options = {"produced": produced}
        db.session.add(cell)
        db.session.commit()
        store = Store(notebook.store_path())
        try:
            store.hand_off("orders", [{"name": "id", "friendly_name": "id", "type": "integer"}], rows)
        finally:
            store.close()
        return notebook, cell

    def download(self, notebook, cell, user=None):
        return self.make_request(
            "get",
            "/api/notebooks/{}/cells/{}/download".format(notebook.id, cell.id),
            user=user or self.factory.user,
        )

    def test_it_hands_over_csv(self):
        notebook, cell = self.a_cell_that_ran([{"id": 1}, {"id": 2}])

        answer = self.download(notebook, cell)

        self.assertEqual(200, answer.status_code)
        self.assertIn("text/csv", answer.headers["Content-Type"])
        self.assertIn("id", answer.data.decode())

    def test_it_is_the_whole_handoff_and_not_the_slice_on_the_page(self):
        """
        The slice is a thousand rows. This writes from the store, so a result
        larger than the slice comes out whole.
        """
        notebook, cell = self.a_cell_that_ran([{"id": n} for n in range(2500)])

        answer = self.download(notebook, cell)

        lines = [one for one in answer.data.decode().splitlines() if one.strip()]
        self.assertEqual(2501, len(lines), "the header and 2,500 rows")

    def test_it_is_named_after_the_title_somebody_gave_it(self):
        notebook, cell = self.a_cell_that_ran([{"id": 1}])
        cell.title = "Orders, cleaned"
        db.session.add(cell)
        db.session.commit()

        answer = self.download(notebook, cell)

        self.assertIn("Orders, cleaned.csv", answer.headers["Content-Disposition"])

    def test_a_title_that_would_not_make_a_filename_is_made_into_one(self):
        notebook, cell = self.a_cell_that_ran([{"id": 1}])
        cell.title = "Orders / 2026: q1?"
        db.session.add(cell)
        db.session.commit()

        answer = self.download(notebook, cell)

        disposition = answer.headers["Content-Disposition"]
        self.assertNotIn("/", disposition.split("filename=")[1])
        self.assertNotIn("?", disposition)

    def test_a_cell_that_printed_has_nothing_to_download(self):
        """There is no relation — a one-column file of printed text would be
        a worse answer than saying so."""
        notebook, cell = self.a_cell_that_ran([{"id": 1}], produced="text")

        answer = self.download(notebook, cell)

        self.assertEqual(400, answer.status_code)

    def test_a_cell_that_has_not_run_says_so(self):
        notebook = self.a_notebook()
        cell = self.a_cell(notebook)

        answer = self.download(notebook, cell)

        self.assertEqual(404, answer.status_code)


class TestHowBigTheListSaysEachNotebookIs(NotebookApiTestCase):
    """
    Counts beside each name, so the list says something before anybody opens
    anything.

    Counted with one grouped query over the page rather than two per
    notebook -- a list of twenty-five would otherwise be fifty round trips to
    put a number beside a name.
    """

    def listed(self):
        answer = self.make_request("get", "/api/notebooks", user=self.factory.user)
        return {one["name"]: one for one in answer.json["results"]}

    def test_it_counts_the_cells(self):
        notebook = self.a_notebook(name="Quarter")
        self.a_cell(notebook, name="a", position=0)
        self.a_cell(notebook, name="b", position=1)

        self.assertEqual(2, self.listed()["Quarter"]["cell_count"])

    def test_it_counts_a_warehouse_once_however_many_cells_hit_it(self):
        """
        Eight cells against one warehouse is one source. "8 data sources"
        would make a notebook look like it reaches further than it does.
        """
        notebook = self.a_notebook(name="Quarter")
        source = self.factory.data_source
        self.a_cell(notebook, name="a", position=0, data_source=source)
        self.a_cell(notebook, name="b", position=1, data_source=source)

        listed = self.listed()["Quarter"]
        self.assertEqual(2, listed["cell_count"])
        self.assertEqual(1, listed["data_source_count"])

    def test_a_cell_reading_earlier_cells_counts_as_no_data_source(self):
        notebook = self.a_notebook(name="Quarter")
        self.a_cell(notebook, name="a", position=0, data_source=self.factory.data_source)
        self.a_cell(notebook, name="b", position=1)

        self.assertEqual(1, self.listed()["Quarter"]["data_source_count"])

    def test_an_empty_notebook_says_zero_rather_than_nothing(self):
        self.a_notebook(name="Empty")

        listed = self.listed()["Empty"]
        self.assertEqual(0, listed["cell_count"])
        self.assertEqual(0, listed["data_source_count"])

    def test_each_notebook_is_counted_against_itself(self):
        small = self.a_notebook(name="Small")
        big = self.a_notebook(name="Big")
        self.a_cell(small, name="a", position=0)
        for n in range(3):
            self.a_cell(big, name="b{}".format(n), position=n)

        listed = self.listed()
        self.assertEqual(1, listed["Small"]["cell_count"])
        self.assertEqual(3, listed["Big"]["cell_count"])

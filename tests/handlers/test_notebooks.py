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

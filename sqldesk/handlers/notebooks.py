"""
A notebook's API: the chain, the cells, and what each one is allowed to do.

Three things here are deliberately not what a first draft would do.

**Opening a notebook attaches no interpreter** (design §4.4). `GET` reports
whether one is attached and never creates one. A Spark session takes 30-60
seconds to come up; if opening a notebook paid that, nothing about this would
feel like a BI tool.

**Every cell carries the sentence saying why it cannot run**, worked out here
rather than guessed at in the browser. The rules are "no interpreter
configured", "a data source and a cell reference at once", "the cell you read
has not run", "the cell you read produced text" -- and each of those needs the
notebook, the install's settings and the other cells' state. Sending the
sentence means the page never has to re-derive any of it, and the limits
cannot drift between the two.

**Staleness is reported, never corrected.** If A feeds B and A has re-run,
B is marked stale and left exactly as it was. Re-running it is somebody's
decision: the number on the screen is still the number that was computed, and
replacing it silently is how a notebook lies.
"""

import logging

from flask import request
from flask_restful import abort

from sqldesk import features, models, notebooks
from sqldesk.handlers.base import BaseResource, get_object_or_404, paginate
from sqldesk.notebooks import interpreter
from sqldesk.notebooks import run as cell_runner
from sqldesk.notebooks.store import Store
from sqldesk.permissions import (
    can_modify,
    require_access,
    require_feature,
    require_object_modify_permission,
    view_only,
)
from sqldesk.serializers import serialize_job
from sqldesk.tasks.notebooks import run_cell

logger = logging.getLogger(__name__)


def serialize_notebook(notebook, with_cells=False, user=None):
    one = {
        "id": notebook.id,
        "name": notebook.name,
        "description": notebook.description,
        "user": {"id": notebook.user_id, "name": notebook.user.name} if notebook.user else None,
        "is_archived": notebook.is_archived,
        "is_draft": notebook.is_draft,
        "created_at": notebook.created_at,
        "updated_at": notebook.updated_at,
        "can_edit": can_modify(notebook, user) if user else False,
        "options": notebook.options or {},
    }
    if with_cells:
        cells = notebook.cells
        runs = _inputs_by_cell(notebook)
        stale = notebooks.staleness(cells, runs)
        missing = notebooks.missing_inputs(cells, runs)
        one["cells"] = [serialize_cell(cell, cells, stale, missing) for cell in cells]
        one["interpreter"] = _interpreter_state(notebook)
    return one


def serialize_cell(cell, cells=None, stale=None, missing=None):
    cells = cells if cells is not None else cell.notebook.cells
    stopped = cell_runner.what_stops_it(cell, cells)
    one = {
        "id": cell.id,
        "notebook_id": cell.notebook_id,
        "name": cell.name,
        "kind": cell.kind,
        "source": cell.source,
        "position": cell.position,
        "data_source_id": cell.data_source_id,
        "latest_result_id": cell.latest_result_id,
        "last_run_at": cell.last_run_at,
        "options": cell.options or {},
        # The sentence the page shows instead of letting somebody press Run
        # and find out -- and the name of the reason beside it, so the page can
        # reason about it without parsing English. It needs that for one case:
        # this describes the cell as *saved*, and somebody who has just typed
        # into an empty cell should not be told it is empty.
        "cannot_run": stopped[1] if stopped else None,
        "cannot_run_code": stopped[0] if stopped else None,
        "reads": cell_runner.reads(cell, cells),
    }
    if stale:
        one["stale_because_of"] = stale.get(cell.id) or []
    if missing:
        one["missing_inputs"] = missing.get(cell.id) or []
    return one


def _inputs_by_cell(notebook):
    """
    What each cell read when it last ran -- which is what staleness is about.

    What it *read then*, not what it refers to now: the number on the screen
    came from the earlier run, so the earlier run's inputs are the ones that
    decide whether it is still true.
    """
    latest = {}
    runs = (
        models.NotebookRun.query.filter(
            models.NotebookRun.notebook_id == notebook.id,
            models.NotebookRun.state == models.NotebookRun.OK,
        )
        .order_by(models.NotebookRun.id.asc())
        .all()
    )
    for record in runs:
        latest[record.cell_id] = list(record.inputs or [])
    return latest


def _interpreter_state(notebook):
    """
    Whether Python cells can run here, and whether one is attached.

    Asked without attaching anything, which is the whole point of §4.4.
    """
    if not interpreter.configured():
        return {"configured": False, "attached": False}
    try:
        return {"configured": True, "attached": interpreter.Interpreter().attached(notebook)}
    except interpreter.NoInterpreter:
        return {"configured": True, "attached": False}


def _notebook(notebook_id, org, user, modifying=False):
    """
    One notebook, if this user may see it -- or change it.

    Not `require_access`: that reads an object's `groups`, which a data source
    and a query have and a notebook does not. A notebook's own visibility is
    the simpler rule queries and dashboards use for drafts -- yours until you
    publish it -- and the data source permission that actually matters is
    checked per cell, where the warehouse is.
    """
    notebook = get_object_or_404(models.Notebook.get_by_id_and_org, notebook_id, org)
    if modifying:
        require_object_modify_permission(notebook, user)
    elif notebook.is_draft and not (user.has_permission("admin") or notebook.user_id == user.id):
        abort(404, message="No such notebook.")
    return notebook


def _cell(notebook, cell_id):
    for cell in notebook.cells:
        if str(cell.id) == str(cell_id):
            return cell
    abort(404, message="No such cell in this notebook.")


def _named(notebook, name, cell=None):
    """A cell name, or a 400 saying what is wrong with it."""
    taken = [one.name for one in notebook.cells if one is not cell]
    problem = notebooks.name_problem(name, taken=taken)
    if problem:
        abort(400, message=problem)
    return name.strip()


class NotebookListResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def get(self):
        """
        The notebooks this user may see, newest first.

        Drafts are the author's own, the same promise queries and dashboards
        make: what you are still building is not in anybody else's list.
        """
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)
        query = models.Notebook.query.filter(
            models.Notebook.org == self.current_org,
            models.Notebook.is_archived.is_(False),
        )
        if not self.current_user.has_permission("admin"):
            query = query.filter(
                models.db.or_(
                    models.Notebook.is_draft.is_(False),
                    models.Notebook.user_id == self.current_user.id,
                )
            )
        query = query.order_by(models.Notebook.updated_at.desc())
        return paginate(query, page, page_size, lambda one: serialize_notebook(one, user=self.current_user))

    @require_feature(features.USE_NOTEBOOKS)
    def post(self):
        body = request.get_json(force=True, silent=True) or {}
        notebook = models.Notebook(
            org=self.current_org,
            user=self.current_user,
            name=(body.get("name") or "New Notebook").strip()[:255],
            description=body.get("description"),
            is_draft=True,
        )
        models.db.session.add(notebook)
        models.db.session.commit()
        self.record_event({"action": "create", "object_id": notebook.id, "object_type": "notebook"})
        return serialize_notebook(notebook, with_cells=True, user=self.current_user)


class NotebookResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def get(self, notebook_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user)
        self.record_event({"action": "view", "object_id": notebook_id, "object_type": "notebook"})
        return serialize_notebook(notebook, with_cells=True, user=self.current_user)

    @require_feature(features.USE_NOTEBOOKS)
    def post(self, notebook_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        body = request.get_json(force=True, silent=True) or {}
        for field in ("name", "description", "is_draft", "options"):
            if field in body:
                setattr(notebook, field, body[field])
        models.db.session.add(notebook)
        models.db.session.commit()
        return serialize_notebook(notebook, with_cells=True, user=self.current_user)

    @require_feature(features.USE_NOTEBOOKS)
    def delete(self, notebook_id):
        """
        Archive it, and throw its handoff away.

        The handoff is disposable by construction -- re-running re-materialises
        it -- so an archived notebook has no reason to hold a DuckDB file. The
        cells, the runs and the displayed results stay, so it still reads.
        """
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        notebook.is_archived = True
        models.db.session.add(notebook)
        models.db.session.commit()
        _discard_everything(notebook)
        self.record_event({"action": "archive", "object_id": notebook_id, "object_type": "notebook"})
        return serialize_notebook(notebook, user=self.current_user)


def _discard_everything(notebook):
    """The store and the session, neither of which outlives the notebook."""
    Store(notebook.store_path()).discard()
    if interpreter.configured():
        try:
            interpreter.Interpreter().detach(notebook)
        except interpreter.NoInterpreter:
            pass


class CellListResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def post(self, notebook_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        body = request.get_json(force=True, silent=True) or {}
        kind = body.get("kind") or models.NotebookCell.SQL
        if kind not in (models.NotebookCell.SQL, models.NotebookCell.PYTHON):
            abort(400, message="A cell is SQL or Python.")

        cell = models.NotebookCell(
            notebook=notebook,
            name=_named(notebook, body.get("name") or _next_name(notebook, kind)),
            kind=kind,
            source=body.get("source") or "",
            # Appended by default. A position given explicitly is the page
            # saying where it was inserted.
            position=body.get("position", _next_position(notebook)),
            data_source_id=body.get("data_source_id") if kind == models.NotebookCell.SQL else None,
        )
        _may_use(cell, self.current_user)
        models.db.session.add(cell)
        models.db.session.commit()
        return serialize_cell(cell)


def _next_name(notebook, kind):
    """
    A name nobody has used, for a cell somebody has not named yet.

    Numbered for convenience only -- the number is part of a name and never an
    identity, so inserting a cell above `cell_2` leaves every reference to it
    pointing at the same cell.
    """
    taken = {one.name for one in notebook.cells}
    stem = "cell" if kind == models.NotebookCell.SQL else "code"
    nth = 1
    while "{}_{}".format(stem, nth) in taken:
        nth += 1
    return "{}_{}".format(stem, nth)


def _next_position(notebook):
    return max([one.position or 0 for one in notebook.cells] or [-1]) + 1


def _may_use(cell, user):
    """
    The data source's own permission, not a new one.

    A SQL cell is a query, and who may query a data source is already decided
    -- so a notebook cannot be the way round it.
    """
    if cell.data_source_id:
        source = get_object_or_404(models.DataSource.get_by_id_and_org, cell.data_source_id, cell.notebook.org)
        require_access(source, user, view_only)


class CellResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def post(self, notebook_id, cell_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        cell = _cell(notebook, cell_id)
        body = request.get_json(force=True, silent=True) or {}

        if "name" in body and body["name"] != cell.name:
            renamed = _named(notebook, body["name"], cell=cell)
            _rename_in_the_store(notebook, cell.name, renamed)
            cell.name = renamed
        for field in ("source", "position", "options"):
            if field in body:
                setattr(cell, field, body[field])
        if "data_source_id" in body:
            cell.data_source_id = body["data_source_id"] if cell.kind == models.NotebookCell.SQL else None
            _may_use(cell, self.current_user)
        models.db.session.add(cell)
        models.db.session.commit()
        return serialize_cell(cell)

    @require_feature(features.USE_NOTEBOOKS)
    def delete(self, notebook_id, cell_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        cell = _cell(notebook, cell_id)
        name = cell.name
        models.db.session.delete(cell)
        models.db.session.commit()
        # Its handoff goes with it. A later cell referring to the name now
        # reports a missing input, which is a different thing from stale and
        # says so.
        store = Store(notebook.store_path())
        try:
            store.drop(name)
        except Exception:
            logger.warning("notebook %s: %s had no handoff to drop", notebook.id, name)
        finally:
            store.close()
        return {"id": cell.id}


def _rename_in_the_store(notebook, old, new):
    """Follow the rename, so the handoff is not orphaned under the old name."""
    store = Store(notebook.store_path())
    try:
        store.rename(old, new)
    except Exception:
        logger.warning("notebook %s: could not rename %s to %s in the store", notebook.id, old, new)
    finally:
        store.close()


class CellResultResource(BaseResource):
    """
    What a cell produced, for the page to draw.

    Fetched per cell rather than inlined into the notebook: the slice is capped
    at a thousand rows, and a notebook of twenty cells would otherwise be
    megabytes of JSON before anybody had looked at anything. One small request
    per cell, in parallel, is what makes reopening feel instant.

    The data source's permission is checked here, not the notebook's. A reader
    who may open a published notebook may still be someone who was never
    allowed that warehouse, and a stored result is that warehouse's data.
    """

    @require_feature(features.USE_NOTEBOOKS)
    def get(self, notebook_id, cell_id):
        notebook = _notebook(notebook_id, self.current_org, self.current_user)
        cell = _cell(notebook, cell_id)
        if not cell.latest_result_id:
            abort(404, message="This cell has not produced anything yet.")
        result = get_object_or_404(models.QueryResult.get_by_id_and_org, cell.latest_result_id, self.current_org)
        if result.data_source is not None:
            require_access(result.data_source, self.current_user, view_only)
        handed_on = _latest_good_run(cell)
        return {
            "id": result.id,
            "data": result.data,
            "row_count": result.row_count,
            "runtime": result.runtime,
            "retrieved_at": result.retrieved_at,
            # What the cell handed on, which is the number the slice is a
            # slice *of* -- so the page can say "first 1,000 of 4.2 million"
            # rather than implying a thousand was the whole answer.
            "handed_on": handed_on.rows if handed_on else None,
            # What the cell printed on its way to this result, so a cell can
            # show its workings and its table at once.
            "printed": handed_on.printed if handed_on else None,
        }


def _latest_good_run(cell):
    return (
        models.NotebookRun.query.filter(
            models.NotebookRun.cell_id == cell.id,
            models.NotebookRun.state == models.NotebookRun.OK,
        )
        .order_by(models.NotebookRun.id.desc())
        .first()
    )


class CellRunResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def post(self, notebook_id, cell_id):
        """
        Enqueue the cell and hand back a job, as running a query does.

        The refusal is checked here as well as in the job, so somebody pressing
        Run on a cell that cannot run is told immediately rather than after a
        round trip through a worker.
        """
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        cell = _cell(notebook, cell_id)
        problem = cell_runner.why_it_cannot_run(cell, notebook.cells)
        if problem:
            abort(400, message=problem)
        _may_use(cell, self.current_user)

        job = run_cell.delay(cell.id, self.current_user.id)
        job.meta["org_id"] = self.current_org.id
        job.meta["user_id"] = self.current_user.id
        job.save_meta()
        return serialize_job(job)


class NotebookStopResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def post(self, notebook_id):
        """
        Cancel the cell that is running. The session and its variables stay
        (design §4.6).
        """
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        if not interpreter.configured():
            return {"stopped": False}
        try:
            return {"stopped": interpreter.Interpreter().stop(notebook)}
        except interpreter.NoInterpreter as e:
            abort(503, message=str(e))


class NotebookSessionResource(BaseResource):
    @require_feature(features.USE_NOTEBOOKS)
    def delete(self, notebook_id):
        """
        Let the interpreter go. Variables go with it; the handoffs do not, so
        the notebook still reads and re-runs.
        """
        notebook = _notebook(notebook_id, self.current_org, self.current_user, modifying=True)
        if not interpreter.configured():
            return {"detached": False}
        try:
            return {"detached": bool(interpreter.Interpreter().detach(notebook))}
        except interpreter.NoInterpreter as e:
            abort(503, message=str(e))

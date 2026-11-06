"""
Running a cell on a worker, rather than in the request that asked for it.

A cell is as slow as somebody's query or somebody's Python, which is the same
reason a query does not run in its own request: a handful of people pressing
Run would hold every gunicorn thread the server has, and the page would stop
answering for everybody else.

So this is the same shape as a query. The handler enqueues, gets a job id
back, and the page polls -- which means the job serializer, the polling and
the cancel the client already has all work here unchanged.

**A SQL cell takes a pool slot like any other query.** It is a query against a
warehouse; the fact that it was typed into a notebook does not make the
warehouse's connection limit any larger. A Python cell takes none: it runs on
the interpreter and touches no data source at all.
"""

import logging

from sqldesk import models, pools
from sqldesk.notebooks import run
from sqldesk.utils import utcnow
from sqldesk.worker import job

logger = logging.getLogger(__name__)

#: Longer than a query's, because a cell may be a Python cell and the
#: interpreter's own deadline is minutes. Shorter than forever, because a
#: worker holding a job nobody is waiting for is a worker nobody else can use.
TIMEOUT = 900


#: A whole notebook is every cell's deadline end to end, so it cannot be the
#: single-cell one. Still finite: a worker holding a job nobody is waiting for
#: is a worker nobody else can use.
WHOLE_NOTEBOOK_TIMEOUT = 3600


@job("queries", timeout=TIMEOUT, ttl=TIMEOUT)
def run_cell(cell_id, user_id):
    """
    Run one cell and leave its result where the page will find it.

    Returns what the job serializer needs: the id of the result to show, or
    `{"error": ...}` to show instead -- the two shapes `serialize_job` reads.
    Raising would make every refusal look like a crash in the logs, and "this
    cell cannot run yet" is not a crash.
    """
    cell = models.NotebookCell.query.get(cell_id)
    if cell is None:
        return {"error": "That cell has been deleted."}
    user = models.User.query.get(user_id)

    record, refusal = _guarded(cell, user, user_id)
    if refusal:
        return {"error": refusal}

    models.db.session.commit()
    if record.state == models.NotebookRun.FAILED:
        return {"error": record.error}
    # The id itself, not a dict around it: `serialize_job` puts whatever a job
    # returns into `query_result_id`, so anything richer would hand the page a
    # dict where it reads an id. What else the page needs -- staleness, what a
    # cell now reads -- it gets by refetching the notebook, which it has to do
    # anyway because a run changes the cells below this one.
    return cell.latest_result_id


def _guarded(cell, user, user_id):
    """
    Run one cell inside its data source's pool slot.

    Answers `(record, None)` or `(None, sentence)`. Shared by the single-cell
    job and the whole-notebook one so a cell run as part of a chain takes a
    slot on exactly the same terms as one somebody pressed Run on -- the
    warehouse's connection limit does not get larger because a notebook is
    running itself.
    """
    slot = None
    try:
        if cell.reaches_a_data_source and cell.data_source:
            pool = pools.pool_for(cell.data_source)
            slot = "notebook-cell-{}".format(cell.id)
            # `acquire` answers None on success and a sentence on refusal --
            # a sentence because somebody reads it, and a better one than
            # anything invented here.
            refusal = pools.acquire(pool, slot, owner=user_id, limit=pools.budget(pool, cell.data_source))
            if refusal:
                slot = None
                return None, refusal
        return _run(cell, user), None
    except run.CannotRun as e:
        # The sentence the page was already showing. Not a failure of ours.
        return None, str(e)
    except Exception as e:
        logger.exception("notebook cell %s could not be run", cell.id)
        models.db.session.rollback()
        return None, str(e)
    finally:
        if slot:
            pools.release(pools.pool_for(cell.data_source), slot)


@job("queries", timeout=WHOLE_NOTEBOOK_TIMEOUT, ttl=WHOLE_NOTEBOOK_TIMEOUT)
def run_notebook(notebook_id, user_id):
    """
    Run every cell, in order, and stop at the first one that fails.

    **Stopping is the point.** A notebook is a chain: if cell two failed, cell
    three reads what cell two did not produce, and running it would either
    refuse or -- worse -- succeed against cell two's *previous* output and put
    a number on the screen computed from data that no longer matches the cell
    above it. One failure, reported against the cell that caused it, is the
    honest answer.

    Committed per cell rather than at the end, so a chain that stops at cell
    seven leaves the first six on the page as results somebody can look at.
    """
    notebook = models.Notebook.query.get(notebook_id)
    if notebook is None:
        return {"error": "That notebook has been deleted."}
    user = models.User.query.get(user_id)

    ran = 0
    for cell in sorted(notebook.cells, key=lambda one: one.position):
        record, refusal = _guarded(cell, user, user_id)
        if refusal:
            models.db.session.commit()
            _record_outcome(notebook, failed=True)
            return {"error": "{} stopped the run: {}".format(cell.name, refusal), "ran": ran}
        models.db.session.commit()
        if record.state == models.NotebookRun.FAILED:
            _record_outcome(notebook, failed=True)
            return {"error": "{} failed: {}".format(cell.name, record.error), "ran": ran}
        ran += 1

    _record_outcome(notebook, failed=False)
    # A dict, not an id: there is no single result to show -- the page
    # refetches the notebook, which it must do anyway because every cell has
    # changed.
    return {"ran": ran}


def _record_outcome(notebook, failed):
    """
    Whether the last run worked, so a schedule can back off.

    Counted on the notebook whether the run was scheduled or somebody pressed
    Run all: a notebook that fails by hand will fail on its schedule too, and
    there is no reason to wait for the scheduler to find that out.
    """
    notebook.schedule_failures = (notebook.schedule_failures or 0) + 1 if failed else 0
    models.db.session.add(notebook)
    models.db.session.commit()


def _run(cell, user):
    if cell.kind == models.NotebookCell.PYTHON:
        return run.run_python_cell(cell, user)
    return run.run_sql_cell(cell, user)


@job("periodic", timeout=300, ttl=300)
def run_due_notebooks():
    """
    Start the notebooks whose cron slot has come round.

    Enqueues rather than runs: each notebook is its own job on the queries
    queue, so one slow notebook does not hold up every other notebook's
    schedule, and a run that outlives this check is fine.

    `last_scheduled_at` is stamped here, at enqueue, not when the run
    finishes. Otherwise a notebook taking longer than its interval would be
    enqueued again on the next check, and again, until the queue was nothing
    but that notebook.
    """
    started = []
    for notebook in models.Notebook.due():
        if notebook.user is None:
            # Nobody to run it as. A scheduled run uses its owner's access,
            # and there is no sensible stand-in for a deleted account.
            logger.warning("notebook %s has a schedule and no owner", notebook.id)
            continue
        try:
            run_notebook.delay(notebook.id, notebook.user_id)
        except Exception:
            logger.exception("could not enqueue notebook %s", notebook.id)
            continue
        notebook.last_scheduled_at = utcnow()
        models.db.session.add(notebook)
        started.append(notebook.id)

    models.db.session.commit()
    if started:
        logger.info("enqueued %d scheduled notebook(s): %s", len(started), started)
    return {"started": started}

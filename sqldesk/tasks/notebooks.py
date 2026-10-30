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
from sqldesk.worker import job

logger = logging.getLogger(__name__)

#: Longer than a query's, because a cell may be a Python cell and the
#: interpreter's own deadline is minutes. Shorter than forever, because a
#: worker holding a job nobody is waiting for is a worker nobody else can use.
TIMEOUT = 900


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
                return {"error": refusal}
        record = _run(cell, user)
    except run.CannotRun as e:
        # The sentence the page was already showing. Not a failure of ours.
        return {"error": str(e)}
    except Exception as e:
        logger.exception("notebook cell %s could not be run", cell_id)
        models.db.session.rollback()
        return {"error": str(e)}
    finally:
        if slot:
            pools.release(pools.pool_for(cell.data_source), slot)

    models.db.session.commit()
    if record.state == models.NotebookRun.FAILED:
        return {"error": record.error}
    # The id itself, not a dict around it: `serialize_job` puts whatever a job
    # returns into `query_result_id`, so anything richer would hand the page a
    # dict where it reads an id. What else the page needs -- staleness, what a
    # cell now reads -- it gets by refetching the notebook, which it has to do
    # anyway because a run changes the cells below this one.
    return cell.latest_result_id


def _run(cell, user):
    if cell.kind == models.NotebookCell.PYTHON:
        return run.run_python_cell(cell, user)
    return run.run_sql_cell(cell, user)

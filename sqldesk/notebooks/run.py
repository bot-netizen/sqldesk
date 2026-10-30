"""
Running one cell, and saying beforehand when it cannot run.

A SQL cell is one of two things, and which one it is follows from whether it
names a data source:

- **It queries a data source.** The ordinary path: the runner the data source
  already has, under the permissions it already has. The full result becomes
  this cell's handoff; a truncated slice becomes what the page shows.
- **It reads earlier cells.** Then it runs inside the notebook's own store,
  where those cells' handoffs are tables -- and its result never leaves DuckDB,
  because `CREATE TABLE AS` can join two of them without a row passing through
  Python.

It cannot be both. A warehouse has never heard of cell `orders`, and we are not
going to push four million rows into it to pretend otherwise. The refusal says
so in a sentence, before the cell runs, which is the rule from the design: *"a
cell says why it cannot run before it is run"* -- Zeppelin's failure mode is
discovering the limits by hitting them.

Nothing here writes back to a data source. 0.8 is read-and-look.
"""

import logging
import re
import time
from datetime import datetime

from sqldesk import models, settings
from sqldesk.models import db
from sqldesk.notebooks.store import Store
from sqldesk.utils import gen_query_hash, utcnow

logger = logging.getLogger(__name__)

#: A relation a cell's SQL reads. Only `FROM` and `JOIN`, and only names this
#: notebook actually has -- the same narrowness the `query_results` runner uses
#: for `query_123`, and for the same reason: every other identifier in a
#: statement is a column, an alias or a function, and treating one as a cell
#: reference would invent dependencies that are not there.
RELATION = re.compile(r"(?:from|join)\s+\"?([A-Za-z_][A-Za-z0-9_]*)\"?", re.IGNORECASE)


class CannotRun(Exception):
    """Said to the person, not logged and swallowed. Carries the sentence."""


def references(sql, names):
    """
    Which of `names` this SQL reads, in the order they first appear.

    Case-insensitively, because an unquoted identifier in SQL is, and a cell
    called `Orders` referred to as `orders` means the one the person meant.
    """
    canonical = {name.lower(): name for name in names}
    found = []
    for candidate in RELATION.findall(sql or ""):
        name = canonical.get(candidate.lower())
        if name is not None and name not in found:
            found.append(name)
    return found


def earlier(cell, cells):
    """The cells above this one. A cell reads what precedes it, never what follows."""
    return [other for other in cells if other.position < cell.position and other.id != cell.id]


def why_it_cannot_run(cell, cells=None):
    """
    The sentence to show on the cell, or None if it is runnable.

    Everything here is answerable without touching a data source or an
    interpreter, which is what makes it something the page can show while
    somebody is still typing.
    """
    cells = cells if cells is not None else (cell.notebook.cells if cell.notebook else [])
    above = earlier(cell, cells)

    if cell.kind == models.NotebookCell.PYTHON:
        if not settings.NOTEBOOK_EXECUTOR_URL:
            return (
                "Python cells need an interpreter, and this install has none configured. "
                "An administrator can turn on the executor, or a SQL cell can do this work."
            )
        if not above:
            return "A Python cell computes; it cannot query. Put a SQL cell above it to fetch the data."
        return None

    if not (cell.source or "").strip():
        return "This cell has no SQL in it yet."

    read = references(cell.source, [one.name for one in above])

    if cell.data_source_id:
        if read:
            return (
                "This cell queries {}, which has never heard of {}. A cell can read a data source "
                "or earlier cells, not both -- remove the data source to read {}.".format(
                    cell.data_source.name if cell.data_source else "a data source",
                    ", ".join(read),
                    read[0],
                )
            )
        return None

    if not read:
        names = ", ".join(one.name for one in above)
        return (
            "This cell has no data source, so it can only read earlier cells -- and it refers to none. "
            "Pick a data source, or read one of: {}.".format(names)
            if above
            else "This cell has no data source and there is no cell above it to read."
        )

    never_ran = [name for name in read if _never_ran(above, name)]
    if never_ran:
        return "{} {} not run yet, so there is nothing to read from {}.".format(
            ", ".join(never_ran),
            "has" if len(never_ran) == 1 else "have",
            "it" if len(never_ran) == 1 else "them",
        )
    return None


def _never_ran(cells, name):
    for one in cells:
        if one.name == name:
            return one.last_run_at is None
    return True


def run_sql_cell(cell, user, run_query=None):
    """
    Run one SQL cell: the handoff, the displayed slice, and the record of it.

    `run_query` is the data source call, injectable so a test can run the whole
    path without a warehouse -- and so the queued version in step 3 can wrap it
    in a pool slot without this function learning about queues.

    Returns the `NotebookRun`. Raises `CannotRun` before doing anything if the
    cell is not runnable, which is the same sentence the page was already
    showing.
    """
    notebook = cell.notebook
    cells = notebook.cells
    problem = why_it_cannot_run(cell, cells)
    if problem:
        raise CannotRun(problem)

    above = earlier(cell, cells)
    read = references(cell.source, [one.name for one in above])
    run = models.NotebookRun(
        notebook=notebook,
        cell=cell,
        user=user,
        state=models.NotebookRun.RUNNING,
        inputs=read,
        started_at=utcnow(),
    )
    db.session.add(run)
    db.session.flush()

    store = Store(notebook.store_path())
    started = time.monotonic()
    try:
        if cell.data_source_id:
            columns, rows, total = _from_a_data_source(cell, user, store, run_query)
        else:
            columns, rows, total = _from_earlier_cells(cell, store)
    except CannotRun:
        raise
    except Exception as e:
        logger.warning("notebook cell %s failed: %s", cell.id, e)
        run.state = models.NotebookRun.FAILED
        run.error = str(e)
        run.finished_at = utcnow()
        run.runtime = time.monotonic() - started
        db.session.add(run)
        return run
    finally:
        store.close()

    run.runtime = time.monotonic() - started
    cell.latest_result = _displayed(cell, columns, rows, run.runtime, origin_data_source(cell, cells))
    cell.last_run_at = utcnow()
    run.state = models.NotebookRun.OK
    run.rows = total
    run.finished_at = utcnow()
    db.session.add_all([cell, run])
    # So that the caller -- and the page -- sees the result's id rather than
    # None. The commit belongs to the handler, as everywhere else.
    db.session.flush()
    return run


def _from_a_data_source(cell, user, store, run_query):
    """The ordinary path, and the only place a warehouse is touched."""
    call = run_query or (lambda source, sql, who: source.query_runner.run_query(sql, who))
    data, error = call(cell.data_source, cell.source, user)
    if error:
        raise RuntimeError(error)
    if not data:
        raise RuntimeError("The query ran but returned nothing to hand on.")

    columns = data["columns"]
    # The whole result into the notebook's store, for the next cell. This is
    # the half Postgres is the wrong shape for.
    total = store.hand_off(cell.name, columns, data["rows"])
    _, rows, total = store.display_slice(cell.name)
    return columns, rows, total


def _from_earlier_cells(cell, store):
    """
    Inside the notebook, where the cells it reads are already tables.

    `materialize` seals the store first, so by the time this SQL runs it can
    reach this notebook's own file and nothing else on the machine.
    """
    store.materialize(cell.name, cell.source)
    columns, rows, total = store.display_slice(cell.name)
    return columns, rows, total


def origin_data_source(cell, cells):
    """
    Where this cell's data came from, following the chain upwards.

    A cell that reads earlier cells has no data source of its own, and
    `query_results.data_source_id` is NOT NULL -- but the honest answer is not
    null anyway. The rows in it were fetched from somewhere, and that somewhere
    is what permission on the result should follow: whoever may see the cell
    this one read may see what this one made of it.

    The walk always terminates at a data source, because a chain has to start
    at one. Nothing else in a notebook can fetch: a code cell reaches no data
    source and a store-only cell has to read something above it.
    """
    seen = set()

    def upwards(one):
        if one is None or one.id in seen:
            return None
        seen.add(one.id)
        if one.data_source_id:
            return one.data_source
        above = earlier(one, cells)
        by_name = {other.name: other for other in above}
        for name in references(one.source, [other.name for other in above]):
            found = upwards(by_name.get(name))
            if found is not None:
                return found
        return None

    return upwards(cell)


def _displayed(cell, columns, rows, runtime, data_source):
    """
    The truncated slice, stored like any other result so the visualization
    editor works on a cell's output without being taught about notebooks.
    """
    # The dict, not JSON: `JSONText` serialises it, and `row_count` is derived
    # from it -- handing over a string stores it twice-encoded and loses the
    # count.
    data = {"columns": columns, "rows": rows}
    return models.QueryResult.store_result(
        cell.notebook.org_id,
        # The instance, not the id: `store_result` assigns it to the
        # relationship.
        data_source,
        gen_query_hash(cell.source or ""),
        cell.source or "",
        data,
        runtime,
        datetime.utcnow(),
    )

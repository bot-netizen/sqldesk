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
import os
import re
import time
from datetime import datetime

from sqldesk import models
from sqldesk.models import db
from sqldesk.notebooks import interpreter
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


def reads(cell, cells):
    """
    The cells this one reads, however its language says so.

    SQL names a relation after FROM or JOIN; Python just uses the variable. The
    two are different enough that one regex for both would either miss half the
    SQL or call every variable a reference.
    """
    above = earlier(cell, cells)
    names = [one.name for one in above]
    if cell.kind == models.NotebookCell.PYTHON:
        return interpreter.references(cell.source, names)
    return references(cell.source, names)


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
        if not interpreter.configured():
            return (
                "Python cells need an interpreter, and this install has none configured. "
                "An administrator can turn on the executor, or a SQL cell can do this work."
            )
        if not (cell.source or "").strip():
            return "This cell has no code in it yet."
        if not above:
            return "A Python cell computes; it cannot query. Put a SQL cell above it to fetch the data."
        read = interpreter.references(cell.source, [one.name for one in above])
        unusable = _without_a_table(above, read)
        if unusable:
            return _no_table_sentence(unusable)
        never_ran = [name for name in read if _never_ran(above, name)]
        if never_ran:
            return _unrun_sentence(never_ran)
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
        return _unrun_sentence(never_ran)
    unusable = _without_a_table(above, read)
    if unusable:
        return _no_table_sentence(unusable)
    return None


def _unrun_sentence(names):
    return "{} {} not run yet, so there is nothing to read from {}.".format(
        ", ".join(names),
        "has" if len(names) == 1 else "have",
        "it" if len(names) == 1 else "them",
    )


def _no_table_sentence(names):
    """
    A cell that ran and produced text rather than a table.

    Worth its own sentence. "Has not run yet" would be a lie, and silence would
    leave somebody re-running a cell that will never give them a relation --
    the Zeppelin failure of finding the limit by hitting it.
    """
    return "{} produced text rather than a table, so there is nothing to read from {}.".format(
        ", ".join(names), "it" if len(names) == 1 else "them"
    )


#: Recorded on a cell when it runs, so the question "is there a relation to
#: read here" is answerable from Postgres rather than by opening the store.
TABLE = "table"
TEXT = "text"


def _without_a_table(cells, names):
    by_name = {one.name: one for one in cells}
    return [
        name
        for name in names
        if by_name.get(name) is not None
        and by_name[name].last_run_at is not None
        and (by_name[name].options or {}).get("produced") == TEXT
    ]


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
    _record(cell, columns, rows, run.runtime, origin_data_source(cell, cells), TABLE)
    cell.last_run_at = utcnow()
    run.state = models.NotebookRun.OK
    run.rows = total
    run.finished_at = utcnow()
    db.session.add_all([cell, run])
    # So that the caller -- and the page -- sees the result's id rather than
    # None. The commit belongs to the handler, as everywhere else.
    db.session.flush()
    return run


def run_python_cell(cell, user, interpreter_for=None):
    """
    Run one Python cell on the interpreter, and land what comes back.

    The shape is the same as a SQL cell and the differences are all at the
    boundary: the inputs it reads are pushed over as Parquet, the code runs
    somewhere else, and what returns is either a dataframe -- which becomes
    this cell's handoff, so a later cell can read it -- or text, which is only
    ever something to look at.

    `interpreter_for` is injectable so a test can run this path without a
    container, the same reason `run_sql_cell` takes `run_query`.
    """
    notebook = cell.notebook
    cells = notebook.cells
    problem = why_it_cannot_run(cell, cells)
    if problem:
        raise CannotRun(problem)

    read = reads(cell, cells)
    record = models.NotebookRun(
        notebook=notebook,
        cell=cell,
        user=user,
        state=models.NotebookRun.RUNNING,
        inputs=read,
        started_at=utcnow(),
    )
    db.session.add(record)
    db.session.flush()

    store = Store(notebook.store_path())
    started = time.monotonic()
    try:
        talker = interpreter_for() if interpreter_for else interpreter.Interpreter()
        session_id = talker.session_for(notebook)
        try:
            columns, rows, total, produced = _on_the_interpreter(cell, store, talker, session_id, read)
        except interpreter.Gone:
            # The interpreter reaped the session while nobody was looking --
            # its idle timeout, or a restart. A fresh one with the inputs
            # shipped again is the same notebook, because every input is
            # another cell's output (§4.1) and all of them are still here.
            logger.info("notebook %s lost its session; opening another", notebook.id)
            talker.detach(notebook)
            session_id = talker.session_for(notebook)
            columns, rows, total, produced = _on_the_interpreter(cell, store, talker, session_id, read)
    except interpreter.NoInterpreter as e:
        raise CannotRun(str(e))
    except Exception as e:
        logger.warning("notebook cell %s failed on the interpreter: %s", cell.id, e)
        record.state = models.NotebookRun.FAILED
        record.error = str(e)
        record.finished_at = utcnow()
        record.runtime = time.monotonic() - started
        db.session.add(record)
        db.session.flush()
        return record
    finally:
        store.close()

    record.runtime = time.monotonic() - started
    _record(cell, columns, rows, record.runtime, origin_data_source(cell, cells), produced)
    cell.last_run_at = utcnow()
    record.state = models.NotebookRun.OK
    record.rows = total
    record.finished_at = utcnow()
    db.session.add_all([cell, record])
    db.session.flush()
    return record


def _on_the_interpreter(cell, store, talker, session_id, read):
    """
    Ship, run, and bring the answer back.

    Separate because it is the part that is retried when a session has gone:
    everything in it is safe to do twice.
    """
    talker.ship(cell.notebook, session_id, store, read)
    answer = talker.run(session_id, cell.source)
    if not answer.get("ok"):
        raise RuntimeError(_cell_error(answer))

    if answer.get("result_id"):
        fetched = os.path.join(store.directory, "{}.parquet".format(answer["result_id"]))
        try:
            talker.fetch(session_id, answer["result_id"], fetched)
            store.hand_off_parquet(cell.name, fetched)
        finally:
            try:
                os.remove(fetched)
            except OSError:
                pass
        columns, rows, total = store.display_slice(cell.name)
        return columns, rows, total, TABLE

    # Text, not a table. Kept in the same place as every other result so the
    # page has one way to show a cell's output -- but nothing downstream can
    # read it, which is what `produced` records.
    return _as_text(answer), [{"output": _printed(answer)}], None, TEXT


def _cell_error(answer):
    """The cell's own error, with whatever it printed before failing."""
    said = answer.get("error") or "The cell failed."
    printed = (answer.get("stdout") or "").strip()
    return "{}\n\n{}".format(said, printed) if printed else said


def _printed(answer):
    parts = [part for part in ((answer.get("stdout") or "").rstrip(), answer.get("value") or "") if part]
    return "\n".join(parts)


def _as_text(answer):
    return [{"name": "output", "friendly_name": "output", "type": "string"}]


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
        by_name = {other.name: other for other in earlier(one, cells)}
        # `reads`, not the SQL regex: a Python cell refers to `orders` by bare
        # name, so matching FROM and JOIN here broke the chain at the first
        # code cell and left its result with no data source at all.
        for name in reads(one, cells):
            found = upwards(by_name.get(name))
            if found is not None:
                return found
        return None

    found = upwards(cell)
    if found is not None:
        return found

    # A cell that reads nothing -- `total = 1 + 1`, or a print -- has no
    # lineage to follow, and `query_results.data_source_id` is NOT NULL. The
    # nearest data source above it is the answer: it over-attributes, in that
    # the output holds none of that warehouse's data, and that is the safe
    # direction. Permission on a result is read through its data source, so
    # null would not be "open to everyone" -- `QueryResult.groups` would raise
    # on it, turning a permission question into a 500.
    for one in reversed(earlier(cell, cells)):
        if one.data_source_id:
            return one.data_source
    return None


def _record(cell, columns, rows, runtime, data_source, produced):
    """
    What the page shows, and whether a later cell can read this one.

    `produced` is kept on the cell so "is there a relation here" is answerable
    without opening the notebook's store -- which the page asks on every
    keystroke while somebody types a reference.
    """
    cell.latest_result = _displayed(cell, columns, rows, runtime, data_source)
    options = dict(cell.options or {})
    options["produced"] = produced
    cell.options = options
    return cell.latest_result


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

"""
Where a cell hands its result to the next one: one DuckDB file per notebook.

Three things hide inside "persist cell output", and they have three different
lifetimes:

| What | Size | Where | Lives |
|---|---|---|---|
| the **displayed** output | small, truncated | `query_results`, keyed to the cell | with the notebook |
| the **handoff** between cells | arbitrary | this file | until re-run; disposable |
| the **provenance** | tiny | `notebook_runs` | for ever |

Keeping the handoff in Postgres is the trap. `query_results.data` is JSON in
one column, and a notebook intermediate is orders of magnitude larger than a
dashboard query's result -- putting five million rows through the one database
nobody can afford to lose would make it also the one under the most write
pressure. So a SQL cell writes **twice**: the whole result in here for the
next cell, and a truncated slice into `query_results` for your eyes.

That split is load-bearing rather than an optimisation. A code cell reaches no
data source (decided 2026-10-04), so a SQL cell is the notebook's only tap --
which means it has to be able to hand over everything it fetched.

Losing one of these files costs a re-run and nothing else, which is why it can
live beside the uploads rather than in a backup.

**Our own SQL and the user's share one connection, in that order.** We
materialise, then `seal()` takes away file access and locks the configuration,
and only then does a cell's SQL run -- which is what `run_cell_sql` is for, so
that the safe order is also the easy one. Doing it the other way round is the
one ordering that does not work: `lock_configuration` is final, so anything we
need must already be set.

Measured on 1.5.6 and on 2.0.0, because the three settings do not do what
their names suggest: **`allowed_directories` on its own restricts nothing.**
With external access enabled, any path on the machine is readable whatever it
says. It is the *carve-out* from `enable_external_access = false`, not a
fence -- which is why a notebook gets a directory to itself, and why sealing
is the thing that makes the sandbox real rather than a pair of belts.
"""

import logging
import os

from sqldesk import settings
from sqldesk.notebooks import NAME
from sqldesk.query_runner import (
    LEGACY_LAMBDA,
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    deferred,
    storage_config,
)
from sqldesk.utils import json_dumps

logger = logging.getLogger(__name__)

duckdb = deferred("duckdb")

#: What to declare a column as when writing a cell's result, by the type the
#: query runner reported. The runner's six types are the whole vocabulary any
#: data source speaks to us in, so this map is complete by construction.
#:
#: Declared rather than inferred on purpose. `read_json_auto` would guess, and
#: it guesses from the values present: a column that happens to be all null in
#: this run comes back `VARCHAR`, and the join in the next cell then fails for
#: a reason that has nothing to do with the data. The runner already told us
#: what the column is; throwing that away and re-deriving it is how a notebook
#: becomes unreproducible.
AS_DUCKDB = {
    TYPE_INTEGER: "BIGINT",
    TYPE_FLOAT: "DOUBLE",
    TYPE_BOOLEAN: "BOOLEAN",
    TYPE_STRING: "VARCHAR",
    TYPE_DATE: "DATE",
    TYPE_DATETIME: "TIMESTAMP WITH TIME ZONE",
}

#: Rows we are willing to hand from one cell to the next. The design promises
#: five million; past that the answer is a SQL cell that aggregates, not a
#: bigger file, because everything downstream -- the Parquet shipped to the
#: executor, the dataframe it builds -- is sized by this number.
ROW_BUDGET = settings.NOTEBOOK_ROW_BUDGET


class TooMuch(Exception):
    """A cell tried to hand over more than the budget allows."""


class Store:
    """
    One notebook's handoff. Cheap to construct; the file opens on first use.
    """

    def __init__(self, path, read_only=False):
        self.path = path
        self.read_only = read_only
        self._connection = None
        self._sealed = False

    # --- the connection -----------------------------------------------------

    @property
    def connection(self):
        if self._connection is None:
            self._ensure_directory()
            self._connection = self._connect()
            self._confine(self._connection)
        return self._connection

    def _ensure_directory(self):
        if not self.read_only:
            os.makedirs(self.directory, exist_ok=True)

    @property
    def directory(self):
        return os.path.dirname(self.path)

    def _connect(self):
        # The same reversible format the rest of SQLDesk writes: 0.8 ships
        # DuckDB 2.0, whose own format 0.7.x cannot open, and a handoff file is
        # not worth making a downgrade impossible over.
        return duckdb.connect(self.path, read_only=self.read_only, config=storage_config())

    def _confine(self, con):
        """
        Everything that can be set while we still have work to do.

        `allowed_directories` goes on now because `seal` cannot widen it later
        -- but on its own it confines nothing, so **this connection can still
        read the machine** and no cell's SQL may touch it until `seal` has run.
        External access stays on until then because writing the handoff and
        exporting Parquet are both file operations of ours.
        """
        for statement in (
            # Keeps `x -> x + 1` working in a cell somebody wrote against
            # 0.7.x. Gone in DuckDB 2.1 along with the syntax, and a cell is
            # perfectly runnable without it, so a refusal here is logged and
            # not raised.
            LEGACY_LAMBDA,
            "SET autoinstall_known_extensions = false",
            "SET autoload_known_extensions = false",
        ):
            try:
                con.execute(statement)
            except Exception:
                logger.info("this DuckDB does not accept %r", statement)
        # A trailing separator, which DuckDB requires to read this as a
        # directory rather than a file of that name.
        con.execute("SET allowed_directories = ?", [[os.path.join(self.directory, "")]])

    def seal(self):
        """
        Take away everything a cell's own SQL has no business reaching.

        Called after the inputs are materialised and before user SQL runs. By
        then every relation the cell refers to is a table in this file, so a
        cell needs no file access at all -- and `lock_configuration` means it
        cannot give itself any back, nor widen the directories it may read.

        What it can still read afterwards is this notebook's own directory,
        which is the carve-out `allowed_directories` describes. That is why the
        scratch file `hand_off` writes is deleted and why the directory holds
        one notebook.
        """
        if self._sealed:
            return
        con = self.connection
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        self._sealed = True

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            self._sealed = False

    def discard(self):
        """Throw the whole handoff away. It is re-materialised by re-running."""
        self.close()
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    # --- writing ------------------------------------------------------------

    def hand_off(self, name, columns, rows):
        """
        A cell's full result, as the relation later cells will refer to.

        Rows go to disk as newline-delimited JSON and DuckDB parses them,
        rather than Python looping `INSERT`s: it is the same reason the stream
        ingest path does it that way, and the measurement there was DuckDB
        parsing a batch 3.6x faster than `json.loads` one message at a time.

        Returns the number of rows written.
        """
        self._writable(name)
        declared = {column["name"]: AS_DUCKDB.get(column.get("type"), "VARCHAR") for column in columns}
        if not declared:
            raise ValueError("A cell cannot hand over a result with no columns.")

        # Before the scratch file, because this is what creates the directory
        # the scratch file goes in -- and on a notebook's first ever cell there
        # is nothing there yet.
        connection = self.connection
        scratch = os.path.join(self.directory, "{}.handoff.json".format(name))
        written = 0
        try:
            with open(scratch, "w", encoding="utf-8") as handle:
                for row in rows:
                    if written >= ROW_BUDGET:
                        raise TooMuch(
                            "{} returned more than {:,} rows, which is the most a cell can hand to the next one. "
                            "Aggregate or filter in this cell.".format(name, ROW_BUDGET)
                        )
                    handle.write(json_dumps({key: row.get(key) for key in declared}))
                    handle.write("\n")
                    written += 1
            connection.execute(
                "CREATE OR REPLACE TABLE {} AS SELECT * FROM read_json(?, columns = {}, format = "
                "'newline_delimited')".format(quoted(name), _as_struct(declared)),
                [scratch],
            )
        finally:
            # Whatever happened, the scratch file is not something to leave
            # inside the sandbox a cell's SQL is allowed to read.
            try:
                os.remove(scratch)
            except OSError:
                pass
        return written

    def materialize(self, name, sql):
        """
        A cell whose SQL reads earlier cells, whose result never leaves DuckDB.

        `CREATE TABLE AS` rather than fetching rows into Python and handing
        them back: the handoff and the inputs are in the same file, so a cell
        that joins four million rows to four million rows costs us nothing but
        the time DuckDB spends on it. It is also the only way this can work
        once sealed -- `hand_off` writes a scratch file, and a sealed
        connection has no file access.

        Seals first. This is somebody else's SQL.
        """
        self._writable(name)
        self.seal()
        self.connection.execute("CREATE OR REPLACE TABLE {} AS {}".format(quoted(name), sql))
        return self.row_count(name)

    def hand_off_parquet(self, name, path):
        """
        The same, from a Parquet file -- how a result comes back from the
        executor, which speaks Parquet so that neither side has to agree on a
        JSON encoding of a timestamp.
        """
        self._writable(name)
        self.connection.execute(
            "CREATE OR REPLACE TABLE {} AS SELECT * FROM read_parquet(?)".format(quoted(name)), [path]
        )
        return self.row_count(name)

    def export(self, name, path):
        """
        A cell's relation as Parquet, to ship to an interpreter.

        Parquet rather than CSV or JSON because it carries its own types: a
        timestamp arrives in pandas as a timestamp without either side
        agreeing a format, which is most of what makes a handoff lossy.
        """
        self.connection.execute("COPY (SELECT * FROM {}) TO ? (FORMAT PARQUET)".format(quoted(name)), [path])
        return path

    def drop(self, name):
        self.connection.execute("DROP TABLE IF EXISTS {}".format(quoted(name)))

    def rename(self, old, new):
        """
        Follow a cell being renamed, so its handoff is not orphaned.

        Cheap, and the alternative is every downstream cell reading a stale
        table under the old name while the page shows the new one.
        """
        self._writable(new)
        if not self.has(old):
            return False
        self.connection.execute("ALTER TABLE {} RENAME TO {}".format(quoted(old), quoted(new)))
        return True

    def _writable(self, name):
        if self.read_only:
            raise ValueError("This notebook store was opened read-only.")
        _checked(name)

    # --- reading ------------------------------------------------------------

    def has(self, name):
        found = self.connection.execute(
            "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [name]
        ).fetchone()
        return found is not None

    def names(self):
        """Which cells have a handoff here, in the order DuckDB lists them."""
        return [row[0] for row in self.connection.execute("SELECT table_name FROM duckdb_tables()").fetchall()]

    def row_count(self, name):
        counted = self.connection.execute("SELECT count(*) FROM {}".format(quoted(name))).fetchone()
        return counted[0] or 0

    def display_slice(self, name, limit=None):
        """
        The small, truncated half of the split: what goes into `query_results`.

        Returns `(columns, rows, total)`, where `total` is the real row count
        -- so the page can say "first 1,000 of 4.2 million" rather than
        implying that is all there was.
        """
        limit = settings.NOTEBOOK_DISPLAY_ROWS if limit is None else limit
        total = self.row_count(name)
        return self.select("SELECT * FROM {} LIMIT {}".format(quoted(name), int(limit))) + (total,)

    def run_cell_sql(self, sql):
        """
        A cell's own SQL, which is the only thing here that somebody else wrote.

        Seals first, every time. The sealing is not optional and not the
        caller's to remember: `allowed_directories` alone leaves the whole
        filesystem readable, so SQL that arrives before this point would run
        with no sandbox at all.
        """
        self.seal()
        return self.select(sql)

    def select(self, sql, parameters=None):
        """
        Run a SELECT and return `(columns, rows)` in the shape a query runner
        would -- so a cell's output lands in `query_results` like any other
        result and the visualization editor works on it unchanged.

        Ours to call. A cell's SQL goes through `run_cell_sql`.
        """
        from sqldesk.query_runner.duckdb import duckdb_type

        cursor = self.connection.execute(sql, parameters or [])
        if cursor.description is None:
            return [], []
        columns = [{"name": d[0], "friendly_name": d[0], "type": duckdb_type(d[1])} for d in cursor.description]
        names = [column["name"] for column in columns]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        return columns, rows


def quoted(name):
    """A cell name as a DuckDB identifier."""
    return '"{}"'.format(name.replace('"', '""'))


def _checked(name):
    """
    A name we are willing to put into SQL.

    `name_problem` has already said this to the person typing it; this is the
    line that makes it true of anything that reaches a statement, including a
    name that arrived from somewhere other than the form.
    """
    if not name or not NAME.match(name):
        raise ValueError("{!r} is not a usable cell name.".format(name))
    return name


def _as_struct(declared):
    """`{'a': 'BIGINT'}` as DuckDB's own struct literal for `read_json`."""
    return "{" + ", ".join("{}: '{}'".format(quoted(key), value) for key, value in declared.items()) + "}"

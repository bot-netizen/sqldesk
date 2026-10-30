"""
Where a stream's events are kept: one DuckDB file per stream.

Not Postgres. Postgres holds the users, the queries and the dashboards, and it
has to stay small enough to back up -- putting fifty thousand rows a second
through it would make the one database nobody can afford to lose also the one
under the most write pressure. DuckDB is columnar, so a few million flattened
events are cheap to store and cheaper to aggregate, truncation is a `DELETE`,
and losing a stream's file costs a window nobody was promised.

**No message is ever decoded in Python.** `append` takes the raw bytes the
consumer collected and writes them straight to a file for DuckDB to parse with
`read_json_auto`. That is the whole reason the ingest path can keep up: on two
cores, `json.loads` one message at a time managed 250,000 events a second and
DuckDB parsing the same batch managed 914,000. `tests/streams` has a test that
fails if `json.loads` is reached while appending.

The file lives under the same sandbox as uploads, so a stream's SQL cannot read
anything else on the machine.
"""

import logging
import os
import time

from sqldesk.query_runner import LEGACY_LAMBDA, deferred, storage_config

logger = logging.getLogger(__name__)

duckdb = deferred("duckdb")

#: The arrival time, added by us. Not a timestamp out of the message: a topic
#: may not have one, may have it in any format, and a producer's clock is not
#: ours. "When SQLDesk saw it" is a fact we can state.
RECEIVED = "_received_at"

#: Rows that did not parse. Counted rather than kept: a malformed message is
#: worth a number on the stream's page and nothing more, and a consumer that
#: stopped for one would be a consumer somebody has to restart at 3am.
MALFORMED = "_malformed"

#: Columns DuckDB may not infer a name for, so they are ours.
RESERVED = (RECEIVED,)


class Store:
    """
    One stream's events. Cheap to construct; the file is opened on first use.
    """

    #: How long a reader waits for a writer to finish a flush, and how often it
    #: tries. A flush is milliseconds; this is generous and still far inside
    #: the time anybody would wait for a page.
    READ_ATTEMPTS = 6
    READ_PAUSE_SECONDS = 0.25

    def __init__(self, path, read_only=False):
        self.path = path
        self.read_only = read_only
        self._connection = None
        #: Whether the window's table is known to exist -- see `_has_table`.
        self._table_exists = False

    # --- the connection -----------------------------------------------------

    @property
    def connection(self):
        if self._connection is None:
            self._ensure_directory()
            self._connection = self._connect()
            self._lock_down(self._connection)
        return self._connection

    def _connect(self):
        """
        Open the window, waiting out a flush if one is in progress.

        DuckDB gives a database file to **one process at a time**: a reader
        cannot open it while a consumer holds it, read-only or not. The
        consumer therefore closes between flushes (see `streams.consumer`), and
        a reader that arrives during one waits rather than failing -- a page
        that errored whenever it happened to land on a flush would be a page
        that errored at random.

        Both ways round. A query holds its windows open while it runs, so the
        consumer waits in its turn rather than losing the events it has already
        polled.
        """
        last = None
        for attempt in range(self.READ_ATTEMPTS):
            try:
                return duckdb.connect(self.path, read_only=self.read_only, config=storage_config())
            except duckdb.IOException as error:
                last = error
                if attempt + 1 < self.READ_ATTEMPTS:
                    time.sleep(self.READ_PAUSE_SECONDS)
        raise last

    def _ensure_directory(self):
        """
        The folder the database and its spill live in.

        Called from both the connection and the spill, because the spill is
        written *first* -- `append` has the bytes before it has any reason to
        open the database -- and relying on the connection to have made the
        folder meant the very first flush of a new stream failed on a missing
        directory.
        """
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def _lock_down(self, connection):
        """
        Take away everything this file's SQL does not need.

        A stream's store is queried by people through the ordinary query
        editor, so DuckDB's defaults -- `read_text` on any path, `glob` over
        every organisation's uploads, `INSTALL httpfs` -- would be theirs. Same
        reasoning and same settings as the uploads runner.

        `allowed_directories` rather than switching external access off
        outright, because the ingest path needs one file: the spill this writes
        beside the database for `read_json_auto` to parse. Switching access off
        entirely blocked that too, which is how the first version of this
        refused every flush.
        """
        # With a trailing separator, as the uploads runner does. Without one
        # DuckDB takes the entry for a file rather than a directory and refuses
        # everything inside it -- which refused this store's own spill file and
        # so every flush.
        folder = os.path.join(os.path.dirname(self.path), "")
        try:
            connection.execute("SET allowed_directories = ?", [[folder]])
        except Exception:
            logger.warning("could not confine a stream store to %s", folder, exc_info=True)
        for statement in (
            LEGACY_LAMBDA,
            "SET enable_external_access=false",
            "SET autoinstall_known_extensions=false",
            "SET autoload_known_extensions=false",
            # And so the SQL being confined cannot simply switch it back.
            "SET lock_configuration=true",
        ):
            try:
                connection.execute(statement)
            except Exception:
                # An older DuckDB may not know one of these. Better to go on
                # with the others than to refuse to open the file.
                logger.warning("could not apply %r to a stream store", statement, exc_info=True)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # --- writing ------------------------------------------------------------

    def append(self, raw_messages):
        """
        Add a flush of raw message bytes. Returns `(added, malformed)`.

        `raw_messages` is a list of `bytes`, one per message, exactly as they
        came off the topic. They are joined with newlines and written to a
        temporary file for DuckDB to parse -- a single write of a few megabytes
        against a parse-per-message in Python, which is the trade this whole
        design is built on.

        The first flush also decides the columns. `read_json_auto` infers them,
        which is a better guess than ours and the only one available before a
        human has looked at the topic.
        """
        if not raw_messages:
            return 0, 0

        path, not_objects = self._spill(raw_messages)
        try:
            added, unparseable = self._load(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        return added, not_objects + unparseable

    def _spill(self, raw_messages):
        """
        The flush, as newline-delimited JSON on disk. Returns `(path, dropped)`.

        Messages that do not begin with `{` are left out and counted. That is a
        **single byte comparison**, not a parse, and it is worth making because
        of what `read_json_auto` does otherwise: handed one `[1,2,3]` or
        `"a string"` in the first flush, it abandons column inference entirely
        and gives one opaque `json` column for the life of the stream. One odd
        message would decide the schema for every chart built on the topic.

        A message that is not a JSON object is not an event anyway -- there are
        no fields on it to group by or plot.

        A fixed name beside the database, overwritten every flush, rather than
        a `tempfile`. Three reasons, and the third is not optional:

        - One file, so nothing accumulates whatever happens.
        - No `mkstemp`, on a path that runs once a second.
        - **DuckDB 1.3.2 refuses to open a path containing `tmp`** once the
          database's own `<db>.tmp/` directory is on the allowed list -- and
          `tempfile` always produces `tmp`-prefixed names, so the first version
          of this refused every single flush with a permission error naming a
          file that was sitting in an allowed directory.

        One consumer per stream, so there is nothing to contend with. Two would
        need a lock, and would have a worse problem than this file.
        """
        self._ensure_directory()
        path = self.path + ".flush.ndjson"
        kept = 0
        with open(path, "wb") as handle:
            # `writelines` over a generator rather than one big join: the
            # buffer is already the largest thing in memory on this path and
            # doubling it to add newlines would be the wrong place to save a
            # syscall.
            for line in _objects_only(raw_messages):
                handle.write(line)
                handle.write(b"\n")
                kept += 1
        return path, len(raw_messages) - kept

    def _load(self, path):
        """
        Parse and insert. Returns `(added, unparseable)`.

        `ignore_errors` keeps a consumer running past a message DuckDB cannot
        read -- but it does not *skip* that message, it inserts a row of nulls.
        Left alone, a topic with a broken producer would quietly fill with
        empty rows while the malformed counter read zero, which is worse than
        either failing or counting. So all-null rows are excluded here and
        counted instead.

        **The known consequence**, stated because it is a real one: a message
        that carries no non-null value at all -- `{"a": null}` on a stream
        whose other columns it omits -- is indistinguishable from a line
        DuckDB could not read, and is counted as malformed. For an event
        stream that is a message with no data in it. A message with one
        non-null field and the rest null is kept, which is the case that
        actually occurs.

        The columns are the table's, chosen once from the first flush and then
        fixed. A field the producer drops arrives as null; a field it adds is
        **ignored** until somebody re-infers the schema. That is deliberate: a
        chart should not change shape because a producer shipped a new field,
        and a stream whose columns moved on their own would make every saved
        query on it a guess. See `sqldesk/streams` on freezing a schema.
        """
        quoted = path.replace("'", "''")
        reader = "read_json_auto('{}', format='newline_delimited', ignore_errors=true)".format(quoted)

        # Parsed once, into a temporary table the three statements below then
        # read.
        #
        # They used to name the reader directly, so the flush file was opened,
        # inferred and parsed three times over: once to describe its columns,
        # once for the INSERT, and once to count the lines that came back all
        # null. On a topic flushing a few megabytes a second that is two
        # parses of everything for nothing -- and the most expensive thing
        # this path does.
        self.connection.execute("CREATE OR REPLACE TEMP TABLE flushed AS SELECT * FROM {}".format(reader))

        if not self._has_table():
            self.connection.execute(
                "CREATE TABLE events AS SELECT now() AS {}, * FROM flushed LIMIT 0".format(RECEIVED)
            )
            self._table_exists = True

        # The columns *this flush* has, not the table's. A producer that drops
        # a field leaves the table with a column the reader knows nothing
        # about, and naming it here is a binder error rather than a null.
        arriving = [row[0] for row in self.connection.execute("DESCRIBE flushed").fetchall()]
        arriving = [name for name in arriving if name not in RESERVED]
        if not arriving:
            # Nothing inferred at all, which means the flush held nothing a
            # reader could make columns out of.
            return 0, 0

        empty = " AND ".join("{} IS NULL".format(_quoted(name)) for name in arriving)

        # One expression per column the table has: the flush's value where it
        # sent one, NULL where it did not. Explicit rather than `*` so neither
        # a dropped field nor an added one is a binder error.
        #
        # Cast to the table's type with TRY_CAST: the columns were fixed by
        # the first flush, and one message sending `"id": "a-17"` where the
        # first sent `"id": 1` made this flush's column VARCHAR, the INSERT a
        # conversion error, and the consumer die -- again on every restart
        # while that message was in the window. Now that value is NULL and the
        # rest of the row is kept.
        kinds = {name: kind for name, kind in self.columns() if name not in RESERVED}
        chosen = ", ".join(
            "TRY_CAST({0} AS {1}) AS {0}".format(_quoted(name), kinds[name])
            if name in arriving
            else "NULL AS {}".format(_quoted(name))
            for name in kinds
        )

        # DuckDB answers an INSERT with the number of rows it wrote, which is
        # what two counts of the whole window were being used to work out.
        inserted = self.connection.execute(
            "INSERT INTO events BY NAME SELECT now() AS {}, {} FROM flushed WHERE NOT ({})".format(
                RECEIVED, chosen, empty
            )
        ).fetchone()
        added = int((inserted or [0])[0] or 0)

        unparseable = self.connection.execute("SELECT count(*) FROM flushed WHERE {}".format(empty)).fetchone()[0]
        return added, int(unparseable or 0)

    def reset(self):
        """
        Empty the window and forget its columns, for a stream now read
        differently. The next flush infers them again from what it decodes.
        """
        if self._has_table():
            self.connection.execute("DROP TABLE events")
            self._table_exists = False

    def _has_table(self):
        """
        Whether the window's table exists yet.

        Remembered once it does. This is asked four or five times a flush --
        by `rows`, by `columns`, by `truncate`, by `_load` -- and each ask was
        a query against information_schema. The table is only ever created
        here and dropped by `reset`, both of which update the answer.
        """
        if self._table_exists:
            return True
        found = self.connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'events'"
        ).fetchone()
        self._table_exists = bool(found and found[0])
        return self._table_exists

    # --- reading and trimming ----------------------------------------------

    def rows(self):
        if not self._has_table():
            return 0
        return int(self.connection.execute("SELECT count(*) FROM events").fetchone()[0])

    def columns(self):
        """The columns `read_json_auto` settled on, ours last."""
        if not self._has_table():
            return []
        described = self.connection.execute("DESCRIBE events").fetchall()
        theirs = [(name, kind) for name, kind, *_rest in described if name not in RESERVED]
        ours = [(name, kind) for name, kind, *_rest in described if name in RESERVED]
        return theirs + ours

    def truncate(self, window_seconds):
        """
        Drop everything older than the window. Returns how many went.

        A `DELETE`, which in a columnar store this size is cheap, and the only
        thing standing between a busy topic and a full disk. It runs on the
        flush rather than on a timer: a timer that stopped would be a disk
        filling with nobody watching.
        """
        if not self._has_table():
            return 0
        before = self.rows()
        self.connection.execute(
            "DELETE FROM events WHERE {} < now() - INTERVAL '{} seconds'".format(RECEIVED, int(window_seconds))
        )
        return before - self.rows()

    def size_bytes(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def observed_rate(self, over_seconds=60):
        """
        Events a second, measured over the last minute of arrivals.

        Measured rather than configured, because the whole window calculation
        depends on it and a topic's rate is not a thing anybody knows in
        advance. Over a minute rather than a second so one quiet moment does
        not open the window to half an hour and one burst does not slam it
        shut.
        """
        if not self._has_table():
            return 0.0
        counted = self.connection.execute(
            "SELECT count(*) FROM events WHERE {} >= now() - INTERVAL '{} seconds'".format(RECEIVED, int(over_seconds))
        ).fetchone()
        return (counted[0] or 0) / float(over_seconds)


def _quoted(name):
    """A column name as a DuckDB identifier, whatever characters the producer put in it."""
    return '"{}"'.format(name.replace('"', '""'))


def _objects_only(raw_messages):
    """
    The messages that are JSON objects, by their first non-space byte.

    One byte compared per message. Not a parse, not a decode -- which is the
    rule the whole ingest path is built on.
    """
    for message in raw_messages:
        if message and message.lstrip()[:1] == b"{":
            yield message

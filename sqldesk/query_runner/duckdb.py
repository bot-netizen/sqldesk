import logging
import os
import re
from contextlib import contextmanager

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    InterruptException,
    deferred,
    installed,
    register,
)

logger = logging.getLogger(__name__)

duckdb = deferred("duckdb")

enabled = installed("duckdb")

# Map DuckDB types to SQLDesk column types. The keys are DuckDB's own names,
# which is what `cursor.description` reports from 1.5 onwards.
TYPES_MAP = {
    "BOOLEAN": TYPE_BOOLEAN,
    "TINYINT": TYPE_INTEGER,
    "SMALLINT": TYPE_INTEGER,
    "INTEGER": TYPE_INTEGER,
    "BIGINT": TYPE_INTEGER,
    "HUGEINT": TYPE_INTEGER,
    "UTINYINT": TYPE_INTEGER,
    "USMALLINT": TYPE_INTEGER,
    "UINTEGER": TYPE_INTEGER,
    "UBIGINT": TYPE_INTEGER,
    "UHUGEINT": TYPE_INTEGER,
    "REAL": TYPE_FLOAT,
    "FLOAT": TYPE_FLOAT,
    "DOUBLE": TYPE_FLOAT,
    "DECIMAL": TYPE_FLOAT,
    "VARCHAR": TYPE_STRING,
    "BLOB": TYPE_STRING,
    "BIT": TYPE_STRING,
    "VARINT": TYPE_STRING,
    "DATE": TYPE_DATE,
    "TIMESTAMP": TYPE_DATETIME,
    "TIMESTAMP_S": TYPE_DATETIME,
    "TIMESTAMP_MS": TYPE_DATETIME,
    "TIMESTAMP_NS": TYPE_DATETIME,
    "TIMESTAMP WITH TIME ZONE": TYPE_DATETIME,
    "TIME": TYPE_DATETIME,
    "TIME WITH TIME ZONE": TYPE_DATETIME,
    "INTERVAL": TYPE_STRING,
    "UUID": TYPE_STRING,
    "JSON": TYPE_STRING,
    "STRUCT": TYPE_STRING,
    "MAP": TYPE_STRING,
    "UNION": TYPE_STRING,
    "ENUM": TYPE_STRING,
}


def _duckdb_type(declared):
    """A column's SQLDesk type, from whatever DuckDB called it.

    Two things had to change here, and the first had been wrong for a long time.

    **`cursor.description` stopped being strings.** Up to 1.3 the type code was
    a `str`; from 1.5 it is a `DuckDBPyType`, and `.upper()` on one of those
    does not fail the way an attribute error normally does -- the object
    forwards unknown attributes to its own child-type lookup, so asking for
    `upper` raised *"Tried to get child type by the name of 'upper'"* and every
    query against a DuckDB source died inside the schema browser.

    **And the names it reports changed, which fixes a silent fault.** 1.3
    returned DB-API names -- `NUMBER`, `STRING`, `DATETIME`, `bool` -- while
    this table has always been keyed by DuckDB's own. Only 5 of 12 ordinary
    column types matched, so **every number and every timestamp from a DuckDB
    source, including every uploaded CSV and Parquet file, was declared a
    string.** It was invisible because the browser sniffs the type of a column
    declared `string` and mostly recovers it. 1.5 reports `INTEGER`,
    `TIMESTAMP`, `BOOLEAN` and the rest, which this table already knew.

    Parameters are dropped before the lookup, because DuckDB reports
    `DECIMAL(10,2)` rather than `DECIMAL` -- the same way Trino reports
    `varchar(255)`. A list stays a string: `INTEGER[]` holds a list, and the
    number inside it is not what the column contains.
    """
    if declared is None:
        return None

    name = str(declared).strip().upper()
    if name.endswith("]"):
        # INTEGER[], VARCHAR[3] -- a list, whatever it is a list of.
        return TYPE_STRING
    if "(" in name:
        # DECIMAL(10,2), STRUCT(a INTEGER), MAP(VARCHAR, INTEGER)
        name = name.split("(", 1)[0].strip()

    return TYPES_MAP.get(name, TYPE_STRING)


class DuckDB(BaseSQLQueryRunner):
    noop_query = "SELECT 1"

    def __init__(self, configuration):
        super().__init__(configuration)
        self.dbpath = configuration.get("dbpath", ":memory:")
        exts = configuration.get("extensions", "")
        self.extensions = [e.strip() for e in exts.split(",") if e.strip()]
        # The one directory this source's SQL may read files from: its own
        # uploads. Set by the data source before the first query (see
        # `confine_to`); until then SQL can read no files at all.
        self.upload_dir = None
        self._connect()

    def confine_to(self, directory) -> None:
        """
        Let this source's SQL read files in `directory` and nowhere else.

        DuckDB's defaults let SQL open any path the worker can: `read_text`
        on /etc/passwd, `glob` over every organization's uploads, `COPY ...
        TO` over the application's own code, `ATTACH`, `INSTALL httpfs`.
        This runner is a default data source that every user in the default
        group can query, so those defaults were everybody's.
        """
        directory = os.path.join(directory, "")
        if directory != self.upload_dir:
            self.upload_dir = directory
            self._connect()

    @classmethod
    def name(cls):
        return "File Upload"

    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "dbpath": {
                    "type": "string",
                    "title": "Database Path",
                    "default": ":memory:",
                },
                "extensions": {
                    "type": "string",
                    "title": "Extensions (comma separated)",
                },
            },
            "order": ["dbpath", "extensions"],
            # Most users just upload a file and never need to touch these, so they're
            # tucked under "Show More Options" rather than shown (or required) up front.
            "extra_options": ["dbpath", "extensions"],
        }

    @classmethod
    def enabled(cls) -> bool:
        return enabled

    # DataSource.query_runner is a property, so a runner -- and therefore a
    # connection -- was built on every single access: a fresh duckdb.connect
    # plus an INSTALL and LOAD for each configured extension, per query.
    # Connections are cached per process instead, keyed by the configuration
    # that produced them so two differently configured sources never share one.
    #
    # Safe across workers because each RQ worker is its own process and the
    # cache is module state. Within a process, queries go through
    # con.cursor(), which is DuckDB's supported way to work concurrently
    # against one connection.
    #
    # Views are still re-registered per query by register_uploaded_files: that
    # is what keeps a cached :memory: catalog honest when an upload is added or
    # deleted, and it is cheap.
    _connections = {}

    #: Uploaded files that have no view, by name and path. Set per runner by
    #: `register_uploaded_files`; empty for a DuckDB source with no uploads at
    #: all, which is why it has a default here rather than only an assignment.
    _unloaded = {}

    def _connection_key(self):
        return (self.dbpath, tuple(self.extensions), self.upload_dir)

    def _connect(self) -> None:
        key = self._connection_key()
        cached = DuckDB._connections.get(key)
        if cached is not None and self._is_alive(cached):
            self.con = cached
            return
        # A cached connection outlives any single query, so it can be closed or
        # invalidated underneath us -- the database file replaced, say. Without
        # this check one dead connection would fail every subsequent query in
        # the process, which is strictly worse than not caching at all.
        self.con = self._open_connection()
        DuckDB._connections[key] = self.con

    @staticmethod
    def _is_alive(con) -> bool:
        try:
            con.execute("SELECT 1").fetchone()
            return True
        except Exception:
            logger.info("Cached DuckDB connection is no longer usable; reconnecting.")
            return False

    def _open_connection(self):
        con = duckdb.connect(self.dbpath)
        # Extensions first: installing one needs the network and a directory
        # of its own, both of which the lines below take away.
        self._load_extensions(con)
        if self.upload_dir:
            con.execute("SET allowed_directories = ?", [[self.upload_dir]])
        con.execute("SET enable_external_access = false")
        con.execute("SET autoinstall_known_extensions = false")
        con.execute("SET autoload_known_extensions = false")
        # And so that the SQL being confined cannot simply switch it back.
        con.execute("SET lock_configuration = true")
        return con

    def _load_extensions(self, con) -> None:
        for ext in self.extensions:
            try:
                if "." in ext:
                    prefix, name = ext.split(".", 1)
                    if prefix == "community":
                        con.execute(f"INSTALL {name} FROM community")
                        con.execute(f"LOAD {name}")
                    else:
                        raise Exception("Unknown extension prefix.")
                else:
                    con.execute(f"INSTALL {ext}")
                    con.execute(f"LOAD {ext}")
            except Exception as e:
                logger.warning("Failed to load extension %s: %s", ext, e)

    # Maps a file extension to the DuckDB table function used to read it.
    READERS = {
        "csv": "read_csv_auto",
        "parquet": "read_parquet",
    }

    def register_uploaded_files(self, files) -> None:
        """Sync queryable views to exactly the given uploaded files.

        `files` is a list of (view_name, absolute_path, load_now) tuples.
        `view_name` is the user-assigned table name (uniqueness enforced at
        upload time, see DataSourceUploadListResource.post), and `path` is
        always server-generated (never taken from query text), so this is safe
        from path-injection via user-supplied SQL.

        `load_now` false means the file has not been queried for a while and
        has been unloaded: no view is created for it, so no query pays for its
        schema inference. It is still listed here, with its path, because a
        query that names it brings it back -- see `run_query`. The file itself
        is untouched either way; unloading costs nothing to reverse.

        Any view that exists but isn't in `files` anymore gets dropped, since
        the connection's catalog otherwise outlives individual uploads (e.g. a
        shared `:memory:` catalog persists across connections within the same
        worker process) -- a deleted upload's table would stay queryable
        forever otherwise. This connector treats the whole schema as owned by
        uploaded files: don't create your own views by hand against a "File
        Upload" data source's dbpath, they'll be dropped on the next upload
        or delete.
        """
        current_view_names = {view_name for view_name, _path, _load in files}
        for stale_view in self._existing_views() - current_view_names:
            try:
                self.con.execute(f'DROP VIEW IF EXISTS "{stale_view}"')
            except Exception as e:
                logger.warning("Failed to drop stale view %s: %s", stale_view, e)

        # Remembered so a query naming one can register it on the spot.
        self._unloaded = {view_name: path for view_name, path, load_now in files if not load_now}
        for view_name, path in self._unloaded.items():
            # An unloaded file whose view is still in the catalog from an
            # earlier query in this process has to go, or unloading saves
            # nothing on a long-lived worker.
            try:
                self.con.execute(f'DROP VIEW IF EXISTS "{view_name}"')
            except Exception as e:
                logger.warning("Failed to unload view %s: %s", view_name, e)

        for view_name, path, load_now in files:
            if load_now:
                self._create_view(view_name, path)

    def _create_view(self, view_name, path) -> None:
        extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        reader = self.READERS.get(extension)
        if reader is None:
            logger.warning("No DuckDB reader for uploaded file extension: %s", extension)
            return
        try:
            # DuckDB DDL statements (CREATE VIEW) don't support prepared-statement
            # parameters, so the path is embedded directly. This is safe because
            # `path` is always server-generated (UUID-based storage path), never
            # taken from query text or other user input.
            escaped_path = path.replace("'", "''")
            self.con.execute(f"CREATE OR REPLACE VIEW \"{view_name}\" AS SELECT * FROM {reader}('{escaped_path}')")
        except Exception as e:
            logger.warning("Failed to register uploaded file %s as view %s: %s", path, view_name, e)

    def _load_anything_the_query_names(self, query) -> None:
        """
        Bring back any unloaded file this query mentions.

        Matched on the view name as a whole word in the SQL. A false positive
        costs one view creation that nobody reads, so the match is deliberately
        generous: the alternative is a query failing with "table does not
        exist" for a file that is sitting right there on the disk, which is the
        one outcome unloading must never produce.
        """
        for view_name in list(self._unloaded):
            if re.search(r"\b{}\b".format(re.escape(view_name)), query, re.IGNORECASE):
                self._create_view(view_name, self._unloaded.pop(view_name))

    def _existing_views(self) -> set:
        try:
            rows = self.con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_type = 'VIEW' AND table_schema NOT IN ('information_schema', 'pg_catalog')"
            ).fetchall()
        except Exception as e:
            logger.warning("Failed to list existing views: %s", e)
            return set()
        return {row[0] for row in rows}

    def run_query(self, query, user) -> tuple:
        self._load_anything_the_query_names(query)
        try:
            cursor = self.con.cursor()
            cursor.execute(query)
            columns = self.fetch_columns(
                [(d[0], _duckdb_type(d[1])) for d in cursor.description]
            )
            rows = [dict(zip((col["name"] for col in columns), row)) for row in cursor.fetchall()]
            data = {"columns": columns, "rows": rows}
            return data, None
        except duckdb.InterruptException:
            raise InterruptException("Query cancelled by user.")
        except Exception as e:
            logger.exception("Error running query: %s", e)
            return None, str(e)

    @contextmanager
    def _everything_loaded(self):
        """
        Every uploaded file visible, including ones nobody has queried lately.

        Unloading is a saving at *query* time: a file nobody asks about should
        not cost schema inference on every query that names something else.
        Reading the schema is the one operation where that inference is the
        whole point -- the catalog harvest and the editor's schema browser both
        arrive here -- and an unloaded file was simply absent from both, which
        reads as the file having been deleted. The catalog harvest then found
        an empty schema, kept the old entries rather than emptying them, and
        the Catalog page showed a source that had not been harvested for days
        however often somebody pressed Harvest.

        Brought back for the read and dropped again afterwards, so a file that
        had gone quiet stays quiet for the queries that follow.
        """
        brought_back = []
        for view_name, path in list(self._unloaded.items()):
            self._create_view(view_name, path)
            brought_back.append(view_name)
        try:
            yield
        finally:
            for view_name in brought_back:
                try:
                    self.con.execute(f'DROP VIEW IF EXISTS "{view_name}"')
                except Exception as e:
                    logger.warning("Failed to unload view %s again: %s", view_name, e)

    def get_schema(self, get_stats=False) -> list:
        with self._everything_loaded():
            return self._read_schema()

    def _read_schema(self) -> list:
        tables_query = """
            SELECT table_catalog, table_schema, table_name FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog');
        """
        tables_results, error = self.run_query(tables_query, None)
        if error:
            raise Exception(f"Failed to get tables: {error}")

        schema = {}
        for table_row in tables_results["rows"]:
            # Include catalog (database) in the full table name for MotherDuck support
            catalog = table_row["table_catalog"]
            schema_name = table_row["table_schema"]
            table_name = table_row["table_name"]

            # Skip catalog prefix for default local databases (memory, temp)
            # but include it for MotherDuck and attached databases
            if catalog.lower() in ("memory", "temp", "system"):
                full_table_name = f"{schema_name}.{table_name}"
                describe_query = f'DESCRIBE "{schema_name}"."{table_name}";'
            else:
                full_table_name = f"{catalog}.{schema_name}.{table_name}"
                describe_query = f'DESCRIBE "{catalog}"."{schema_name}"."{table_name}";'

            schema[full_table_name] = {"name": full_table_name, "columns": []}
            columns_results, error = self.run_query(describe_query, None)
            if error:
                logger.warning("Failed to describe table %s: %s", full_table_name, error)
                continue

            for col_row in columns_results["rows"]:
                col = {"name": col_row["column_name"], "type": col_row["column_type"]}
                schema[full_table_name]["columns"].append(col)

                if col_row["column_type"].startswith("STRUCT("):
                    schema[full_table_name]["columns"].extend(
                        self._expand_struct_fields(col["name"], col_row["column_type"])
                    )

        return list(schema.values())

    def _expand_struct_fields(self, base_name: str, struct_type: str) -> list:
        """Recursively expand STRUCT(...) definitions into pseudo-columns."""
        fields = []
        # strip STRUCT( ... )
        inner = struct_type[len("STRUCT(") : -1].strip()
        # careful: nested structs, so parse comma-separated parts properly
        depth, current, parts = 0, [], []
        for c in inner:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if c == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(c)
        if current:
            parts.append("".join(current).strip())

        for part in parts:
            # each part looks like: "fieldname TYPE"
            fname, ftype = part.split(" ", 1)
            colname = f"{base_name}.{fname}"
            fields.append({"name": colname, "type": ftype})
            if ftype.startswith("STRUCT("):
                fields.extend(self._expand_struct_fields(colname, ftype))
        return fields


register(DuckDB)

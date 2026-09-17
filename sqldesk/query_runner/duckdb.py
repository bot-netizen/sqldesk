import logging

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    BaseSQLQueryRunner,
    InterruptException,
    register,
)

logger = logging.getLogger(__name__)

try:
    import duckdb

    enabled = True
except ImportError:
    enabled = False

# Map DuckDB types to SQLDesk column types
TYPES_MAP = {
    "BOOLEAN": TYPE_BOOLEAN,
    "TINYINT": TYPE_INTEGER,
    "SMALLINT": TYPE_INTEGER,
    "INTEGER": TYPE_INTEGER,
    "BIGINT": TYPE_INTEGER,
    "HUGEINT": TYPE_INTEGER,
    "REAL": TYPE_FLOAT,
    "DOUBLE": TYPE_FLOAT,
    "DECIMAL": TYPE_FLOAT,
    "VARCHAR": TYPE_STRING,
    "BLOB": TYPE_STRING,
    "DATE": TYPE_DATE,
    "TIMESTAMP": TYPE_DATETIME,
    "TIMESTAMP WITH TIME ZONE": TYPE_DATETIME,
    "TIME": TYPE_DATETIME,
    "INTERVAL": TYPE_STRING,
    "UUID": TYPE_STRING,
    "JSON": TYPE_STRING,
    "STRUCT": TYPE_STRING,
    "MAP": TYPE_STRING,
    "UNION": TYPE_STRING,
}


class DuckDB(BaseSQLQueryRunner):
    noop_query = "SELECT 1"

    def __init__(self, configuration):
        super().__init__(configuration)
        self.dbpath = configuration.get("dbpath", ":memory:")
        exts = configuration.get("extensions", "")
        self.extensions = [e.strip() for e in exts.split(",") if e.strip()]
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

    def _connection_key(self):
        return (self.dbpath, tuple(self.extensions))

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
        self._load_extensions(con)
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

        `files` is a list of (view_name, absolute_path) tuples. `view_name` is
        now the user-assigned table name (uniqueness enforced at upload time,
        see DataSourceUploadListResource.post), and `path` is always
        server-generated (never taken from query text), so this is safe from
        path-injection via user-supplied SQL.

        Any view that exists but isn't in `files` anymore gets dropped, since
        the connection's catalog otherwise outlives individual uploads (e.g. a
        shared `:memory:` catalog persists across connections within the same
        worker process) -- a deleted upload's table would stay queryable
        forever otherwise. This connector treats the whole schema as owned by
        uploaded files: don't create your own views by hand against a "File
        Upload" data source's dbpath, they'll be dropped on the next upload
        or delete.
        """
        current_view_names = {view_name for view_name, _ in files}
        for stale_view in self._existing_views() - current_view_names:
            try:
                self.con.execute(f'DROP VIEW IF EXISTS "{stale_view}"')
            except Exception as e:
                logger.warning("Failed to drop stale view %s: %s", stale_view, e)

        for view_name, path in files:
            extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            reader = self.READERS.get(extension)
            if reader is None:
                logger.warning("No DuckDB reader for uploaded file extension: %s", extension)
                continue
            try:
                # DuckDB DDL statements (CREATE VIEW) don't support prepared-statement
                # parameters, so the path is embedded directly. This is safe because
                # `path` is always server-generated (UUID-based storage path), never
                # taken from query text or other user input.
                escaped_path = path.replace("'", "''")
                self.con.execute(f"CREATE OR REPLACE VIEW \"{view_name}\" AS SELECT * FROM {reader}('{escaped_path}')")
            except Exception as e:
                logger.warning("Failed to register uploaded file %s as view %s: %s", path, view_name, e)

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
        try:
            cursor = self.con.cursor()
            cursor.execute(query)
            columns = self.fetch_columns(
                [(d[0], TYPES_MAP.get(d[1].upper(), TYPE_STRING)) for d in cursor.description]
            )
            rows = [dict(zip((col["name"] for col in columns), row)) for row in cursor.fetchall()]
            data = {"columns": columns, "rows": rows}
            return data, None
        except duckdb.InterruptException:
            raise InterruptException("Query cancelled by user.")
        except Exception as e:
            logger.exception("Error running query: %s", e)
            return None, str(e)

    def get_schema(self, get_stats=False) -> list:
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

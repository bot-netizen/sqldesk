import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
)
from sqldesk.query_runner.duckdb import DuckDB, _duckdb_type


class TestDuckDBSchema(TestCase):
    def setUp(self) -> None:
        self.runner = DuckDB({"dbpath": ":memory:"})

    @patch.object(DuckDB, "run_query")
    def test_simple_schema_build(self, mock_run_query) -> None:
        # Simulate queries: first for tables, then for DESCRIBE
        mock_run_query.side_effect = [
            (
                {
                    "rows": [
                        {
                            "table_catalog": "memory",
                            "table_schema": "main",
                            "table_name": "users",
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "rows": [
                        {"column_name": "id", "column_type": "INTEGER"},
                        {"column_name": "name", "column_type": "VARCHAR"},
                    ]
                },
                None,
            ),
        ]

        schema = self.runner.get_schema()
        self.assertEqual(len(schema), 1)
        self.assertEqual(schema[0]["name"], "main.users")
        self.assertListEqual(
            schema[0]["columns"],
            [{"name": "id", "type": "INTEGER"}, {"name": "name", "type": "VARCHAR"}],
        )

    @patch.object(DuckDB, "run_query")
    def test_struct_column_expansion(self, mock_run_query) -> None:
        # First call to run_query -> tables list
        mock_run_query.side_effect = [
            (
                {
                    "rows": [
                        {
                            "table_catalog": "memory",
                            "table_schema": "main",
                            "table_name": "events",
                        }
                    ]
                },
                None,
            ),
            # Second call -> DESCRIBE output
            (
                {
                    "rows": [
                        {
                            "column_name": "payload",
                            "column_type": "STRUCT(a INTEGER, b VARCHAR)",
                        }
                    ]
                },
                None,
            ),
        ]

        schema_list = self.runner.get_schema()
        self.assertEqual(len(schema_list), 1)
        schema = schema_list[0]

        # Ensure both raw and expanded struct fields are present
        self.assertIn("main.events", schema["name"])
        self.assertListEqual(
            schema["columns"],
            [
                {"name": "payload", "type": "STRUCT(a INTEGER, b VARCHAR)"},
                {"name": "payload.a", "type": "INTEGER"},
                {"name": "payload.b", "type": "VARCHAR"},
            ],
        )

    def test_nested_struct_expansion(self) -> None:
        runner = DuckDB({"dbpath": ":memory:"})
        runner.con.execute(
            """
            CREATE TABLE sample_struct_table (
                id INTEGER,
                info STRUCT(
                    name VARCHAR,
                    metrics STRUCT(score DOUBLE, rank INTEGER),
                    tags STRUCT(primary_tag VARCHAR, secondary_tag VARCHAR)
                )
            );
        """
        )

        schema = runner.get_schema()
        table = next(t for t in schema if t["name"] == "main.sample_struct_table")
        colnames = [c["name"] for c in table["columns"]]

        assert "info" in colnames
        assert 'info."name"' in colnames
        assert "info.metrics" in colnames
        assert "info.metrics.score" in colnames
        assert "info.metrics.rank" in colnames
        assert "info.tags.primary_tag" in colnames
        assert "info.tags.secondary_tag" in colnames

    @patch.object(DuckDB, "run_query")
    def test_motherduck_catalog_included(self, mock_run_query) -> None:
        # Test that non-default catalogs (like MotherDuck) include catalog in name
        mock_run_query.side_effect = [
            (
                {
                    "rows": [
                        {
                            "table_catalog": "sample_data",
                            "table_schema": "kaggle",
                            "table_name": "movies",
                        }
                    ]
                },
                None,
            ),
            (
                {
                    "rows": [
                        {"column_name": "title", "column_type": "VARCHAR"},
                    ]
                },
                None,
            ),
        ]

        schema = self.runner.get_schema()
        self.assertEqual(len(schema), 1)
        # Should include catalog name for non-default catalogs
        self.assertEqual(schema[0]["name"], "sample_data.kaggle.movies")

    @patch.object(DuckDB, "run_query")
    def test_error_propagation(self, mock_run_query) -> None:
        mock_run_query.return_value = (None, "boom")
        with self.assertRaises(Exception) as ctx:
            self.runner.get_schema()
        self.assertIn("boom", str(ctx.exception))


class TestTheSqlStaysInItsOwnFolder(TestCase):
    """
    DuckDB's defaults let SQL open any path the worker can, and this is a
    default data source every user in the default group can query.
    """

    def setUp(self):
        import tempfile

        self.root = tempfile.mkdtemp()
        self.mine = os.path.join(self.root, "1", "2")
        self.theirs = os.path.join(self.root, "1", "3")
        os.makedirs(self.mine)
        os.makedirs(self.theirs)
        with open(os.path.join(self.mine, "a.csv"), "w") as handle:
            handle.write("x\n1\n")
        with open(os.path.join(self.theirs, "b.csv"), "w") as handle:
            handle.write("secret\n42\n")
        self.runner = DuckDB({"dbpath": ":memory:"})
        self.runner.confine_to(self.mine)

    def run_sql(self, sql):
        return self.runner.run_query(sql, None)

    def test_its_own_uploads_are_readable(self):
        self.runner.register_uploaded_files([("a", os.path.join(self.mine, "a.csv"), True)])
        data, error = self.run_sql("SELECT * FROM a")
        self.assertIsNone(error)
        self.assertEqual([{"x": 1}], data["rows"])

    def test_another_sources_uploads_are_not(self):
        data, error = self.run_sql("SELECT * FROM read_csv_auto('{}/b.csv')".format(self.theirs))
        self.assertIsNone(data)
        self.assertIn("Permission", error)

    def test_nor_is_the_rest_of_the_machine(self):
        for sql in (
            "SELECT * FROM read_text('/etc/passwd')",
            "SELECT * FROM glob('{}/**')".format(self.root),
            "COPY (SELECT 1) TO '{}/out.csv'".format(self.root),
            "ATTACH '{}/x.db'".format(self.root),
        ):
            data, error = self.run_sql(sql)
            self.assertIsNone(data, sql)

    def test_and_it_cannot_be_switched_back_on(self):
        data, error = self.run_sql("SET enable_external_access = true")
        self.assertIsNone(data)
        data, error = self.run_sql("SELECT * FROM read_text('/etc/passwd')")
        self.assertIsNone(data)


class TestUnloadingAFileNobodyQueries(TestCase):
    """
    A file unqueried for days stops being registered. That saves every query
    on this data source the schema inference for a file nobody is reading --
    which on a source with thirty uploads is most of what a query costs before
    it starts.

    The file is untouched, so the one outcome this must never produce is a
    query failing for a file that is sitting right there on the disk.
    """

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        with open(os.path.join(self.folder, "sales.csv"), "w") as handle:
            handle.write("x\n1\n")
        with open(os.path.join(self.folder, "old_notes.csv"), "w") as handle:
            handle.write("y\n2\n")
        self.runner = DuckDB({"dbpath": ":memory:"})
        self.runner.confine_to(self.folder)

    def register(self, *files):
        self.runner.register_uploaded_files(
            [(name, os.path.join(self.folder, "{}.csv".format(name)), load) for name, load in files]
        )

    def test_an_unloaded_file_has_no_view(self):
        self.register(("sales", True), ("old_notes", False))

        self.assertIn("sales", self.runner._existing_views())
        self.assertNotIn("old_notes", self.runner._existing_views())

    def test_but_a_query_that_names_it_still_works(self):
        self.register(("sales", True), ("old_notes", False))

        data, error = self.runner.run_query("SELECT * FROM old_notes", None)

        self.assertIsNone(error)
        self.assertEqual([{"y": 2}], data["rows"])

    def test_and_it_stays_loaded_afterwards(self):
        self.register(("sales", True), ("old_notes", False))
        self.runner.run_query("SELECT * FROM old_notes", None)

        self.assertIn("old_notes", self.runner._existing_views())

    def test_the_name_is_matched_as_a_whole_word(self):
        # `notes` must not bring back `old_notes`; a substring match would load
        # half the data source on any query with a common word in it.
        self.register(("sales", True), ("old_notes", False))

        self.runner.run_query("SELECT 'notes' AS label", None)

        self.assertNotIn("old_notes", self.runner._existing_views())

    def test_unloading_drops_a_view_an_earlier_query_created(self):
        # A worker process is long-lived and its catalog outlives one query, so
        # without this the unload saves nothing after the first use.
        self.register(("sales", True), ("old_notes", True))
        self.assertIn("old_notes", self.runner._existing_views())

        self.register(("sales", True), ("old_notes", False))

        self.assertNotIn("old_notes", self.runner._existing_views())


class TestTheSchemaShowsEveryUploadedFile(TestCase):
    """
    Reading the schema is the one place unloading must not reach.

    Unloading saves query time: a file nobody asks about should not cost schema
    inference on every query that names something else. But the catalog harvest
    and the editor's schema browser both ask for the schema, and an unloaded
    file was simply missing from both -- which reads as the file having been
    deleted.

    What that looked like in practice: the harvest found an empty schema, kept
    the old entries rather than emptying them, and the Catalog page went on
    saying "last harvested 7 days ago" however often somebody pressed Harvest.
    """

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        for name, column in (("sales", "x"), ("old_notes", "y")):
            with open(os.path.join(self.folder, "{}.csv".format(name)), "w") as handle:
                handle.write("{}\n1\n".format(column))
        self.runner = DuckDB({"dbpath": ":memory:"})
        self.runner.confine_to(self.folder)
        self.runner.register_uploaded_files(
            [
                ("sales", os.path.join(self.folder, "sales.csv"), True),
                ("old_notes", os.path.join(self.folder, "old_notes.csv"), False),
            ]
        )

    def names(self):
        return {table["name"].split(".")[-1] for table in self.runner.get_schema()}

    def test_an_unloaded_file_is_in_the_schema(self):
        self.assertEqual({"sales", "old_notes"}, self.names())

    def test_with_its_columns(self):
        # The whole point of harvesting it: a name with no columns tells a
        # model nothing it could write SQL against.
        found = {table["name"].split(".")[-1]: table for table in self.runner.get_schema()}

        self.assertEqual(["y"], [column["name"] for column in found["old_notes"]["columns"]])

    def test_and_it_is_unloaded_again_afterwards(self):
        # Reading the schema is not somebody querying the file, so it must not
        # quietly undo the unload for every query that follows.
        self.runner.get_schema()

        self.assertNotIn("old_notes", self.runner._existing_views())
        self.assertIn("sales", self.runner._existing_views())

    def test_a_file_that_cannot_be_read_does_not_lose_the_rest_of_the_schema(self):
        self.runner.register_uploaded_files(
            [
                ("sales", os.path.join(self.folder, "sales.csv"), True),
                ("mystery", os.path.join(self.folder, "mystery.doc"), False),
            ]
        )

        self.assertEqual({"sales"}, self.names())

    def test_a_source_with_no_uploads_at_all_still_reports_its_schema(self):
        # `_unloaded` is only ever assigned by `register_uploaded_files`, so a
        # DuckDB source pointed at a database of its own never sets it.
        # Its own database file rather than `:memory:`, whose catalog is cached
        # per process and shared with every other test in this file.
        plain = DuckDB({"dbpath": os.path.join(self.folder, "own.duckdb")})
        plain.run_query("CREATE TABLE t (a INTEGER)", None)

        self.assertEqual(["t"], [table["name"].split(".")[-1] for table in plain.get_schema()])


class TestColumnTypes(TestCase):
    """DuckDB's own names for its types, asked of DuckDB rather than assumed.

    This is the test that would have caught the upgrade. `cursor.description`
    changed twice at once in 1.5: the type code stopped being a `str`, and the
    names stopped being DB-API ones. The first raised; the second was silent,
    and had been silently wrong the whole time -- on 1.3 only 5 of these 12
    mapped, so every number and timestamp from a DuckDB source was a string.
    """

    SAMPLE = """
        select true                   as a_bool,
               42::tinyint            as a_tinyint,
               42::integer            as a_int,
               42::bigint             as a_bigint,
               42::ubigint            as a_ubigint,
               1.5::real              as a_real,
               1.5::double            as a_double,
               1.5::decimal(10,2)     as a_decimal,
               'x'                    as a_varchar,
               date '2026-01-01'      as a_date,
               timestamp '2026-01-01' as a_timestamp,
               now()                  as a_timestamptz,
               time '12:00:00'        as a_time,
               gen_random_uuid()      as a_uuid,
               [1, 2]                 as a_list,
               {'a': 1}               as a_struct,
               interval 1 day         as a_interval
    """

    EXPECTED = {
        "a_bool": TYPE_BOOLEAN,
        "a_tinyint": TYPE_INTEGER,
        "a_int": TYPE_INTEGER,
        "a_bigint": TYPE_INTEGER,
        "a_ubigint": TYPE_INTEGER,
        "a_real": TYPE_FLOAT,
        "a_double": TYPE_FLOAT,
        # A decimal is reported as DECIMAL(10,2); a bare-name lookup misses it.
        "a_decimal": TYPE_FLOAT,
        "a_varchar": TYPE_STRING,
        "a_date": TYPE_DATE,
        "a_timestamp": TYPE_DATETIME,
        "a_timestamptz": TYPE_DATETIME,
        "a_time": TYPE_DATETIME,
        "a_uuid": TYPE_STRING,
        # A list holds a list. The type inside it is not what the column is.
        "a_list": TYPE_STRING,
        "a_struct": TYPE_STRING,
        "a_interval": TYPE_STRING,
    }

    def test_every_ordinary_column_type_is_mapped(self):
        runner = DuckDB({"dbpath": ":memory:"})
        data, error = runner.run_query(self.SAMPLE, None)
        self.assertIsNone(error)

        got = {column["name"]: column["type"] for column in data["columns"]}
        self.assertEqual(self.EXPECTED, got)

    def test_a_type_code_is_not_a_string_any_more(self):
        # The reason the upgrade broke: .upper() on a DuckDBPyType forwards to
        # its child-type lookup instead of raising a plain AttributeError.
        import duckdb

        code = duckdb.connect().execute("select 1::integer").description[0][1]
        self.assertNotIsInstance(code, str)
        with self.assertRaises(Exception):
            code.upper()
        self.assertEqual(_duckdb_type(code), TYPE_INTEGER)

    def test_an_unknown_type_is_a_string_rather_than_nothing(self):
        self.assertEqual(_duckdb_type("SOME_FUTURE_TYPE"), TYPE_STRING)
        self.assertIsNone(_duckdb_type(None))

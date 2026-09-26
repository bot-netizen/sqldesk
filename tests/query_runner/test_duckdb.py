import os
from unittest import TestCase
from unittest.mock import patch

from sqldesk.query_runner.duckdb import DuckDB


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
        self.runner.register_uploaded_files([("a", os.path.join(self.mine, "a.csv"))])
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

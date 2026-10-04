"""
Some test cases for Trino.
"""

from unittest import TestCase
from unittest.mock import patch

from trino.exceptions import DatabaseError
from trino.types import NamedRowTuple

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
)
from sqldesk.query_runner.trino import (
    Trino,
    _convert_row_types,
    _database_error_message,
    _trino_type,
)


class TestTrino(TestCase):
    catalog_name = "memory"
    schema_name = "default"
    table_name = "users"
    column_name = "id"
    column_type = "integer"

    @patch.object(Trino, "_get_catalogs")
    @patch.object(Trino, "run_query")
    def test_get_schema_no_catalog_set(self, mock_run_query, mock__get_catalogs):
        runner = Trino({})
        self._assert_schema_catalog(mock_run_query, mock__get_catalogs, runner)

    @patch.object(Trino, "_get_catalogs")
    @patch.object(Trino, "run_query")
    def test_get_schema_catalog_set(self, mock_run_query, mock__get_catalogs):
        runner = Trino({"catalog": TestTrino.catalog_name})
        self._assert_schema_catalog(mock_run_query, mock__get_catalogs, runner)

    def _assert_schema_catalog(self, mock_run_query, mock__get_catalogs, runner):
        mock_run_query.return_value = (
            {
                "rows": [
                    {
                        "table_schema": TestTrino.schema_name,
                        "table_name": TestTrino.table_name,
                        "column_name": TestTrino.column_name,
                        "data_type": TestTrino.column_type,
                    }
                ]
            },
            None,
        )
        mock__get_catalogs.return_value = [TestTrino.catalog_name]
        schema = runner.get_schema()
        expected_schema = [
            {
                "name": f"{TestTrino.catalog_name}.{TestTrino.schema_name}.{TestTrino.table_name}",
                "columns": [{"name": TestTrino.column_name, "type": TestTrino.column_type}],
            }
        ]
        self.assertEqual(schema, expected_schema)

    @patch.object(Trino, "run_query")
    def test__get_catalogs(self, mock_run_query):
        mock_run_query.return_value = ({"rows": [{"Catalog": TestTrino.catalog_name}]}, None)
        runner = Trino({})
        catalogs = runner._get_catalogs()
        expected_catalogs = [TestTrino.catalog_name]
        self.assertEqual(catalogs, expected_catalogs)

    def test_get_client_tags_parses_comma_separated_values(self):
        runner = Trino({"client_tags": "finance,  sqldesk  , ,analytics"})
        self.assertEqual(runner._get_client_tags(), ["finance", "sqldesk", "analytics"])

    def test_get_client_tags_returns_none_when_empty(self):
        runner = Trino({"client_tags": " ,  , "})
        self.assertIsNone(runner._get_client_tags())

    def test_supports_auto_limit(self):
        runner = Trino({})
        self.assertTrue(runner.supports_auto_limit)

    def test_apply_auto_limit_adds_limit_to_select(self):
        runner = Trino({})
        result = runner.apply_auto_limit("SELECT * FROM users", True)
        self.assertEqual(result, "SELECT * FROM users LIMIT 1000")

    def test_apply_auto_limit_keeps_existing_limit(self):
        runner = Trino({})
        query = "SELECT * FROM users LIMIT 10"
        self.assertEqual(runner.apply_auto_limit(query, True), query)

    def test_apply_auto_limit_disabled(self):
        runner = Trino({})
        query = "SELECT * FROM users"
        self.assertEqual(runner.apply_auto_limit(query, False), query)


class TestConvertRowTypes(TestCase):
    def test_plain_values_unchanged(self):
        self.assertEqual(_convert_row_types(42), 42)
        self.assertEqual(_convert_row_types("hello"), "hello")
        self.assertIsNone(_convert_row_types(None))

    def test_named_row_tuple_to_dict(self):
        row = NamedRowTuple([1, "alice"], ["id", "name"], ["integer", "varchar"])
        result = _convert_row_types(row)
        self.assertEqual(result, {"id": 1, "name": "alice"})

    def test_nested_row_tuple(self):
        inner = NamedRowTuple([10, 20], ["x", "y"], ["integer", "integer"])
        outer = NamedRowTuple([1, inner], ["id", "point"], ["integer", "row"])
        result = _convert_row_types(outer)
        self.assertEqual(result, {"id": 1, "point": {"x": 10, "y": 20}})

    def test_row_tuple_inside_list(self):
        row = NamedRowTuple([1, "a"], ["id", "val"], ["integer", "varchar"])
        result = _convert_row_types([row, row])
        self.assertEqual(result, [{"id": 1, "val": "a"}, {"id": 1, "val": "a"}])

    def test_unnamed_fields_get_positional_names(self):
        row = NamedRowTuple([1, 2], [None, None], ["integer", "integer"])
        result = _convert_row_types(row)
        self.assertEqual(result, {"_field0": 1, "_field1": 2})


class TestTrinoTypes(TestCase):
    """Trino reports a column's declared type, which almost never looks like the bare
    name a lookup table holds."""

    def test_bare_names_still_work(self):
        self.assertEqual(_trino_type("bigint"), TYPE_INTEGER)
        self.assertEqual(_trino_type("boolean"), TYPE_BOOLEAN)
        self.assertEqual(_trino_type("date"), TYPE_DATE)

    def test_a_decimal_is_not_an_integer(self):
        self.assertEqual(_trino_type("decimal"), TYPE_FLOAT)
        self.assertEqual(_trino_type("decimal(10,2)"), TYPE_FLOAT)

    def test_parameterised_types_are_mapped(self):
        self.assertEqual(_trino_type("varchar(255)"), TYPE_STRING)
        self.assertEqual(_trino_type("char(3)"), TYPE_STRING)

    def test_a_precise_timestamp_is_still_a_timestamp(self):
        # Trino's default is timestamp(3); before this it came back with no type.
        self.assertEqual(_trino_type("timestamp(3)"), TYPE_DATETIME)
        self.assertEqual(_trino_type("timestamp(6) with time zone"), TYPE_DATETIME)
        self.assertEqual(_trino_type("timestamp with time zone"), TYPE_DATETIME)

    def test_case_and_space_do_not_matter(self):
        self.assertEqual(_trino_type("  VARCHAR(10) "), TYPE_STRING)

    def test_structures_stay_untyped_on_purpose(self):
        # These values are dicts and lists after _convert_row_types; calling them
        # strings would be a worse answer than calling them nothing.
        self.assertIsNone(_trino_type("row(a varchar, b bigint)"))
        self.assertIsNone(_trino_type("array(varchar)"))
        self.assertIsNone(_trino_type("map(varchar, bigint)"))

    def test_nothing_is_not_a_type(self):
        self.assertIsNone(_trino_type(None))
        self.assertIsNone(_trino_type(""))


class TestTrinoDatabaseErrorMessage(TestCase):
    def test_trinos_own_message_is_preferred(self):
        err = DatabaseError({"failureInfo": {"message": "Table does not exist"}})
        self.assertEqual(_database_error_message(err), "Table does not exist")

    def test_a_missing_failure_info_does_not_lose_the_error(self):
        # This is the regression: the fallback was a set literal, `.get` on it raised
        # AttributeError, and the handler reporting the failure became the failure.
        err = DatabaseError({"message": "Query exceeded per-node memory limit"})
        self.assertEqual(_database_error_message(err), "Query exceeded per-node memory limit")

    def test_an_error_with_nothing_useful_still_reports_something(self):
        for arg in [{}, "a string", None]:
            message = _database_error_message(DatabaseError(arg))
            self.assertIn("Unspecified DatabaseError", message)

    def test_an_error_with_no_args_at_all(self):
        self.assertIn("Unspecified DatabaseError", _database_error_message(DatabaseError()))

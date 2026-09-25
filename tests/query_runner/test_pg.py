from copy import deepcopy
from unittest import TestCase

from sqldesk.query_runner.pg import _parse_dsn, apply_comments, build_schema


class TestParameters(TestCase):
    def test_parse_dsn(self):
        configuration = {"dsn": "application_name=sqldesk connect_timeout=5"}
        self.assertDictEqual(_parse_dsn(configuration), {"application_name": "sqldesk", "connect_timeout": "5"})

    def test_parse_dsn_not_permitted(self):
        configuration = {"dsn": "password=xyz"}
        self.assertRaises(ValueError, _parse_dsn, configuration)


class TestBuildSchema(TestCase):
    def test_handles_dups_between_public_and_other_schemas(self):
        results = {
            "rows": [
                {
                    "table_schema": "public",
                    "table_name": "main.users",
                    "column_name": "id",
                },
                {"table_schema": "main", "table_name": "users", "column_name": "id"},
                {"table_schema": "main", "table_name": "users", "column_name": "name"},
            ]
        }

        schema = {}

        build_schema(results, schema)

        self.assertIn("main.users", schema.keys())
        self.assertListEqual(schema["main.users"]["columns"], ["id", "name"])
        self.assertIn('public."main.users"', schema.keys())
        self.assertListEqual(schema['public."main.users"']["columns"], ["id"])

    def test_build_schema_with_data_types(self):
        results = {
            "rows": [
                {"table_schema": "main", "table_name": "users", "column_name": "id", "data_type": "integer"},
                {"table_schema": "main", "table_name": "users", "column_name": "name", "data_type": "varchar"},
            ]
        }

        schema = {}

        build_schema(results, schema)

        self.assertListEqual(
            schema["main.users"]["columns"], [{"name": "id", "type": "integer"}, {"name": "name", "type": "varchar"}]
        )


class TestApplyComments(TestCase):
    """
    `COMMENT ON` is the only place most warehouses record what a thing means,
    and it was being read by nobody.
    """

    def _schema(self):
        return {
            "orders": {
                "name": "orders",
                "columns": [{"name": "id", "type": "bigint"}, {"name": "flag_c2", "type": "boolean"}],
            },
            "plain": {"name": "plain", "columns": [{"name": "id", "type": "bigint"}]},
        }

    def _rows(self, rows):
        return {"rows": rows}

    def test_a_table_comment_lands_on_the_table(self):
        schema = self._schema()
        apply_comments(
            self._rows(
                [
                    {
                        "table_schema": "public",
                        "table_name": "orders",
                        "column_name": None,
                        "description": "Net of cancellations.",
                    }
                ]
            ),
            schema,
        )

        self.assertEqual("Net of cancellations.", schema["orders"]["description"])

    def test_a_column_comment_lands_on_the_column(self):
        schema = self._schema()
        apply_comments(
            self._rows(
                [
                    {
                        "table_schema": "public",
                        "table_name": "orders",
                        "column_name": "flag_c2",
                        "description": "Finance signed off.",
                    }
                ]
            ),
            schema,
        )

        flag = [c for c in schema["orders"]["columns"] if c["name"] == "flag_c2"][0]
        self.assertEqual("Finance signed off.", flag["description"])

    def test_a_table_nobody_documented_is_left_exactly_as_it_was(self):
        schema = self._schema()
        before = deepcopy(schema["plain"])
        apply_comments(
            self._rows([{"table_schema": "public", "table_name": "orders", "column_name": None, "description": "x"}]),
            schema,
        )

        self.assertEqual(before, schema["plain"])

    def test_a_bare_column_name_becomes_a_dict_so_it_can_carry_one(self):
        # Materialized views come back as bare names, with no type.
        schema = {"mv": {"name": "mv", "columns": ["id", "total"]}}
        apply_comments(
            self._rows(
                [{"table_schema": "public", "table_name": "mv", "column_name": "total", "description": "Gross."}]
            ),
            schema,
        )

        self.assertEqual(["id", {"name": "total", "description": "Gross."}], schema["mv"]["columns"])

    def test_a_schema_qualified_table_is_matched(self):
        schema = {"cmt.orders": {"name": "cmt.orders", "columns": [{"name": "id"}]}}
        apply_comments(
            self._rows([{"table_schema": "cmt", "table_name": "orders", "column_name": None, "description": "Yes."}]),
            schema,
        )

        self.assertEqual("Yes.", schema["cmt.orders"]["description"])

    def test_no_comments_anywhere_changes_nothing(self):
        schema = self._schema()
        before = deepcopy(schema)
        apply_comments(self._rows([]), schema)

        self.assertEqual(before, schema)

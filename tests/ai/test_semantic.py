import os
import tempfile
from unittest import mock

import yaml

from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.ai.catalog.semantic import cube_type, export_catalog, import_catalog
from sqldesk.models import MEASURE_APPROVED, CatalogColumn, CatalogMeasure, CatalogTable, db
from tests import BaseTestCase

SCHEMA = [
    {
        "name": "orders",
        "description": "One row per placed order.",
        "columns": [
            {"name": "id", "type": "bigint"},
            {"name": "user_id", "type": "bigint"},
            {"name": "amount", "type": "numeric"},
            {"name": "placed_at", "type": "timestamp"},
            {"name": "cancelled", "type": "boolean"},
            {"name": "region", "type": "varchar"},
        ],
    },
    {"name": "users", "columns": [{"name": "id", "type": "bigint"}]},
]


class HarvestHelpers(BaseTestCase):
    """
    Queries the catalog will actually learn from.

    Mining reads queries that have *run* inside the usage window, so a query
    created in a test and never executed is invisible to it -- correctly, but
    it makes for confusing tests. This gives one a fresh result, which is
    what every real saved query has.
    """

    def _ran(self, source, sql):
        query = self.factory.create_query(query_text=sql, data_source=source)
        query.latest_query_data = self.factory.create_query_result(data_source=source)
        return query


class TestCubeTypes(BaseTestCase):
    def test_sql_types_become_the_five_cube_knows(self):
        self.assertEqual("number", cube_type("bigint"))
        self.assertEqual("number", cube_type("numeric(10,2)"))
        self.assertEqual("time", cube_type("timestamp with time zone"))
        self.assertEqual("boolean", cube_type("boolean"))
        self.assertEqual("string", cube_type("varchar"))

    def test_something_unrecognised_is_a_string_rather_than_a_guess(self):
        self.assertEqual("string", cube_type("hstore"))
        self.assertEqual("string", cube_type(None))


class TestExport(HarvestHelpers):
    def _harvest(self, queries=()):
        source = self.factory.create_data_source()
        for sql in queries:
            self._ran(source, sql)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        return source

    def _export(self, source):
        directory = tempfile.mkdtemp()
        export_catalog(self.factory.org, directory, data_source=source)
        return directory

    def _orders(self, directory):
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if name == "orders.yml":
                    with open(os.path.join(root, name)) as handle:
                        return yaml.safe_load(handle)["cubes"][0]
        raise AssertionError("orders.yml was not written")

    def test_it_writes_a_cube_per_table(self):
        source = self._harvest()
        cube = self._orders(self._export(source))

        self.assertEqual("orders", cube["name"])
        self.assertEqual("orders", cube["sql_table"])
        self.assertEqual("One row per placed order.", cube["description"])

    def test_columns_become_dimensions_with_cube_types(self):
        source = self._harvest()
        cube = self._orders(self._export(source))
        types = {d["name"]: d["type"] for d in cube["dimensions"]}

        self.assertEqual("number", types["amount"])
        self.assertEqual("time", types["placed_at"])
        self.assertEqual("boolean", types["cancelled"])
        self.assertEqual("string", types["region"])

    def test_only_agreed_measures_are_written(self):
        # An export is read and approved in a pull request; filling it with
        # proposals nobody has looked at makes the diff meaningless.
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        cube = self._orders(self._export(source))
        self.assertNotIn("measures", cube)

        measure = CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).one()
        measure.status = MEASURE_APPROVED
        db.session.commit()

        cube = self._orders(self._export(source))
        self.assertEqual([{"name": "gross_revenue", "type": "sum", "sql": "amount"}], cube["measures"])

    def test_a_mined_join_becomes_a_cube_join(self):
        source = self._harvest(["SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"])
        cube = self._orders(self._export(source))

        self.assertEqual("users", cube["joins"][0]["name"])
        self.assertIn("{CUBE}.user_id = {users}.id", cube["joins"][0]["sql"])

    def test_it_is_valid_yaml_that_round_trips(self):
        source = self._harvest()
        directory = self._export(source)
        written = self._orders(directory)

        self.assertIsInstance(written, dict)


class TestImport(HarvestHelpers):
    def _harvest(self, queries=(), source=None):
        source = source or self.factory.create_data_source()
        for sql in queries:
            self._ran(source, sql)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        return source

    def _write(self, cube):
        directory = tempfile.mkdtemp()
        with open(os.path.join(directory, "orders.yml"), "w") as handle:
            yaml.safe_dump({"cubes": [cube]}, handle)
        return directory

    def _table(self, source):
        db.session.expire_all()
        return CatalogTable.query.filter(CatalogTable.data_source_id == source.id, CatalogTable.name == "orders").one()

    def test_a_description_from_a_file_is_applied(self):
        source = self._harvest()
        directory = self._write(
            {"name": "orders", "sql_table": "orders", "description": "Orders, excluding the test tenant."}
        )

        import_catalog(self.factory.org, directory)

        table = self._table(source)
        self.assertEqual("Orders, excluding the test tenant.", table.description)
        self.assertEqual("file", table.description_source)

    def test_a_dimension_description_reaches_the_column(self):
        source = self._harvest()
        directory = self._write(
            {
                "name": "orders",
                "sql_table": "orders",
                "dimensions": [{"name": "amount", "sql": "amount", "description": "Gross, before refunds."}],
            }
        )

        import_catalog(self.factory.org, directory)

        db.session.expire_all()
        column = CatalogColumn.query.filter(
            CatalogColumn.catalog_table_id == self._table(source).id, CatalogColumn.name == "amount"
        ).one()
        self.assertEqual("Gross, before refunds.", column.description)

    def test_naming_a_measure_in_a_file_agrees_it(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        directory = self._write(
            {
                "name": "orders",
                "sql_table": "orders",
                "measures": [{"name": "gross_revenue", "type": "sum", "description": "Agreed with finance."}],
            }
        )

        import_catalog(self.factory.org, directory)

        db.session.expire_all()
        measure = CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).one()
        self.assertEqual(MEASURE_APPROVED, measure.status)
        self.assertEqual("Agreed with finance.", measure.description)

    def test_a_file_cannot_redefine_what_a_measure_computes(self):
        # sql and type are what the miner found in real queries. A file that
        # could change them would let the catalog claim a definition that
        # nobody actually writes.
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        directory = self._write(
            {
                "name": "orders",
                "sql_table": "orders",
                "measures": [{"name": "gross_revenue", "type": "count", "sql": "id"}],
            }
        )

        import_catalog(self.factory.org, directory)

        db.session.expire_all()
        measure = CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).one()
        self.assertEqual("sum", measure.kind)
        self.assertEqual("amount", measure.column_name)

    def test_a_table_the_catalog_never_heard_of_is_skipped_not_invented(self):
        self._harvest()
        directory = self._write({"name": "ghosts", "sql_table": "ghosts", "description": "Not real."})

        result = import_catalog(self.factory.org, directory)

        self.assertEqual(1, result["skipped"])
        self.assertIsNone(CatalogTable.query.filter(CatalogTable.name == "ghosts").first())

    def test_unreadable_yaml_is_reported_rather_than_raised(self):
        self._harvest()
        directory = tempfile.mkdtemp()
        with open(os.path.join(directory, "broken.yml"), "w") as handle:
            handle.write("cubes: [ unclosed")

        result = import_catalog(self.factory.org, directory)

        self.assertEqual(1, result["skipped"])

    def test_the_whole_loop(self):
        # Export, edit as somebody would in a pull request, import.
        source = self._harvest()
        directory = tempfile.mkdtemp()
        export_catalog(self.factory.org, directory, data_source=source)

        path = None
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if name == "orders.yml":
                    path = os.path.join(root, name)
        with open(path) as handle:
            document = yaml.safe_load(handle)
        document["cubes"][0]["description"] = "Edited in the repo."
        with open(path, "w") as handle:
            yaml.safe_dump(document, handle)

        import_catalog(self.factory.org, directory)

        self.assertEqual("Edited in the repo.", self._table(source).description)


class TestExportedFileShape(HarvestHelpers):
    """
    What the file on disk actually looks like, since that is what somebody
    reads in a pull request.
    """

    def test_a_reviewer_sees_readable_yaml(self):
        source = self.factory.create_data_source(name="Warehouse One")
        self._ran(source, "SELECT SUM(amount) AS gross_revenue FROM orders")
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).one().status = MEASURE_APPROVED
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)

        directory = tempfile.mkdtemp()
        export_catalog(self.factory.org, directory, data_source=source)

        path = os.path.join(directory, "warehouse_one", "orders.yml")
        self.assertTrue(os.path.exists(path), "named after the data source, then the table")

        text = open(path).read()
        # Keys in the order cube documents them, not alphabetised, because a
        # reviewer reads name and sql_table before three hundred dimensions.
        self.assertLess(text.index("name:"), text.index("dimensions:"))
        self.assertIn("gross_revenue", text)
        self.assertNotIn("!!python", text, "safe_dump only, no Python tags")

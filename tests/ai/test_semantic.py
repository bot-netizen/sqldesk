import datetime
import os
import tempfile
from unittest import mock

import yaml
from sqlalchemy import event

from sqldesk import models
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.ai.catalog.semantic import cube_type, export_catalog, import_catalog
from sqldesk.models import (
    MEASURE_APPROVED,
    CatalogColumn,
    CatalogMeasure,
    CatalogTable,
    db,
)
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


class TestImportDoesNotRunOverWhatSomebodyJustWrote(TestImport):
    """
    Somebody fixes a description on the catalog page; the next import replaces
    it with the file's older sentence and their fix looks like it never saved.
    The file wins only where it is the newer statement.
    """

    def _write(self, cube, written_at=None):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "orders.yml")
        with open(path, "w") as handle:
            yaml.safe_dump({"cubes": [cube]}, handle)
        if written_at is not None:
            stamp = written_at.timestamp()
            os.utime(path, (stamp, stamp))
        return directory

    def _table(self, source):
        db.session.expire_all()
        return CatalogTable.query.filter(CatalogTable.data_source_id == source.id, CatalogTable.name == "orders").one()

    def _described_here(self, source, text, source_name="human", at=None):
        table = self._table(source)
        table.description = text
        table.description_source = source_name
        table.described_at = at or datetime.datetime.now(datetime.timezone.utc)
        db.session.commit()
        return table

    def _older_file(self, description="From the file."):
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        return self._write({"name": "orders", "sql_table": "orders", "description": description}, written_at=yesterday)

    def test_a_description_written_since_the_file_is_kept(self):
        source = self._harvest()
        self._described_here(source, "Fixed on the page.")

        result = import_catalog(self.factory.org, self._older_file())

        self.assertEqual("Fixed on the page.", self._table(source).description)
        self.assertEqual(1, result["kept"])
        self.assertEqual(0, result["tables"])

    def test_one_an_agent_wrote_is_kept_too(self):
        source = self._harvest()
        self._described_here(source, "Written through MCP.", source_name="mcp")

        import_catalog(self.factory.org, self._older_file())

        self.assertEqual("Written through MCP.", self._table(source).description)

    def test_the_engines_own_comment_is_the_files_to_replace(self):
        source = self._harvest()
        self._described_here(source, "A warehouse comment.", source_name="engine")

        import_catalog(self.factory.org, self._older_file())

        self.assertEqual("From the file.", self._table(source).description)

    def test_and_so_is_a_previous_imports(self):
        source = self._harvest()
        self._described_here(source, "An older file's words.", source_name="file")

        import_catalog(self.factory.org, self._older_file())

        self.assertEqual("From the file.", self._table(source).description)

    def test_a_file_newer_than_the_description_wins(self):
        source = self._harvest()
        self._described_here(
            source,
            "Written before the file was.",
            at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2),
        )

        import_catalog(self.factory.org, self._older_file())

        self.assertEqual("From the file.", self._table(source).description)

    def test_overwrite_takes_the_file_regardless(self):
        source = self._harvest()
        self._described_here(source, "Fixed on the page.")

        import_catalog(self.factory.org, self._older_file(), overwrite=True)

        self.assertEqual("From the file.", self._table(source).description)

    def test_a_column_somebody_described_is_kept_as_well(self):
        source = self._harvest()
        column = CatalogColumn.query.filter(
            CatalogColumn.catalog_table_id == self._table(source).id, CatalogColumn.name == "amount"
        ).one()
        column.description = "Gross, as the page says."
        column.description_source = "human"
        column.described_at = datetime.datetime.now(datetime.timezone.utc)
        db.session.commit()
        yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        directory = self._write(
            {
                "name": "orders",
                "sql_table": "orders",
                "dimensions": [{"name": "amount", "sql": "amount", "description": "From the file."}],
            },
            written_at=yesterday,
        )

        import_catalog(self.factory.org, directory)

        db.session.expire_all()
        self.assertEqual("Gross, as the page says.", models.CatalogColumn.query.get(column.id).description)


class TestImportFindsTheRightSource(HarvestHelpers):
    """
    Staging and production usually share table names. Matched on the name
    alone, a description written for one landed on whichever the database
    returned first.
    """

    _harvest = TestImport._harvest
    _write = TestImport._write
    _table = TestImport._table

    def _two(self):
        staging = self._harvest(source=self.factory.create_data_source(name="Staging"))
        production = self._harvest(source=self.factory.create_data_source(name="Production"))
        return staging, production

    def _write_in(self, folder, cube):
        directory = tempfile.mkdtemp()
        os.makedirs(os.path.join(directory, folder))
        with open(os.path.join(directory, folder, "orders.yml"), "w") as handle:
            yaml.safe_dump({"cubes": [cube]}, handle)
        return directory

    def test_the_folder_says_which_data_source(self):
        staging, production = self._two()
        directory = self._write_in("production", {"name": "orders", "description": "Production orders."})

        import_catalog(self.factory.org, directory)

        self.assertEqual("Production orders.", self._table(production).description)
        self.assertNotEqual("Production orders.", self._table(staging).description)

    def test_a_flat_file_naming_two_tables_is_skipped_not_guessed(self):
        staging, production = self._two()
        directory = self._write({"name": "orders", "description": "Which one?"})

        result = import_catalog(self.factory.org, directory)

        self.assertEqual(1, result["skipped"])
        self.assertNotEqual("Which one?", self._table(staging).description)
        self.assertNotEqual("Which one?", self._table(production).description)


class TestExportCost(HarvestHelpers):
    def test_the_statements_do_not_grow_with_the_tables(self):
        """
        Asked per table, the joins were read in full once for every table --
        tables times joins, inside the web request behind the download
        button.
        """
        source = self.factory.create_data_source()
        big = [{"name": "t{}".format(i), "columns": [{"name": "id", "type": "int"}]} for i in range(60)]
        with mock.patch.object(type(source), "get_schema", return_value=big):
            harvest_data_source(source)

        counted = []

        def count(*args, **kwargs):
            counted.append(1)

        event.listen(db.engine, "before_cursor_execute", count)
        try:
            written = export_catalog(self.factory.org, tempfile.mkdtemp(), data_source=source)
        finally:
            event.remove(db.engine, "before_cursor_execute", count)

        self.assertEqual(60, written["tables"])
        self.assertLess(len(counted), 10, "{} statements to export 60 tables".format(len(counted)))


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

    def test_a_long_description_stays_on_one_line(self):
        # The default wraps at 80 columns, which turns a one-word edit into a
        # four-line diff in a file that exists to be read as a diff.
        source = self.factory.create_data_source(name="Wrapping")
        long_text = (
            "One row per placed order, net of cancellations and excluding the internal test "
            "tenant, which is the thing everybody gets wrong the first time they use this table."
        )
        schema = [{"name": "orders", "description": long_text, "columns": [{"name": "id", "type": "bigint"}]}]
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=schema):
            harvest_data_source(source)

        directory = tempfile.mkdtemp()
        export_catalog(self.factory.org, directory, data_source=source)

        text = open(os.path.join(directory, "wrapping", "orders.yml")).read()
        description_lines = [line for line in text.splitlines() if line.strip().startswith("description:")]
        self.assertEqual(1, len(description_lines))
        self.assertIn(long_text, description_lines[0])


class TestExportingVerifiedQueries(TestExport):
    """
    Beside the cubes, not inside them: cube has no idea of a reviewed answer,
    and inventing a key in its namespace makes files that stop loading the
    day cube uses that name for something else.
    """

    def _verified_file(self, directory):
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if name == "verified_queries.yml":
                    with open(os.path.join(root, name)) as handle:
                        return yaml.safe_load(handle)["verified_queries"]
        return None

    def _confirm(self, query, **fields):
        row = models.CatalogVerifiedQuery(
            org=self.factory.org,
            query_id=query.id,
            verified_by=self.factory.user,
            query_hash=query.query_hash,
            **fields,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_a_confirmed_query_is_written_with_its_sql(self):
        source = self._harvest()
        query = self._ran(source, "select region, sum(amount) from orders group by 1")
        db.session.commit()
        self._confirm(query, question="What did each region take?", note="Excludes internal orders.")

        written = self._verified_file(self._export(source))

        self.assertEqual(1, len(written))
        self.assertEqual("What did each region take?", written[0]["question"])
        self.assertEqual("Excludes internal orders.", written[0]["note"])
        self.assertIn("sum(amount)", written[0]["sql"])
        self.assertEqual(self.factory.user.name, written[0]["verified_by"])

    def test_with_no_question_the_query_name_stands_in(self):
        source = self._harvest()
        query = self._ran(source, "select 1")
        query.name = "Revenue by region"
        db.session.commit()
        self._confirm(query)

        self.assertEqual("Revenue by region", self._verified_file(self._export(source))[0]["question"])

    def test_no_file_is_written_when_nothing_is_confirmed(self):
        # An empty file in a directory people read as a diff is noise that
        # never goes away.
        source = self._harvest()
        self._ran(source, "select 1")
        db.session.commit()

        self.assertIsNone(self._verified_file(self._export(source)))

    def test_a_query_edited_since_is_left_out(self):
        # An export is something people approve. A line claiming a query is
        # verified when it has been edited since would be the one claim in
        # the file that is false.
        source = self._harvest()
        query = self._ran(source, "select 1")
        db.session.commit()
        self._confirm(query)
        query.query_text = "select 2"
        query.query_hash = models.utils.gen_query_hash(query.query_text)
        db.session.commit()

        self.assertIsNone(self._verified_file(self._export(source)))

    def test_the_cube_files_are_untouched_by_it(self):
        # The point of a separate file: adding this must not change a byte of
        # what cube reads.
        source = self._harvest()
        query = self._ran(source, "select 1")
        db.session.commit()
        before = self._orders(self._export(source))

        self._confirm(query, question="Anything")

        self.assertEqual(before, self._orders(self._export(source)))

    def test_it_is_valid_yaml_that_round_trips(self):
        source = self._harvest()
        query = self._ran(source, "select 'it''s'\n-- a comment with: a colon\nfrom orders")
        db.session.commit()
        self._confirm(query, question="Does quoting survive?")

        written = self._verified_file(self._export(source))

        self.assertIn("it''s", written[0]["sql"])
        self.assertIn("a comment with: a colon", written[0]["sql"])

import datetime

import mock
from mock import patch

from sqldesk import settings
from sqldesk.models import (
    CatalogColumn,
    CatalogMeasure,
    CatalogRelationship,
    CatalogTable,
    DataSource,
    Query,
    QueryResult,
    db,
)
from sqldesk.utils.configuration import ConfigurationContainer
from tests import BaseTestCase


class DataSourceTest(BaseTestCase):
    def test_get_schema(self):
        return_value = [{"name": "table", "columns": []}]

        with mock.patch("sqldesk.query_runner.pg.PostgreSQL.get_schema") as patched_get_schema:
            patched_get_schema.return_value = return_value

            schema = self.factory.data_source.get_schema()

            self.assertEqual(return_value, schema)

    def test_get_schema_uses_cache(self):
        return_value = [{"name": "table", "columns": []}]
        with mock.patch("sqldesk.query_runner.pg.PostgreSQL.get_schema") as patched_get_schema:
            patched_get_schema.return_value = return_value

            self.factory.data_source.get_schema()
            schema = self.factory.data_source.get_schema()

            self.assertEqual(return_value, schema)
            self.assertEqual(patched_get_schema.call_count, 1)

    def test_get_schema_skips_cache_with_refresh_true(self):
        return_value = [{"name": "table", "columns": []}]
        with mock.patch("sqldesk.query_runner.pg.PostgreSQL.get_schema") as patched_get_schema:
            patched_get_schema.return_value = return_value

            self.factory.data_source.get_schema()
            new_return_value = [{"name": "new_table", "columns": []}]
            patched_get_schema.return_value = new_return_value
            schema = self.factory.data_source.get_schema(refresh=True)

            self.assertEqual(new_return_value, schema)
            self.assertEqual(patched_get_schema.call_count, 2)

    def test_schema_sorter(self):
        input_data = [
            {"name": "zoo", "columns": ["is_zebra", "is_snake", "is_cow"]},
            {
                "name": "all_terain_vehicle",
                "columns": ["has_wheels", "has_engine", "has_all_wheel_drive"],
            },
        ]

        expected_output = [
            {
                "name": "all_terain_vehicle",
                "columns": ["has_all_wheel_drive", "has_engine", "has_wheels"],
            },
            {"name": "zoo", "columns": ["is_cow", "is_snake", "is_zebra"]},
        ]

        real_output = self.factory.data_source._sort_schema(input_data)

        self.assertEqual(real_output, expected_output)

    def test_model_uses_schema_sorter(self):
        orig_schema = [
            {"name": "zoo", "columns": ["is_zebra", "is_snake", "is_cow"]},
            {
                "name": "all_terain_vehicle",
                "columns": ["has_wheels", "has_engine", "has_all_wheel_drive"],
            },
        ]

        sorted_schema = [
            {
                "name": "all_terain_vehicle",
                "columns": ["has_all_wheel_drive", "has_engine", "has_wheels"],
            },
            {"name": "zoo", "columns": ["is_cow", "is_snake", "is_zebra"]},
        ]

        with mock.patch("sqldesk.query_runner.pg.PostgreSQL.get_schema") as patched_get_schema:
            patched_get_schema.return_value = orig_schema

            out_schema = self.factory.data_source.get_schema()

            self.assertEqual(out_schema, sorted_schema)

    @patch("sqldesk.redis_connection.set")
    def test_expires_schema(self, mock_redis):
        # The refresh interval plus a week. The periodic refresh is what keeps
        # this cache warm; the week is the grace for an install where it is not
        # running, so the schema browser still has something to show.
        #
        # Derived rather than written out as a number. It was `606600` -- 30
        # minutes and seven days -- and moving the default to 180 minutes in
        # 0.7.8 therefore failed a test that is not about the default at all.
        expected_ttl = int(datetime.timedelta(minutes=settings.SCHEMAS_REFRESH_SCHEDULE, days=7).total_seconds())

        with mock.patch("sqldesk.query_runner.pg.PostgreSQL.get_schema") as patched_get_schema:
            patched_get_schema.return_value = None
            self.factory.data_source.get_schema(refresh=True)

        mock_redis.assert_called_with("data_source:schema:1", "null", ex=expected_ttl)


class TestDataSourceCreate(BaseTestCase):
    def test_adds_data_source_to_default_group(self):
        data_source = DataSource.create_with_group(
            org=self.factory.org,
            name="test",
            options=ConfigurationContainer.from_json('{"dbname": "test"}'),
            type="pg",
        )
        self.assertIn(self.factory.org.default_group.id, data_source.groups)


class TestDataSourceIsPaused(BaseTestCase):
    def test_returns_false_by_default(self):
        self.assertFalse(self.factory.data_source.paused)

    def test_persists_selection(self):
        self.factory.data_source.pause()
        self.assertTrue(self.factory.data_source.paused)

        self.factory.data_source.resume()
        self.assertFalse(self.factory.data_source.paused)

    def test_allows_setting_reason(self):
        reason = "Some good reason."
        self.factory.data_source.pause(reason)
        self.assertTrue(self.factory.data_source.paused)
        self.assertEqual(self.factory.data_source.pause_reason, reason)

    def test_resume_clears_reason(self):
        self.factory.data_source.pause("Reason")
        self.factory.data_source.resume()
        self.assertEqual(self.factory.data_source.pause_reason, None)

    def test_reason_is_none_by_default(self):
        self.assertEqual(self.factory.data_source.pause_reason, None)


class TestDataSourceDelete(BaseTestCase):
    def test_deletes_the_data_source(self):
        data_source = self.factory.create_data_source()
        data_source.delete()

        self.assertIsNone(DataSource.query.get(data_source.id))

    def test_sets_queries_data_source_to_null(self):
        data_source = self.factory.create_data_source()
        query = self.factory.create_query(data_source=data_source)

        data_source.delete()
        self.assertIsNone(DataSource.query.get(data_source.id))
        self.assertIsNone(Query.query.get(query.id).data_source_id)

    def test_deletes_child_models(self):
        data_source = self.factory.create_data_source()
        self.factory.create_query_result(data_source=data_source)
        self.factory.create_query(
            data_source=data_source,
            latest_query_data=self.factory.create_query_result(data_source=data_source),
        )

        data_source.delete()
        self.assertIsNone(DataSource.query.get(data_source.id))
        self.assertEqual(0, QueryResult.query.filter(QueryResult.data_source == data_source).count())

    @patch("sqldesk.redis_connection.delete")
    def test_deletes_schema(self, mock_redis):
        data_source = self.factory.create_data_source()
        data_source.delete()

        mock_redis.assert_called_with(data_source._schema_key)


class TestDeletingASourceTheCatalogKnowsAbout(BaseTestCase):
    """
    Deleting a data source worked until somebody described one of its tables.

    `catalog_tables`, `catalog_measures` and `catalog_relationships` all
    carry a NOT NULL reference to `data_sources` and none of them cascade,
    so the delete failed outright with a ForeignKeyViolation. The catalog
    arrived after `DataSource.delete` was written and nothing brought the
    two together; every test here created a source with queries and results
    on it and never with a catalog.
    """

    def describe(self, data_source):
        org = data_source.org
        table = CatalogTable(org_id=org.id, data_source_id=data_source.id, name="orders")
        db.session.add(table)
        db.session.flush()
        db.session.add(CatalogColumn(catalog_table_id=table.id, name="total"))
        db.session.add(
            CatalogMeasure(
                org_id=org.id,
                data_source_id=data_source.id,
                table_name="orders",
                name="revenue",
                kind="sum",
                column_name="total",
            )
        )
        db.session.add(
            CatalogRelationship(
                org_id=org.id,
                data_source_id=data_source.id,
                left_table="orders",
                left_column="customer_id",
                right_table="customers",
                right_column="id",
            )
        )
        db.session.commit()
        return table

    def test_a_described_source_can_still_be_deleted(self):
        data_source = self.factory.create_data_source()
        self.describe(data_source)

        data_source.delete()

        self.assertIsNone(DataSource.query.get(data_source.id))

    def test_what_the_catalog_knew_goes_with_it(self):
        data_source = self.factory.create_data_source()
        table = self.describe(data_source)

        data_source.delete()

        self.assertEqual(0, CatalogTable.query.filter(CatalogTable.data_source_id == data_source.id).count())
        self.assertEqual(0, CatalogMeasure.query.filter(CatalogMeasure.data_source_id == data_source.id).count())
        self.assertEqual(
            0, CatalogRelationship.query.filter(CatalogRelationship.data_source_id == data_source.id).count()
        )
        # Columns hang off tables and do not cascade either, so taking the
        # tables first fails one constraint further down.
        self.assertEqual(0, CatalogColumn.query.filter(CatalogColumn.catalog_table_id == table.id).count())

    def test_another_source_keeps_its_catalog(self):
        mine = self.factory.create_data_source()
        theirs = self.factory.create_data_source(name="Untouched")
        self.describe(mine)
        self.describe(theirs)

        mine.delete()

        self.assertEqual(1, CatalogTable.query.filter(CatalogTable.data_source_id == theirs.id).count())
        self.assertEqual(1, CatalogMeasure.query.filter(CatalogMeasure.data_source_id == theirs.id).count())

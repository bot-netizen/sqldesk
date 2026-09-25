from unittest import mock

from sqldesk.ai.catalog.harvest import build_card, harvest_data_source
from sqldesk.ai.catalog.retrieve import context_for, find_tables
from sqldesk.models import CatalogColumn, CatalogRelationship, CatalogTable, db
from tests import BaseTestCase

SCHEMA = [
    {
        "name": "orders",
        "columns": [
            {"name": "id", "type": "bigint"},
            {"name": "user_id", "type": "bigint"},
            {"name": "amount", "type": "decimal"},
            {"name": "note", "type": "text"},
        ],
    },
    {"name": "users", "columns": [{"name": "id", "type": "bigint"}, {"name": "email", "type": "varchar"}]},
    {"name": "audit_log", "columns": [{"name": "id", "type": "bigint"}]},
]


class TestHarvest(BaseTestCase):
    def _harvest(self, queries=(), schema=SCHEMA):
        source = self.factory.create_data_source()
        for sql in queries:
            self.factory.create_query(query_text=sql, data_source=source)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=schema):
            result = harvest_data_source(source)
        return source, result

    def test_it_records_what_the_source_has(self):
        source, result = self._harvest()
        self.assertEqual(3, result["tables"])
        names = {t.name for t in CatalogTable.query.filter(CatalogTable.data_source_id == source.id)}
        self.assertEqual({"orders", "users", "audit_log"}, names)

    def test_running_it_twice_updates_rather_than_duplicates(self):
        source, _ = self._harvest()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        self.assertEqual(3, CatalogTable.query.filter(CatalogTable.data_source_id == source.id).count())

    def test_usage_comes_from_the_saved_queries(self):
        source, _ = self._harvest(
            queries=[
                "SELECT amount FROM orders WHERE id = 1",
                "SELECT amount FROM orders WHERE id = 2",
            ]
        )
        orders = CatalogTable.query.filter(CatalogTable.name == "orders").one()
        audit = CatalogTable.query.filter(CatalogTable.name == "audit_log").one()
        self.assertEqual(2, orders.usage_count)
        self.assertEqual(0, audit.usage_count, "a table nobody queries stays at zero")

    def test_column_usage_separates_the_used_from_the_ignored(self):
        source, _ = self._harvest(queries=["SELECT amount FROM orders WHERE id = 1"])
        orders = CatalogTable.query.filter(CatalogTable.name == "orders").one()
        counts = {
            c.name: c.usage_count for c in CatalogColumn.query.filter(CatalogColumn.catalog_table_id == orders.id)
        }
        self.assertEqual(1, counts["amount"])
        self.assertEqual(0, counts["note"], "the column nobody selects is how a 300-column table is pruned")

    def test_the_join_graph_is_mined_not_declared(self):
        # No foreign keys anywhere; this comes from what people wrote.
        source, _ = self._harvest(queries=["SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"])
        edge = CatalogRelationship.query.filter(CatalogRelationship.data_source_id == source.id).one()
        self.assertEqual(
            ("orders", "user_id", "users", "id"),
            (edge.left_table, edge.left_column, edge.right_table, edge.right_column),
        )
        self.assertEqual(1, edge.observed_count)

    def test_the_same_join_written_twice_is_counted_twice_not_duplicated(self):
        sql = "SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"
        source, _ = self._harvest(queries=[sql, sql])
        edge = CatalogRelationship.query.filter(CatalogRelationship.data_source_id == source.id).one()
        self.assertEqual(2, edge.observed_count)

    def test_harvesting_again_does_not_collide_on_the_edge_index(self):
        # The upsert exists for exactly this: the harvester runs on a schedule.
        sql = "SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"
        source, _ = self._harvest(queries=[sql])
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        self.assertEqual(1, CatalogRelationship.query.filter(CatalogRelationship.data_source_id == source.id).count())

    def test_a_runner_that_can_say_more_is_asked(self):
        source = self.factory.create_data_source()
        richer = [
            {"name": "orders", "columns": [{"name": "id", "type": "bigint"}], "properties": {"partitioned_by": "day"}}
        ]
        runner = source.query_runner
        with mock.patch.object(type(source), "query_runner", new_callable=mock.PropertyMock) as prop:
            prop.return_value = mock.Mock(get_catalog_metadata=mock.Mock(return_value=richer), wraps=runner)
            harvest_data_source(source)
        self.assertEqual(
            {"partitioned_by": "day"}, CatalogTable.query.filter(CatalogTable.name == "orders").one().properties
        )

    def test_a_runner_whose_extra_fails_still_gets_its_schema(self):
        source = self.factory.create_data_source()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            with mock.patch.object(type(source), "query_runner", new_callable=mock.PropertyMock) as prop:
                prop.return_value = mock.Mock(get_catalog_metadata=mock.Mock(side_effect=RuntimeError("boom")))
                harvest_data_source(source)
        self.assertEqual(3, CatalogTable.query.filter(CatalogTable.data_source_id == source.id).count())


class TestCards:
    def test_a_card_is_ddl_shaped_not_json(self):
        table = mock.Mock(name_="orders", usage_count=4)
        table.name = "orders"
        card = build_card(table, [("id", "bigint"), ("amount", "decimal")], [("users", 9)])
        assert "orders(id bigint, amount decimal)" in card
        assert "used by 4 saved queries" in card
        assert "joined with users (9)" in card

    def test_a_wide_table_says_how_much_it_left_out(self):
        table = mock.Mock(usage_count=0)
        table.name = "wide"
        columns = [("c{}".format(i), "int") for i in range(60)]
        card = build_card(table, columns, [])
        assert "+30 more columns" in card


class TestRetrieval(BaseTestCase):
    def _catalogued(self):
        source = self.factory.create_data_source()
        for name, uses in (("orders", 10), ("order_archive", 1), ("unrelated", 5)):
            db.session.add(
                CatalogTable(org=self.factory.org, data_source=source, name=name, usage_count=uses, card=name)
            )
        db.session.commit()
        return source

    def test_the_table_people_use_wins(self):
        # Two names both match "order"; usage is what separates them.
        source = self._catalogued()
        found = find_tables(self.factory.org, "revenue by order", data_source=source)
        self.assertEqual("orders", found[0].name)

    def test_a_question_in_nobodys_vocabulary_still_gets_the_busy_tables(self):
        # Better than nothing, and the normal case before a glossary exists.
        source = self._catalogued()
        found = find_tables(self.factory.org, "how much money did we make", data_source=source)
        self.assertEqual("orders", found[0].name)

    def test_context_carries_the_cards(self):
        source = self._catalogued()
        context = context_for(self.factory.org, "orders", data_source=source)
        self.assertEqual("orders", context["tables"][0]["card"])


class TestRankingOnRealShapes(BaseTestCase):
    """
    The failure that name-only matching actually produced: "revenue by region"
    names no table, matched `region_targets` -- a four-row lookup -- and
    missed `orders`, which has a `region` column and forty-three queries.
    """

    def _warehouse(self):
        source = self.factory.create_data_source()
        orders = CatalogTable(org=self.factory.org, data_source=source, name="orders", usage_count=43, card="orders")
        targets = CatalogTable(
            org=self.factory.org, data_source=source, name="region_targets", usage_count=4, card="region_targets"
        )
        db.session.add_all([orders, targets])
        db.session.flush()
        db.session.add_all(
            [
                CatalogColumn(catalog_table=orders, name="amount", usage_count=30),
                CatalogColumn(catalog_table=orders, name="region", usage_count=20),
                CatalogColumn(catalog_table=targets, name="target", usage_count=4),
            ]
        )
        db.session.add(
            CatalogRelationship(
                org=self.factory.org,
                data_source=source,
                left_table="orders",
                left_column="region",
                right_table="region_targets",
                right_column="region",
                observed_count=4,
            )
        )
        db.session.commit()
        return source

    def test_a_column_name_is_enough_to_match_a_table(self):
        source = self._warehouse()
        names = [t.name for t in find_tables(self.factory.org, "revenue by region", data_source=source)]
        self.assertEqual("orders", names[0], "the table people use, not the one whose name happens to match")

    def test_a_matched_tables_neighbours_come_with_it(self):
        # A join is itself a reason to be included: `orders` is no use without
        # `region_targets` if the question compares one to the other.
        source = self._warehouse()
        context = context_for(self.factory.org, "amount", data_source=source)
        self.assertEqual({"orders", "region_targets"}, {t["name"] for t in context["tables"]})

    def test_the_neighbour_does_not_outrank_the_match(self):
        source = self._warehouse()
        context = context_for(self.factory.org, "amount", data_source=source)
        self.assertEqual("orders", context["tables"][0]["name"])

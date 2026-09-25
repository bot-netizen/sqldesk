import datetime
from unittest import mock

from sqldesk import settings
from sqldesk.ai.catalog.harvest import build_card, harvest_data_source
from sqldesk.ai.catalog.retrieve import context_for, find_tables
from sqldesk.models import (
    MEASURE_APPROVED,
    MEASURE_DENIED,
    CatalogColumn,
    CatalogMeasure,
    CatalogRelationship,
    CatalogTable,
    db,
)
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


class TestHarvest(HarvestHelpers):
    def _harvest(self, queries=(), schema=SCHEMA):
        source = self.factory.create_data_source()
        for sql in queries:
            self._ran(source, sql)
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
        card = build_card("orders", 4, [("id", "bigint", 0), ("amount", "decimal", 0)], [("users", 9)])
        assert "orders(id bigint, amount decimal)" in card
        assert "used by 4 saved queries" in card
        assert "joined with users (9)" in card

    def test_a_wide_table_says_how_much_it_left_out(self):
        columns = [("c{}".format(i), "int", 0) for i in range(60)]
        card = build_card("wide", 0, columns, [])
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


class TestHarvestDoesNotScaleWithRowCount(BaseTestCase):
    """
    The first version read then wrote one row at a time: 200 tables of 40
    columns came to 25,031 statements and 13 seconds, which extrapolates to
    roughly 375,000 statements on a three-thousand table warehouse.

    Bulk upserts made that 22 statements and 0.7s. This pins the shape of it
    -- a constant, not a multiple of the schema -- because the regression is
    invisible on the small schemas every other test here uses.
    """

    def test_the_statement_count_does_not_follow_the_schema(self):
        from sqlalchemy import event

        source = self.factory.create_data_source()
        big = [
            {"name": "t{}".format(i), "columns": [{"name": "c{}".format(j), "type": "int"} for j in range(40)]}
            for i in range(100)
        ]

        counted = []

        def count(*args, **kwargs):
            counted.append(1)

        # The same function object has to be handed to `remove` that was
        # handed to `listen`; a lambda cannot be taken off again.
        event.listen(db.engine, "before_cursor_execute", count)
        try:
            with mock.patch.object(type(source), "get_schema", return_value=big):
                harvest_data_source(source)
        finally:
            event.remove(db.engine, "before_cursor_execute", count)

        self.assertLess(
            len(counted),
            120,
            "harvest issued {} statements for 100 tables; it should not grow with the schema".format(len(counted)),
        )
        self.assertEqual(100, CatalogTable.query.filter(CatalogTable.data_source_id == source.id).count())

    def test_a_table_dropped_from_the_warehouse_leaves_the_catalog(self):
        # Otherwise it is offered to a model forever and every query written
        # against it fails.
        source = self.factory.create_data_source()
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA):
            harvest_data_source(source)
        with mock.patch.object(type(source), "get_schema", return_value=SCHEMA[:1]):
            harvest_data_source(source)
        names = {t.name for t in CatalogTable.query.filter(CatalogTable.data_source_id == source.id)}
        self.assertEqual({"orders"}, names)


class TestRetrievalIsOrgScopedByConstruction(BaseTestCase):
    def test_another_orgs_columns_are_not_even_scanned(self):
        """
        A CatalogColumn carries no org of its own -- it belongs to one through
        its table. The column subquery was unconstrained, and the outer filter
        still made the result correct, which is exactly what makes it the kind
        of mistake nobody notices until the subquery is reused somewhere the
        outer filter is not.
        """
        mine = self.factory.create_data_source()
        ours = CatalogTable(org=self.factory.org, data_source=mine, name="ours", usage_count=1, card="ours")
        db.session.add(ours)
        db.session.flush()
        db.session.add(CatalogColumn(catalog_table=ours, name="shared_name", usage_count=1))

        other_org = self.factory.create_org(name="Other", slug="other-scope")
        theirs_source = self.factory.create_data_source(org=other_org)
        theirs = CatalogTable(org=other_org, data_source=theirs_source, name="theirs", usage_count=99, card="theirs")
        db.session.add(theirs)
        db.session.flush()
        db.session.add(CatalogColumn(catalog_table=theirs, name="shared_name", usage_count=99))
        db.session.commit()

        found = [t.name for t in find_tables(self.factory.org, "shared_name")]
        self.assertEqual(["ours"], found)


DESCRIBED = [
    {
        "name": "orders",
        "description": "One row per placed order, net of cancellations.",
        "columns": [
            {"name": "id", "type": "bigint"},
            {"name": "flag_c2", "type": "boolean", "description": "True once finance has signed the order off."},
        ],
    }
]


class TestDescriptions(HarvestHelpers):
    """
    What a table *means* cannot be derived from its shape or from how often
    anyone queries it. Some engines carry it already -- MySQL returns
    `table_comment` and `column_comment` -- and it used to be dropped between
    the runner and the catalog.
    """

    def _harvest(self, schema, source=None):
        source = source or self.factory.create_data_source()
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=schema):
            harvest_data_source(source)
        return source

    def _table(self, source):
        # The harvester writes with Core statements, which the session knows
        # nothing about. Without expiring first, a row this test loaded or set
        # earlier comes back from the identity map and the assertion checks
        # what the test itself wrote -- which is how the guard below passed
        # against an implementation that had no guard in it.
        db.session.expire_all()
        return CatalogTable.query.filter(CatalogTable.data_source_id == source.id, CatalogTable.name == "orders").one()

    def test_a_description_the_engine_gave_us_is_kept(self):
        source = self._harvest(DESCRIBED)
        table = self._table(source)

        self.assertEqual("One row per placed order, net of cancellations.", table.description)
        self.assertEqual("engine", table.description_source)

    def test_a_column_comment_is_kept_too(self):
        source = self._harvest(DESCRIBED)
        column = CatalogColumn.query.filter(
            CatalogColumn.catalog_table_id == self._table(source).id, CatalogColumn.name == "flag_c2"
        ).one()

        self.assertEqual("True once finance has signed the order off.", column.description)

    def test_the_card_puts_the_description_where_a_model_will_read_it(self):
        source = self._harvest(DESCRIBED)
        card = self._table(source).card

        self.assertIn("One row per placed order", card)
        self.assertIn("/* True once finance has signed the order off. */", card)

    def test_harvesting_again_does_not_erase_what_a_person_wrote(self):
        # The whole point. A harvest runs on a schedule and a person writes a
        # sentence once; if the schedule wins, the sentence disappears and
        # nobody is watching a cron job to notice.
        source = self._harvest(DESCRIBED)
        table = self._table(source)
        table.description = "Orders, excluding the test tenant."
        table.description_source = "human"
        db.session.commit()

        # The engine still offers its own wording, so this is a contest the
        # human has to win -- not merely an absence they survive.
        self._harvest(DESCRIBED, source=source)

        table = self._table(source)
        self.assertEqual("Orders, excluding the test tenant.", table.description)
        self.assertEqual("human", table.description_source)

    def test_a_persons_words_reach_the_card_too(self):
        # Keeping the description in the row is only half of it. The card is
        # what a model is actually handed, and it was rebuilt from what the
        # *engine* said -- so a sentence somebody typed survived in the
        # database and vanished from the one place it was meant to appear.
        source = self._harvest(DESCRIBED)
        table = self._table(source)
        table.description = "Orders, excluding the test tenant."
        table.description_source = "human"
        db.session.commit()

        self._harvest(DESCRIBED, source=source)

        self.assertIn("Orders, excluding the test tenant.", self._table(source).card)

    def test_the_engine_may_still_fill_a_blank(self):
        source = self._harvest([{"name": "orders", "columns": [{"name": "id", "type": "bigint"}]}])
        self.assertIsNone(self._table(source).description)

        self._harvest(DESCRIBED, source=source)
        self.assertEqual("One row per placed order, net of cancellations.", self._table(source).description)

    def test_a_description_imported_from_a_file_is_protected_too(self):
        # "file" is a person's words that arrived by another road. Protecting
        # only "human" would let the next harvest overwrite a repo.
        source = self._harvest(DESCRIBED)
        table = self._table(source)
        table.description = "From the semantic repo."
        table.description_source = "file"
        db.session.commit()

        self._harvest(DESCRIBED, source=source)

        table = self._table(source)
        self.assertEqual("From the semantic repo.", table.description)
        self.assertEqual("file", table.description_source)


class TestMeasureProposals(HarvestHelpers):
    """
    Mined from saved SQL, and believed only once somebody says so. A metric
    definition that is merely plausible is worse than none: the wrong revenue
    number is still a revenue number.
    """

    SCHEMA = [{"name": "orders", "columns": [{"name": "amount", "type": "numeric"}]}]

    def _harvest(self, queries, source=None):
        source = source or self.factory.create_data_source()
        for sql in queries:
            self._ran(source, sql)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)
        return source

    def _measures(self, source):
        db.session.expire_all()
        return CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).all()

    def test_a_named_aggregate_is_proposed(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        found = self._measures(source)

        self.assertEqual(1, len(found))
        self.assertEqual("gross_revenue", found[0].name)
        self.assertEqual("sum", found[0].kind)

    def test_a_proposal_is_not_approved(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])

        self.assertEqual("proposed", self._measures(source)[0].status)

    def test_an_unapproved_measure_stays_off_the_card(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        table = CatalogTable.query.filter(
            CatalogTable.data_source_id == source.id, CatalogTable.name == "orders"
        ).one()

        self.assertNotIn("gross_revenue", table.card)

    def test_an_approved_one_reaches_the_card(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        measure = self._measures(source)[0]
        measure.status = MEASURE_APPROVED
        db.session.commit()

        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

        db.session.expire_all()
        table = CatalogTable.query.filter(
            CatalogTable.data_source_id == source.id, CatalogTable.name == "orders"
        ).one()
        self.assertIn("gross_revenue = SUM(amount)", table.card)

    def test_harvesting_again_does_not_un_approve_anything(self):
        source = self._harvest(["SELECT SUM(amount) AS gross_revenue FROM orders"])
        measure = self._measures(source)[0]
        measure.status = MEASURE_APPROVED
        measure.description = "Agreed with finance."
        db.session.commit()

        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

        again = self._measures(source)[0]
        self.assertEqual(MEASURE_APPROVED, again.status)
        self.assertEqual("Agreed with finance.", again.description)


class TestDenial(HarvestHelpers):
    """
    A proposal nobody can reject is one that comes back every night until
    the list stops being read.
    """

    SCHEMA = [{"name": "orders", "columns": [{"name": "amount", "type": "numeric"}]}]
    SQL = "SELECT SUM(amount) AS gross_revenue FROM orders"

    def _harvest(self, source=None, queries=(SQL,)):
        source = source or self.factory.create_data_source()
        for sql in queries:
            self._ran(source, sql)
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)
        return source

    def _measure(self, source):
        db.session.expire_all()
        return CatalogMeasure.query.filter(CatalogMeasure.data_source_id == source.id).one()

    def test_a_denied_measure_stays_denied_through_a_harvest(self):
        source = self._harvest()
        measure = self._measure(source)
        measure.status = MEASURE_DENIED
        db.session.commit()

        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

        self.assertEqual(MEASURE_DENIED, self._measure(source).status)

    def test_a_denied_measure_never_reaches_a_card(self):
        source = self._harvest()
        measure = self._measure(source)
        measure.status = MEASURE_DENIED
        db.session.commit()

        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

        db.session.expire_all()
        table = CatalogTable.query.filter(
            CatalogTable.data_source_id == source.id, CatalogTable.name == "orders"
        ).one()
        self.assertNotIn("gross_revenue", table.card)

    def test_its_count_still_moves_because_that_is_a_fact(self):
        # Denying a definition says we do not stand behind it, not that
        # nobody writes it. The count is evidence either way.
        source = self._harvest()
        measure = self._measure(source)
        measure.status = MEASURE_DENIED
        db.session.commit()
        before = self._measure(source).usage_count

        self._ran(source, "SELECT SUM(amount) AS gross_revenue FROM orders WHERE region = 'north'")
        db.session.commit()
        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

        self.assertGreater(self._measure(source).usage_count, before)
        self.assertEqual(MEASURE_DENIED, self._measure(source).status)


class TestUsageWindow(HarvestHelpers):
    """
    Only what has run lately teaches the catalog anything.

    Measured by when a query last *ran*, not when it was last edited: a
    dashboard refreshed every morning and untouched for a year is the most
    important thing in the warehouse.
    """

    SCHEMA = [{"name": "orders", "columns": [{"name": "amount", "type": "numeric"}]}]

    def _table(self, source):
        db.session.expire_all()
        return CatalogTable.query.filter(CatalogTable.data_source_id == source.id, CatalogTable.name == "orders").one()

    def _harvest(self, source):
        with mock.patch.object(type(source), "get_schema", return_value=self.SCHEMA):
            harvest_data_source(source)

    def test_a_query_that_ran_inside_the_window_counts(self):
        source = self.factory.create_data_source()
        self._ran(source, "SELECT SUM(amount) FROM orders")
        db.session.commit()

        with mock.patch.object(settings, "CATALOG_USAGE_WINDOW_HOURS", 168):
            self._harvest(source)

        self.assertEqual(1, self._table(source).usage_count)

    def test_a_query_that_last_ran_before_it_does_not(self):
        source = self.factory.create_data_source()
        query = self._ran(source, "SELECT SUM(amount) FROM orders")
        query.latest_query_data.retrieved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=30
        )
        db.session.commit()

        with mock.patch.object(settings, "CATALOG_USAGE_WINDOW_HOURS", 168):
            self._harvest(source)

        self.assertEqual(0, self._table(source).usage_count)

    def test_editing_a_query_does_not_make_it_recent(self):
        # Editing is a poor proxy for mattering, and using it would let a
        # query somebody tweaked and never ran outvote a live dashboard.
        source = self.factory.create_data_source()
        query = self._ran(source, "SELECT SUM(amount) FROM orders")
        query.latest_query_data.retrieved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=30
        )
        query.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.session.commit()

        with mock.patch.object(settings, "CATALOG_USAGE_WINDOW_HOURS", 168):
            self._harvest(source)

        self.assertEqual(0, self._table(source).usage_count)

    def test_a_query_that_has_never_run_is_never_mined(self):
        source = self.factory.create_data_source()
        self.factory.create_query(query_text="SELECT SUM(amount) FROM orders", data_source=source)
        db.session.commit()

        with mock.patch.object(settings, "CATALOG_USAGE_WINDOW_HOURS", 168):
            self._harvest(source)

        self.assertEqual(0, self._table(source).usage_count)

    def test_zero_means_every_saved_query_however_old(self):
        source = self.factory.create_data_source()
        query = self._ran(source, "SELECT SUM(amount) FROM orders")
        query.latest_query_data.retrieved_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=900
        )
        db.session.commit()

        with mock.patch.object(settings, "CATALOG_USAGE_WINDOW_HOURS", 0):
            self._harvest(source)

        self.assertEqual(1, self._table(source).usage_count)

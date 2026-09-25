from sqldesk.ai.catalog.mine import mine, mine_all, strip_parameters


class TestParameters:
    """
    Saved SQL here is Mustache. `{{ region }}` is not SQL, sqlglot refuses the
    whole statement over it, and a parameterized query is usually the
    interesting one -- so this is the difference between mining the good
    queries and skipping them.
    """

    def test_a_parameter_becomes_a_literal_not_a_hole(self):
        # Removed, `WHERE x = ` is not a predicate and the parse still fails.
        assert "{{" not in strip_parameters("SELECT * FROM t WHERE x = {{ region }}")

    def test_a_parameterized_query_still_yields_its_tables(self):
        found = mine("SELECT id FROM orders WHERE region = '{{ region }}'")
        assert "orders" in found["tables"]

    def test_a_parameterized_join_still_yields_its_edge(self):
        sql = """
            SELECT o.id FROM orders o JOIN users u ON o.user_id = u.id
            WHERE o.region = '{{ region }}' AND o.ts > '{{ since }}'
        """
        assert (("orders", "user_id"), ("users", "id")) in found_joins(sql)


def found_joins(sql, **kwargs):
    return set(mine(sql, **kwargs)["joins"])


class TestTheJoinGraph:
    def test_a_join_on_is_an_edge(self):
        sql = "SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"
        assert (("orders", "user_id"), ("users", "id")) in found_joins(sql)

    def test_the_edge_is_the_same_whichever_way_round_it_is_written(self):
        a = found_joins("SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id")
        b = found_joins("SELECT 1 FROM users u JOIN orders o ON u.id = o.user_id")
        assert a == b

    def test_an_old_style_join_in_the_where_clause_counts(self):
        sql = "SELECT 1 FROM orders o, users u WHERE o.user_id = u.id"
        assert (("orders", "user_id"), ("users", "id")) in found_joins(sql)

    def test_a_filter_is_not_an_edge(self):
        assert found_joins("SELECT 1 FROM orders o WHERE o.status = 'paid'") == set()

    def test_a_column_compared_to_itself_is_not_an_edge(self):
        assert found_joins("SELECT 1 FROM orders o WHERE o.a = o.b") == set()

    def test_schemas_are_kept(self):
        sql = "SELECT 1 FROM analytics.orders o JOIN analytics.users u ON o.user_id = u.id"
        assert (("analytics.orders", "user_id"), ("analytics.users", "id")) in found_joins(sql)


class TestColumnUsage:
    def test_qualified_columns_go_to_their_table(self):
        found = mine("SELECT o.amount, u.email FROM orders o JOIN users u ON o.user_id = u.id")
        assert found["columns"][("orders", "amount")] == 1
        assert found["columns"][("users", "email")] == 1

    def test_a_bare_column_with_one_table_in_scope_is_attributed(self):
        found = mine("SELECT amount FROM orders WHERE status = 'paid'")
        assert found["columns"][("orders", "amount")] == 1
        assert found["columns"][("orders", "status")] == 1

    def test_a_bare_column_with_two_tables_in_scope_is_not_guessed_at(self):
        # Attributing it would put usage on the wrong table, which is worse
        # than not counting it.
        found = mine("SELECT amount FROM orders o JOIN users u ON o.user_id = u.id")
        assert ("orders", "amount") not in found["columns"]

    def test_a_star_is_not_a_column(self):
        found = mine("SELECT * FROM orders")
        assert not any(name == "*" for _, name in found["columns"])


class TestFoldingManyQueries:
    def test_a_habit_is_counted_once_per_query_not_once_per_mention(self):
        # One baroque query repeating a join five times is one team habit;
        # counting mentions would let it outvote a department.
        busy = "SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id WHERE o.user_id = u.id"
        result = mine_all([(busy, None)])
        assert result["joins"][(("orders", "user_id"), ("users", "id"))] == 1

    def test_two_queries_agreeing_counts_twice(self):
        sql = "SELECT 1 FROM orders o JOIN users u ON o.user_id = u.id"
        result = mine_all([(sql, None), (sql, None)])
        assert result["joins"][(("orders", "user_id"), ("users", "id"))] == 2

    def test_unparseable_queries_are_skipped_not_fatal(self):
        result = mine_all([("SELECT FROM WHERE", None), ("SELECT id FROM orders", None)])
        assert "orders" in result["tables"]

    def test_a_non_sql_source_contributes_nothing(self):
        assert mine_all([('{"find": "orders"}', "mongodb")])["tables"] == {}


class TestTheParameterTokenDoesNotBecomeData:
    def test_an_unquoted_parameter_is_not_counted_as_a_column(self):
        # `LIMIT {{ n }}` and `x = {{ id }}` leave a bare identifier behind.
        # Counted, it becomes a phantom in every table's most-used list.
        found = mine("SELECT id FROM orders WHERE user_id = {{ user }}")
        assert not any("param" in name for _, name in found["columns"])

    def test_a_quoted_parameter_is_not_counted_either(self):
        found = mine("SELECT id FROM orders WHERE region = '{{ region }}'")
        assert not any("param" in name for _, name in found["columns"])
        assert "orders" in found["tables"]

    def test_a_parameter_is_not_mistaken_for_a_join(self):
        found = mine("SELECT 1 FROM orders o JOIN users u ON o.user_id = {{ user }}")
        assert found["joins"] == {}


class TestMeasures:
    """
    `SUM(amount) AS gross_revenue` is somebody naming a metric. It is the one
    part of a semantic layer that can be found rather than asked for.
    """

    def _measures(self, sql):
        return dict(mine(sql, "pg")["measures"])

    def test_the_authors_own_alias_becomes_the_name(self):
        found = self._measures("SELECT SUM(amount) AS gross_revenue FROM orders")

        assert found == {("orders", "gross_revenue", "sum", "amount"): 1}

    def test_an_unnamed_aggregate_gets_a_composed_name(self):
        found = self._measures("SELECT MAX(created_at) FROM orders")

        assert ("orders", "max_created_at", "max", "created_at") in found

    def test_count_star_is_kept(self):
        found = self._measures("SELECT COUNT(*) AS orders FROM orders")

        assert found == {("orders", "orders", "count", "*"): 1}

    def test_an_aggregate_over_a_join_is_not_attributed_to_either_table(self):
        # A number about a join is not a number about a table, and filing it
        # under whichever came first is a definition nobody could trust.
        found = self._measures("SELECT AVG(o.total) FROM orders o JOIN users u ON o.user_id = u.id")

        assert found == {}

    def test_an_expression_is_left_for_a_person_to_write(self):
        # SUM(price * qty) is real, but it cannot be checked against a column.
        found = self._measures("SELECT SUM(price * qty) AS weird FROM orders")

        assert found == {}

    def test_something_that_is_not_an_aggregate_is_not_a_measure(self):
        found = self._measures("SELECT region, created_at FROM orders")

        assert found == {}

    def test_the_same_definition_in_four_queries_counts_four(self):
        sql = "SELECT SUM(amount) AS gross_revenue FROM orders"
        found = mine_all([(sql, "pg")] * 4)["measures"]

        assert found[("orders", "gross_revenue", "sum", "amount")] == 4

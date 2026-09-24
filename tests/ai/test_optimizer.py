from sqldesk.ai.optimizer import CRITICAL, WARNING, analyze


def rules(sql, **kwargs):
    return {f["rule"] for f in analyze(sql, **kwargs)["findings"]}


def finding(sql, rule, **kwargs):
    return next(f for f in analyze(sql, **kwargs)["findings"] if f["rule"] == rule)


class TestWhatItCatches:
    def test_select_star(self):
        assert "select_star" in rules("SELECT * FROM orders WHERE region = 'North'")

    def test_naming_the_columns_is_not_flagged(self):
        assert "select_star" not in rules("SELECT id, amount FROM orders WHERE region = 'North'")

    def test_order_by_with_no_limit(self):
        assert "order_without_limit" in rules("SELECT id FROM orders WHERE x = 1 ORDER BY created_at")

    def test_a_limit_settles_it(self):
        assert "order_without_limit" not in rules("SELECT id FROM orders WHERE x = 1 ORDER BY created_at LIMIT 50")

    def test_a_window_functions_order_by_is_not_a_sort_of_the_result(self):
        # The commonest false positive there is: ORDER BY inside OVER().
        sql = "SELECT id, row_number() OVER (ORDER BY created_at) FROM orders WHERE x = 1"
        assert "order_without_limit" not in rules(sql)

    def test_no_where_and_no_limit(self):
        assert "no_predicate" in rules("SELECT id FROM orders")

    def test_a_limit_is_enough_while_exploring(self):
        assert "no_predicate" not in rules("SELECT id FROM orders LIMIT 10")

    def test_a_join_with_no_condition_is_critical(self):
        found = finding("SELECT a.id FROM orders a JOIN users b", "cross_join")
        assert found["severity"] == CRITICAL

    def test_a_join_with_a_condition_is_fine(self):
        assert "cross_join" not in rules("SELECT a.id FROM orders a JOIN users b ON a.user_id = b.id")

    def test_a_function_on_a_filtered_column(self):
        found = finding("SELECT id FROM orders WHERE date(created_at) = '2026-01-01'", "function_on_filtered_column")
        assert found["severity"] == WARNING
        # It names the function, because "a function" is not actionable.
        assert "DATE" in found["detail"].upper()

    def test_the_bare_column_is_fine(self):
        sql = "SELECT id FROM orders WHERE created_at >= '2026-01-01' AND created_at < '2026-01-02'"
        assert "function_on_filtered_column" not in rules(sql)

    def test_a_leading_wildcard(self):
        assert "leading_wildcard" in rules("SELECT id FROM orders WHERE name LIKE '%smith'")

    def test_a_trailing_wildcard_is_fine(self):
        assert "leading_wildcard" not in rules("SELECT id FROM orders WHERE name LIKE 'smith%'")

    def test_union_that_could_be_union_all(self):
        assert "union_distinct" in rules("SELECT id FROM a WHERE x=1 UNION SELECT id FROM b WHERE x=1")

    def test_union_all_is_not_flagged(self):
        assert "union_distinct" not in rules("SELECT id FROM a WHERE x=1 UNION ALL SELECT id FROM b WHERE x=1")

    def test_worst_first(self):
        sql = "SELECT * FROM orders a JOIN users b"
        severities = [f["severity"] for f in analyze(sql)["findings"]]
        assert severities[0] == CRITICAL


class TestWhenItDeclines:
    """
    Half-written SQL is the editor's normal state, and a data source that is
    not SQL is not a failure. Neither should look like an error.
    """

    def test_unparseable_sql_is_reported_not_raised(self):
        result = analyze("SELECT FROM WHERE ORDER", data_source_type="pg")
        assert result["applicable"] is False
        assert result["findings"] == []
        assert "parse" in result["reason"].lower()

    def test_an_empty_editor_says_nothing_to_look_at(self):
        assert analyze("")["applicable"] is False

    def test_a_non_sql_source_is_not_parsed_as_sql(self):
        result = analyze('{"collection": "orders"}', data_source_type="mongodb")
        assert result["applicable"] is False
        assert "does not use SQL" in result["reason"]

    def test_an_unknown_runner_falls_back_to_generic_rather_than_refusing(self):
        result = analyze("SELECT * FROM orders", data_source_type="some_new_runner")
        assert result["applicable"] is True
        assert result["dialect"] == "generic"

    def test_the_dialect_is_used(self):
        # Postgres-only syntax should parse as postgres.
        assert analyze("SELECT id FROM orders WHERE tags @> ARRAY['a'] LIMIT 1", data_source_type="pg")["applicable"]

    def test_one_broken_rule_does_not_lose_the_others(self, monkeypatch):
        from sqldesk.ai import optimizer

        def explodes(tree):
            raise RuntimeError("boom")

        monkeypatch.setattr(optimizer, "RULES", (explodes, optimizer.rule_select_star))
        result = optimizer.analyze("SELECT * FROM orders WHERE x = 1")
        assert "select_star" in {f["rule"] for f in result["findings"]}

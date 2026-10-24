"""
What a data source's queries are written in, and who gets to decide.

MCP decided it from a list of data source *types* kept in `sqldesk/mcp`. The
list was written when the runners it named were the only ones that were not
SQL, and nothing made anybody add to it: `mimir` arrived without a line in it,
so a PromQL query was parsed as SQL and refused for not beginning with SELECT,
and `yandex_*` and `google_search_console` had been missing from it for longer
than that. The runner knows its own language; these tests hold that it says so,
and that nothing classifies a language the other end has never heard of.
"""

from unittest import TestCase

from sqldesk.mcp import LANGUAGE_CHECKS, _by_language, _not_sql_here
from sqldesk.query_runner import (
    LANGUAGE_SQL,
    READ_ONLY_LANGUAGES,
    UNCHECKABLE_LANGUAGES,
    BaseQueryRunner,
    query_language_for,
    query_runners,
)
from sqldesk.query_runner.prometheus import Mimir, Prometheus


class Source:
    """A data source, as the language checks read one: a type and nothing else."""

    def __init__(self, source_type):
        self.type = source_type


class TestRunnersDeclareTheirLanguage(TestCase):
    def test_sql_is_the_default(self):
        self.assertEqual(LANGUAGE_SQL, BaseQueryRunner.query_language)
        self.assertEqual(LANGUAGE_SQL, query_language_for("pg"))

    def test_a_type_no_runner_claims_is_read_as_sql(self):
        # The rest of the application assumes SQL of a source it cannot place,
        # and a runner that is not installed cannot be queried at all.
        self.assertEqual(LANGUAGE_SQL, query_language_for("no_such_runner"))
        self.assertEqual(LANGUAGE_SQL, query_language_for(None))

    def test_prometheus_and_mimir_speak_the_same_language(self):
        self.assertEqual("promql", Prometheus.query_language)
        self.assertEqual("promql", Mimir.query_language)
        self.assertEqual("promql", query_language_for("prometheus"))
        self.assertEqual("promql", query_language_for("mimir"))

    def test_promql_cannot_write(self):
        self.assertIn("promql", READ_ONLY_LANGUAGES)

    def test_the_sources_that_were_missing_from_the_list_are_covered(self):
        for source_type in (
            "mimir",
            "yandex_metrika",
            "yandex_appmetrika",
            "yandex_disk",
            "google_search_console",
        ):
            language = query_language_for(source_type)
            self.assertNotEqual(LANGUAGE_SQL, language, source_type)
            self.assertIn(language, READ_ONLY_LANGUAGES, source_type)

    def test_every_registered_runner_is_classified(self):
        """
        A language is SQL, or it is read-only, or it is refused, or there is a
        check for it. A new runner that is none of those is the bug this
        attribute exists to stop, so it fails here rather than in production.
        """
        placed = READ_ONLY_LANGUAGES | UNCHECKABLE_LANGUAGES | set(LANGUAGE_CHECKS) | {LANGUAGE_SQL}
        unplaced = sorted(
            {runner.query_language for runner in query_runners.values() if runner.query_language not in placed}
        )
        self.assertEqual([], unplaced)


class TestWhatTheLanguageDecides(TestCase):
    def test_a_promql_query_is_not_judged_as_sql(self):
        # The whole of M1: this used to come back "Only a read (SELECT, WITH,
        # SHOW, DESCRIBE) can be run from here."
        decided, reason = _by_language('rate(http_requests_total{job="api"}[5m]) + 1', Source("mimir"))
        self.assertTrue(decided)
        self.assertIsNone(reason)

    def test_a_language_nothing_can_read_is_still_refused(self):
        decided, reason = _by_language(".drop table T", Source("azure_kusto"))
        self.assertTrue(decided)
        self.assertIn("editor", reason)

    def test_python_says_so_even_where_the_runner_is_switched_off(self):
        # Both program runners are opt-in, so in most installs -- this one
        # included -- no class is registered to be asked what they speak.
        for source_type in ("python", "insecure_script"):
            decided, reason = _by_language("print(1)", Source(source_type))
            self.assertTrue(decided, source_type)
            self.assertIn("Python", reason)

    def test_mongodb_and_the_json_source_keep_their_own_checks(self):
        self.assertIn("$out", _by_language('{"aggregate": [{"$out": "orders"}]}', Source("mongodb"))[1])
        self.assertIn("POST", _by_language("url: https://x/y\nmethod: post", Source("json"))[1])

    def test_sql_is_left_to_the_sql_checks(self):
        self.assertEqual((False, None), _by_language("SELECT 1", Source("pg")))


class TestCheckingSqlOnSomethingThatIsNot(TestCase):
    def test_a_sql_source_has_nothing_to_explain(self):
        self.assertIsNone(_not_sql_here(Source("pg")))
        self.assertIsNone(_not_sql_here(None))

    def test_promql_is_not_offered_a_plan_or_a_parse(self):
        reason = _not_sql_here(Source("mimir"))
        self.assertIn("not SQL", reason)
        self.assertIn("promql", reason)

    def test_a_language_the_optimizer_never_heard_of_is_refused_too(self):
        # The optimizer's own list of what is not SQL names eight runners.
        # Everything else went through it as SQL, findings and all.
        self.assertIsNotNone(_not_sql_here(Source("yandex_disk")))
        self.assertIsNotNone(_not_sql_here(Source("cloudwatch_insights")))

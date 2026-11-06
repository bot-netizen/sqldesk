"""
`/metrics`: what a cluster scrapes, and who may scrape it.

Two things are worth holding here.

**It is off unless a token is set, and absent rather than refusing.** An
endpoint that exists and says no is one more thing to explain in a port scan;
the labels carry pool and queue names, which carry data source names.

**A scrape that returns half the truth beats one that returns an error.**
Redis being unreachable should cost the queue metrics and nothing else --
during an incident, which is the only time anybody reads this, the half that
still works is the half that matters.
"""

from unittest import mock

from sqldesk.metrics import prometheus
from tests import BaseTestCase, authenticate_request


class MetricsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch("sqldesk.settings.METRICS_TOKEN", "a-scrape-token")
        patch.start()
        self.addCleanup(patch.stop)

    def scrape(self, token="a-scrape-token"):
        headers = {"Authorization": "Bearer {}".format(token)} if token else {}
        return self.client.get("/metrics", headers=headers)


class TestWhoMayScrape(MetricsTestCase):
    def test_with_the_token_it_answers(self):
        answer = self.scrape()

        self.assertEqual(200, answer.status_code)
        self.assertIn("text/plain", answer.headers["Content-Type"])

    def test_without_a_token_configured_there_is_no_endpoint_at_all(self):
        with mock.patch("sqldesk.settings.METRICS_TOKEN", ""):
            answer = self.scrape(token=None)

        self.assertEqual(404, answer.status_code)

    def test_an_empty_bearer_does_not_match_an_unconfigured_token(self):
        """
        The hole the `enabled()` check exists to close, and the reason it is
        not redundant with the comparison below it: with no token configured,
        `Bearer ` carries an empty string, and an empty string compares equal
        to an empty setting. Without the check, turning metrics off by leaving
        the setting blank would open them to anyone who sent that header.
        """
        with mock.patch("sqldesk.settings.METRICS_TOKEN", ""):
            answer = self.client.get("/metrics", headers={"Authorization": "Bearer "})

        self.assertEqual(404, answer.status_code)

    def test_a_wrong_token_is_a_404_not_a_403(self):
        """A refusal would confirm there is something here to find."""
        self.assertEqual(404, self.scrape(token="not-it").status_code)

    def test_no_header_at_all_is_the_same_404(self):
        self.assertEqual(404, self.scrape(token=None).status_code)

    def test_a_signed_in_session_is_not_a_way_in_either(self):
        """
        This is not part of the API and not part of anybody's organization: a
        scraper has no cookie, and a cookie is not a scraper's token.

        Asked at the real path rather than through `make_request`, which
        prefixes the organization and lands on the SPA's catch-all -- a 200 of
        HTML that says nothing about this endpoint at all.
        """
        authenticate_request(self.client, self.factory.user)

        self.assertEqual(404, self.client.get("/metrics").status_code)

    def test_the_catch_all_is_not_what_these_tests_are_reading(self):
        """
        The trap the test above fell into: an unknown path under an
        organization returns the single-page app, so a test that asked the
        wrong way would pass while the endpoint did nothing.
        """
        answer = self.scrape()

        self.assertIn("text/plain", answer.headers["Content-Type"])
        self.assertNotIn("<html", answer.get_data(as_text=True).lower())


class TestWhatItSays(MetricsTestCase):
    def test_it_says_the_instance_is_up(self):
        body = self.scrape().get_data(as_text=True)

        self.assertIn("sqldesk_up 1.0", body)

    def test_every_metric_is_prefixed_so_two_installs_can_share_a_prometheus(self):
        body = self.scrape().get_data(as_text=True)

        for line in body.splitlines():
            if line and not line.startswith("#"):
                self.assertTrue(line.startswith("sqldesk_"), line)

    def test_every_metric_declares_its_type_before_it_is_used(self):
        body = self.scrape().get_data(as_text=True)
        declared = set()
        for line in body.splitlines():
            if line.startswith("# TYPE "):
                declared.add(line.split()[2])
            elif line and not line.startswith("#"):
                name = line.split("{")[0].split(" ")[0]
                self.assertIn(name, declared, "{} is reported before its TYPE".format(name))

    def test_the_queues_are_there(self):
        body = self.scrape().get_data(as_text=True)

        self.assertIn("sqldesk_queue_depth", body)
        self.assertIn("sqldesk_workers", body)

    def test_database_connections_are_there_because_that_is_what_falls_over(self):
        body = self.scrape().get_data(as_text=True)

        self.assertIn("sqldesk_db_connections_in_use", body)

    def test_the_database_numbers_are_ones_a_dashboard_can_divide(self):
        """
        Every value non-negative, and a ceiling to divide by. The first version
        reported `pool.overflow()`, which SQLAlchemy starts at minus the pool
        size -- a healthy install said `-4`.
        """
        body = self.scrape().get_data(as_text=True)

        self.assertIn("sqldesk_db_pool_limit", body)
        for line in body.splitlines():
            if line.startswith("sqldesk_db_"):
                value = float(line.rsplit(" ", 1)[1])
                self.assertGreaterEqual(value, 0, line)


class TestWhenSomethingIsDown(MetricsTestCase):
    def test_redis_being_unreachable_costs_the_queues_and_nothing_else(self):
        with mock.patch("sqldesk.monitor.rq_queues", side_effect=OSError("redis is gone")):
            body = self.scrape().get_data(as_text=True)

        self.assertIn("sqldesk_up 1.0", body)
        self.assertIn("sqldesk_db_connections_in_use", body)
        self.assertNotIn("sqldesk_queue_depth", body)


class TheRealThing:
    """A scrape of the live collector, for a claim that must hold of both."""

    def __init__(self, case):
        self.case = case

    def scrape(self):
        with mock.patch("sqldesk.settings.METRICS_TOKEN", "a-scrape-token"):
            answer = self.case.client.get("/metrics", headers={"Authorization": "Bearer a-scrape-token"})
        return answer.get_data(as_text=True)


class TestTheFormat(BaseTestCase):
    """The exposition format, which is written by hand and so worth checking."""

    def test_a_label_value_with_a_quote_in_it_is_escaped(self):
        out = prometheus.Metrics()
        out.add("thing", 1, {"pool": 'ds:"odd"'})

        self.assertIn(r'pool="ds:\"odd\""', out.render())

    def test_labels_are_sorted_so_the_output_does_not_churn(self):
        out = prometheus.Metrics()
        out.add("thing", 1, {"z": "1", "a": "2"})

        self.assertIn('{a="2",z="1"}', out.render())

    def test_a_value_is_a_float_because_that_is_what_prometheus_reads(self):
        out = prometheus.Metrics()
        out.add("thing", 3)

        self.assertIn("sqldesk_thing 3.0", out.render())

    def test_an_unreadable_value_is_zero_rather_than_a_broken_scrape(self):
        out = prometheus.Metrics()
        out.add("thing", None)

        self.assertIn("sqldesk_thing 0.0", out.render())

    def test_the_type_is_declared_once_however_many_series_there_are(self):
        out = prometheus.Metrics()
        out.add("thing", 1, {"queue": "a"}, help_text="A thing.")
        out.add("thing", 2, {"queue": "b"})

        self.assertEqual(1, out.render().count("# TYPE sqldesk_thing"))
        self.assertEqual(1, out.render().count("# HELP sqldesk_thing"))

    def test_every_sample_of_a_family_arrives_together(self):
        """
        What the format requires and what collecting per queue naturally
        breaks: depth, started, depth, started would split both families in
        two, and a strict parser rejects the second half as a duplicate.
        """
        out = prometheus.Metrics()
        out.add("depth", 1, {"queue": "a"})
        out.add("started", 2, {"queue": "a"})
        out.add("depth", 3, {"queue": "b"})
        out.add("started", 4, {"queue": "b"})

        seen, families = [], []
        for line in out.render().splitlines():
            if line.startswith("#") or not line:
                continue
            name = line.split("{")[0].split(" ")[0]
            if not families or families[-1] != name:
                families.append(name)
            seen.append(name)

        self.assertEqual(["sqldesk_depth", "sqldesk_started"], families, "a family was split in two")
        self.assertEqual(2, seen.count("sqldesk_depth"))

    def test_a_scrape_of_several_queues_keeps_that_true(self):
        """The same claim against the real collector rather than a toy."""
        body = TheRealThing(self).scrape()
        families = []
        for line in body.splitlines():
            if line.startswith("#") or not line:
                continue
            name = line.split("{")[0].split(" ")[0]
            if not families or families[-1] != name:
                families.append(name)

        self.assertEqual(len(families), len(set(families)), "a family appeared in two places: {}".format(families))

    def test_the_body_ends_with_a_newline_as_the_format_requires(self):
        out = prometheus.Metrics()
        out.add("thing", 1)

        self.assertTrue(out.render().endswith("\n"))

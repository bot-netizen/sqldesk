import os
import re
import unittest

from sqldesk import features

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def page(name):
    with open(os.path.join(DOCS, name), encoding="utf-8") as f:
        return f.read()


class TestThePermissionsTable(unittest.TestCase):
    """
    The administration page lists the permissions an administrator hands to a
    group. A list of those written by hand is a list that goes stale the first
    time somebody adds a feature, and the way it goes stale is the bad way: a
    permission exists, nothing documents it, and nobody grants it because
    nobody knows it is there.
    """

    def listed(self):
        return set(re.findall(r"<code>([a-z_]+)</code></td><td>", page("guide/administration.html")))

    def test_lists_every_feature_there_is(self):
        named = {feature.name for feature in features.all_features()}

        self.assertEqual(self.listed() & named, named, "a feature exists that the docs do not mention")

    def test_and_invents_none(self):
        named = {feature.name for feature in features.all_features()}
        # Only the rows of that table; other `<code>` on the page is settings.
        invented = {one for one in self.listed() if one.startswith(("manage_", "use_", "keep_", "send_"))} - named

        self.assertEqual(invented, set())


class TestThePlanDirectory(unittest.TestCase):
    """
    `plan/` is the working context a new session reads before anything else,
    and a plan describing something the code does not do is worse than no
    plan. These check the few claims in it that a code change can silently
    falsify -- not the prose, which only a person can keep honest.
    """

    def plan(self, name):
        with open(os.path.join(os.path.dirname(DOCS), "plan", name), encoding="utf-8") as f:
            return f.read()

    def test_every_file_the_index_lists_exists(self):
        import re

        root = os.path.join(os.path.dirname(DOCS), "plan")
        listed = set(re.findall(r"\]\((\w[\w.-]*\.md)\)", self.plan("README.md")))

        self.assertTrue(listed, "the index links to nothing")
        for name in listed:
            self.assertTrue(os.path.exists(os.path.join(root, name)), "plan/README.md links to a missing " + name)

    def test_the_release_names_match_the_ones_in_the_docs(self):
        # The naming convention is the thing most likely to drift, because it
        # is written down in three places and only one of them is code.
        conventions = self.plan("conventions.md")
        releases = page("releases.html")

        for version, name in (("0.4", "Live"), ("0.5", "Interface"), ("0.6", "MCP"), ("0.8", "Notebooks")):
            self.assertIn(name, conventions)
            self.assertIn("{} &mdash; {}".format(version, name), releases)

    def test_claude_md_sends_people_to_it(self):
        with open(os.path.join(os.path.dirname(DOCS), "CLAUDE.md"), encoding="utf-8") as f:
            self.assertIn("plan/README.md", f.read())


class TestTheDeploymentDefaults(unittest.TestCase):
    """
    The deploying page tells somebody what is off until they ask for it. If a
    default moves and the page does not, the page is worse than nothing: it is
    a reason not to check.
    """

    def test_says_what_is_off_by_default(self):
        import yaml

        with open(os.path.join(os.path.dirname(DOCS), "charts", "sqldesk", "values.yaml"), encoding="utf-8") as f:
            values = yaml.safe_load(f)
        text = page("guide/deploying.html")

        for value, path in (
            ("mcp.enabled", ("mcp", "enabled")),
            ("streams.enabled", ("streams", "enabled")),
            ("uploads.enabled", ("uploads", "enabled")),
            ("rendering.enabled", ("rendering", "enabled")),
            ("notebooks.enabled", ("notebooks", "enabled")),
        ):
            at = values
            for key in path:
                at = at[key]
            self.assertFalse(at, "{} is no longer off by default".format(value))
            self.assertIn("<code>{}</code>".format(value), text)


TOOLS = os.path.join(DOCS, "tools")


def _tool(name):
    """A module from docs/tools, which is not a package and is run as a script."""
    import importlib.util
    import sys

    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    spec = importlib.util.spec_from_file_location("site_" + name, os.path.join(TOOLS, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheFrontPageSaysWhatIsTrue(unittest.TestCase):
    """
    Every number and every name on the front page, held to the code it describes.

    The page this replaced said "Fifteen tools" when there were eighteen, called
    0.8 "Next" after it shipped, listed Databricks as if every image had it, and
    drew a "live" chart from Math.random(). Each was true once, or nearly, and
    nothing noticed when it stopped being.
    """

    def front(self):
        return page("index.html")

    def stated(self, pattern):
        found = re.search(pattern, self.front())
        self.assertIsNotNone(found, "the front page no longer says " + pattern)
        return int(found.group(1))

    def test_the_count_of_mcp_tools(self):
        from sqldesk.mcp import HANDLERS

        self.assertEqual(len(HANDLERS), self.stated(r"<li>(\d+) tools:"))

    def test_the_count_of_visualizations(self):
        path = os.path.join(os.path.dirname(DOCS), "viz-lib", "src", "visualizations", "registeredVisualizations.ts")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        block = source.split("flatten([", 1)[1].split("])", 1)[0]
        registered = re.findall(r"\b\w+Visualization\b", block)

        self.assertEqual(len(registered), self.stated(r"(\d+) kinds of visualization"))
        self.assertEqual(len(registered), self.stated(r"<p>(\d+) kinds &mdash;"))

    def test_the_count_of_alert_destinations(self):
        from sqldesk.destinations import destinations

        self.assertEqual(len(destinations), self.stated(r"Alerts to (\d+) destinations"))
        self.assertEqual(len(destinations), self.stated(r"any of (\d+) destinations"))

    def connector_types(self):
        """Every connector the configured modules define, installed driver or not."""
        import importlib
        import inspect

        from sqldesk import settings
        from sqldesk.query_runner import BaseQueryRunner

        types = set()
        # The default list, not QUERY_RUNNERS: that one is a generator the
        # application has already used up by the time a test can read it.
        for name in settings.default_query_runners:
            module = importlib.import_module(name)
            for _, cls in inspect.getmembers(module, inspect.isclass):
                if issubclass(cls, BaseQueryRunner) and cls.__module__ == module.__name__:
                    types.add(cls.type())
        return types

    def test_every_connector_it_names_is_one_sqldesk_has(self):
        types = self.connector_types()
        named = re.findall(r'<li data-type="([^"]+)"', self.front())
        self.assertGreater(len(named), 60)
        self.assertEqual([], sorted(set(named) - types), "the front page names connectors that do not exist")
        self.assertEqual(len(named), len(set(named)), "a connector is listed twice")

    def test_and_more_than_seventy_of_them_ship(self):
        self.assertIn("More than 70 connectors", self.front())
        self.assertGreater(len(self.connector_types()), 70)

    def test_the_release_it_calls_latest_is_the_one_out(self):
        import sqldesk

        major_minor = ".".join(sqldesk.__version__.split(".")[:2])
        self.assertRegex(
            self.front(),
            r'<h3>{} &mdash; [^<]+</h3><span class="badge">Latest</span>'.format(re.escape(major_minor)),
        )

    def test_every_picture_it_shows_is_there(self):
        front = self.front()
        pictures = set(re.findall(r'src="(assets/[^"]+)"', front))
        for srcset in re.findall(r'srcset="([^"]+)"', front):
            pictures.update(part.strip().split(" ")[0] for part in srcset.split(","))

        self.assertTrue(pictures)
        for picture in pictures:
            self.assertTrue(os.path.exists(os.path.join(DOCS, picture)), picture + " is missing")


class TestTheGuideCanBeJumpedInto(unittest.TestCase):
    """
    Search sends somebody to a section, and the list on the right of a guide
    page links to its sections: both need every section to have an id, and the
    pages to be the ones chrome.py writes.
    """

    def test_every_section_has_an_id(self):
        chrome = _tool("chrome")
        for filename, _title, _section in chrome.PAGES:
            if filename.startswith("../"):
                continue
            body = page("guide/" + filename)
            for heading in re.findall(r"<h2(?:\s[^>]*)?>", body):
                self.assertIn(
                    ' id="', heading, "a section of guide/{} has no id: run docs/tools/chrome.py".format(filename)
                )

    def test_the_pages_are_what_chrome_writes(self):
        chrome = _tool("chrome")
        for filename, _title, _section in chrome.PAGES:
            if filename.startswith("../"):
                continue
            path = os.path.join(DOCS, "guide", filename)
            expected = chrome.render(filename, chrome._description(path), chrome.anchor_headings(chrome._read(path)))
            self.assertEqual(
                expected, page("guide/" + filename), "guide/{} is stale: run docs/tools/chrome.py".format(filename)
            )

    def test_no_page_uses_an_id_twice(self):
        for name in ["index.html", "releases.html"] + ["guide/" + f for f in os.listdir(os.path.join(DOCS, "guide"))]:
            if not name.endswith(".html"):
                continue
            ids = re.findall(r'\sid="([^"]+)"', page(name))
            repeated = sorted({i for i in ids if ids.count(i) > 1})
            self.assertEqual([], repeated, "{} uses these ids more than once".format(name))

    def test_every_link_the_application_makes_into_the_guide_lands(self):
        """The help links in the app name sections by id; renaming one breaks them silently."""
        root = os.path.dirname(DOCS)
        found = set()
        for folder in ("client/app", "sqldesk", "viz-lib/src"):
            for directory, _dirs, files in os.walk(os.path.join(root, folder)):
                for name in files:
                    if name.endswith((".js", ".jsx", ".ts", ".tsx", ".py")):
                        with open(os.path.join(directory, name), encoding="utf-8", errors="ignore") as f:
                            found.update(re.findall(r"guide/([a-z-]+\.html)#([\w-]+)", f.read()))

        self.assertTrue(found)
        for filename, anchor in found:
            self.assertIn(' id="{}"'.format(anchor), page("guide/" + filename), "guide/{}#{}".format(filename, anchor))


class TestTheSearchIndex(unittest.TestCase):
    def test_it_covers_every_guide_page_and_the_releases(self):
        records = _tool("search").build()
        chrome = _tool("chrome")
        urls = {record["u"].split("#")[0] for record in records}
        for filename, _title, _section in chrome.PAGES:
            if not filename.startswith("../"):
                self.assertIn("guide/" + filename, urls)
        self.assertIn("releases.html", urls)

    def test_every_result_lands_somewhere(self):
        for record in _tool("search").build():
            path, _, anchor = record["u"].partition("#")
            self.assertTrue(os.path.exists(os.path.join(DOCS, path)), record["u"])
            if anchor:
                self.assertIn(' id="{}"'.format(anchor), page(path), record["u"])

    def test_a_section_carries_its_own_words_and_not_the_next_ones(self):
        records = _tool("search").build()
        by_url = {record["u"]: record for record in records}
        streams = by_url["guide/streams.html#received-at"]
        self.assertIn("_received_at", streams["t"])
        self.assertNotIn("Running, paused, cold", streams["t"])

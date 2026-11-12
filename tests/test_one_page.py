import pathlib
import re

from sqldesk import one_page
from tests import BaseTestCase

CLIENT = pathlib.Path(__file__).parent.parent / "client" / "app" / "pages" / "dashboards" / "export"


def _number(path, pattern):
    match = re.search(pattern, (CLIENT / path).read_text())
    if not match:
        raise AssertionError("{} no longer defines {}".format(path, pattern))
    return int(match.group(1))


class TestTheRuleMatchesTheOneInTheBrowser(BaseTestCase):
    """
    The same question is answered twice: here, from the stored layout, for a
    subscription; and in the browser, from the rendered grid, for the Export
    button. Two copies drift, and the drift is invisible -- a dashboard the
    button exports happily but a subscription refuses, or worse, the other way
    round, discovered by twenty recipients.

    So the numbers are read out of the file that holds them. A change to
    either side is a failing test rather than a surprise in somebody's inbox.
    """

    def test_the_widget_limit(self):
        self.assertEqual(_number("index.js", r"MAX_WIDGETS = (\d+)"), one_page.MAX_WIDGETS)

    def test_how_far_a_page_may_shrink(self):
        stretch = re.search(r"ONE_PAGE_STRETCH = ([\d.]+)", (CLIENT / "index.js").read_text())
        self.assertIsNotNone(stretch, "index.js no longer defines ONE_PAGE_STRETCH")
        self.assertEqual(float(stretch.group(1)), one_page.ONE_PAGE_STRETCH)

    def test_the_paper(self):
        page = re.search(
            r"A4_LANDSCAPE = \{ width: (\d+), height: (\d+) \}", (CLIENT / "singleImagePdf.js").read_text()
        )
        self.assertIsNotNone(page, "singleImagePdf.js no longer defines A4_LANDSCAPE")
        self.assertEqual((int(page.group(1)), int(page.group(2))), one_page.A4_LANDSCAPE)

    def test_what_the_page_puts_around_the_dashboard(self):
        self.assertEqual(_number("compose.js", r"MARGIN = (\d+)"), one_page.MARGIN)
        self.assertEqual(_number("compose.js", r"HEADER_HEIGHT = (\d+)"), one_page.HEADER_HEIGHT)

    def test_and_the_grid_it_is_laid_out_on(self):
        grid = (
            pathlib.Path(__file__).parent.parent / "client" / "app" / "config" / "dashboard-grid-options.js"
        ).read_text()
        self.assertEqual(int(re.search(r"rowHeight: (\d+)", grid).group(1)), one_page.ROW_HEIGHT)
        self.assertEqual(int(re.search(r"margins: (\d+)", grid).group(1)), one_page.GRID_MARGIN)


class TestWhatIsTooBigToSend(BaseTestCase):
    def _widgets(self, count, rows_each=4):
        return [
            type("W", (), {"options": {"position": {"row": i * rows_each, "sizeY": rows_each, "col": 0, "sizeX": 12}}})
            for i in range(count)
        ]

    def test_a_small_dashboard_is_fine(self):
        self.assertIsNone(one_page.too_big_to_send(self._widgets(4)))

    def test_one_with_no_widgets_at_all_is_fine(self):
        # Nothing to send is not the same as too much to send, and refusing it
        # here would be refusing it for the wrong reason.
        self.assertIsNone(one_page.too_big_to_send([]))

    def test_too_many_widgets_is_refused_and_says_how_many(self):
        reason = one_page.too_big_to_send(self._widgets(one_page.MAX_WIDGETS + 1, rows_each=1))

        self.assertIn("has 13 widgets", reason)
        self.assertIn("up to 12 widgets", reason)

    def test_exactly_the_limit_is_allowed(self):
        self.assertIsNone(one_page.too_big_to_send(self._widgets(one_page.MAX_WIDGETS, rows_each=1)))

    def test_too_tall_is_refused_and_says_how_many_pages(self):
        # Few widgets, each enormous: the other way to be too big.
        reason = one_page.too_big_to_send(self._widgets(3, rows_each=40))

        self.assertIn("pages", reason)
        self.assertNotIn("widgets.", reason.split(". ")[1])

    def test_the_height_comes_from_the_layout_not_the_count(self):
        # Two widgets side by side are one row tall, not two.
        beside = [
            type("W", (), {"options": {"position": {"row": 0, "sizeY": 6, "col": 0, "sizeX": 12}}}),
            type("W", (), {"options": {"position": {"row": 0, "sizeY": 6, "col": 12, "sizeX": 12}}}),
        ]
        stacked = [
            type("W", (), {"options": {"position": {"row": 0, "sizeY": 6, "col": 0, "sizeX": 24}}}),
            type("W", (), {"options": {"position": {"row": 6, "sizeY": 6, "col": 0, "sizeX": 24}}}),
        ]

        self.assertLess(one_page.grid_height(beside), one_page.grid_height(stacked))

    def test_a_widget_with_no_position_does_not_break_it(self):
        # Textboxes and anything half-saved. Nothing here should raise.
        odd = [type("W", (), {"options": None}), type("W", (), {"options": {}})]

        self.assertEqual(0, one_page.grid_height(odd))
        self.assertIsNone(one_page.too_big_to_send(odd))


class TestWhatToDoAboutIt(BaseTestCase):
    """The advice that comes with a refusal, which is the half somebody acts on."""

    def _widgets(self, count, rows_each=4):
        return [
            type("W", (), {"options": {"position": {"row": i * rows_each, "sizeY": rows_each, "col": 0, "sizeX": 12}}})
            for i in range(count)
        ]

    def test_a_dashboard_that_fits_has_no_advice(self):
        check = one_page.size_check(self._widgets(4))

        self.assertTrue(check["fits"])
        self.assertIsNone(check["advice"])

    def test_too_many_says_how_many_to_remove(self):
        check = one_page.size_check(self._widgets(15, rows_each=0))

        self.assertEqual(3, check["remove"])
        self.assertFalse(check["too_tall"])
        self.assertIn("remove 3 widgets", check["advice"])

    def test_one_too_many_is_said_in_the_singular(self):
        check = one_page.size_check(self._widgets(13, rows_each=0))

        self.assertIn("remove 1 widget,", check["advice"])

    def test_too_tall_says_to_make_it_shorter_rather_than_to_count(self):
        check = one_page.size_check(self._widgets(3, rows_each=40))

        self.assertEqual(0, check["remove"])
        self.assertTrue(check["too_tall"])
        self.assertIn("make it shorter", check["advice"])

    def test_both_says_both(self):
        check = one_page.size_check(self._widgets(15, rows_each=10))

        self.assertIn("at least 3 widgets", check["advice"])
        self.assertIn("make it shorter", check["advice"])

    def test_and_always_offers_a_copy_with_just_what_matters(self):
        for widgets in (self._widgets(15, rows_each=0), self._widgets(3, rows_each=40)):
            self.assertIn("a copy of it", one_page.size_check(widgets)["advice"])

    def test_the_refusal_is_the_problem_and_the_advice_together(self):
        widgets = self._widgets(15, rows_each=0)
        check = one_page.size_check(widgets)

        self.assertEqual("{} {}".format(check["problem"], check["advice"]), one_page.too_big_to_send(widgets))

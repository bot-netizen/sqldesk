"""
Whether a dashboard is small enough to send as one page.

A subscription arrives in somebody's inbox. A dashboard of eighty widgets
arrives as an eleven-page PDF nobody opens, or a picture so long that every
chart on it is a smudge -- so past one page the answer is "too big", said when
the subscription is saved rather than discovered by twenty recipients a week
later. It is asked again before each send, because a dashboard grows after
somebody has subscribed to it.

**There is a second copy of this rule**, in
`client/app/pages/dashboards/export/index.js`, which answers the same question
about the dashboard on the page for the Export button. That one measures the
rendered grid; this one works from the stored layout, because there is no
browser here. They have to agree, and `tests/test_one_page.py` pins the
numbers against the file that holds them so a change to either is a failing
test rather than a surprise in somebody's email.

The rule is about a *page*, so it governs a PDF and a subscription and not an
image. Downloading a dashboard as a picture sizes the canvas to the dashboard
and has no page to overflow; its only limit is what the browser will allocate.

Sending to Slack, now or on a schedule, follows the rule even though what it
sends is a picture: a channel shows the picture at the width of a message, so
a dashboard taller than a page arrives as a strip of charts too small to read
until somebody opens it full size -- the eleven-page PDF again, in a channel.
"""

import math

#: Past this, it is something to scroll rather than something to print -- and
#: it keeps a send quick: twelve charts drew in under a second.
MAX_WIDGETS = 12

#: A4 landscape in points, the paper a subscription is printed on.
A4_LANDSCAPE = (842, 595)

#: What the page puts around the dashboard: a margin either side, and a header
#: with the dashboard's name and when the numbers are from.
MARGIN = 40
HEADER_HEIGHT = 64

#: A page may be shrunk this much to fit. Further than this and it is too
#: small to read, which is not a page anybody wanted either.
ONE_PAGE_STRETCH = 1.3

#: The window the renderer draws into, and so the width the grid is laid out
#: at. Matches SCREENSHOT_WIDTH's default; a deployment that changes one
#: should change the other, which is why it is named rather than buried.
RENDER_WIDTH = 1400

#: The grid a dashboard is laid out on: twenty-four columns, each row this
#: tall including its bottom padding. Mirrors
#: `client/app/config/dashboard-grid-options.js`.
ROW_HEIGHT = 25
GRID_MARGIN = 15


def grid_height(widgets):
    """
    How tall this dashboard is, in CSS pixels, from the stored layout.

    A widget's position is `{col, row, sizeX, sizeY}` in grid units. The
    tallest bottom edge is the height of the grid, which is the number the
    rule below needs -- there is no browser here to measure one.
    """
    rows = 0
    for widget in widgets:
        position = (widget.options or {}).get("position") or {}
        bottom = (position.get("row") or 0) + (position.get("sizeY") or 0)
        rows = max(rows, bottom)

    if not rows:
        return 0
    return rows * ROW_HEIGHT + GRID_MARGIN


def size_check(widgets):
    """
    How this dashboard measures against one page, and what to change if it
    does not fit.

    Asked by the Send to Slack and subscription dialogs as they open, so
    somebody learns a dashboard is too big -- and what to do about it --
    before they have picked a channel and pressed Send, rather than after.

    `remove` is how many widgets have to go for the count to fit; `too_tall`
    is whether the layout is taller than a page even so. The two are separate
    because they want different advice: a dashboard of fifteen small charts is
    fixed by removing three, and one of four enormous ones is not fixed by
    removing anything short of all of them.
    """
    # `dashboard.widgets` is a dynamic relationship, not a list, and a caller
    # holding one should not have to remember that.
    widgets = list(widgets)
    count = len(widgets)
    height = grid_height(widgets)

    page_width = RENDER_WIDTH + MARGIN * 2
    page_height = page_width * (A4_LANDSCAPE[1] / A4_LANDSCAPE[0])
    needed = height + HEADER_HEIGHT + MARGIN * 2
    pages = math.ceil(needed / page_height) if page_height else 1

    remove = max(0, count - MAX_WIDGETS)
    too_tall = needed > page_height * ONE_PAGE_STRETCH
    fits = not remove and not too_tall

    problem = advice = None
    if not fits:
        size = (
            "This dashboard has {} widgets".format(count)
            if remove
            else "This dashboard would need {} pages".format(pages)
        )
        problem = "A dashboard is sent as a one-page report: up to {} widgets, one page tall. {}.".format(
            MAX_WIDGETS, size
        )
        copy = "or send a copy of it with just the widgets that matter."
        if remove and too_tall:
            advice = "To send it, remove at least {} {} and make it shorter, {}".format(
                remove, "widget" if remove == 1 else "widgets", copy
            )
        elif remove:
            advice = "To send it, remove {} {}, {}".format(remove, "widget" if remove == 1 else "widgets", copy)
        else:
            advice = "To send it, make it shorter -- fewer or smaller widgets -- {}".format(copy)

    return {
        "fits": fits,
        "widgets": count,
        "max_widgets": MAX_WIDGETS,
        "pages": pages,
        "remove": remove,
        "too_tall": too_tall,
        "problem": problem,
        "advice": advice,
    }


def too_big_to_send(widgets):
    """
    Why this dashboard cannot be sent as one page, and what to do, or None.

    Kept close to the client's message: somebody who has met one of these
    should recognise the other.
    """
    check = size_check(widgets)
    if check["fits"]:
        return None
    return "{} {}".format(check["problem"], check["advice"])

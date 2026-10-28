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


def too_big_to_send(widgets):
    """
    Why this dashboard cannot be sent as one page, or None.

    Kept word-for-word close to the client's message: somebody who has met
    one of these should recognise the other.
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

    if count <= MAX_WIDGETS and needed <= page_height * ONE_PAGE_STRETCH:
        return None

    size = (
        "This dashboard has {} widgets".format(count)
        if count > MAX_WIDGETS
        else "This dashboard would need {} pages".format(pages)
    )
    return (
        "A subscription sends a one-page report: up to {} widgets, one page tall. {}. "
        "Send a dashboard of just the widgets that matter instead.".format(MAX_WIDGETS, size)
    )

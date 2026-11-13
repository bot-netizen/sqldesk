"""
The renderer: one endpoint that turns a URL into a PNG.

This runs in its own container, not in the SQLDesk image, and that is the
whole point. Drawing a dashboard means running it, which means a browser, and
a browser is several hundred megabytes added to an image the server and the
worker share -- for a feature most installs never turn on. Here it is opt-in:
if you do not run this service, nothing changes and nothing extra is pulled.

Grafana ships its renderer as a separate service for the same reason and says
so in its own documentation. Superset does not ship one at all and tells its
users to extend the image themselves. This is the first of those.

It is deliberately small and deliberately dumb. It holds no credentials, knows
nothing about alerts, and keeps no state: it is handed a URL and the headers
to use, and it gives back an image. Everything that decides *what* to draw
lives in sqldesk/screenshots.py, on the other side of this boundary.
"""

import hmac
import logging
import os
import re
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

#: The window the page is drawn into. Wide enough that a dashboard lays out
#: the way it does on a laptop rather than collapsing to its mobile layout,
#: which is a different picture of a different thing.
VIEWPORT = {
    "width": int(os.environ.get("SCREENSHOT_WIDTH", "1400")),
    "height": int(os.environ.get("SCREENSHOT_HEIGHT", "900")),
}

#: The widest window a caller may ask for. SQLDesk asks for the width of the
#: screen the picture is being sent from, so a dashboard is laid out the way
#: that person sees it; a 4K screen at 100% is 3840, and the branded frame
#: adds 80.
MIN_WIDTH = 600
MAX_WIDTH = 3920

#: Twice the pixels on an ordinary screen, so text is not soft where the
#: picture is read; fewer on a wide one, where twice would be an image of
#: seven thousand pixels across for Slack to shrink. Text stays as sharp as
#: a 2000px window at 2x.
SHARP_WIDTH = 4000

#: Above this, stop waiting and say so.
MAX_TIMEOUT_SECONDS = int(os.environ.get("SCREENSHOT_MAX_TIMEOUT", "120"))

#: A ceiling on the window a full-page capture stretches to. A dashboard long
#: enough to exceed this is one the one-page rule should already have refused;
#: this is here so a runaway page cannot ask for a window measured in tens of
#: thousands of pixels and take the browser down with it.
MAX_CAPTURE_HEIGHT = int(os.environ.get("SCREENSHOT_MAX_HEIGHT", "30000"))

#: The branded page SQLDesk draws around what it is photographed for -- the
#: same frame Export as image draws (client/app/components/ScreenshotFrame).
#: Where the page has one, the picture is the frame and nothing else: cropped
#: to it, as the export is sized to its own content, rather than a window
#: 900px tall with a short dashboard at the top and empty page below. A page
#: without one -- an older SQLDesk -- is photographed as it always was.
FRAME_SELECTOR = "[data-test='ScreenshotFrame']"

# Two things keep this from being a browser anyone on the network can point
# anywhere -- at a cloud metadata address, an internal admin page, or SQLDesk
# itself with a header of their choosing. The caller shows a token, and the
# page has to be SQLDesk's own address. Both are set by the chart and the
# compose file; unset, nothing is checked, which is right only on a network
# with nothing else on it.
TOKEN = os.environ.get("SCREENSHOT_TOKEN", "")
ALLOWED_ORIGIN = os.environ.get("SCREENSHOT_ALLOWED_ORIGIN", "")


def _refusal(url):
    """Why this URL will not be rendered, or None."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "Only http and https pages are rendered."
    if ALLOWED_ORIGIN and _origin(url) != _origin(ALLOWED_ORIGIN):
        return "That address is not the SQLDesk this renderer serves."
    return None


def _origin(url):
    parts = urlsplit(url)
    return (parts.scheme, parts.netloc)


#: What a caller may ask for. PNG is a picture of the page; PDF is the page
#: printed, so its text is text -- selectable, searchable, and legible when
#: somebody zooms in, which a photograph of text is not.
PNG = "png"
PDF = "pdf"
FORMATS = (PNG, PDF)


def _window(width):
    """The window to draw in: the width asked for, if it is a sensible one."""
    if isinstance(width, bool) or not isinstance(width, int) or not MIN_WIDTH <= width <= MAX_WIDTH:
        return dict(VIEWPORT)
    return {"width": width, "height": VIEWPORT["height"]}


def _scale(window):
    return round(min(2.0, SHARP_WIDTH / window["width"]), 3)


#: An IANA name, such as America/Toronto or UTC. SQLDesk checks the name
#: against the zone database before sending it; this only keeps anything
#: that is not shaped like one away from the browser.
_TIME_ZONE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}$")


def _time_zone(value):
    return value if isinstance(value, str) and len(value) <= 64 and _TIME_ZONE.match(value) else None


def _render(url, headers, wait_for, timeout_seconds, full_page, fmt=PNG, width=None, time_zone=None):
    timeout_ms = min(timeout_seconds, MAX_TIMEOUT_SECONDS) * 1000
    window = _window(width)
    zone = _time_zone(time_zone)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(
                viewport=window,
                # Twice the pixels, so text in the image is not soft on the
                # screen somebody reads the email on -- see SHARP_WIDTH.
                device_scale_factor=_scale(window),
                # "Generated at" in the frame reads in the zone of the person
                # it is sent for, as their own export would. Charts are not
                # affected: they read timestamps in the zone they were stored.
                **({"timezone_id": zone} if zone else {}),
                # A still picture of a chart that animates itself into view is
                # a picture of it half drawn. Measured: a sparkline's area fill
                # reached 74% of its width at the moment of capture while the
                # final point was already in place -- the shape was wrong in a
                # way that looked like missing data rather than an artefact.
                #
                # Asking for reduced motion rather than reaching into the
                # charts: the application already turns ECharts animation off
                # for anyone whose system asks for it, so the renderer just
                # says it is one of those viewers and every visualization
                # settles instantly, with no rendering code that exists only
                # for screenshots.
                reduced_motion="reduce",
            )
            # The headers carry a SQLDesk API key, so they go to SQLDesk and
            # nowhere else. `extra_http_headers` would attach them to every
            # request the page makes -- the map tiles, a web font, an image
            # somebody put in a textbox -- and hand the key to whoever serves
            # those.
            if headers:
                ours = _origin(url)

                def only_to_sqldesk(route, outgoing):
                    if _origin(outgoing.url) == ours:
                        route.continue_(headers={**outgoing.headers, **headers})
                    else:
                        route.continue_()

                context.route("**/*", only_to_sqldesk)
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            if wait_for:
                # The page says when it has finished drawing. Without this the
                # usual result is a photograph of a loading spinner -- the
                # failure Superset's own docs warn about, and the reason they
                # check captures for blank content afterwards.
                page.wait_for_selector(wait_for, timeout=timeout_ms, state="attached")

            if full_page and fmt == PNG:
                # Stretch the window to the whole document, *then* ask again.
                #
                # `screenshot(full_page=True)` does this resize itself and
                # shoots immediately after, which is too early: a resize
                # re-lays-out every chart and ECharts redraws asynchronously,
                # so a dashboard of fifty-four charts came back about a
                # quarter of the time with its tiles drawn and its charts
                # blank. The page withdraws its "drawn" attribute when the
                # window changes size, so waiting for it a second time waits
                # for the redraw that the resize caused.
                height = min(int(page.evaluate("document.documentElement.scrollHeight")), MAX_CAPTURE_HEIGHT)
                if height > window["height"]:
                    page.set_viewport_size({"width": window["width"], "height": height})
                    if wait_for:
                        page.wait_for_selector(wait_for, timeout=timeout_ms, state="attached")

            if fmt == PDF:
                # Chromium's own print output, so the text in a subscription's
                # attachment is text rather than a photograph of text.
                #
                # `print_background` because a dashboard is mostly background:
                # tile surfaces, chart fills, the page itself. Without it the
                # PDF is an outline of a dashboard.
                #
                # A4 landscape, because the thing being made is an
                # attachment somebody may print, and paper is a size. What
                # keeps it to *one* page is the rule applied before any of
                # this: a dashboard past twelve widgets, or taller than a
                # page allows, is refused when the subscription is saved.
                # If one arrives anyway it paginates rather than losing
                # anything, and the caller counts the pages.
                return page.pdf(
                    print_background=True,
                    format="A4",
                    landscape=True,
                    margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                )

            # The caller's timeout covers the capture too. Playwright's own
            # default is 30 seconds, and a full-page shot of a long dashboard
            # goes past it: one of 2800x21574 timed out here while the same
            # page had loaded and drawn in a fraction of that. The picture
            # being slow is not a reason to send the alert without one.
            frame = page.query_selector(FRAME_SELECTOR)
            if frame is not None:
                return frame.screenshot(type="png", timeout=timeout_ms)
            return page.screenshot(full_page=full_page, type="png", timeout=timeout_ms)
        finally:
            browser.close()


@app.post("/screenshot")
def screenshot():
    if TOKEN and not hmac.compare_digest(request.headers.get("X-Screenshot-Token", ""), TOKEN):
        return jsonify({"error": "A token is required."}), 401

    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url or not isinstance(url, str):
        return jsonify({"error": "No url given."}), 400
    refusal = _refusal(url)
    if refusal:
        return jsonify({"error": refusal}), 400

    fmt = (body.get("format") or PNG).lower()
    if fmt not in FORMATS:
        return jsonify({"error": "Unknown format {!r}; expected one of {}.".format(fmt, ", ".join(FORMATS))}), 400

    try:
        image = _render(
            url,
            body.get("headers"),
            body.get("wait_for"),
            int(body.get("timeout", 60)),
            bool(body.get("full_page")),
            fmt,
            body.get("width"),
            body.get("time_zone"),
        )
    except PlaywrightError as error:
        # The caller treats any failure the same way -- send the alert without
        # a picture -- but the reason belongs in this service's log, where
        # somebody debugging a blank image will look.
        logging.exception("Could not render %s", url)
        return jsonify({"error": str(error)}), 502

    return app.response_class(image, mimetype="application/pdf" if fmt == PDF else "image/png")


@app.get("/ping")
def ping():
    return "PONG."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))

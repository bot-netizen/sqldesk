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

import logging
import os

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

#: Above this, stop waiting and say so.
MAX_TIMEOUT_SECONDS = int(os.environ.get("SCREENSHOT_MAX_TIMEOUT", "120"))


def _render(url, headers, wait_for, timeout_seconds, full_page):
    timeout_ms = min(timeout_seconds, MAX_TIMEOUT_SECONDS) * 1000

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(
                viewport=VIEWPORT,
                # Twice the pixels, so text in the image is not soft on the
                # screen somebody reads the email on.
                device_scale_factor=2,
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
                extra_http_headers=headers or {},
            )
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

            if wait_for:
                # The page says when it has finished drawing. Without this the
                # usual result is a photograph of a loading spinner -- the
                # failure Superset's own docs warn about, and the reason they
                # check captures for blank content afterwards.
                page.wait_for_selector(wait_for, timeout=timeout_ms, state="attached")

            return page.screenshot(full_page=full_page, type="png")
        finally:
            browser.close()


@app.post("/screenshot")
def screenshot():
    body = request.get_json(silent=True) or {}
    url = body.get("url")
    if not url:
        return jsonify({"error": "No url given."}), 400

    try:
        image = _render(
            url,
            body.get("headers"),
            body.get("wait_for"),
            int(body.get("timeout", 60)),
            bool(body.get("full_page")),
        )
    except PlaywrightError as error:
        # The caller treats any failure the same way -- send the alert without
        # a picture -- but the reason belongs in this service's log, where
        # somebody debugging a blank image will look.
        logging.exception("Could not render %s", url)
        return jsonify({"error": str(error)}), 502

    return app.response_class(image, mimetype="image/png")


@app.get("/ping")
def ping():
    return "PONG."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))

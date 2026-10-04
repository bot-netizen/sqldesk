"""Compressing responses, which nothing did until 0.7.2.

No part of what SQLDesk shipped compressed anything: not the app, not the
chart, not the ingress templates. A `/ping` asked with `Accept-Encoding: gzip`
came back with no `Content-Encoding` at all. So a 20,000-row result sent its
full **3.7 MB**, and the 6.7 MB of JavaScript and CSS behind a cold page load
went out byte for byte.

Measured on that result (and the codecs are chosen from this, not from habit):

    brotli q1          8.3 ms     8.0x
    brotli q4         27.2 ms     8.8x      <- flask-compress default
    gzip level 1      14.1 ms     7.0x
    gzip level 6      31.1 ms     8.8x      <- flask-compress default
    gzip level 9     156.6 ms     9.7x      <- five times the CPU for 10%

The defaults are where the measurements land, so they are left alone. Level 9
is deliberately not used. For scale: encoding that result as JSON already
costs 112 ms, so 31 ms buys an 8.8x smaller body -- and a sync Gunicorn worker,
of which there are four, holds its socket for a fraction as long. That is the
real saving, because the web tier is the first ceiling this install meets.

On BREACH: compressing authenticated responses is the usual argument against
this, and it needs a secret in the *body*. SQLDesk's CSRF token is set as a
cookie (`security.inject_csrf_token`), not rendered into a response, so the
classic vector does not apply.

One asymmetry worth knowing before it looks like a bug: flask-compress will
only use an algorithm it can compress incrementally on a *streamed* response,
and its streaming set is `('zstd', 'br', 'deflate')` -- **gzip is not in it**.
A static file is streamed, so `Accept-Encoding: gzip` alone gets a static
asset back uncompressed while the same header compresses JSON fine. Every
browser since about 2017 offers `br`, so in practice static assets are
compressed and this affects nothing real; it shows up only when probing with a
hand-written single-algorithm header.

Set SQLDESK_COMPRESS_RESPONSES=false to turn it off.
"""

from flask_compress import Compress

from sqldesk import settings

compress = Compress()

# Text, and nothing already compressed. A PNG from the renderer, an .xlsx
# (which is a zip) and a Parquet upload all get bigger and cost CPU for it.
COMPRESSIBLE = [
    "application/javascript",
    "application/json",
    "image/svg+xml",
    "text/css",
    "text/csv",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/xml",
]


def init_app(app):
    if not settings.COMPRESS_RESPONSES:
        return

    app.config["COMPRESS_MIMETYPES"] = COMPRESSIBLE
    # Under this, the header costs more than the saving.
    app.config["COMPRESS_MIN_SIZE"] = 1024
    # Preference order: brotli for anything modern, gzip for the rest. Zstd is
    # faster still (5.5 ms, 8.5x) but Safari does not accept it, and offering
    # it only changes which clients pay less.
    app.config["COMPRESS_ALGORITHM"] = ["br", "gzip", "deflate"]
    app.config["COMPRESS_LEVEL"] = settings.COMPRESS_GZIP_LEVEL
    app.config["COMPRESS_BR_LEVEL"] = settings.COMPRESS_BROTLI_LEVEL

    compress.init_app(app)

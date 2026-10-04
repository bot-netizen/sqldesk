"""Responses are compressed, which nothing in SQLDesk did before 0.7.2.

The fault was invisible: no error, no warning, just a `/ping` answered with no
`Content-Encoding` and a 3.7 MB result sent whole. These pin the parts that
would make it silently stop again -- a mimetype list that loses `application/json`,
a preference order that loses brotli, a threshold that swallows everything.
"""

from flask import Response, jsonify

from sqldesk import compression
from tests import BaseTestCase

# Long enough to beat COMPRESS_MIN_SIZE, repetitive enough to compress loudly.
BODY = "the quick brown fox jumps over the lazy dog " * 500


class TestCompression(BaseTestCase):
    def setUp(self):
        super().setUp()

        @self.app.route("/__compressible")
        def compressible():
            return jsonify({"rows": [{"text": BODY}]})

        @self.app.route("/__already_compressed")
        def already_compressed():
            return Response(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30000, mimetype="image/png")

        @self.app.route("/__tiny")
        def tiny():
            return jsonify({"ok": True})

        self.client = self.app.test_client()

    def _encoding(self, path, accept):
        response = self.client.get(path, headers={"Accept-Encoding": accept})
        return response.headers.get("Content-Encoding"), len(response.data)

    def test_json_is_compressed_for_a_browser(self):
        encoding, size = self._encoding("/__compressible", "gzip, deflate, br")
        self.assertEqual(encoding, "br")
        self.assertLess(size, 2000)

    def test_gzip_is_there_for_anything_that_cannot_do_brotli(self):
        encoding, size = self._encoding("/__compressible", "gzip")
        self.assertEqual(encoding, "gzip")
        self.assertLess(size, 2000)

    def test_brotli_is_preferred_over_gzip(self):
        # Measured: brotli q4 is 27 ms for 8.8x where gzip 6 is 31 ms for the
        # same. Losing brotli from the order costs both.
        self.assertEqual(compression.compress.enabled_algorithms[0], "br")

    def test_a_client_that_asks_for_nothing_gets_plain_bytes(self):
        response = self.client.get("/__compressible", headers={"Accept-Encoding": ""})
        self.assertIsNone(response.headers.get("Content-Encoding"))

    def test_an_already_compressed_body_is_left_alone(self):
        # A PNG from the renderer, an .xlsx (a zip) and a Parquet upload all
        # get *bigger* for CPU spent.
        encoding, size = self._encoding("/__already_compressed", "gzip, deflate, br")
        self.assertIsNone(encoding)
        self.assertGreater(size, 30000)

    def test_a_tiny_body_is_not_worth_a_header(self):
        encoding, _ = self._encoding("/__tiny", "gzip, deflate, br")
        self.assertIsNone(encoding)

    def test_caches_vary_on_the_encoding(self):
        # Without this a proxy serves a brotli body to a client that cannot
        # read it.
        response = self.client.get("/__compressible", headers={"Accept-Encoding": "br"})
        self.assertIn("Accept-Encoding", response.headers.get("Vary", ""))

    def test_json_and_csv_are_both_in_the_list(self):
        # CSV is the download path and compresses about as well as JSON.
        self.assertIn("application/json", compression.COMPRESSIBLE)
        self.assertIn("text/csv", compression.COMPRESSIBLE)

    def test_nothing_already_compressed_is_in_the_list(self):
        for mimetype in ["image/png", "application/zip", "application/octet-stream", "application/vnd.ms-excel"]:
            self.assertNotIn(mimetype, compression.COMPRESSIBLE)

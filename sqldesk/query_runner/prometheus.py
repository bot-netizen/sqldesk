import json
import os
import re
from base64 import b64decode
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from urllib.parse import unquote

import requests
from dateutil import parser

from sqldesk.query_runner import (
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_STRING,
    BaseQueryRunner,
    register,
)

#: Everything the Prometheus HTTP API takes beside the expression itself. A
#: query body is written as a URL query string, and the PromQL in it is not
#: encoded, so these names are what tells an `&` that begins the next
#: parameter from an `&` inside a label value.
API_PARAMETERS = ("query", "start", "end", "step", "time", "timeout", "limit")

_NEXT_PARAMETER = re.compile(r"&(?=(?:{})=)".format("|".join(API_PARAMETERS)))


def split_query_body(body):
    """The query body as parameter name -> value.

    `parse_qs` was doing this, and using it is why PromQL did not survive the
    trip. It reads a body as a *form submission*, where `+` means an encoded
    space: `a + b` arrived as `a   b`, which Prometheus answers with a 400,
    and `web-[0-9]+` as `web-[0-9] `, a regex that matches nothing and says
    nothing about why. It also split on every `&`, including one inside a
    label value, which turned the rest of the query into a parameter nobody
    asked for.

    A label value holding the text `&step=` -- or any other parameter name
    with its `=` -- still has to be written `%26`; nothing can tell that from
    the start of the next parameter.
    """
    fields = {}
    for part in _NEXT_PARAMETER.split(body):
        name, _, value = part.partition("=")
        # unquote, not unquote_plus: in PromQL a `+` is the addition operator
        # or part of a regex, never a space. Anybody who really is encoding
        # one still has %20.
        fields[name.strip()] = unquote(value).strip()
    return fields


#: The columns a native histogram sample brings instead of a value. Prefixed
#: because `count` and `sum` are both perfectly ordinary label names, and a
#: label would have been given a numeric column holding its text.
HISTOGRAM_COLUMNS = {
    "histogram_count": TYPE_FLOAT,
    "histogram_sum": TYPE_FLOAT,
    "histogram_buckets": TYPE_STRING,
}


def sample_time(timestamp):
    """When a sample was taken, in UTC.

    Prometheus timestamps are unix seconds and carry no zone;
    `datetime.fromtimestamp` with no `tz` reads them into the *worker's* local
    time and drops the fact, so the same query read differently depending on
    which pod answered it, and a chart could not say which.
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def api_error(response):
    """What the server said about a refused request, not just its status line.

    Prometheus and Mimir answer one with a JSON body naming the problem:
    "parse error at char 8: unexpected character" says where to look, and "no
    org id" says a tenant never arrived. `raise_for_status` threw all of that
    away and left "400 Client Error: Bad Request for url: ...", which is the
    one part the person reading it already knew.
    """
    try:
        body = response.json()
    except ValueError:
        body = None

    detail = None
    if isinstance(body, dict) and body.get("error"):
        detail = body["error"]
        if body.get("errorType"):
            detail = "{}: {}".format(body["errorType"], detail)
    if not detail:
        detail = " ".join((response.text or "").split())[:500] or None

    status = "{} {}".format(response.status_code, response.reason or "").strip()
    return "{} ({})".format(detail, status) if detail else status


def sample_value(value):
    """A sample's value as a number.

    The API sends it as a string -- "1", "0.5", "NaN", "+Inf" -- and handing
    that on as one typed the column as text, so a chart over Prometheus got a
    category axis and nothing could be summed. "NaN" and the infinities are
    floats in Python, so they survive as themselves.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def histogram_fields(histogram):
    """A native histogram, which has no single value, as columns of its own.

    What anybody charts is the count or the sum. The buckets are kept as they
    came, so the part nobody charts is still there to read rather than being
    quietly dropped -- which is what happened to the whole sample before
    this, by way of a KeyError on `value`.
    """
    histogram = histogram or {}
    return {
        "histogram_count": sample_value(histogram.get("count")),
        "histogram_sum": sample_value(histogram.get("sum")),
        "histogram_buckets": json.dumps(histogram.get("buckets") or []),
    }


def get_instant_rows(metrics_data):
    rows = []

    for metric in metrics_data:
        row_data = dict(metric.get("metric") or {})

        if "histogram" in metric:
            timestamp, histogram = metric["histogram"]
            row_data.update(histogram_fields(histogram))
        else:
            timestamp, value = metric["value"]
            row_data["value"] = sample_value(value)

        row_data["timestamp"] = sample_time(timestamp)
        rows.append(row_data)
    return rows


def get_range_rows(metrics_data):
    rows = []

    for metric in metrics_data:
        metric_labels = metric.get("metric") or {}

        for timestamp, value in metric.get("values") or []:
            row_data = dict(metric_labels)
            row_data["value"] = sample_value(value)
            row_data["timestamp"] = sample_time(timestamp)
            rows.append(row_data)

        for timestamp, histogram in metric.get("histograms") or []:
            row_data = dict(metric_labels)
            row_data.update(histogram_fields(histogram))
            row_data["timestamp"] = sample_time(timestamp)
            rows.append(row_data)
    return rows


def get_scalar_rows(result, numeric=True):
    """A `scalar` or a `string` result: one sample, no labels, not in a list.

    Both crashed on `metric["metric"]`, and both are ordinary things to ask
    for -- `scalar(up)` and `time()` answer with the first, and a
    `label_replace` over a constant with the second.
    """
    timestamp, value = result
    return [{"timestamp": sample_time(timestamp), "value": sample_value(value) if numeric else value}]


def guess_result_type(result):
    """Which of the four shapes came back, for an answer that did not say.

    Prometheus always sends `resultType`; something else speaking its API, or
    a recorded response, may not, and the shapes tell themselves apart. The
    endpoint cannot be trusted to say either: `/api/v1/query` answers a range
    selector like `foo[5m]` with a *matrix*, and reading that as a vector was
    a KeyError rather than a result.
    """
    if not isinstance(result, list) or not result:
        return "vector"
    if not isinstance(result[0], dict):
        return "scalar"
    if "values" in result[0] or "histograms" in result[0]:
        return "matrix"
    return "vector"


def rows_for(result, result_type):
    """The rows of any result type, or None for one nothing here can read."""
    if result_type == "matrix":
        return get_range_rows(result)
    if result_type == "vector":
        return get_instant_rows(result)
    if result_type in ("scalar", "string"):
        return get_scalar_rows(result, numeric=result_type == "scalar")
    return None


def columns_for(rows, value_type=TYPE_FLOAT):
    """The columns a result needs, taken from every row rather than the first.

    Two series in one result need not carry the same labels -- an `or` of two
    selectors, a `label_replace`, a recording rule beside a raw metric -- and
    reading the names off `result[0]` dropped every label the first series
    happened not to have, along with the values under them.
    """
    columns = [
        {"friendly_name": "timestamp", "type": TYPE_DATETIME, "name": "timestamp"},
        {"friendly_name": "value", "type": value_type, "name": "value"},
    ]

    named = {"timestamp", "value"}
    for row in rows:
        for name in row:
            if name in named:
                continue
            named.add(name)
            columns.append(
                {
                    "friendly_name": name,
                    "type": HISTOGRAM_COLUMNS.get(name, TYPE_STRING),
                    "name": name,
                }
            )
    return columns


#: `now`, and `now-1h`: how a window that ends at the present gets written.
#: Prometheus itself takes absolute times only.
_RELATIVE_TIME = re.compile(r"now\s*(?:-\s*([0-9]+)\s*(ms|[smhdwy]))?", re.I)
_UNIT_SECONDS = {
    "ms": 0.001,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31536000,
}


def epoch(value):
    """A `datetime` as a unix timestamp, reading one with no zone as UTC.

    That is the API's own convention for a time written without an offset, and
    the only reading that answers the same question on every worker.
    `time.mktime` was doing this, and it reads a `datetime` as the *local*
    time of whatever process it is in: `2018-01-26T00:00:00Z` meant a
    different instant depending on which pod picked up the job, and the offset
    an RFC3339 time carries was dropped on the way.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def resolve_time(value, now):
    """One `start` or `end` as a unix timestamp Prometheus will accept.

    A bare unix timestamp is passed through, which is what it already did.
    `now` and `now-1h` are new: they are how a relative window is written
    everywhere else, and `dateutil` raised on them.
    """
    if isinstance(value, datetime):
        return epoch(value)

    value = (value or "").strip()
    relative = _RELATIVE_TIME.fullmatch(value)
    if relative:
        amount, unit = relative.groups()
        if amount is None:
            return epoch(now)
        return epoch(now) - int(amount) * _UNIT_SECONDS[unit.lower()]

    try:
        return float(value)
    except ValueError:
        pass

    return epoch(parser.parse(value))


class Prometheus(BaseQueryRunner):
    query_language = "promql"
    should_annotate_query = False

    def _get_datetime_now(self):
        """The present, with its zone on it -- see `epoch`."""
        return datetime.now(timezone.utc)

    def _get_prometheus_kwargs(self):
        ca_cert_file = self._create_cert_file("ca_cert_File")
        if ca_cert_file is not None:
            verify = ca_cert_file
        else:
            verify = self.configuration.get("verify_ssl", True)

        cert_file = self._create_cert_file("cert_File")
        cert_key_file = self._create_cert_file("cert_key_File")
        if cert_file is not None and cert_key_file is not None:
            cert = (cert_file, cert_key_file)
        else:
            cert = ()

        kwargs = {
            "verify": verify,
            "cert": cert,
        }

        auth = self._get_auth()
        if auth is not None:
            kwargs["auth"] = auth

        headers = self._get_extra_headers()
        if headers:
            kwargs["headers"] = headers

        return kwargs

    def _get_auth(self):
        username = self.configuration.get("username")
        password = self.configuration.get("password")
        if username and password:
            return (username, password)
        return None

    def _get_extra_headers(self):
        """Headers for every request: a bearer token, then whatever else was typed.

        Prometheus itself needs none of this. Everything that speaks its API and is
        not Prometheus does: Mimir wants a tenant, Thanos and Cortex sit behind
        gateways, and a Prometheus behind an auth proxy wants a token. Without it the
        only credential this runner could carry was a TLS client certificate.
        """
        headers = {}

        token = self.configuration.get("bearer_token")
        if token:
            headers["Authorization"] = "Bearer {}".format(token.strip())

        for line in (self.configuration.get("extra_headers") or "").splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            name, _, value = line.partition(":")
            name = name.strip()
            if name:
                headers[name] = value.strip()

        return headers

    def _create_cert_file(self, key):
        cert_file_name = None

        if self.configuration.get(key, None) is not None:
            with NamedTemporaryFile(mode="w", delete=False) as cert_file:
                cert_bytes = b64decode(self.configuration[key])
                cert_file.write(cert_bytes.decode("utf-8"))
                cert_file_name = cert_file.name

        return cert_file_name

    def _cleanup_cert_files(self, promehteus_kwargs):
        verify = promehteus_kwargs.get("verify", True)
        if isinstance(verify, str) and os.path.exists(verify):
            os.remove(verify)

        cert = promehteus_kwargs.get("cert", ())
        for cert_file in cert:
            if os.path.exists(cert_file):
                os.remove(cert_file)

    @property
    def api_base_url(self):
        """Where the Prometheus HTTP API lives. Subclasses that serve it under a
        prefix -- Mimir does -- override this rather than every caller."""
        return (self.configuration.get("url") or "").rstrip("/")

    @classmethod
    def configuration_schema(cls):
        # files has to end with "File" in name
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "title": "Prometheus API URL"},
                "verify_ssl": {
                    "type": "boolean",
                    "title": "Verify SSL (Ignored, if SSL Root Certificate is given)",
                    "default": True,
                },
                "cert_File": {"type": "string", "title": "SSL Client Certificate", "default": None},
                "cert_key_File": {"type": "string", "title": "SSL Client Key", "default": None},
                "ca_cert_File": {"type": "string", "title": "SSL Root Certificate", "default": None},
                "username": {"type": "string", "title": "HTTP Basic Auth Username"},
                "password": {"type": "string", "title": "HTTP Basic Auth Password"},
                "bearer_token": {"type": "string", "title": "Bearer Token"},
                "extra_headers": {
                    "type": "string",
                    "title": "Extra Headers (one Name: value per line)",
                },
            },
            "required": ["url"],
            "secret": ["cert_File", "cert_key_File", "ca_cert_File", "password", "bearer_token"],
            "extra_options": [
                "verify_ssl",
                "cert_File",
                "cert_key_File",
                "ca_cert_File",
                "username",
                "password",
                "bearer_token",
                "extra_headers",
            ],
        }

    def test_connection(self):
        result = False
        promehteus_kwargs = {}
        try:
            promehteus_kwargs = self._get_prometheus_kwargs()
            resp = requests.get(self.configuration.get("url", None), **promehteus_kwargs)
            result = resp.ok
        except Exception:
            raise
        finally:
            self._cleanup_cert_files(promehteus_kwargs)

        return result

    def get_schema(self, get_stats=False):
        schema = []
        promehteus_kwargs = {}
        try:
            base_url = self.api_base_url
            metrics_path = "/api/v1/label/__name__/values"
            promehteus_kwargs = self._get_prometheus_kwargs()

            response = requests.get(base_url + metrics_path, **promehteus_kwargs)

            if not response.ok:
                raise Exception(api_error(response))
            data = response.json()["data"]

            schema = {}
            for name in data:
                schema[name] = {"name": name, "columns": []}
            schema = list(schema.values())
        except Exception:
            raise
        finally:
            self._cleanup_cert_files(promehteus_kwargs)

        return schema

    def run_query(self, query, user):
        """
        Query Syntax, actually it is the URL query string.
        Check the Prometheus HTTP API for the details of the supported query string.

        https://prometheus.io/docs/prometheus/latest/querying/api/

        example: instant query
            query=http_requests_total

        example: range query
            query=http_requests_total&start=2018-01-20T00:00:00.000Z&end=2018-01-25T00:00:00.000Z&step=60s

        example: until now range query
            query=http_requests_total&start=2018-01-20T00:00:00.000Z&step=60s
            query=http_requests_total&start=2018-01-20T00:00:00.000Z&end=now&step=60s
        """

        base_url = self.api_base_url
        promehteus_kwargs = {}

        try:
            error = None
            query = query.strip()
            # for backward compatibility
            query = "query={}".format(query) if not query.startswith("query=") else query

            payload = split_query_body(query)
            query_type = "query_range" if "step" in payload.keys() else "query"

            if query_type == "query" and ("start" in payload or "end" in payload):
                # The silence was the bug: a start and an end with no step ran
                # as an instant query, answered for the present, and read as
                # the history having gone missing.
                return None, "A range needs a step, which Prometheus has no default for: add `&step=60s`."

            # for the range of until now
            if query_type == "query_range" and not payload.get("end"):
                payload["end"] = "now"

            now = self._get_datetime_now()
            for key in ("start", "end"):
                if key not in payload:
                    continue
                try:
                    payload[key] = resolve_time(payload[key], now)
                except (ValueError, OverflowError) as time_error:
                    return None, "Could not read `{}={}`: {}".format(key, payload[key], time_error)

            api_endpoint = base_url + "/api/v1/{}".format(query_type)

            promehteus_kwargs = self._get_prometheus_kwargs()

            response = requests.get(api_endpoint, params=payload, **promehteus_kwargs)
            if not response.ok:
                return None, api_error(response)

            body = response.json().get("data") or {}
            result = body.get("result")
            # The server's own word for the shape, not the endpoint we asked:
            # an instant query given a range selector answers with a matrix.
            result_type = body.get("resultType") or guess_result_type(result)

            rows = rows_for(result, result_type)
            if rows is None:
                return None, "Prometheus answered with a {} result, which this cannot read.".format(result_type)

            # No rows is an answer, not a failure: a matcher that matches
            # nothing, a window that starts before the data does, or -- the
            # one that cost the most time -- a Mimir tenant with a typo in it.
            # Returned as "query result is empty." it read as a broken data
            # source, and sent people looking anywhere but at the tenant.
            data = {
                "rows": rows,
                "columns": columns_for(rows, TYPE_STRING if result_type == "string" else TYPE_FLOAT),
            }

        except requests.RequestException as e:
            return None, str(e)
        except Exception:
            raise
        finally:
            self._cleanup_cert_files(promehteus_kwargs)

        return data, error


register(Prometheus)


class Mimir(Prometheus):
    """Grafana Mimir, which answers PromQL at a Prometheus-compatible API.

    Two things stop the Prometheus runner from reaching a real Mimir, and both are
    handled here rather than left as instructions nobody reads:

    * Mimir serves the Prometheus API under a prefix, `/prometheus` by default, so
      a URL without one produces 404s from every query.
    * With `-auth.enabled` -- which is the default, and every multi-tenant install --
      a request without `X-Scope-OrgID` is refused. The tenant is not an optional
      extra; it is the thing that decides which data you are asking about.
    """

    @classmethod
    def type(cls):
        return "mimir"

    @classmethod
    def name(cls):
        return "Grafana Mimir"

    @classmethod
    def configuration_schema(cls):
        schema = super().configuration_schema()
        schema["properties"]["url"]["title"] = "Mimir URL (the /prometheus prefix is added for you)"
        schema["properties"]["org_id"] = {
            "type": "string",
            "title": "Tenant ID (sent as X-Scope-OrgID)",
        }
        schema["order"] = ["url", "org_id"]
        schema["required"] = ["url", "org_id"]
        return schema

    @property
    def api_base_url(self):
        """Mimir's Prometheus API lives under a prefix; accept a URL with or without it."""
        url = (self.configuration.get("url") or "").rstrip("/")
        prefix = (self.configuration.get("prometheus_prefix") or "/prometheus").strip("/")
        if url.endswith("/" + prefix):
            return url
        return "{}/{}".format(url, prefix)

    def test_connection(self):
        """Ask the query API, not the root URL, and ask it something the tenant
        decides the answer to.

        `GET /prometheus` on Mimir is not dependably a 200, and a bare `requests.get`
        against a gateway happily succeeds on a welcome page -- which is how you get a
        data source that tests fine and cannot answer a query.

        `query=1` is no better: Mimir answers it without reading a single series, so
        the test passed for every tenant that has ever been typed, including one with
        a letter missing. That tenant then answers every real query with nothing,
        which is the hardest possible way to find a typo. The tenant's own metric
        names are the cheapest question whose answer depends on which tenant was sent.
        """
        prometheus_kwargs = {}
        try:
            prometheus_kwargs = self._get_prometheus_kwargs()
            response = requests.get(
                self.api_base_url + "/api/v1/label/__name__/values",
                **prometheus_kwargs,
            )
            if not response.ok:
                raise Exception(api_error(response))

            body = response.json() or {}
            if body.get("status") != "success":
                raise Exception(api_error(response))
            if not body.get("data"):
                raise Exception(
                    "Mimir answered, but tenant '{}' holds no metrics. Check the Tenant ID.".format(
                        self.configuration.get("org_id")
                    )
                )
            return True
        finally:
            self._cleanup_cert_files(prometheus_kwargs)

    def _get_extra_headers(self):
        headers = super()._get_extra_headers()
        org_id = self.configuration.get("org_id")
        if org_id:
            # Only set it if the operator has not already said otherwise by hand.
            headers.setdefault("X-Scope-OrgID", str(org_id).strip())
        return headers


register(Mimir)

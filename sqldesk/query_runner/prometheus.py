import os
import time
from base64 import b64decode
from datetime import datetime
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs

import requests
from dateutil import parser

from sqldesk.query_runner import (
    TYPE_DATETIME,
    TYPE_STRING,
    BaseQueryRunner,
    register,
)


def get_instant_rows(metrics_data):
    rows = []

    for metric in metrics_data:
        row_data = metric["metric"]

        timestamp, value = metric["value"]
        date_time = datetime.fromtimestamp(timestamp)

        row_data.update({"timestamp": date_time, "value": value})
        rows.append(row_data)
    return rows


def get_range_rows(metrics_data):
    rows = []

    for metric in metrics_data:
        ts_values = metric["values"]
        metric_labels = metric["metric"]

        for values in ts_values:
            row_data = metric_labels.copy()

            timestamp, value = values
            date_time = datetime.fromtimestamp(timestamp)

            row_data.update({"timestamp": date_time, "value": value})
            rows.append(row_data)
    return rows


# Convert datetime string to timestamp
def convert_query_range(payload):
    query_range = {}

    for key in ["start", "end"]:
        if key not in payload.keys():
            continue
        value = payload[key][0]

        if isinstance(value, str):
            # Don't convert timestamp string
            try:
                int(value)
                continue
            except ValueError:
                pass
            value = parser.parse(value)

        if type(value) is datetime:
            query_range[key] = [int(time.mktime(value.timetuple()))]

    payload.update(query_range)


class Prometheus(BaseQueryRunner):
    should_annotate_query = False

    def _get_datetime_now(self):
        return datetime.now()

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

            response.raise_for_status()
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
        columns = [
            {"friendly_name": "timestamp", "type": TYPE_DATETIME, "name": "timestamp"},
            {"friendly_name": "value", "type": TYPE_STRING, "name": "value"},
        ]
        promehteus_kwargs = {}

        try:
            error = None
            query = query.strip()
            # for backward compatibility
            query = "query={}".format(query) if not query.startswith("query=") else query

            payload = parse_qs(query)
            query_type = "query_range" if "step" in payload.keys() else "query"

            # for the range of until now
            if query_type == "query_range" and ("end" not in payload.keys() or "now" in payload["end"]):
                date_now = self._get_datetime_now()
                payload.update({"end": [date_now]})

            convert_query_range(payload)

            api_endpoint = base_url + "/api/v1/{}".format(query_type)

            promehteus_kwargs = self._get_prometheus_kwargs()

            response = requests.get(api_endpoint, params=payload, **promehteus_kwargs)
            response.raise_for_status()

            metrics = response.json()["data"]["result"]

            if len(metrics) == 0:
                return None, "query result is empty."

            metric_labels = metrics[0]["metric"].keys()

            for label_name in metric_labels:
                columns.append(
                    {
                        "friendly_name": label_name,
                        "type": TYPE_STRING,
                        "name": label_name,
                    }
                )

            if query_type == "query_range":
                rows = get_range_rows(metrics)
            else:
                rows = get_instant_rows(metrics)

            data = {"rows": rows, "columns": columns}

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
        """Ask the query API, not the root URL.

        `GET /prometheus` on Mimir is not dependably a 200, and a bare `requests.get`
        against a gateway happily succeeds on a welcome page -- which is how you get a
        data source that tests fine and cannot answer a query.
        """
        prometheus_kwargs = {}
        try:
            prometheus_kwargs = self._get_prometheus_kwargs()
            response = requests.get(
                self.api_base_url + "/api/v1/query",
                params={"query": "1"},
                **prometheus_kwargs,
            )
            response.raise_for_status()
            return response.json().get("status") == "success"
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

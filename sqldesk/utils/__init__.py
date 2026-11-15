import binascii
import datetime
import decimal
import hashlib
import json
import math
import os
import random
import re
import sys
import uuid

import pystache
import pytz
import sqlparse
from dateutil.relativedelta import relativedelta
from flask import current_app
from funcy import select_values
from sqlalchemy.orm.query import Query

from sqldesk import settings

from .human_time import parse_human_time

try:
    import orjson
except ImportError:  # pragma: no cover - a transitive dependency; fall back if it goes
    orjson = None

COMMENTS_REGEX = re.compile(r"/\*.*?\*/")


def utcnow():
    """Return datetime.now value with timezone specified.

    Without the timezone data, when the timestamp stored to the database it gets the current timezone of the server,
    which leads to errors in calculations.
    """
    return datetime.datetime.now(pytz.utc)


def dt_from_timestamp(timestamp, tz_aware=True):
    timestamp = datetime.datetime.utcfromtimestamp(float(timestamp))

    if tz_aware:
        timestamp = timestamp.replace(tzinfo=pytz.utc)

    return timestamp


def slugify(s):
    return re.sub(r"[^a-z0-9_\-]+", "-", s.lower())


def gen_query_hash(sql):
    """Return hash of the given query after stripping all comments, line breaks
    and multiple spaces.

    The following queries will get different ids:
        1. SELECT 1 FROM table WHERE column='Value';
        2. SELECT 1 FROM table where column='value';
    """
    sql = COMMENTS_REGEX.sub("", sql)
    sql = "".join(sql.split())
    return hashlib.md5(sql.encode("utf-8"), usedforsecurity=False).hexdigest()


def generate_token(length):
    chars = "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "0123456789"

    rand = random.SystemRandom()
    return "".join(rand.choice(chars) for x in range(length))


class JSONEncoder(json.JSONEncoder):
    """Adapter for `json.dumps`."""

    def __init__(self, **kwargs):
        from sqldesk.query_runner import query_runners

        self.encoders = [r.custom_json_encoder for r in query_runners.values() if hasattr(r, "custom_json_encoder")]
        super().__init__(**kwargs)

    def default(self, o):
        for encoder in self.encoders:
            result = encoder(self, o)
            # `is not None`, not truthiness: a runner's encoder can rightly
            # answer 0 or "" -- Mongo's Decimal128("0") is Decimal("0"), an
            # empty pg range is "" -- and treating those as "not mine" fell
            # through to json's default, which raised, and the whole result
            # failed to store.
            if result is not None:
                return result
        if isinstance(o, Query):
            result = list(o)
        elif isinstance(o, decimal.Decimal):
            result = float(o)
        elif isinstance(o, (datetime.timedelta, uuid.UUID)):
            result = str(o)
        elif isinstance(o, relativedelta):
            result = _interval_text(o)
        # See "Date Time String Format" in the ECMA-262 specification.
        elif isinstance(o, datetime.datetime):
            result = o.isoformat()
            if o.microsecond:
                result = result[:23] + result[26:]
            if result.endswith("+00:00"):
                result = result[:-6] + "Z"
        elif isinstance(o, datetime.date):
            result = o.isoformat()
        elif isinstance(o, datetime.time):
            if o.utcoffset() is not None:
                raise ValueError("JSON can't represent timezone-aware times.")
            result = o.isoformat()
            if o.microsecond:
                result = result[:12]
        elif isinstance(o, (memoryview, bytes)):
            result = binascii.hexlify(o).decode()
        else:
            result = super().default(o)
        return result


def _interval_text(interval):
    """
    An interval with months in it, written the way a timedelta is.

    vertica-python returns an INTERVAL as a relativedelta, which nothing here
    knew how to write: any Vertica query with an interval column failed to
    store at all ("Object of type relativedelta is not JSON serializable").
    Days and smaller read as a timedelta does ("3 days, 4:05:06"); years and
    months, which a timedelta cannot hold, go in front ("1 year 2 months ...").
    """
    interval = interval.normalized()
    parts = []
    for amount, unit in ((interval.years, "year"), (interval.months, "month")):
        if amount:
            parts.append("{} {}{}".format(amount, unit, "" if abs(amount) == 1 else "s"))
    rest = datetime.timedelta(
        days=interval.days,
        hours=interval.hours,
        minutes=interval.minutes,
        seconds=interval.seconds,
        microseconds=interval.microseconds,
    )
    if rest or not parts:
        parts.append(str(rest))
    return " ".join(parts)


def json_loads(data, *args, **kwargs):
    """A custom JSON loading function which passes all parameters to the
    json.loads function."""
    return json.loads(data, *args, **kwargs)


# Convert NaN, Inf, and -Inf to None, as they are not valid JSON values.
def _sanitize_data(data):
    if isinstance(data, dict):
        return {k: _sanitize_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_data(v) for v in data]
    if isinstance(data, float) and (math.isnan(data) or math.isinf(data)):
        return None
    return data


def json_dumps(data, *args, **kwargs):
    """A custom JSON dumping function which passes all parameters to the
    json.dumps function."""
    kwargs.setdefault("cls", JSONEncoder)
    kwargs.setdefault("ensure_ascii", False)
    # Float value nan or inf in Python should be render to None or null in json.
    # Using allow_nan = True will make Python render nan as NaN, leading to parse error in front-end
    kwargs.setdefault("allow_nan", False)
    return json.dumps(_sanitize_data(data), *args, **kwargs)


def json_dumps_result(data):
    """
    A query result as JSON, the same values `json_dumps` writes, much sooner.

    Storing a result went through `json_dumps`: first `_sanitize_data`, which
    rebuilds every row only to turn NaN and infinity into null, then the
    pure-Python encoder. Measured on a million rows of dates, decimals and
    text, that was 48 seconds and 730 MB on top of the result itself. orjson
    writes NaN as null on its own, and hands dates, decimals and anything else
    it does not know to the same `JSONEncoder.default`, so the values are the
    ones json_dumps writes: 8 seconds and 500 MB. Only the spacing differs.

    Anything orjson refuses -- an integer past 64 bits, a key it cannot write
    -- goes the old way rather than failing the result.
    """
    if orjson is None:
        return json_dumps(data)
    encoder = JSONEncoder()

    def default(o):
        # A float subclass orjson will not take (numpy's): what json_dumps does.
        if isinstance(o, float):
            return None if math.isnan(o) or math.isinf(o) else float(o)
        return encoder.default(o)

    try:
        return orjson.dumps(
            data, default=default, option=orjson.OPT_PASSTHROUGH_DATETIME | orjson.OPT_NON_STR_KEYS
        ).decode()
    except (TypeError, ValueError):
        return json_dumps(data)


def mustache_render(template, context=None, **kwargs):
    renderer = pystache.Renderer(escape=lambda u: u)
    return renderer.render(template, context, **kwargs)


def mustache_render_escape(template, context=None, **kwargs):
    renderer = pystache.Renderer()
    return renderer.render(template, context, **kwargs)


def build_url(request, host, path):
    parts = request.host.split(":")
    if len(parts) > 1:
        port = parts[1]
        if (port, request.scheme) not in (("80", "http"), ("443", "https")):
            host = "{}:{}".format(host, port)

    return "{}://{}{}".format(request.scheme, host, path)


def collect_parameters_from_request(args):
    parameters = {}

    for k, v in args.items():
        if k.startswith("p_"):
            parameters[k[2:]] = v

    return parameters


def base_url(org):
    if settings.MULTI_ORG:
        return "{}/{}".format(settings.HOST, org.slug)

    return settings.HOST


def filter_none(d):
    return select_values(lambda v: v is not None, d)


def to_filename(s):
    s = re.sub(r'[<>:"\\\/|?*]+', " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s, flags=re.UNICODE)
    return s.strip("_")


def deprecated():
    def wrapper(K):
        setattr(K, "deprecated", True)
        return K

    return wrapper


def render_template(path, context):
    """Render a template with context, without loading the entire app context.
    Using Flask's `render_template` function requires the entire app context to load, which in turn triggers any
    function decorated with the `context_processor` decorator, which is not explicitly required for rendering purposes.
    """
    return current_app.jinja_env.get_template(path).render(**context)

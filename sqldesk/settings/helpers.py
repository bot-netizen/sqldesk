import os
from urllib.parse import urlparse, urlunparse

# SQLDesk reads SQLDESK_* environment variables. This project has been renamed
# twice -- Redash set REDASH_*, Tealdash set TEALDASH_* -- and an operator
# upgrading in place has no reason to expect their .env to stop working, so both
# older prefixes are accepted as fallbacks. An explicitly set SQLDESK_* always
# wins, and TEALDASH_* wins over REDASH_* because it is the more recent thing
# the operator wrote.
#
# This lives here rather than in settings/__init__.py because that module reads
# the environment at import time, and it imports this one first. Remove a prefix
# once no deployment carries it.
for _prefix in ("TEALDASH_", "REDASH_"):
    for _key, _value in list(os.environ.items()):
        if _key.startswith(_prefix):
            os.environ.setdefault("SQLDESK_" + _key[len(_prefix) :], _value)
del _prefix, _key, _value


def fix_assets_path(path):
    fullpath = os.path.join(os.path.dirname(__file__), "../", path)
    return fullpath


def array_from_string(s):
    array = s.split(",")
    if "" in array:
        array.remove("")

    return array


def set_from_string(s):
    return set(array_from_string(s))


def parse_boolean(s):
    """Takes a string and returns the equivalent as a boolean value."""
    s = s.strip().lower()
    if s in ("yes", "true", "on", "1"):
        return True
    elif s in ("no", "false", "off", "0", "none"):
        return False
    else:
        raise ValueError("Invalid boolean value %r" % s)


def cast_int_or_default(val, default=None):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def int_or_none(value):
    if value is None:
        return value

    return int(value)


def add_decode_responses_to_redis_url(url):
    """Make sure that the Redis URL includes the `decode_responses` option."""
    parsed = urlparse(url)

    query = "decode_responses=True"
    if parsed.query and "decode_responses" not in parsed.query:
        query = "{}&{}".format(parsed.query, query)
    elif "decode_responses" in parsed.query:
        query = parsed.query

    return urlunparse(
        [
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment,
        ]
    )

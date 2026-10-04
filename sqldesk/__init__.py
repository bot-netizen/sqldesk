import logging
import os
import socket
import sys

import redis
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from statsd import StatsClient

from sqldesk import settings
from sqldesk.app import create_app  # noqa
from sqldesk.destinations import import_destinations
from sqldesk.query_runner import import_query_runners

__version__ = "0.7.0"


if os.environ.get("REMOTE_DEBUG"):
    # debugpy is a development dependency, so the released image does not
    # carry a debug server -- say so, rather than failing on the import.
    try:
        import debugpy
    except ImportError:
        sys.stderr.write("REMOTE_DEBUG is set, but debugpy is not installed. This image does not include it.\n")
    else:
        debugpy.listen(("0.0.0.0", 5678))
        debugpy.wait_for_client()


def setup_logging():
    handler = logging.StreamHandler(sys.stdout if settings.LOG_STDOUT else sys.stderr)
    formatter = logging.Formatter(settings.LOG_FORMAT)
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(settings.LOG_LEVEL)

    # Make noisy libraries less noisy
    if settings.LOG_LEVEL != "DEBUG":
        for name in [
            "passlib",
            "requests.packages.urllib3",
            "snowflake.connector",
            "apiclient",
        ]:
            logging.getLogger(name).setLevel("ERROR")


setup_logging()


def _redis(url):
    """
    A Redis client that notices when the other end has gone away.

    `from_url` on its own gives a socket with no keepalive and no health
    check, so a connection whose peer has vanished -- a laptop that slept, a
    network blip, a NAT table that forgot -- leaves the next command blocked
    in recv() until the kernel gives up on the TCP connection, which is around
    fifteen minutes by default. For the scheduler that means fifteen minutes
    in which nothing is scheduled and the process looks perfectly healthy.
    Measured on the development cluster: twenty-four minutes of a scheduler
    that was up, awake, and enqueueing nothing.

    `health_check_interval` makes redis-py PING a connection that has been
    idle that long before handing it out, and reconnect if the PING fails.
    Keepalive makes the kernel notice a dead peer in about ninety seconds
    rather than fifteen minutes.

    Deliberately no `socket_timeout`: RQ workers wait on BLPOP for longer than
    any sensible value, and a socket timeout below that turns an idle worker
    into a reconnect loop.
    """
    options = {"health_check_interval": 30, "socket_keepalive": True}

    # The TCP keepalive knobs are Linux's names. macOS spells the first one
    # differently and has none of the others, so ask for what exists rather
    # than assuming the platform.
    keepalive = {}
    for name, value in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
        option = getattr(socket, name, None)
        if option is not None:
            keepalive[option] = value
    if keepalive:
        options["socket_keepalive_options"] = keepalive

    return redis.from_url(url, **options)


redis_connection = _redis(settings.REDIS_URL)
rq_redis_connection = _redis(settings.RQ_REDIS_URL)
mail = Mail()
migrate = Migrate(compare_type=True)
statsd_client = StatsClient(host=settings.STATSD_HOST, port=settings.STATSD_PORT, prefix=settings.STATSD_PREFIX)
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.LIMITER_STORAGE)

import_query_runners(settings.QUERY_RUNNERS)
import_destinations(settings.DESTINATIONS)

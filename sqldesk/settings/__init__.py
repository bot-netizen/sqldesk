import importlib
import os
import ssl

from flask_talisman import talisman
from funcy import distinct, remove

from sqldesk.settings.helpers import (
    add_decode_responses_to_redis_url,
    array_from_string,
    cast_int_or_default,
    fix_assets_path,
    int_or_none,
    parse_boolean,
    set_from_string,
)
from sqldesk.settings.organization import DATE_FORMAT, TIME_FORMAT  # noqa

# _REDIS_URL is the unchanged REDIS_URL we get from env vars, to be used later with RQ
_REDIS_URL = os.environ.get("SQLDESK_REDIS_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
# This is the one to use for SQLDesk' own connection:
REDIS_URL = add_decode_responses_to_redis_url(_REDIS_URL)
PROXIES_COUNT = int(os.environ.get("SQLDESK_PROXIES_COUNT", "1"))

STATSD_HOST = os.environ.get("SQLDESK_STATSD_HOST", "127.0.0.1")
STATSD_PORT = int(os.environ.get("SQLDESK_STATSD_PORT", "8125"))
STATSD_PREFIX = os.environ.get("SQLDESK_STATSD_PREFIX", "sqldesk")
STATSD_USE_TAGS = parse_boolean(os.environ.get("SQLDESK_STATSD_USE_TAGS", "false"))

# Connection settings for SQLDesk's own database (where we store the queries, results, etc)
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SQLDESK_DATABASE_URL", os.environ.get("DATABASE_URL", "postgresql:///postgres")
)
SQLALCHEMY_MAX_OVERFLOW = int_or_none(os.environ.get("SQLALCHEMY_MAX_OVERFLOW"))
SQLALCHEMY_POOL_SIZE = int_or_none(os.environ.get("SQLALCHEMY_POOL_SIZE"))
SQLALCHEMY_DISABLE_POOL = parse_boolean(os.environ.get("SQLALCHEMY_DISABLE_POOL", "false"))
SQLALCHEMY_ENABLE_POOL_PRE_PING = parse_boolean(os.environ.get("SQLALCHEMY_ENABLE_POOL_PRE_PING", "false"))
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False

RQ_REDIS_URL = os.environ.get("RQ_REDIS_URL", _REDIS_URL)

# The following enables periodic job (every 5 minutes) of removing unused query results.
QUERY_RESULTS_CLEANUP_ENABLED = parse_boolean(os.environ.get("SQLDESK_QUERY_RESULTS_CLEANUP_ENABLED", "true"))
# Raised from 100. The cleanup job runs every 5 minutes, so the old default
# capped eviction at 288 x 100 = 28,800 rows a day -- about 20 results a minute.
# A few hundred queries on short schedules exceeds that, and once it does,
# query_results grows without bound forever with nothing saying so. 1,000 gives
# ten times the headroom and is still a trivial DELETE; raise it further if
# cleanup_query_results starts logging that it hit the cap.
QUERY_RESULTS_CLEANUP_COUNT = int(os.environ.get("SQLDESK_QUERY_RESULTS_CLEANUP_COUNT", "1000"))
QUERY_RESULTS_CLEANUP_MAX_AGE = int(os.environ.get("SQLDESK_QUERY_RESULTS_CLEANUP_MAX_AGE", "7"))

# `events` gets a row every time anyone runs a query, each carrying the full
# query text, so it is the fastest-growing table in the schema and the one
# nobody thinks to look at. Kept for a quarter by default, which is long
# enough for "who ran that, and when" and short enough not to become the
# largest thing in the database.
EVENTS_CLEANUP_MAX_AGE = int(os.environ.get("SQLDESK_EVENTS_CLEANUP_MAX_AGE", "90"))
EVENTS_CLEANUP_COUNT = int(os.environ.get("SQLDESK_EVENTS_CLEANUP_COUNT", "10000"))

QUERY_RESULTS_EXPIRED_TTL_ENABLED = parse_boolean(os.environ.get("SQLDESK_QUERY_RESULTS_EXPIRED_TTL_ENABLED", "false"))
# default set query results expired ttl 86400 seconds
QUERY_RESULTS_EXPIRED_TTL = int(os.environ.get("SQLDESK_QUERY_RESULTS_EXPIRED_TTL", "86400"))

SCHEMAS_REFRESH_SCHEDULE = int(os.environ.get("SQLDESK_SCHEMAS_REFRESH_SCHEDULE", 30))
SCHEMAS_REFRESH_TIMEOUT = int(os.environ.get("SQLDESK_SCHEMAS_REFRESH_TIMEOUT", 300))

AUTH_TYPE = os.environ.get("SQLDESK_AUTH_TYPE", "api_key")
INVITATION_TOKEN_MAX_AGE = int(os.environ.get("SQLDESK_INVITATION_TOKEN_MAX_AGE", 60 * 60 * 24 * 7))

# The secret key to use in the Flask app for various cryptographic features
SECRET_KEY = os.environ.get("SQLDESK_COOKIE_SECRET")

if SECRET_KEY is None:
    raise Exception(
        "You must set the SQLDESK_COOKIE_SECRET environment variable. See https://bot-netizen.github.io/sqldesk/docs/configuration for more information."
    )

# The secret key to use when encrypting data source options
DATASOURCE_SECRET_KEY = os.environ.get("SQLDESK_SECRET_KEY", SECRET_KEY)

# Whether and how to redirect non-HTTP requests to HTTPS. Disabled by default.
ENFORCE_HTTPS = parse_boolean(os.environ.get("SQLDESK_ENFORCE_HTTPS", "false"))
ENFORCE_HTTPS_PERMANENT = parse_boolean(os.environ.get("SQLDESK_ENFORCE_HTTPS_PERMANENT", "false"))
# Whether file downloads are enforced or not.
ENFORCE_FILE_SAVE = parse_boolean(os.environ.get("SQLDESK_ENFORCE_FILE_SAVE", "true"))

# Whether api calls using the json query runner will block private addresses
ENFORCE_PRIVATE_ADDRESS_BLOCK = parse_boolean(os.environ.get("SQLDESK_ENFORCE_PRIVATE_IP_BLOCK", "true"))

# Whether to use secure cookies by default.
COOKIES_SECURE = parse_boolean(os.environ.get("SQLDESK_COOKIES_SECURE", str(ENFORCE_HTTPS)))
# Whether the session cookie is set to secure.
SESSION_COOKIE_SECURE = parse_boolean(os.environ.get("SQLDESK_SESSION_COOKIE_SECURE") or str(COOKIES_SECURE))
# Whether the session cookie is set HttpOnly.
SESSION_COOKIE_HTTPONLY = parse_boolean(os.environ.get("SQLDESK_SESSION_COOKIE_HTTPONLY", "true"))
SESSION_EXPIRY_TIME = int(os.environ.get("SQLDESK_SESSION_EXPIRY_TIME", 60 * 60 * 6))
SESSION_COOKIE_NAME = os.environ.get("SQLDESK_SESSION_COOKIE_NAME", "session")

# Whether the session cookie is set to secure.
REMEMBER_COOKIE_SECURE = parse_boolean(os.environ.get("SQLDESK_REMEMBER_COOKIE_SECURE") or str(COOKIES_SECURE))
# Whether the remember cookie is set HttpOnly.
REMEMBER_COOKIE_HTTPONLY = parse_boolean(os.environ.get("SQLDESK_REMEMBER_COOKIE_HTTPONLY", "true"))
# The amount of time before the remember cookie expires.
REMEMBER_COOKIE_DURATION = int(os.environ.get("SQLDESK_REMEMBER_COOKIE_DURATION", 60 * 60 * 24 * 31))

# Doesn't set X-Frame-Options by default since it's highly dependent
# on the specific deployment.
# See https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
# for more information.
FRAME_OPTIONS = os.environ.get("SQLDESK_FRAME_OPTIONS", "deny")
FRAME_OPTIONS_ALLOW_FROM = os.environ.get("SQLDESK_FRAME_OPTIONS_ALLOW_FROM", "")

# Whether and how to send Strict-Transport-Security response headers.
# See https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
# for more information.
HSTS_ENABLED = parse_boolean(os.environ.get("SQLDESK_HSTS_ENABLED") or str(ENFORCE_HTTPS))
HSTS_PRELOAD = parse_boolean(os.environ.get("SQLDESK_HSTS_PRELOAD", "false"))
HSTS_MAX_AGE = int(os.environ.get("SQLDESK_HSTS_MAX_AGE", talisman.ONE_YEAR_IN_SECS))
HSTS_INCLUDE_SUBDOMAINS = parse_boolean(os.environ.get("SQLDESK_HSTS_INCLUDE_SUBDOMAINS", "false"))

# Whether and how to send Content-Security-Policy response headers.
# See https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
# for more information.
# Overriding this value via an environment variables requires setting it
# as a string in the general CSP format of a semicolon separated list of
# individual CSP directives, see https://github.com/GoogleCloudPlatform/flask-talisman#example-7
# for more information. E.g.:
CONTENT_SECURITY_POLICY = os.environ.get(
    "SQLDESK_CONTENT_SECURITY_POLICY",
    "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-eval'; font-src 'self' data:; img-src 'self' http: https: data: blob:; object-src 'none'; frame-ancestors 'none';",
)
CONTENT_SECURITY_POLICY_REPORT_URI = os.environ.get("SQLDESK_CONTENT_SECURITY_POLICY_REPORT_URI", "")
CONTENT_SECURITY_POLICY_REPORT_ONLY = parse_boolean(
    os.environ.get("SQLDESK_CONTENT_SECURITY_POLICY_REPORT_ONLY", "false")
)
CONTENT_SECURITY_POLICY_NONCE_IN = array_from_string(os.environ.get("SQLDESK_CONTENT_SECURITY_POLICY_NONCE_IN", ""))

# Whether and how to send Referrer-Policy response headers. Defaults to
# 'strict-origin-when-cross-origin'.
# See https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy
# for more information.
REFERRER_POLICY = os.environ.get("SQLDESK_REFERRER_POLICY", "strict-origin-when-cross-origin")
# Whether and how to send Feature-Policy response headers. Defaults to
# an empty value.
# See https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Feature-Policy
# for more information.
FEATURE_POLICY = os.environ.get("SQLDESK_FEATURE_POLICY", "")

MULTI_ORG = parse_boolean(os.environ.get("SQLDESK_MULTI_ORG", "false"))

# If SQLDesk is behind a proxy it might sometimes receive a X-Forwarded-Proto of HTTP
# even if your actual SQLDesk URL scheme is HTTPS. This will cause Flask to build
# the OAuth redirect URL incorrectly thus failing auth. This is especially common if
# you're behind a SSL/TCP configured AWS ELB or similar.
# This setting will force the URL scheme.
GOOGLE_OAUTH_SCHEME_OVERRIDE = os.environ.get("SQLDESK_GOOGLE_OAUTH_SCHEME_OVERRIDE", "")

GOOGLE_CLIENT_ID = os.environ.get("SQLDESK_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("SQLDESK_GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# If SQLDesk is behind a proxy it might sometimes receive a X-Forwarded-Proto of HTTP
# even if your actual SQLDesk URL scheme is HTTPS. This will cause Flask to build
# the SAML redirect URL incorrect thus failing auth. This is especially common if
# you're behind a SSL/TCP configured AWS ELB or similar.
# This setting will force the URL scheme.
SAML_SCHEME_OVERRIDE = os.environ.get("SQLDESK_SAML_SCHEME_OVERRIDE", "")

SAML_ENCRYPTION_PEM_PATH = os.environ.get("SQLDESK_SAML_ENCRYPTION_PEM_PATH", "")
SAML_ENCRYPTION_CERT_PATH = os.environ.get("SQLDESK_SAML_ENCRYPTION_CERT_PATH", "")
SAML_ENCRYPTION_ENABLED = SAML_ENCRYPTION_PEM_PATH != "" and SAML_ENCRYPTION_CERT_PATH != ""

# Enables the use of an externally-provided and trusted remote user via an HTTP
# header.  The "user" must be an email address.
#
# By default the trusted header is X-Forwarded-Remote-User.  You can change
# this by setting SQLDESK_REMOTE_USER_HEADER.
#
# Enabling this authentication method is *potentially dangerous*, and it is
# your responsibility to ensure that only a trusted frontend (usually on the
# same server) can talk to the backend server, otherwise people will be
# able to login as anyone they want by directly talking to the backend.
# You must *also* ensure that any special header in the original request is
# removed or always overwritten by your frontend, otherwise your frontend may
# pass it through to the backend unchanged.
#
# Note that the remote user is only checked once, upon the first need
# for a login, and then set a cookie which keeps the user logged in.  Dropping
# the remote user header after subsequent requests won't automatically log the
# user out.  Doing so could be done with further work, but usually it's
# unnecessary.
#
# If you also set the organization setting auth_password_login_enabled to false,
# then your authentication will be seamless.  Otherwise a link will be presented
# on the login page to trigger remote user auth.
REMOTE_USER_LOGIN_ENABLED = parse_boolean(os.environ.get("SQLDESK_REMOTE_USER_LOGIN_ENABLED", "false"))
REMOTE_USER_HEADER = os.environ.get("SQLDESK_REMOTE_USER_HEADER", "X-Forwarded-Remote-User")

# If the organization setting auth_password_login_enabled is not false, then users will still be
# able to login through SQLDesk instead of the LDAP server
LDAP_LOGIN_ENABLED = parse_boolean(os.environ.get("SQLDESK_LDAP_LOGIN_ENABLED", "false"))
# Bind LDAP using SSL. Default is False
LDAP_SSL = parse_boolean(os.environ.get("SQLDESK_LDAP_USE_SSL", "false"))
# Choose authentication method(SIMPLE, ANONYMOUS or NTLM). Default is SIMPLE
LDAP_AUTH_METHOD = os.environ.get("SQLDESK_LDAP_AUTH_METHOD", "SIMPLE")
# The LDAP directory address (ex. ldap://10.0.10.1:389)
LDAP_HOST_URL = os.environ.get("SQLDESK_LDAP_URL", None)
# The DN & password used to connect to LDAP to determine the identity of the user being authenticated.
# For AD this should be "org\\user".
LDAP_BIND_DN = os.environ.get("SQLDESK_LDAP_BIND_DN", None)
LDAP_BIND_DN_PASSWORD = os.environ.get("SQLDESK_LDAP_BIND_DN_PASSWORD", "")
# AD/LDAP email and display name keys
LDAP_DISPLAY_NAME_KEY = os.environ.get("SQLDESK_LDAP_DISPLAY_NAME_KEY", "displayName")
LDAP_EMAIL_KEY = os.environ.get("SQLDESK_LDAP_EMAIL_KEY", "mail")
# Prompt that should be shown above username/email field.
LDAP_CUSTOM_USERNAME_PROMPT = os.environ.get("SQLDESK_LDAP_CUSTOM_USERNAME_PROMPT", "LDAP/AD/SSO username:")
# LDAP Search DN TEMPLATE (for AD this should be "(sAMAccountName=%(username)s)"")
LDAP_SEARCH_TEMPLATE = os.environ.get("SQLDESK_LDAP_SEARCH_TEMPLATE", "(cn=%(username)s)")
# The schema to bind to (ex. cn=users,dc=ORG,dc=local)
LDAP_SEARCH_DN = os.environ.get("SQLDESK_LDAP_SEARCH_DN", os.environ.get("SQLDESK_SEARCH_DN"))

STATIC_ASSETS_PATH = fix_assets_path(os.environ.get("SQLDESK_STATIC_ASSETS_PATH", "../client/dist/"))
FLASK_TEMPLATE_PATH = fix_assets_path(os.environ.get("SQLDESK_FLASK_TEMPLATE_PATH", STATIC_ASSETS_PATH))

# Root directory for server-side storage of user-uploaded files (e.g. files queried via the DuckDB data source).
UPLOAD_ROOT = fix_assets_path(os.environ.get("SQLDESK_UPLOAD_ROOT", "../uploads/"))
UPLOAD_MAX_SIZE_MB = int(os.environ.get("SQLDESK_UPLOAD_MAX_SIZE_MB", "200"))
UPLOAD_ALLOWED_EXTENSIONS = set_from_string(os.environ.get("SQLDESK_UPLOAD_ALLOWED_EXTENSIONS", "csv,parquet"))
# Time limit (in seconds) for scheduled queries. Set this to -1 to execute without a time limit.
SCHEDULED_QUERY_TIME_LIMIT = int(os.environ.get("SQLDESK_SCHEDULED_QUERY_TIME_LIMIT", -1))

# Time limit (in seconds) for adhoc queries. Set this to -1 to execute without a time limit.
ADHOC_QUERY_TIME_LIMIT = int(os.environ.get("SQLDESK_ADHOC_QUERY_TIME_LIMIT", -1))

JOB_EXPIRY_TIME = int(os.environ.get("SQLDESK_JOB_EXPIRY_TIME", 3600 * 12))
JOB_DEFAULT_FAILURE_TTL = int(os.environ.get("SQLDESK_JOB_DEFAULT_FAILURE_TTL", 7 * 24 * 60 * 60))

LOG_LEVEL = os.environ.get("SQLDESK_LOG_LEVEL", "INFO")
LOG_STDOUT = parse_boolean(os.environ.get("SQLDESK_LOG_STDOUT", "false"))
LOG_PREFIX = os.environ.get("SQLDESK_LOG_PREFIX", "")
LOG_FORMAT = os.environ.get(
    "SQLDESK_LOG_FORMAT",
    LOG_PREFIX + "[%(asctime)s][PID:%(process)d][%(levelname)s][%(name)s] %(message)s",
)
RQ_WORKER_JOB_LOG_FORMAT = os.environ.get(
    "SQLDESK_RQ_WORKER_JOB_LOG_FORMAT",
    (
        LOG_PREFIX + "[%(asctime)s][PID:%(process)d][%(levelname)s][%(name)s] "
        "job.func_name=%(job_func_name)s "
        "job.id=%(job_id)s %(message)s"
    ),
)

# Mail settings:
MAIL_SERVER = os.environ.get("SQLDESK_MAIL_SERVER", "localhost")
MAIL_PORT = int(os.environ.get("SQLDESK_MAIL_PORT", 25))
MAIL_USE_TLS = parse_boolean(os.environ.get("SQLDESK_MAIL_USE_TLS", "false"))
MAIL_USE_SSL = parse_boolean(os.environ.get("SQLDESK_MAIL_USE_SSL", "false"))
MAIL_USERNAME = os.environ.get("SQLDESK_MAIL_USERNAME", None)
MAIL_PASSWORD = os.environ.get("SQLDESK_MAIL_PASSWORD", None)
MAIL_DEFAULT_SENDER = os.environ.get("SQLDESK_MAIL_DEFAULT_SENDER", None)
MAIL_MAX_EMAILS = os.environ.get("SQLDESK_MAIL_MAX_EMAILS", None)
MAIL_ASCII_ATTACHMENTS = parse_boolean(os.environ.get("SQLDESK_MAIL_ASCII_ATTACHMENTS", "false"))


def email_server_is_configured():
    return MAIL_DEFAULT_SENDER is not None


HOST = os.environ.get("SQLDESK_HOST", "")

SEND_FAILURE_EMAIL_INTERVAL = int(os.environ.get("SQLDESK_SEND_FAILURE_EMAIL_INTERVAL", 60))
MAX_FAILURE_REPORTS_PER_QUERY = int(os.environ.get("SQLDESK_MAX_FAILURE_REPORTS_PER_QUERY", 100))

ALERTS_DEFAULT_MAIL_SUBJECT_TEMPLATE = os.environ.get(
    "SQLDESK_ALERTS_DEFAULT_MAIL_SUBJECT_TEMPLATE", "Alert: {alert_name} changed status to {state}"
)

SQLDESK_ALERTS_DEFAULT_MAIL_BODY_TEMPLATE_FILE = os.environ.get(
    "SQLDESK_ALERTS_DEFAULT_MAIL_BODY_TEMPLATE_FILE", fix_assets_path("templates/emails/alert.html")
)

# How many requests are allowed per IP to the login page before
# being throttled?
# See https://flask-limiter.readthedocs.io/en/stable/#rate-limit-string-notation

RATELIMIT_ENABLED = parse_boolean(os.environ.get("SQLDESK_RATELIMIT_ENABLED", "true"))
THROTTLE_LOGIN_PATTERN = os.environ.get("SQLDESK_THROTTLE_LOGIN_PATTERN", "50/hour")
LIMITER_STORAGE = os.environ.get("SQLDESK_LIMITER_STORAGE", REDIS_URL)
THROTTLE_PASS_RESET_PATTERN = os.environ.get("SQLDESK_THROTTLE_PASS_RESET_PATTERN", "10/hour")

# CORS settings for the Query Result API (and possibly future external APIs).
# In most cases all you need to do is set SQLDESK_CORS_ACCESS_CONTROL_ALLOW_ORIGIN
# to the calling domain (or domains in a comma separated list).
ACCESS_CONTROL_ALLOW_ORIGIN = set_from_string(os.environ.get("SQLDESK_CORS_ACCESS_CONTROL_ALLOW_ORIGIN", ""))
ACCESS_CONTROL_ALLOW_CREDENTIALS = parse_boolean(
    os.environ.get("SQLDESK_CORS_ACCESS_CONTROL_ALLOW_CREDENTIALS", "false")
)
ACCESS_CONTROL_REQUEST_METHOD = os.environ.get("SQLDESK_CORS_ACCESS_CONTROL_REQUEST_METHOD", "GET, POST, PUT")
ACCESS_CONTROL_ALLOW_HEADERS = os.environ.get("SQLDESK_CORS_ACCESS_CONTROL_ALLOW_HEADERS", "Content-Type")

# Query Runners
default_query_runners = [
    "sqldesk.query_runner.athena",
    "sqldesk.query_runner.big_query",
    "sqldesk.query_runner.google_spreadsheets",
    "sqldesk.query_runner.graphite",
    "sqldesk.query_runner.mongodb",
    "sqldesk.query_runner.couchbase",
    "sqldesk.query_runner.mysql",
    "sqldesk.query_runner.pg",
    "sqldesk.query_runner.url",
    "sqldesk.query_runner.influx_db",
    "sqldesk.query_runner.influx_db_v2",
    "sqldesk.query_runner.elasticsearch",
    "sqldesk.query_runner.elasticsearch2",
    "sqldesk.query_runner.amazon_elasticsearch",
    "sqldesk.query_runner.trino",
    "sqldesk.query_runner.presto",
    "sqldesk.query_runner.pinot",
    "sqldesk.query_runner.databricks",
    "sqldesk.query_runner.hive_ds",
    "sqldesk.query_runner.impala_ds",
    "sqldesk.query_runner.vertica",
    "sqldesk.query_runner.clickhouse",
    "sqldesk.query_runner.tinybird",
    "sqldesk.query_runner.yandex_metrica",
    "sqldesk.query_runner.yandex_disk",
    "sqldesk.query_runner.rockset",
    "sqldesk.query_runner.treasuredata",
    "sqldesk.query_runner.sqlite",
    "sqldesk.query_runner.mssql",
    "sqldesk.query_runner.mssql_odbc",
    "sqldesk.query_runner.memsql_ds",
    "sqldesk.query_runner.jql",
    "sqldesk.query_runner.google_analytics",
    "sqldesk.query_runner.axibase_tsd",
    "sqldesk.query_runner.salesforce",
    "sqldesk.query_runner.query_results",
    "sqldesk.query_runner.prometheus",
    "sqldesk.query_runner.db2",
    "sqldesk.query_runner.druid",
    "sqldesk.query_runner.kylin",
    "sqldesk.query_runner.drill",
    "sqldesk.query_runner.uptycs",
    "sqldesk.query_runner.snowflake",
    "sqldesk.query_runner.phoenix",
    "sqldesk.query_runner.json_ds",
    "sqldesk.query_runner.cass",
    "sqldesk.query_runner.dgraph",
    "sqldesk.query_runner.azure_kusto",
    "sqldesk.query_runner.exasol",
    "sqldesk.query_runner.cloudwatch",
    "sqldesk.query_runner.cloudwatch_insights",
    "sqldesk.query_runner.corporate_memory",
    "sqldesk.query_runner.sparql_endpoint",
    "sqldesk.query_runner.excel",
    "sqldesk.query_runner.csv",
    "sqldesk.query_runner.databend",
    "sqldesk.query_runner.nz",
    "sqldesk.query_runner.arango",
    "sqldesk.query_runner.google_analytics4",
    "sqldesk.query_runner.google_search_console",
    "sqldesk.query_runner.ignite",
    "sqldesk.query_runner.oracle",
    "sqldesk.query_runner.e6data",
    "sqldesk.query_runner.risingwave",
    "sqldesk.query_runner.d1",
    "sqldesk.query_runner.duckdb",
]

enabled_query_runners = array_from_string(
    os.environ.get("SQLDESK_ENABLED_QUERY_RUNNERS", ",".join(default_query_runners))
)
additional_query_runners = array_from_string(os.environ.get("SQLDESK_ADDITIONAL_QUERY_RUNNERS", ""))
disabled_query_runners = array_from_string(os.environ.get("SQLDESK_DISABLED_QUERY_RUNNERS", ""))

QUERY_RUNNERS = remove(
    set(disabled_query_runners),
    distinct(enabled_query_runners + additional_query_runners),
)

dynamic_settings = importlib.import_module(
    os.environ.get("SQLDESK_DYNAMIC_SETTINGS_MODULE", "sqldesk.settings.dynamic_settings")
)

# Destinations
default_destinations = [
    "sqldesk.destinations.email",
    "sqldesk.destinations.slack",
    "sqldesk.destinations.webhook",
    "sqldesk.destinations.discord",
    "sqldesk.destinations.mattermost",
    "sqldesk.destinations.chatwork",
    "sqldesk.destinations.pagerduty",
    "sqldesk.destinations.hangoutschat",
    "sqldesk.destinations.microsoft_teams_webhook",
    "sqldesk.destinations.asana",
    "sqldesk.destinations.webex",
    "sqldesk.destinations.datadog",
]

enabled_destinations = array_from_string(
    os.environ.get("SQLDESK_ENABLED_DESTINATIONS", ",".join(default_destinations))
)
additional_destinations = array_from_string(os.environ.get("SQLDESK_ADDITIONAL_DESTINATIONS", ""))

DESTINATIONS = distinct(enabled_destinations + additional_destinations)

EVENT_REPORTING_WEBHOOKS = array_from_string(os.environ.get("SQLDESK_EVENT_REPORTING_WEBHOOKS", ""))

# Support for Sentry (https://getsentry.com/). Just set your Sentry DSN to enable it:
SENTRY_DSN = os.environ.get("SQLDESK_SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.environ.get("SQLDESK_SENTRY_ENVIRONMENT")

# Client side toggles:
ALLOW_SCRIPTS_IN_USER_INPUT = parse_boolean(os.environ.get("SQLDESK_ALLOW_SCRIPTS_IN_USER_INPUT", "false"))
# An ordinary dashboard's auto-refresh is a timer in every open tab, so it
# starts at ten minutes; anything faster is what live dashboards are for,
# which run the queries once on the server however many people watch. Values
# under the minimum are dropped even when set explicitly.
DASHBOARD_REFRESH_MINIMUM = 600
DASHBOARD_REFRESH_INTERVALS = [
    interval
    for interval in map(
        int,
        array_from_string(os.environ.get("SQLDESK_DASHBOARD_REFRESH_INTERVALS", "600,1800,3600,43200,86400")),
    )
    if interval >= DASHBOARD_REFRESH_MINIMUM
]
QUERY_REFRESH_INTERVALS = list(
    map(
        int,
        array_from_string(
            os.environ.get(
                "SQLDESK_QUERY_REFRESH_INTERVALS",
                "60, 300, 600, 900, 1800, 3600, 7200, 10800, 14400, 18000, 21600, 25200, 28800, 32400, 36000, 39600, 43200, 86400, 604800, 1209600, 2592000",
            )
        ),
    )
)
PAGE_SIZE = int(os.environ.get("SQLDESK_PAGE_SIZE", 20))
PAGE_SIZE_OPTIONS = list(
    map(
        int,
        array_from_string(os.environ.get("SQLDESK_PAGE_SIZE_OPTIONS", "5,10,20,50,100")),
    )
)
TABLE_CELL_MAX_JSON_SIZE = int(os.environ.get("SQLDESK_TABLE_CELL_MAX_JSON_SIZE", 50000))

# Features:
VERSION_CHECK = parse_boolean(os.environ.get("SQLDESK_VERSION_CHECK", "true"))
# Empty by default and therefore off. Upstream shipped a hard-coded endpoint on
# its own infrastructure; SQLDesk will not send anything anywhere unless an
# operator names the destination, because the payload includes usage data.
VERSION_CHECK_URL = os.environ.get("SQLDESK_VERSION_CHECK_URL", "")
FEATURE_DISABLE_REFRESH_QUERIES = parse_boolean(os.environ.get("SQLDESK_FEATURE_DISABLE_REFRESH_QUERIES", "false"))
FEATURE_SHOW_QUERY_RESULTS_COUNT = parse_boolean(os.environ.get("SQLDESK_FEATURE_SHOW_QUERY_RESULTS_COUNT", "true"))
FEATURE_AUTO_PUBLISH_NAMED_QUERIES = parse_boolean(
    os.environ.get("SQLDESK_FEATURE_AUTO_PUBLISH_NAMED_QUERIES", "true")
)
FEATURE_EXTENDED_ALERT_OPTIONS = parse_boolean(os.environ.get("SQLDESK_FEATURE_EXTENDED_ALERT_OPTIONS", "false"))

# Attaching a picture of a dashboard or a query to an alert needs something
# that can draw one, and nothing in this image can: see SCREENSHOT_URL. Off
# unless that is pointed at a renderer, so an install that never wants this
# pulls nothing extra and behaves exactly as it did.
FEATURE_ALERT_SCREENSHOTS = parse_boolean(os.environ.get("SQLDESK_FEATURE_ALERT_SCREENSHOTS", "false"))
# Where that renderer is, e.g. http://screenshots:3000. Empty means there is
# none, which turns the feature off however the flag above is set.
SCREENSHOT_URL = os.environ.get("SQLDESK_SCREENSHOT_URL", "")
SCREENSHOT_TIMEOUT = int(os.environ.get("SQLDESK_SCREENSHOT_TIMEOUT", "60"))
# How the renderer reaches this application. The worker and the renderer are
# other containers, so "localhost" is not it.
INTERNAL_BASE_URL = os.environ.get("SQLDESK_INTERNAL_BASE_URL", "http://server:5000")
#: Most images one alert may carry.
MAX_ALERT_ATTACHMENTS = 5

# BigQuery
BIGQUERY_HTTP_TIMEOUT = int(os.environ.get("SQLDESK_BIGQUERY_HTTP_TIMEOUT", "600"))

# Allow Parameters in Embeds
# WARNING: Deprecated!
# Embedded visualizations can take parameters from the query string when this is on.
ALLOW_PARAMETERS_IN_EMBEDS = parse_boolean(os.environ.get("SQLDESK_ALLOW_PARAMETERS_IN_EMBEDS", "false"))

# Enhance schema fetching
SCHEMA_RUN_TABLE_SIZE_CALCULATIONS = parse_boolean(
    os.environ.get("SQLDESK_SCHEMA_RUN_TABLE_SIZE_CALCULATIONS", "false")
)

# kylin
KYLIN_OFFSET = int(os.environ.get("SQLDESK_KYLIN_OFFSET", 0))
KYLIN_LIMIT = int(os.environ.get("SQLDESK_KYLIN_LIMIT", 50000))
KYLIN_ACCEPT_PARTIAL = parse_boolean(os.environ.get("SQLDESK_KYLIN_ACCEPT_PARTIAL", "false"))

# sqlparse
SQLPARSE_FORMAT_OPTIONS = {
    "reindent": parse_boolean(os.environ.get("SQLPARSE_FORMAT_REINDENT", "true")),
    "keyword_case": os.environ.get("SQLPARSE_FORMAT_KEYWORD_CASE", "upper"),
}

# requests
REQUESTS_ALLOW_REDIRECTS = parse_boolean(os.environ.get("SQLDESK_REQUESTS_ALLOW_REDIRECTS", "false"))

# Enforces CSRF token validation on API requests.
# This is turned off by default to avoid breaking any existing deployments but it is highly recommended to turn this toggle on to prevent CSRF attacks.
ENFORCE_CSRF = parse_boolean(os.environ.get("SQLDESK_ENFORCE_CSRF", "false"))

# Databricks

CSRF_TIME_LIMIT = int(os.environ.get("SQLDESK_CSRF_TIME_LIMIT", 3600 * 6))

# Email blocked domains, use delimiter comma to separated multiple domains
BLOCKED_DOMAINS = set_from_string(os.environ.get("SQLDESK_BLOCKED_DOMAINS", "qq.com"))

"""
The HTTP end of the MCP server, and its audit.

Streamable HTTP rather than stdio: stdio means the server runs on the machine
the client runs on, and the whole point here is that SQLDesk is somewhere
else -- a cluster, a VM, a container. One POST endpoint carrying JSON-RPC,
which is what a remote MCP client speaks.

Authentication is a SQLDesk API key in the Authorization header: a credential
the user already has, which already identifies a user, so every permission
check downstream is the one the rest of the application makes.

Every request is recorded, including the ones refused before anyone was
identified. Those are the rows worth having.
"""

import datetime
import logging
import re
import time
import uuid

from flask import jsonify, request
from flask_restful import abort
from sqlalchemy.orm.exc import NoResultFound

from sqldesk import features, models, oauth, redis_connection, settings
from sqldesk.authentication import current_org
from sqldesk.handlers.base import BaseResource, routes
from sqldesk.mcp import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    McpError,
    handle,
    take_write_note,
    time_budget,
)
from sqldesk.permissions import require_super_admin
from sqldesk.security import csrf

logger = logging.getLogger(__name__)

UNAUTHORIZED = -32001
SESSION_HEADER = "Mcp-Session-Id"
SESSION_ID = re.compile(r"[0-9a-f]{32}")
#: Long enough to be worth reading, short enough not to be a copy of the
#: request. A caller can put anything in an argument.
DETAIL_LIMIT = 500
#: JSON-RPC batches were dropped from MCP in 2025-06-18; older clients may
#: still send them. Each message is a tool call on this web worker's time.
MAX_BATCH = 10


def _error(code, message, message_id=None):
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _record(org, user, session_id, client, method, tool, outcome, detail=None, started=None):
    """
    One row per request. Never raises: an audit that can fail the thing it is
    auditing is worse than no audit, because the failure looks like the
    feature being broken.
    """
    try:
        models.db.session.add(
            models.McpEvent(
                org=org,
                user=user if user is not None and not user.is_api_user() else None,
                session_id=(session_id or None) and str(session_id)[:64],
                client=(client or None) and str(client)[:255],
                method=(method or "")[:64],
                tool=(tool or None) and str(tool)[:64],
                outcome=outcome,
                detail=(detail or None) and str(detail)[:DETAIL_LIMIT],
                duration_ms=int((time.time() - started) * 1000) if started else None,
                remote_addr=(request.remote_addr or "")[:64] or None,
            )
        )
        models.db.session.commit()
    except Exception:
        logger.exception("could not write an MCP audit row")
        models.db.session.rollback()


def _refusal_worth_recording():
    """
    Whether this address has room left in its minute's allowance of refused
    rows. A script trying keys would otherwise write rows as fast as it can
    post. The answer is still 401 either way, and nobody is blocked: a limit
    on requests would also shut out the working clients behind the same
    address, which on a VPN is everyone.
    """
    try:
        key = "mcp:refused:{}:{}".format(request.remote_addr, int(time.time() // 60))
        count = redis_connection.incr(key)
        if count == 1:
            redis_connection.expire(key, 120)
        return count <= settings.MCP_AUDIT_REFUSALS_PER_MINUTE
    except Exception:
        # The audit is worth more than the limit on it.
        return True


def _bearer():
    """
    The credential the client presented, however it presented it.

    The header is preferred over the query parameter because a URL is logged by
    every proxy between here and the client; the parameter stays for the
    scripts that already use it.
    """
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    if header.lower().startswith("key "):
        return header[4:].strip()
    return request.args.get("api_key")


def _identify(org):
    """
    Who is calling: `(user, oauth_token)`, either part possibly None.

    Two credentials are accepted and they are not equivalent. An OAuth token
    expires, can be revoked from a profile page, and names the client that
    holds it. An API key does none of those things -- it is the same secret
    forever, and it is kept because scripts and headless setups need one.

    The prefix decides which table to look in, so the common case is one
    indexed lookup rather than two. A credential with our prefix is never
    tried as an API key: a token that has been revoked must be refused, not
    quietly re-interpreted.
    """
    credential = _bearer()
    if not credential:
        return None, None

    if oauth.looks_like_an_oauth_token(credential):
        token = oauth.token_for_bearer(credential, org)
        return (token.user if token else None), token

    try:
        user = models.User.get_by_api_key_and_org(credential, org)
    except NoResultFound:
        return None, None
    return (None if user.is_disabled else user), None


def _client_name(message):
    """What the client called itself at initialize, for the audit."""
    if not isinstance(message, dict) or message.get("method") != "initialize":
        return None
    params = message.get("params") or {}
    info = (params.get("clientInfo") or {}) if isinstance(params, dict) else {}
    if not isinstance(info, dict):
        return None
    name = info.get("name")
    version = info.get("version")
    return "{} {}".format(name, version).strip() if name else None


def _summary(message):
    """
    A line worth keeping. The question asked, or the tool called -- never the
    whole argument object, which is a caller's to fill however they like.

    A write says what it changed, before and after: "update_table ok" did not
    answer the one question anybody brings to an audit of an agent's writes,
    which is what that table used to say.
    """
    written = take_write_note()
    if written:
        return written[:DETAIL_LIMIT]
    params = (message.get("params") or {}) if isinstance(message, dict) else {}
    arguments = (params.get("arguments") or {}) if isinstance(params, dict) else {}
    if not isinstance(arguments, dict):
        return None
    for field in ("question", "sql"):
        if arguments.get(field):
            return "{}: {}".format(field, str(arguments[field])[:200])
    if arguments.get("names"):
        return "names: {}".format(", ".join(str(n) for n in arguments["names"])[:200])
    return None


# Exempt from CSRF, which protects cookie sessions: a browser attaches the
# cookie to a forged request by itself. Nothing attaches an API key by itself,
# and an MCP client has no page to have read a CSRF token from -- with
# SQLDESK_ENFORCE_CSRF on, every call was refused before it was authenticated.
@csrf.exempt
@routes.route("/mcp", methods=["POST"])
@routes.route("/api/mcp", methods=["POST"])
def mcp_endpoint():
    if not settings.FEATURE_AI:
        return jsonify(_error(INVALID_REQUEST, "MCP is off on this instance.")), 404

    started = time.time()
    org = current_org._get_current_object()
    # Only an id this server issued. Anything else went into a 64-character
    # column as given; longer, the audit row failed to save, and the request
    # went ahead without one.
    session_id = request.headers.get(SESSION_HEADER)
    if session_id and not SESSION_ID.fullmatch(session_id):
        session_id = None
    user, token = _identify(org)

    if user is None:
        # Recorded before anything else: a credential that does not work,
        # tried repeatedly, is the thing an audit exists to show -- up to a
        # point.
        if _refusal_worth_recording():
            _record(org, None, session_id, None, "authenticate", None, "refused", "no or unknown credential", started)
        return _challenge()

    if not features.can(user, features.USE_MCP):
        # A working key belonging to somebody who may not use MCP. Recorded
        # under their name, which is the difference between this and an
        # unknown key: an administrator can see who is trying and grant it.
        if _refusal_worth_recording():
            _record(org, user, session_id, None, "authenticate", None, "refused", "no MCP permission", started)
        response = jsonify(
            _error(
                UNAUTHORIZED,
                "This account may not use MCP. An administrator grants it to a group under Settings -> Groups.",
            )
        )
        response.status_code = 403
        return response

    payload = request.get_json(force=True, silent=True)
    if payload is None:
        _record(org, user, session_id, None, "?", None, "error", "body was not JSON", started)
        return jsonify(_error(PARSE_ERROR, "Expected a JSON body.")), 400

    # A batch is a list. Notifications inside it produce no reply, and a batch
    # of nothing but notifications is answered with 202 and no body.
    messages = payload if isinstance(payload, list) else [payload]
    if not messages or len(messages) > MAX_BATCH:
        detail = "empty batch" if not messages else "batch of {}".format(len(messages))
        _record(org, user, session_id, None, "batch", None, "refused", detail, started)
        return jsonify(_error(INVALID_REQUEST, "A batch holds 1 to {} messages.".format(MAX_BATCH))), 400

    if token is not None:
        # Written at most once a minute per token; see sqldesk.oauth. This is
        # what makes "last used" on somebody's profile worth reading, and the
        # difference between a client they still use and one they forgot.
        oauth.note_used(token)

    with time_budget(settings.MCP_TIME_BUDGET):
        replies, issued_session = _answer(messages, org, user, session_id, token=token)

    if not replies:
        response = jsonify(None)
        response.status_code = 202
        response.set_data(b"")
    else:
        response = jsonify(replies if isinstance(payload, list) else replies[0])
    if issued_session:
        response.headers[SESSION_HEADER] = issued_session
    return response


def _registered_client_name(token):
    """
    What the client holding this token registered as.

    Preferred over the name a client gives at `initialize`, which is whatever
    it chose to say this minute. This one was recorded when somebody agreed to
    it on a consent page, so an audit row says which connection was used.
    """
    if token is None:
        return None
    client = models.OAuthClient.query.filter(models.OAuthClient.client_id == token.client_id).first()
    return client.name if client is not None else None


def _challenge():
    """
    401, and where to go next.

    `resource_metadata` is how a client discovers that OAuth exists here: RFC
    9728 says the resource points at its own metadata document from this
    header, and an MCP client reads it, follows it to the authorization
    server, and starts the flow. Without this parameter a client has no way to
    find any of it and the only route left is a pasted API key.

    Built from the request so a client reached on a port-forward or behind a
    different name is sent somewhere it can actually open.
    """
    if settings.MCP_OAUTH_ENABLED and settings.FEATURE_AI:
        message = (
            "Authentication is required. Sign in through the OAuth flow advertised in WWW-Authenticate, "
            "or send a SQLDesk API key as Authorization: Bearer <key>."
        )
    else:
        message = "A SQLDesk API key is required: Authorization: Bearer <key>."

    response = jsonify(_error(UNAUTHORIZED, message))
    response.status_code = 401
    if settings.MCP_OAUTH_ENABLED and settings.FEATURE_AI:
        root = request.url_root.rstrip("/")
        slug = (request.view_args or {}).get("org_slug")
        origin = "{}/{}".format(root, slug) if slug else root
        response.headers[
            "WWW-Authenticate"
        ] = 'Bearer resource_metadata="{}/.well-known/oauth-protected-resource"'.format(origin)
    else:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def _answer(messages, org, user, session_id, token=None):
    replies, issued_session = [], None
    # The registered name of the client holding the token, where there is one.
    # A client that authenticated with OAuth is identified even before it says
    # anything about itself at initialize -- and it cannot lie about this one.
    granted_to = _registered_client_name(token)
    for message in messages:
        message_started = time.time()
        message_id = message.get("id") if isinstance(message, dict) else None
        method = message.get("method") if isinstance(message, dict) else "?"
        tool = None
        if method == "tools/call":
            params = message.get("params") if isinstance(message, dict) else None
            tool = params.get("name") if isinstance(params, dict) else None

        # A session is issued at initialize and echoed by the client after.
        # Without it "who is connected" has nothing to group by, because this
        # transport holds no connection open.
        if method == "initialize" and not session_id:
            session_id = issued_session = uuid.uuid4().hex

        try:
            result = handle(message, user, org, by_api_key=token is None)
        except McpError as error:
            _record(
                org,
                user,
                session_id,
                granted_to or _client_name(message),
                method,
                tool,
                "error",
                error.message,
                message_started,
            )
            replies.append(_error(error.code, error.message, message_id))
            continue
        except Exception:
            logger.exception("MCP request failed")
            _record(org, user, session_id, None, method, tool, "error", "unhandled", message_started)
            replies.append(_error(INTERNAL_ERROR, "That request could not be handled.", message_id))
            continue

        if result is None and "id" not in message:
            # A notification: acknowledged, never run. The row said "ok".
            outcome = "ignored"
        else:
            outcome = "error" if isinstance(result, dict) and result.get("isError") else "ok"
        _record(
            org,
            user,
            session_id,
            granted_to or _client_name(message),
            method,
            tool,
            outcome,
            _summary(message),
            message_started,
        )
        if result is not None:
            replies.append({"jsonrpc": "2.0", "id": message_id, "result": result})
    return replies, issued_session


class MyMcpResource(BaseResource):
    """
    One person's own MCP activity, for the My MCP page.

    Separate from the audit above, and the difference is the point. The audit
    names every user, every question and every address; this names nobody else
    and carries **no question, no SQL and no arguments** -- only which tool was
    called, when, whether it worked and how long it took. A page that showed
    somebody their own questions would be harmless; a page that showed them
    through an endpoint that could be asked about another user would not, so
    the endpoint cannot be asked about another user at all.

    Behind `use_mcp`: somebody who may not connect a client has nothing to see
    here, and offering the page would be offering a page about a feature they
    do not have.
    """

    #: Enough to see what a client has been doing without reading a log.
    LIMIT = 50
    #: The transport holds no socket open, so "connected" can only mean
    #: "recently active". Saying otherwise with a green dot would be a lie.
    ACTIVE_MINUTES = 15

    def get(self):
        if not features.can(self.current_user, features.USE_MCP):
            abort(403, message="Your account may not use MCP.")

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=self.ACTIVE_MINUTES)
        mine = models.McpEvent.query.filter(
            models.McpEvent.org == self.current_org,
            models.McpEvent.user_id == self.current_user.id,
        )

        events = mine.order_by(models.McpEvent.created_at.desc()).limit(self.LIMIT).all()
        recent = [event for event in events if event.created_at >= since]

        return {
            # Before a first call the page shows only how to connect, so it
            # needs to know there has not been one.
            "ever_connected": bool(events),
            "connected": bool(recent),
            "last_call_at": events[0].created_at if events else None,
            "clients": sorted({event.client for event in recent if event.client}),
            "calls": [
                {
                    "at": event.created_at,
                    "method": event.method,
                    "tool": event.tool,
                    "outcome": event.outcome,
                    "duration_ms": event.duration_ms,
                    # Deliberately not `detail`: it holds the question or the
                    # SQL, and this endpoint carries neither.
                }
                for event in events
            ],
        }


class McpAuditResource(BaseResource):
    #: What a page of the audit shows. More than this and nobody reads it;
    #: fewer and the interesting request has already scrolled past.
    DEFAULT_LIMIT = 200
    MAX_LIMIT = 1000
    #: A session with nothing in this window is not connected. The transport
    #: holds no socket open, so "connected" can only mean "recently active",
    #: and saying otherwise on a page would be a lie with a green dot on it.
    ACTIVE_MINUTES = 15

    @require_super_admin
    def get(self):
        """
        Who has been using MCP, and what they asked for.

        Admin only: it names every user, every question and every address,
        which is the whole point and also not everyone's business.
        """
        import datetime

        limit = min(
            max(request.args.get("limit", self.DEFAULT_LIMIT, type=int) or self.DEFAULT_LIMIT, 1), self.MAX_LIMIT
        )
        events = (
            models.McpEvent.query.filter(models.McpEvent.org == self.current_org)
            .order_by(models.McpEvent.created_at.desc())
            .limit(limit)
            .all()
        )

        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=self.ACTIVE_MINUTES)
        active = {}
        for event in models.McpEvent.query.filter(
            models.McpEvent.org == self.current_org,
            models.McpEvent.created_at >= since,
            models.McpEvent.session_id.isnot(None),
        ).order_by(models.McpEvent.created_at.desc()):
            session = active.setdefault(
                event.session_id,
                {
                    "session_id": event.session_id,
                    "user": event.user.name if event.user else None,
                    "client": None,
                    "last_seen": event.created_at,
                    "calls": 0,
                },
            )
            session["calls"] += 1
            # The name arrives with `initialize`, which is the oldest row in
            # the session rather than the newest.
            if event.client and not session["client"]:
                session["client"] = event.client

        return {
            "events": [event.to_dict() for event in events],
            "active": sorted(active.values(), key=lambda s: s["last_seen"], reverse=True),
            "active_minutes": self.ACTIVE_MINUTES,
            "enabled": settings.FEATURE_AI,
        }

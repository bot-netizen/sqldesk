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

import logging
import time
import uuid

from flask import jsonify, request
from sqlalchemy.orm.exc import NoResultFound

from sqldesk import models, settings
from sqldesk.authentication import current_org
from sqldesk.handlers.base import routes
from sqldesk.mcp import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    McpError,
    handle,
    time_budget,
)

logger = logging.getLogger(__name__)

UNAUTHORIZED = -32001
SESSION_HEADER = "Mcp-Session-Id"
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
                session_id=session_id,
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


def _user_from_request(org):
    """
    The user behind the API key, or None.

    A user's own key, not a query's: a query API key is scoped to one query's
    results and would be a strange thing to hand a tool server. The header is
    preferred over a query parameter because a URL is logged by every proxy
    between here and the client.
    """
    header = request.headers.get("Authorization", "")
    api_key = None
    if header.lower().startswith("bearer "):
        api_key = header[7:].strip()
    elif header.lower().startswith("key "):
        api_key = header[4:].strip()
    if not api_key:
        api_key = request.args.get("api_key")
    if not api_key:
        return None

    try:
        user = models.User.get_by_api_key_and_org(api_key, org)
    except NoResultFound:
        return None
    return None if user.is_disabled else user


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
    """
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


@routes.route("/mcp", methods=["POST"])
@routes.route("/api/mcp", methods=["POST"])
def mcp_endpoint():
    if not settings.FEATURE_AI:
        return jsonify(_error(INVALID_REQUEST, "MCP is off on this instance.")), 404

    started = time.time()
    org = current_org._get_current_object()
    session_id = request.headers.get(SESSION_HEADER)
    user = _user_from_request(org)

    if user is None:
        # Recorded before anything else: a key that does not work, tried
        # repeatedly, is the thing an audit exists to show.
        _record(org, None, session_id, None, "authenticate", None, "refused", "no or unknown API key", started)
        response = jsonify(_error(UNAUTHORIZED, "A SQLDesk API key is required: Authorization: Bearer <key>."))
        response.status_code = 401
        response.headers["WWW-Authenticate"] = "Bearer"
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

    with time_budget(settings.MCP_TIME_BUDGET):
        replies, issued_session = _answer(messages, org, user, session_id)

    if not replies:
        response = jsonify(None)
        response.status_code = 202
        response.set_data(b"")
    else:
        response = jsonify(replies if isinstance(payload, list) else replies[0])
    if issued_session:
        response.headers[SESSION_HEADER] = issued_session
    return response


def _answer(messages, org, user, session_id):
    replies, issued_session = [], None
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
            result = handle(message, user, org)
        except McpError as error:
            _record(
                org, user, session_id, _client_name(message), method, tool, "error", error.message, message_started
            )
            replies.append(_error(error.code, error.message, message_id))
            continue
        except Exception:
            logger.exception("MCP request failed")
            _record(org, user, session_id, None, method, tool, "error", "unhandled", message_started)
            replies.append(_error(INTERNAL_ERROR, "That request could not be handled.", message_id))
            continue

        outcome = "error" if isinstance(result, dict) and result.get("isError") else "ok"
        _record(
            org, user, session_id, _client_name(message), method, tool, outcome, _summary(message), message_started
        )
        if result is not None:
            replies.append({"jsonrpc": "2.0", "id": message_id, "result": result})
    return replies, issued_session

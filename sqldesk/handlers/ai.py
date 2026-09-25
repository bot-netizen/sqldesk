from flask import request
from flask_login import login_required

from sqldesk import models, settings
from sqldesk.ai import ModelError, load_provider, provider_from
from sqldesk.ai.optimizer import analyze
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import require_access, require_super_admin, view_only

#: Longer than any query anyone writes by hand, and short enough that parsing
#: it is never the thing that hurts.
MAX_QUERY_CHARS = 200_000


class AIStatusResource(BaseResource):
    @login_required
    def get(self):
        """
        Whether the AI features are on, and -- for an admin -- what they are
        pointed at.

        Two flags, not one. `SQLDESK_FEATURE_AI` says the operator wants this;
        a configured provider says there is something to talk to. The page has
        to tell those apart, because the remedy is different: one is an
        environment variable and the other is `manage ai configure`.

        The provider block is admin-only. It names an internal endpoint and
        says whether a key exists, which is not everyone's business -- and it
        never carries the key itself, which is nobody's.
        """
        provider, unreadable = load_provider(self.current_org)
        configured = provider is not None and provider.enabled

        response = {
            "enabled": settings.FEATURE_AI,
            "configured": configured,
            "available": settings.FEATURE_AI and configured,
        }
        if self.current_user.has_permission("super_admin"):
            response["provider"] = provider.to_dict() if provider else None
            response["error"] = unreadable
            response["providerTypes"] = sorted(t for t in ("anthropic", "openai", "local"))
        return response


class AITestResource(BaseResource):
    @require_super_admin
    def post(self):
        """
        Ask the configured model one question, and report what came back.

        The same thing `manage ai test` does, for an admin who would rather
        press a button than find a shell. It sends a fixed prompt and no data:
        this answers "is the key right and the endpoint reachable", not
        anything about a warehouse.
        """
        provider_row, unreadable = load_provider(self.current_org)
        if unreadable:
            return {"ok": False, "error": unreadable}
        if provider_row is None:
            return {"ok": False, "error": "No provider configured. Run `manage ai configure` on the server."}

        try:
            provider = provider_from(provider_row, timeout=settings.AI_TIMEOUT)
            answer = provider.complete("Reply with the single word: ready")
        except ModelError as error:
            return {"ok": False, "error": str(error)}

        self.record_event({"action": "test", "object_type": "ai_provider", "object_id": provider_row.id})
        return {"ok": True, "answer": answer}


class QueryOptimizeResource(BaseResource):
    @login_required
    def post(self):
        """
        Look at some SQL and say what is wrong with it.

        Stateless on purpose: the editor sends whatever is in it, saved or
        not, because the query you want checked is usually the one you have
        not saved yet.

        Needs no model and no key. This is the deterministic half -- parse and
        rules -- so it works on an instance with no AI configured at all,
        which is why it is gated on access to the data source rather than on
        the AI feature flag.
        """
        body = request.get_json(force=True, silent=True) or {}
        query_text = body.get("query", "") or ""

        # sqlglot builds a tree in memory and a pathological statement costs
        # real CPU. The editor never holds anything close to this, so a cap
        # here only ever stops something that was not a query.
        if len(query_text) > MAX_QUERY_CHARS:
            return {
                "applicable": False,
                "reason": "That is {} characters; the optimizer looks at queries up to {}.".format(
                    len(query_text), MAX_QUERY_CHARS
                ),
                "findings": [],
            }

        data_source_type = None
        data_source_id = body.get("data_source_id")
        if data_source_id:
            # `get_object_or_404`, not a bare lookup: a data source in another
            # org raises NoResultFound, which without this is a 500 rather than
            # the 404 every other handler here returns.
            data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
            # Whoever can read the data source can have its SQL parsed. Nothing
            # is executed and nothing is sent anywhere, but the dialect and the
            # findings describe that source.
            require_access(data_source, self.current_user, view_only)
            data_source_type = data_source.type

        return analyze(query_text, data_source_type)


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

        limit = min(int(request.args.get("limit", self.DEFAULT_LIMIT)), self.MAX_LIMIT)
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

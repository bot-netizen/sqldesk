from flask import request
from flask_login import login_required

from sqldesk import models, settings
from sqldesk.ai import ModelError, get_provider
from sqldesk.ai.optimizer import analyze
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import require_access, require_super_admin, view_only


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
        provider = models.AIProvider.get_for_org(self.current_org)
        configured = provider is not None and provider.enabled

        response = {
            "enabled": settings.FEATURE_AI,
            "configured": configured,
            "available": settings.FEATURE_AI and configured,
        }
        if self.current_user.has_permission("super_admin"):
            response["provider"] = provider.to_dict() if provider else None
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
        provider_row = models.AIProvider.get_for_org(self.current_org)
        if provider_row is None:
            return {"ok": False, "error": "No provider configured. Run `manage ai configure` on the server."}

        try:
            provider = get_provider(
                provider_row.type,
                model=provider_row.model,
                api_key=provider_row.api_key,
                base_url=provider_row.base_url,
                timeout=settings.AI_TIMEOUT,
            )
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
        query_text = body.get("query", "")

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

from flask_login import login_required

from sqldesk import models, settings
from sqldesk.ai import ModelError, get_provider
from sqldesk.handlers.base import BaseResource
from sqldesk.permissions import require_super_admin


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

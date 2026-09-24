"""
The model layer.

Three providers and two HTTP shapes: Anthropic has its own, and OpenAI's is
spoken by OpenAI, Ollama, vLLM, LM Studio, LiteLLM and most of the rest -- so
"local" is not a third implementation, it is OpenAI's with a different base
URL and usually no key.

No vendor SDK. `requests` is already a dependency and these are three POST
endpoints; adding two SDKs to carry them would grow the image everybody pulls
for a feature that is off by default, which is the same argument that kept the
screenshot renderer in its own container.

Nothing here reads configuration. A provider is handed what it needs, so the
same class serves a saved configuration, a CLI flag and a test double.
"""

import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60

_PROVIDERS = {}


class ModelError(Exception):
    """Anything that stopped a completion, in words an operator can act on."""


def register(cls):
    _PROVIDERS[cls.type] = cls
    return cls


def provider_types():
    return sorted(_PROVIDERS)


def get_provider(type_, **kwargs):
    if type_ not in _PROVIDERS:
        raise ModelError("Unknown provider {!r}. Known: {}".format(type_, ", ".join(provider_types())))
    return _PROVIDERS[type_](**kwargs)


class BaseProvider:
    type = None
    #: Shown by `ai configure --help` so nobody has to guess a model string.
    example_model = None
    #: Whether a key is required. A model on your own hardware usually wants none.
    needs_api_key = True

    def __init__(self, model=None, api_key=None, base_url=None, timeout=DEFAULT_TIMEOUT):
        self.model = model or self.example_model
        self.api_key = api_key
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.timeout = timeout

    @property
    def default_base_url(self):
        raise NotImplementedError

    def complete(self, prompt, system=None, max_tokens=1024):
        """One turn in, one string out. Raises ModelError with something readable."""
        raise NotImplementedError

    def _post(self, url, headers, payload):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout:
            raise ModelError("{} did not answer within {}s.".format(self.type, self.timeout))
        except requests.exceptions.RequestException as error:
            raise ModelError("Could not reach {} at {}: {}".format(self.type, self.base_url, error))

        if response.status_code >= 400:
            # The body carries the reason -- a bad key, an unknown model, a
            # rate limit -- and a bare status code sends people to the wrong
            # place. Truncated because some of them return a page.
            raise ModelError("{} returned {}: {}".format(self.type, response.status_code, response.text[:400].strip()))
        try:
            return response.json()
        except ValueError:
            raise ModelError("{} returned something that is not JSON: {}".format(self.type, response.text[:200]))


@register
class AnthropicProvider(BaseProvider):
    type = "anthropic"
    example_model = "claude-sonnet-5"

    @property
    def default_base_url(self):
        return "https://api.anthropic.com"

    def complete(self, prompt, system=None, max_tokens=1024):
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        body = self._post(
            "{}/v1/messages".format(self.base_url),
            {
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload,
        )
        parts = [block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"]
        return "".join(parts).strip()


@register
class OpenAIProvider(BaseProvider):
    type = "openai"
    example_model = "gpt-4.1"

    @property
    def default_base_url(self):
        return "https://api.openai.com"

    def complete(self, prompt, system=None, max_tokens=1024):
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = self._post(
            "{}/v1/chat/completions".format(self.base_url),
            {"authorization": "Bearer {}".format(self.api_key or ""), "content-type": "application/json"},
            {"model": self.model, "max_tokens": max_tokens, "messages": messages},
        )
        choices = body.get("choices") or []
        if not choices:
            raise ModelError("{} returned no choices: {}".format(self.type, str(body)[:200]))
        return (choices[0].get("message", {}).get("content") or "").strip()


@register
class LocalProvider(OpenAIProvider):
    """
    Anything speaking OpenAI's API on hardware you control -- Ollama, vLLM,
    LM Studio, LiteLLM. The same request; a base URL is required because there
    is no sensible default, and a key usually is not.
    """

    type = "local"
    example_model = "llama3.1"
    needs_api_key = False

    @property
    def default_base_url(self):
        raise ModelError("A local provider needs --base-url, for example http://ollama:11434/v1")

    def __init__(self, model=None, api_key=None, base_url=None, timeout=DEFAULT_TIMEOUT):
        if not base_url:
            raise ModelError("A local provider needs --base-url, for example http://ollama:11434/v1")
        super().__init__(model=model, api_key=api_key, base_url=base_url, timeout=timeout)

    def complete(self, prompt, system=None, max_tokens=1024):
        # Local servers are usually configured with the /v1 already on them,
        # and doubling it is the commonest way this fails.
        suffix = "/chat/completions" if self.base_url.endswith("/v1") else "/v1/chat/completions"
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = "Bearer {}".format(self.api_key)
        body = self._post(self.base_url + suffix, headers, {"model": self.model, "messages": messages})
        choices = body.get("choices") or []
        if not choices:
            raise ModelError("{} returned no choices: {}".format(self.type, str(body)[:200]))
        return (choices[0].get("message", {}).get("content") or "").strip()

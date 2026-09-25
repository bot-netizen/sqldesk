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
import shutil
import subprocess

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60

_PROVIDERS = {}


class ModelError(Exception):
    """Anything that stopped a completion, in words an operator can act on."""


class CredentialsUnreadable(ModelError):
    """
    The stored key will not decrypt with this SQLDESK_SECRET_KEY.

    Which happens for an ordinary reason -- somebody rotated the secret, or
    restored a database into an instance configured with a different one. The
    row is intact and useless, and the remedy is to configure it again.
    """


def provider_from(row, timeout=None):
    """
    A live provider from a stored row.

    One place that knows a row's fields map to a provider's arguments, because
    three callers doing it separately is three places to forget `command`.
    """
    kwargs = {"model": row.model, "api_key": row.api_key, "base_url": row.base_url}
    if timeout:
        kwargs["timeout"] = timeout
    if row.type == "cli":
        # A CLI has no endpoint and no key; it has a command.
        kwargs = {"model": row.model, "command": (row.options or {}).get("command")}
        if timeout:
            kwargs["timeout"] = timeout
    return get_provider(row.type, **kwargs)


class EnvironmentProvider:
    """
    A provider declared by the operator, standing in for a stored row.

    Quacks like `models.AIProvider` where it is read -- the handlers, the CLI
    and `provider_from` all take a row -- so naming it in the environment
    needs no second path through any of them.
    """

    from_environment = True
    enabled = True
    updated_at = None

    def __init__(self, type, model, api_key, base_url, command):
        self.type = type
        self.model = model or None
        self.api_key = api_key or None
        self.base_url = base_url or None
        self.options = {"command": command} if command else {}

    def to_dict(self):
        return {
            "type": self.type,
            "model": self.model,
            "base_url": self.base_url,
            "enabled": True,
            "has_api_key": bool(self.api_key),
            "from_environment": True,
            "updated_at": None,
        }


def provider_from_environment():
    """The configured provider from the environment, or None if none is named."""
    from sqldesk import settings

    if not settings.AI_PROVIDER:
        return None
    if settings.AI_PROVIDER not in _PROVIDERS:
        logger.error(
            "SQLDESK_AI_PROVIDER is %r, which is not one of: %s",
            settings.AI_PROVIDER,
            ", ".join(provider_types()),
        )
        return None
    return EnvironmentProvider(
        settings.AI_PROVIDER,
        settings.AI_MODEL,
        settings.AI_API_KEY,
        settings.AI_BASE_URL,
        settings.AI_COMMAND,
    )


def load_provider(org):
    """
    The configured provider, or why it cannot be read.

    Returns `(provider, error)` and never raises on a bad key: the column
    decrypts while the row loads, so an unreadable key takes out whatever
    asked for it. That turned the whole AI page into a 500 -- one bad row and
    the feature has no way to tell you what is wrong with it.
    """
    from cryptography.fernet import InvalidToken

    from sqldesk import models

    # The environment wins. An operator who named a provider in a Secret has
    # said what this instance talks to, and a row somebody wrote with
    # `kubectl exec` three deploys ago should not quietly outrank it.
    declared = provider_from_environment()
    if declared is not None:
        return declared, None

    try:
        provider = models.AIProvider.get_for_org(org)
        if provider is not None:
            # Force the decrypt here rather than wherever it is first read.
            provider.api_key
        return provider, None
    except InvalidToken:
        logger.warning("the stored AI credentials for org %s will not decrypt", getattr(org, "id", None))
        return None, (
            "The stored API key cannot be read with this instance's SQLDESK_SECRET_KEY. "
            "It was saved under a different one -- run `manage ai configure` again to replace it."
        )


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


@register
class ClaudeCLIProvider(BaseProvider):
    """
    The `claude` command, on this machine.

    If somebody has signed Claude Code in with their subscription there is no
    API key to find, buy or paste anywhere -- which is the whole appeal, and
    also the whole caveat. `~/.claude` holds one person's session, so every
    question the instance asks is asked as them.

    That makes this right for a developer running SQLDesk on their own laptop
    and wrong for a shared server: the authentication is personal, each call
    spawns a Node process so it does not thread, and a personal subscription
    standing behind a multi-user product's backend is a question for whoever
    owns the subscription rather than an assumption to make quietly. Use
    `anthropic` for anything other people rely on.

    Nothing is passed to a shell. The prompt is an argument, so a question
    containing a backtick is a question containing a backtick.
    """

    type = "cli"
    example_model = None  # whatever the CLI is already set to
    needs_api_key = False
    #: Generous: a local CLI starts a Node runtime before it starts thinking.
    default_timeout = 180

    def __init__(self, model=None, api_key=None, base_url=None, timeout=None, command=None):
        self.model = model
        self.api_key = None
        self.base_url = None
        self.command = command or "claude"
        self.timeout = timeout or self.default_timeout

    @property
    def default_base_url(self):
        return ""

    def _argv(self, prompt, system):
        argv = [self.command, "-p"]
        if self.model:
            argv += ["--model", self.model]
        if system:
            argv += ["--append-system-prompt", system]
        return argv + [prompt]

    def complete(self, prompt, system=None, max_tokens=1024):
        if shutil.which(self.command) is None:
            raise ModelError(
                "`{}` is not on this container's PATH. The CLI runs on the machine SQLDesk runs on, "
                "so it has to be installed there or mounted in -- see the AI setup page.".format(self.command)
            )

        try:
            finished = subprocess.run(  # noqa: S603 - argv, never a shell
                self._argv(prompt, system),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise ModelError("`{}` did not answer within {}s.".format(self.command, self.timeout))
        except OSError as error:
            raise ModelError("Could not run `{}`: {}".format(self.command, error))

        if finished.returncode != 0:
            # The CLI puts the reason on stderr -- not signed in, unknown
            # model, no network. A bare exit code sends people nowhere.
            detail = (finished.stderr or finished.stdout or "").strip()[:400]
            raise ModelError("`{}` exited {}: {}".format(self.command, finished.returncode, detail or "no output"))

        answer = (finished.stdout or "").strip()
        if not answer:
            raise ModelError(
                "`{}` returned nothing. Is it signed in? Try `{} -p hello` yourself.".format(
                    self.command, self.command
                )
            )
        return answer

from click import argument, option
from flask.cli import AppGroup

from sqldesk import ai, models, settings

manager = AppGroup(help="Configure the model SQLDesk talks to.")


def _org():
    org = models.Organization.query.first()
    if org is None:
        raise SystemExit("No organization yet. Run `manage database create_tables` first.")
    return org


def _read_key(api_key, api_key_stdin, env_var):
    """
    A key from a flag lands in shell history and in `ps`. Three ways in, and
    the one on the command line is the one documented last.
    """
    if api_key_stdin:
        import sys

        return sys.stdin.read().strip()
    if api_key:
        return api_key.strip()
    import os

    return (os.environ.get(env_var) or "").strip() or None


@manager.command(name="configure")
@argument("provider_type")
@option("--model", default=None, help="Model name. Defaults to the provider's usual one.")
@option("--base-url", default=None, help="Required for `local`; overrides the endpoint otherwise.")
@option("--api-key", default=None, help="Discouraged: lands in shell history. Prefer --api-key-stdin.")
@option("--api-key-stdin", is_flag=True, default=False, help="Read the key from standard input.")
@option("--disabled", is_flag=True, default=False, help="Save it, but leave the features off.")
def configure(provider_type, model, base_url, api_key, api_key_stdin, disabled):
    """
    Point SQLDesk at a model. PROVIDER_TYPE is one of: anthropic, openai, local.

    \b
      manage ai configure anthropic --model claude-sonnet-5 --api-key-stdin
      manage ai configure openai --model gpt-4.1 --api-key-stdin
      manage ai configure local --base-url http://ollama:11434/v1 --model llama3.1
    """
    if provider_type not in ai.provider_types():
        raise SystemExit("Unknown provider {!r}. Known: {}".format(provider_type, ", ".join(ai.provider_types())))

    key = _read_key(api_key, api_key_stdin, "SQLDESK_AI_API_KEY")
    cls = ai._PROVIDERS[provider_type]

    org = _org()
    provider = models.AIProvider.get_for_org(org) or models.AIProvider(org=org)
    was = provider.type

    # The key already on file counts. Changing the model should not mean
    # typing the key again, and demanding it is how people end up putting a
    # key on the command line where the shell history keeps it.
    already = provider.api_key if was == provider_type else None
    if cls.needs_api_key and not key and not already:
        raise SystemExit("{} needs a key. Pass --api-key-stdin, or set SQLDESK_AI_API_KEY.".format(provider_type))

    # `to_dict()`, not `dict(...)`: a ConfigurationContainer has `get` and
    # `__getitem__` but no `keys()`, so `dict()` falls back to iterating it as
    # a sequence and asks it for index 0.
    options = provider.options.to_dict() if provider.options is not None else {}
    if was and was != provider_type:
        # A key for Anthropic is not a key for OpenAI. Carrying it across would
        # fail later as an unhelpful 401 rather than here as a missing key.
        options.pop("api_key", None)
    if key:
        options["api_key"] = key

    provider.type = provider_type
    provider.model = model or cls.example_model
    provider.base_url = base_url
    provider.enabled = not disabled
    provider.options = options

    models.db.session.add(provider)
    models.db.session.commit()

    print("Configured {} / {}".format(provider.type, provider.model))
    if provider.base_url:
        print("  endpoint: {}".format(provider.base_url))
    print("  key: {}".format("stored" if provider.api_key else "none"))
    print("  features: {}".format("on" if provider.enabled else "off (saved, --disabled)"))
    if not settings.FEATURE_AI:
        print("  note: SQLDESK_FEATURE_AI is false, so nothing will use this yet.")


@manager.command(name="status")
def status():
    """Say what is configured, without printing the key."""
    print("SQLDESK_FEATURE_AI: {}".format("on" if settings.FEATURE_AI else "off"))
    provider = models.AIProvider.get_for_org(_org())
    if provider is None:
        print("No provider configured. Nothing will call out, and the AI features stay hidden.")
        print("Try: manage ai configure anthropic --api-key-stdin")
        return
    for key, value in provider.to_dict().items():
        print("  {}: {}".format(key, value))


@manager.command(name="test")
@argument("prompt", required=False)
def test(prompt):
    """Send one prompt and print what comes back, so a bad key fails here."""
    provider_row = models.AIProvider.get_for_org(_org())
    if provider_row is None:
        raise SystemExit("No provider configured. Run `manage ai configure` first.")

    provider = ai.get_provider(
        provider_row.type,
        model=provider_row.model,
        api_key=provider_row.api_key,
        base_url=provider_row.base_url,
    )
    print("Asking {} / {} ...".format(provider_row.type, provider_row.model))
    try:
        answer = provider.complete(prompt or "Reply with the single word: ready")
    except ai.ModelError as error:
        raise SystemExit("FAILED: {}".format(error))
    print(answer or "(empty response)")


@manager.command(name="disable")
def disable():
    """Turn the features off without forgetting the configuration."""
    provider = models.AIProvider.get_for_org(_org())
    if provider is None:
        raise SystemExit("Nothing configured.")
    provider.enabled = False
    models.db.session.add(provider)
    models.db.session.commit()
    print("Disabled. The configuration and key are kept; `manage ai configure` turns it back on.")


@manager.command(name="forget")
def forget():
    """Delete the configuration and the stored key."""
    provider = models.AIProvider.get_for_org(_org())
    if provider is None:
        raise SystemExit("Nothing configured.")
    models.db.session.delete(provider)
    models.db.session.commit()
    print("Forgotten.")

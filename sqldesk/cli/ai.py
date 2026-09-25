import os

from click import argument, option
from flask.cli import AppGroup

from sqldesk import ai, models, settings
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.ai.catalog.semantic import export_catalog, import_catalog

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
@option("--command", default=None, help="For `cli`: the executable, if it is not simply `claude`.")
@option("--disabled", is_flag=True, default=False, help="Save it, but leave the features off.")
def configure(provider_type, model, base_url, api_key, api_key_stdin, command, disabled):
    """
    Point SQLDesk at a model. PROVIDER_TYPE is one of: anthropic, openai, local.

    \b
      manage ai configure anthropic --model claude-sonnet-5 --api-key-stdin
      manage ai configure openai --model gpt-4.1 --api-key-stdin
      manage ai configure local --base-url http://ollama:11434/v1 --model llama3.1
      manage ai configure cli

    `cli` shells out to the `claude` command on this machine and needs no key
    at all, which makes it the quickest way to try this on a laptop. It is
    for one developer on their own machine -- see `docs/ai-setup.md`.
    """
    if provider_type not in ai.provider_types():
        raise SystemExit("Unknown provider {!r}. Known: {}".format(provider_type, ", ".join(ai.provider_types())))

    if settings.AI_PROVIDER:
        raise SystemExit(
            "SQLDESK_AI_PROVIDER is set to {!r}, so the environment is the configuration and a stored "
            "row would never be read. Change the environment instead.".format(settings.AI_PROVIDER)
        )

    key = _read_key(api_key, api_key_stdin, "SQLDESK_AI_API_KEY")
    cls = ai._PROVIDERS[provider_type]

    org = _org()
    provider, unreadable = ai.load_provider(org)
    if unreadable:
        # The whole point of running this again is to replace a key that
        # cannot be read, so it must not be the thing that stops you.
        print("Replacing credentials that could not be decrypted.")
        models.AIProvider.query.filter(models.AIProvider.org_id == org.id).delete()
        models.db.session.commit()
        provider = None
    provider = provider or models.AIProvider(org=org)
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
    if command:
        options["command"] = command

    provider.type = provider_type
    # `cli` has no default model: whatever the command is already set to is
    # the right answer, and naming one here overrides a choice somebody made.
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
    provider, unreadable = ai.load_provider(_org())
    if unreadable:
        print(unreadable)
        return
    if provider is None:
        print("No provider configured. Nothing will call out, and the AI features stay hidden.")
        print("Try: manage ai configure anthropic --api-key-stdin")
        return
    for key, value in provider.to_dict().items():
        print("  {}: {}".format(key, value))
    if getattr(provider, "from_environment", False):
        print("  (declared by SQLDESK_AI_PROVIDER; `manage ai configure` would not be read)")


@manager.command(name="test")
@argument("prompt", required=False)
def test(prompt):
    """Send one prompt and print what comes back, so a bad key fails here."""
    provider_row, unreadable = ai.load_provider(_org())
    if unreadable:
        raise SystemExit(unreadable)
    if provider_row is None:
        raise SystemExit("No provider configured. Run `manage ai configure` first.")

    provider = ai.provider_from(provider_row)
    print("Asking {} / {} ...".format(provider_row.type, provider_row.model))
    try:
        answer = provider.complete(prompt or "Reply with the single word: ready")
    except ai.ModelError as error:
        raise SystemExit("FAILED: {}".format(error))
    print(answer or "(empty response)")


@manager.command(name="disable")
def disable():
    """Turn the features off without forgetting the configuration."""
    changed = models.AIProvider.query.filter(models.AIProvider.org_id == _org().id).update({"enabled": False})
    models.db.session.commit()
    if not changed:
        raise SystemExit("Nothing configured.")
    print("Disabled. The configuration and key are kept; `manage ai configure` turns it back on.")


@manager.command(name="forget")
def forget():
    """Delete the configuration and the stored key."""
    # Deleted by id rather than loaded first: a row whose key will not
    # decrypt is exactly the one somebody wants rid of.
    removed = models.AIProvider.query.filter(models.AIProvider.org_id == _org().id).delete()
    models.db.session.commit()
    if not removed:
        raise SystemExit("Nothing configured.")
    print("Forgotten.")


@manager.command(name="harvest")
@option("--data-source", default=None, help="One data source by name. Default: all of them.")
def harvest(data_source):
    """
    Fill the catalog: what each data source has, and what the saved queries
    say anyone does with it.

    Safe to run again -- everything is keyed on names, so a second run updates
    rather than duplicates. Needs no model: this is phase 0, and it is useful
    on its own as searchable schema.
    """
    org = _org()
    sources = models.DataSource.query.filter(models.DataSource.org == org)
    if data_source:
        sources = sources.filter(models.DataSource.name == data_source)
    sources = sources.all()
    if not sources:
        raise SystemExit("No data source matched.")

    for source in sources:
        print("Harvesting {} ({}) ...".format(source.name, source.type))
        try:
            result = harvest_data_source(source)
        except Exception as error:
            # One unreachable warehouse must not stop the others.
            print("  failed: {}".format(error))
            models.db.session.rollback()
            continue
        print("  {tables} tables, {relationships} joins, from {queries_mined} saved queries".format(**result))


@manager.command(name="context")
@argument("question")
@option("--data-source", default=None, help="Restrict to one data source by name.")
def context(question, data_source):
    """Show what a model would be told about QUESTION."""
    from sqldesk.ai.catalog.retrieve import context_for

    org = _org()
    source = None
    if data_source:
        source = models.DataSource.query.filter(
            models.DataSource.org == org, models.DataSource.name == data_source
        ).first()
        if source is None:
            raise SystemExit("No data source called {!r}.".format(data_source))

    found = context_for(org, question, data_source=source)
    if not found["tables"]:
        raise SystemExit("Nothing in the catalog yet. Run `manage ai harvest` first.")
    for table in found["tables"]:
        print(table["card"] or table["name"])
        print()


def _must_be_writable(directory):
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as error:
        raise SystemExit("Cannot create {}: {}".format(directory, error))
    if not os.access(directory, os.W_OK | os.X_OK):
        raise SystemExit(
            "{} is not writable by this container (running as uid {}). "
            "If it is a bind mount, `chown -R {}: <the host directory>`.".format(directory, os.getuid(), os.getuid())
        )


@manager.command(name="export")
@argument("directory")
@option("--data-source", default=None, help="One data source by name. Default: all of them.")
def export_semantic(directory, data_source):
    """
    Write the catalog out as cube-shaped YAML, one file per table.

    This is the half of the loop that belongs in git: commit the directory,
    review changes as a pull request, and run `manage ai import` on deploy.
    Only measures somebody has agreed are written -- an export full of
    unreviewed proposals has a diff nobody can read.
    """
    org = _org()
    source = None
    if data_source:
        source = models.DataSource.query.filter(
            models.DataSource.org == org, models.DataSource.name == data_source
        ).first()
        if source is None:
            raise SystemExit("No data source matched.")

    # Checked here rather than left to fail mid-write, because the usual
    # cause is a bind mount owned by the host's user while the container runs
    # as `sqldesk` -- which is invisible on Docker Desktop, where the file
    # sharing layer is permissive, and immediate on Linux.
    _must_be_writable(directory)

    result = export_catalog(org, directory, data_source=source)
    print(
        "Wrote {} tables from {} data source(s) into {}.".format(result["tables"], result["data_sources"], directory)
    )


@manager.command(name="import")
@argument("directory")
def import_semantic(directory):
    """
    Read descriptions and agreed measures back out of a directory of YAML.

    Structure is not imported: what tables and columns exist is the
    warehouse's to state, and a file claiming otherwise is a second opinion
    about a fact. What a file carries is what people wrote -- descriptions,
    and which definitions they stand behind.
    """
    if not os.path.isdir(directory):
        raise SystemExit("{} is not a directory.".format(directory))

    result = import_catalog(_org(), directory)
    print(
        "Applied {} table and {} column descriptions, and agreed {} measures. "
        "Skipped {} that the catalog has not heard of.".format(
            result["tables"], result["columns"], result["measures"], result["skipped"]
        )
    )

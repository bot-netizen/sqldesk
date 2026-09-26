import os

from click import argument, option
from flask.cli import AppGroup

from sqldesk import models
from sqldesk.ai.catalog.harvest import harvest_data_source
from sqldesk.ai.catalog.semantic import export_catalog, import_catalog

manager = AppGroup(help="The catalog behind MCP: harvest it, look at it, export and import it.")


def _org():
    org = models.Organization.query.first()
    if org is None:
        raise SystemExit("No organization yet. Run `manage database create_tables` first.")
    return org


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
        if result.get("skipped"):
            print("  skipped: {}; the catalog is unchanged".format(result["skipped"]))
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

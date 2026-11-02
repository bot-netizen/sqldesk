"""
A demo install, built from nothing: data, queries, every visualization, a
dashboard and a notebook.

It exists to answer a question nobody can answer by reading code -- *do the
visualizations actually work?* -- and to answer it on any install, including
one with no data sources at all. That is why the data is a DuckDB file this
builds rather than a warehouse somebody has to have.

Everything it creates is tagged, which is what makes `remove` honest: it
takes away exactly what `seed` made and nothing that looks like it.
"""

import logging
import os

from sqldesk import models, settings
from sqldesk.demo import content, data
from sqldesk.models import db

logger = logging.getLogger(__name__)

#: On every query, dashboard and notebook this creates. The handle `remove`
#: works from, so it can never take away somebody's own work that happens to
#: share a name.
TAG = "demo"

DATA_SOURCE_NAME = "Demo data"


def store_path():
    """Where the demo's DuckDB file lives: beside the uploads, not in the repo."""
    return os.path.join(settings.UPLOAD_ROOT, "demo", "demo.duckdb")


def build_the_data(path=None):
    """
    Create the DuckDB file and fill it.

    Replaced rather than appended to, so seeding twice leaves one copy of
    everything instead of two.

    **Built beside the destination and moved into place.** DuckDB keeps one
    database instance per path for the life of the process, and the query
    runner locks that instance's configuration -- so a file this opened and
    closed cannot then be opened by the runner, which needs to set
    `allowed_directories` on it and is refused: *Cannot change configuration
    option "allowed_directories" - the configuration has been locked*.
    Writing somewhere else and renaming means the runner is the first thing
    in the process to open the path it uses.
    """
    from sqldesk.query_runner import deferred

    duckdb = deferred("duckdb")
    path = path or store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    building = path + ".building"
    for leftover in (building, path):
        if os.path.exists(leftover):
            os.remove(leftover)

    connection = duckdb.connect(building)
    try:
        for statement in data.statements():
            connection.execute(statement)
    finally:
        connection.close()

    os.replace(building, path)
    return path


def _data_source(org, path):
    """
    The demo's own DuckDB source, pointed at the file just built.

    `options` is a `ConfigurationContainer`, not a dict -- the column is
    encrypted and the container is what knows the runner's schema. A plain
    dict is accepted by the model and then read back as nothing, which leaves
    the runner on its default `:memory:` and is not obvious until a query
    comes back empty.
    """
    from sqldesk.query_runner import get_configuration_schema_for_query_runner_type
    from sqldesk.utils.configuration import ConfigurationContainer

    schema = get_configuration_schema_for_query_runner_type("duckdb")
    options = ConfigurationContainer({"dbpath": path}, schema)

    source = models.DataSource.query.filter(
        models.DataSource.org == org, models.DataSource.name == DATA_SOURCE_NAME
    ).first()
    if source is None:
        source = models.DataSource.create_with_group(org=org, name=DATA_SOURCE_NAME, type="duckdb", options=options)
    else:
        source.options = options
        db.session.add(source)
    return source


def _query(org, user, source, name, description, sql):
    existing = models.Query.query.filter(
        models.Query.org == org, models.Query.name == name, models.Query.is_archived.is_(False)
    ).first()
    if existing is not None:
        existing.query_text = sql
        existing.description = description
        existing.data_source = source
        existing.update_query_hash()
        db.session.add(existing)
        return existing

    query = models.Query.create(
        name=name,
        description=description,
        query_text=sql,
        user=user,
        data_source=source,
        org=org,
        is_draft=False,
        tags=[TAG],
    )
    db.session.add(query)
    return query


def _visualization(query, type_, name, options):
    existing = next((one for one in query.visualizations if one.name == name and one.type == type_), None)
    if existing is not None:
        existing.options = dict(options)
        db.session.add(existing)
        return existing
    made = models.Visualization(query_rel=query, type=type_, name=name, description="", options=dict(options))
    db.session.add(made)
    return made


def seed(org, user):
    """
    Build the lot, idempotently.

    Safe to run twice: everything is found by name and updated rather than
    duplicated, which matters because the first thing anybody does with a
    demo is seed it again after breaking it.
    """
    path = build_the_data()
    source = _data_source(org, path)
    db.session.commit()

    queries = {}
    for name, description, sql in content.QUERIES:
        queries[name] = _query(org, user, source, name, description, sql)
    db.session.commit()

    made = {}
    for query_name, type_, name, options in content.VISUALIZATIONS:
        query = queries[query_name]
        made[name] = _visualization(query, type_, name, options)
    db.session.commit()

    dashboard = _dashboard(org, user, made)
    notebook = _notebook(org, user, source)
    db.session.commit()

    return {
        "data_source": source,
        "queries": list(queries.values()),
        "visualizations": list(made.values()),
        "dashboard": dashboard,
        "notebook": notebook,
    }


def _dashboard(org, user, visualizations):
    dashboard = models.Dashboard.query.filter(
        models.Dashboard.org == org, models.Dashboard.name == content.DASHBOARD
    ).first()
    if dashboard is None:
        dashboard = models.Dashboard(
            name=content.DASHBOARD, org=org, user=user, is_archived=False, is_draft=False, layout=[], tags=[TAG]
        )
        db.session.add(dashboard)
        db.session.flush()
    else:
        for widget in dashboard.widgets.all():
            db.session.delete(widget)
        db.session.flush()

    # Laid out left to right, wrapping at the full width. The grid is six
    # rows per widget, which is what the dashboard's own default is.
    row, column = 0, 0
    for entry in content.DASHBOARD_WIDGETS:
        name, width = entry[0], entry[1]
        tabs = entry[2] if len(entry) > 2 else []
        visualization = visualizations.get(name)
        if visualization is None:
            continue
        if column + width > 2:
            row, column = row + 6, 0
        options = {
            "position": {"col": column * 3, "row": row, "sizeX": width * 3, "sizeY": 6},
        }
        tab_ids = [visualizations[one].id for one in tabs if one in visualizations]
        if tab_ids:
            options["tabs"] = tab_ids
        db.session.add(models.Widget(dashboard=dashboard, visualization=visualization, options=options, width=width))
        column += width
        if column >= 2:
            row, column = row + 6, 0
    return dashboard


def _notebook(org, user, source):
    notebook = models.Notebook.query.filter(
        models.Notebook.org == org, models.Notebook.name == content.NOTEBOOK
    ).first()
    if notebook is None:
        notebook = models.Notebook(
            org=org, user=user, name=content.NOTEBOOK, description=content.NOTEBOOK_DESCRIPTION, is_draft=False
        )
        db.session.add(notebook)
        db.session.flush()
    else:
        for cell in list(notebook.cells):
            db.session.delete(cell)
        db.session.flush()

    for position, (name, title, kind, uses_source, sql) in enumerate(content.NOTEBOOK_CELLS):
        db.session.add(
            models.NotebookCell(
                notebook=notebook,
                name=name,
                title=title,
                kind=kind,
                source=sql,
                position=position,
                data_source=source if uses_source else None,
            )
        )
    return notebook


def remove(org):
    """
    Take away exactly what `seed` made.

    By tag rather than by name: somebody may well have a dashboard called
    something similar, and a demo that eats it would be worse than one that
    cannot be cleaned up.
    """
    removed = {"queries": 0, "dashboards": 0, "notebooks": 0, "data_sources": 0}

    # `delete_permanently` rather than `session.delete`: a dashboard's widgets
    # do not cascade, so deleting the row on its own tries to orphan them and
    # fails on a not-null column. The models already know how to take one
    # apart -- this is the same call the Delete button makes.
    for dashboard in models.Dashboard.query.filter(models.Dashboard.org == org).all():
        if TAG in (dashboard.tags or []):
            dashboard.delete_permanently()
            removed["dashboards"] += 1

    for notebook in models.Notebook.query.filter(
        models.Notebook.org == org, models.Notebook.name == content.NOTEBOOK
    ).all():
        db.session.delete(notebook)
        removed["notebooks"] += 1

    for query in models.Query.query.filter(models.Query.org == org).all():
        if TAG in (query.tags or []):
            query.delete_permanently()
            removed["queries"] += 1

    source = models.DataSource.query.filter(
        models.DataSource.org == org, models.DataSource.name == DATA_SOURCE_NAME
    ).first()
    if source is not None:
        models.DataSource.delete(source)
        removed["data_sources"] += 1

    db.session.commit()

    path = store_path()
    if os.path.exists(path):
        os.remove(path)
    return removed

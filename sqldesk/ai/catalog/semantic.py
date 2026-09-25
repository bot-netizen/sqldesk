"""
The catalog as files, and back again.

Curated meaning belongs under review, and the review anyone already has is a
pull request. So the database is the cache and a directory of YAML is the
record: `export` writes what is known, somebody edits and commits it, and
`import` on deploy puts it back. SQLDesk never speaks to git -- no deploy
key, no conflict handling, no worker that needs to reach GitHub -- because
the pipeline that already does those things does them better.

The shape is cube's, because a semantic layer nobody else can read is a
private format with extra steps. A cube reads `name`, `sql_table`,
`dimensions`, `measures` and `joins`, and every one of those is something
this catalog already holds.

One file per table rather than one per warehouse: a three-thousand line file
has no readable diff, and the diff is the entire point of keeping it in git.
"""

import logging
import os
import re

import yaml

from sqldesk.ai.catalog.harvest import FILE
from sqldesk.models import (
    CatalogColumn,
    CatalogMeasure,
    CatalogRelationship,
    CatalogTable,
    DataSource,
    db,
)

logger = logging.getLogger(__name__)

#: SQL types are per-engine and endless; cube's are five. Anything unmatched
#: becomes a string, which is the one that is never actively wrong.
TYPES = [
    (re.compile(r"bool"), "boolean"),
    (re.compile(r"(date|time)"), "time"),
    (re.compile(r"(int|numeric|decimal|real|double|float|money|serial)"), "number"),
]


def cube_type(sql_type):
    lowered = (sql_type or "").lower()
    for pattern, kind in TYPES:
        if pattern.search(lowered):
            return kind
    return "string"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "source"


def _cube_name(table_name):
    """Cube names cannot carry a dot, so `public.orders` becomes `public_orders`."""
    return _slug(table_name)


def cube_for(table, columns, measures, joins):
    """One table as a cube, with only the keys it has something to say for."""
    cube = {"name": _cube_name(table.name), "sql_table": table.name}
    if table.description:
        cube["description"] = table.description

    dimensions = []
    for column in columns:
        dimension = {"name": column.name, "sql": column.name, "type": cube_type(column.type)}
        if column.description:
            dimension["description"] = column.description
        dimensions.append(dimension)
    if dimensions:
        cube["dimensions"] = dimensions

    written = []
    for measure in measures:
        entry = {"name": measure.name, "type": measure.kind}
        # `count` over a star has no column to point at, and cube does not
        # want one.
        if measure.column_name and measure.column_name != "*":
            entry["sql"] = measure.column_name
        if measure.description:
            entry["description"] = measure.description
        written.append(entry)
    if written:
        cube["measures"] = written

    related = []
    for join in joins:
        related.append(
            {
                "name": _cube_name(join["table"]),
                "sql": "{{CUBE}}.{} = {{{}}}.{}".format(join["local"], _cube_name(join["table"]), join["remote"]),
                "relationship": "many_to_one",
            }
        )
    if related:
        cube["joins"] = related

    return cube


def _joins_for(table):
    """This table's edges, as (their table, my column, their column)."""
    edges = []
    for relationship in CatalogRelationship.query.filter(CatalogRelationship.data_source_id == table.data_source_id):
        if relationship.left_table == table.name:
            edges.append(
                {
                    "table": relationship.right_table,
                    "local": relationship.left_column,
                    "remote": relationship.right_column,
                }
            )
        elif relationship.right_table == table.name:
            edges.append(
                {
                    "table": relationship.left_table,
                    "local": relationship.right_column,
                    "remote": relationship.left_column,
                }
            )
    return edges


def export_catalog(org, directory, data_source=None):
    """
    Write every table as `<directory>/<data source>/<table>.yml`.

    Only *agreed* measures are written. An export is a thing people read and
    approve in a pull request, and filling it with proposals nobody has
    looked at would make the diff meaningless.
    """
    sources = [data_source] if data_source else DataSource.query.filter(DataSource.org == org).all()
    written = 0

    for source in sources:
        tables = CatalogTable.query.filter(CatalogTable.data_source_id == source.id).order_by(CatalogTable.name)
        folder = os.path.join(directory, _slug(source.name))

        for table in tables:
            columns = (
                CatalogColumn.query.filter(CatalogColumn.catalog_table_id == table.id)
                .order_by(CatalogColumn.name)
                .all()
            )
            measures = (
                CatalogMeasure.query.filter(
                    CatalogMeasure.data_source_id == source.id,
                    CatalogMeasure.table_name == table.name,
                    CatalogMeasure.approved.is_(True),
                )
                .order_by(CatalogMeasure.name)
                .all()
            )
            cube = cube_for(table, columns, measures, _joins_for(table))

            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "{}.yml".format(_cube_name(table.name)))
            with open(path, "w") as handle:
                yaml.safe_dump(
                    {"cubes": [cube]},
                    handle,
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                )
            written += 1

    return {"tables": written, "data_sources": len(sources)}


def _files(directory):
    for root, _dirs, names in os.walk(directory):
        for name in sorted(names):
            if name.endswith((".yml", ".yaml")):
                yield os.path.join(root, name)


def import_catalog(org, directory):
    """
    Read descriptions and agreed measures back out of the files.

    Only the parts a person writes are taken: descriptions, and which
    measures are agreed. Structure is not imported, because structure is the
    warehouse's to state and a file claiming otherwise would be a second
    opinion about a fact.

    A table or measure the catalog has never heard of is skipped rather than
    created -- it means the file is ahead of the harvest, or names something
    that no longer exists, and inventing a row for it would put something in
    front of a model that is not in the warehouse.
    """
    applied = {"tables": 0, "columns": 0, "measures": 0, "skipped": 0}

    for path in _files(directory):
        try:
            with open(path) as handle:
                document = yaml.safe_load(handle) or {}
        except yaml.YAMLError:
            logger.warning("could not read %s", path)
            applied["skipped"] += 1
            continue

        for cube in document.get("cubes") or []:
            name = cube.get("sql_table") or cube.get("name")
            table = CatalogTable.query.filter(CatalogTable.org == org, CatalogTable.name == name).first()
            if table is None:
                applied["skipped"] += 1
                continue

            if cube.get("description"):
                table.description = cube["description"]
                table.description_source = FILE
                applied["tables"] += 1

            applied["columns"] += _apply_dimensions(table, cube.get("dimensions") or [])
            applied["measures"] += _apply_measures(table, cube.get("measures") or [])

    db.session.commit()
    return applied


def _apply_dimensions(table, dimensions):
    described = {d["name"]: d["description"] for d in dimensions if d.get("name") and d.get("description")}
    if not described:
        return 0

    count = 0
    for column in CatalogColumn.query.filter(
        CatalogColumn.catalog_table_id == table.id, CatalogColumn.name.in_(described)
    ):
        column.description = described[column.name]
        column.description_source = FILE
        count += 1
    return count


def _apply_measures(table, measures):
    """
    A measure named in a file is one somebody committed, so it is agreed.

    The definition itself is not taken from the file: `sql` and `type` are
    what the miner found in real queries, and letting a file redefine them
    would mean the catalog claims a definition nobody writes.
    """
    named = {m["name"]: m.get("description") for m in measures if m.get("name")}
    if not named:
        return 0

    count = 0
    for measure in CatalogMeasure.query.filter(
        CatalogMeasure.data_source_id == table.data_source_id,
        CatalogMeasure.table_name == table.name,
        CatalogMeasure.name.in_(named),
    ):
        measure.approved = True
        if named[measure.name]:
            measure.description = named[measure.name]
        count += 1
    return count

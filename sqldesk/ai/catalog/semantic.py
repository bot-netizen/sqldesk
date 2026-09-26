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
    MEASURE_APPROVED,
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


def _joins_by_table(source):
    """
    Every table's edges, as (their table, my column, their column), read in
    one query per data source. Asked per table, this read the whole
    relationship list once for every table -- tables times joins, in a web
    request, for the download button.
    """
    edges = {}
    for relationship in CatalogRelationship.query.filter(CatalogRelationship.data_source_id == source.id):
        edges.setdefault(relationship.left_table, []).append(
            {"table": relationship.right_table, "local": relationship.left_column, "remote": relationship.right_column}
        )
        edges.setdefault(relationship.right_table, []).append(
            {"table": relationship.left_table, "local": relationship.right_column, "remote": relationship.left_column}
        )
    return edges


def catalog_documents(org, data_source=None):
    """
    Every table as a relative path and the YAML that goes in it.

    Separate from writing them, because the same files are also wanted as a
    download from the browser -- and having the zip build a directory in a
    temporary folder just to read it back would be two implementations of
    one format, which is how a download and a checkout start to differ.

    Only *agreed* measures are included. An export is a thing people read
    and approve in a pull request, and filling it with proposals nobody has
    looked at would make the diff meaningless.
    """
    sources = [data_source] if data_source else DataSource.query.filter(DataSource.org == org).all()

    for source in sources:
        tables = CatalogTable.query.filter(CatalogTable.data_source_id == source.id).order_by(CatalogTable.name).all()

        # Four queries per data source, however many tables it has.
        columns = {}
        for column in (
            CatalogColumn.query.join(CatalogTable, CatalogTable.id == CatalogColumn.catalog_table_id)
            .filter(CatalogTable.data_source_id == source.id)
            .order_by(CatalogColumn.name)
        ):
            columns.setdefault(column.catalog_table_id, []).append(column)
        measures = {}
        for measure in CatalogMeasure.query.filter(
            CatalogMeasure.data_source_id == source.id,
            CatalogMeasure.status == MEASURE_APPROVED,
        ).order_by(CatalogMeasure.name):
            measures.setdefault(measure.table_name, []).append(measure)
        joins = _joins_by_table(source)

        for table in tables:
            cube = cube_for(table, columns.get(table.id, []), measures.get(table.name, []), joins.get(table.name, []))

            yield (
                "{}/{}.yml".format(_slug(source.name), _cube_name(table.name)),
                yaml.safe_dump(
                    {"cubes": [cube]},
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                    # One fact per line, however long. The default wraps
                    # scalars at 80 columns, so changing a word in the middle
                    # of a description rewraps the lines after it and the
                    # diff shows four changed lines for one changed word --
                    # in a file whose whole purpose is being read as a diff.
                    width=100000,
                ),
            )


def export_catalog(org, directory, data_source=None):
    """Write what `catalog_documents` yields, under `directory`."""
    sources = [data_source] if data_source else DataSource.query.filter(DataSource.org == org).all()
    written = 0

    for relative, text in catalog_documents(org, data_source=data_source):
        path = os.path.join(directory, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)
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

    # Export writes `<data source>/<table>.yml`, so the folder says which
    # source a file is about. Matching on the table name alone put staging's
    # description on production's `orders` -- whichever the database
    # returned first.
    by_folder = {}
    for source in DataSource.query.filter(DataSource.org == org):
        by_folder.setdefault(_slug(source.name), []).append(source)

    for path in _files(directory):
        try:
            with open(path) as handle:
                document = yaml.safe_load(handle) or {}
        except yaml.YAMLError:
            logger.warning("could not read %s", path)
            applied["skipped"] += 1
            continue

        relative = os.path.relpath(path, directory).split(os.sep)
        sources = by_folder.get(relative[0]) if len(relative) > 1 else None

        for cube in document.get("cubes") or []:
            name = cube.get("sql_table") or cube.get("name")
            table = _table_for(org, name, sources)
            if table is None:
                logger.warning("%s: no single table %r in the catalog to apply it to", path, name)
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


def _table_for(org, name, sources):
    """
    The one catalog table a cube is about, or None.

    In a folder named for a data source, that source's table. Anywhere else
    -- a flat directory, a folder named for nothing -- only a name that is
    unique across the organization, because guessing between two tables of
    the same name is how a description lands on the wrong one.
    """
    query = CatalogTable.query.filter(CatalogTable.org == org, CatalogTable.name == name)
    if sources is not None:
        if len(sources) != 1:
            return None
        return query.filter(CatalogTable.data_source_id == sources[0].id).first()
    matches = query.limit(2).all()
    return matches[0] if len(matches) == 1 else None


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
        # A file naming a measure is an explicit, reviewed statement, so it
        # wins even over an earlier denial -- somebody put it in the repo on
        # purpose, and exports only ever contain approved ones anyway.
        measure.status = MEASURE_APPROVED
        if named[measure.name]:
            measure.description = named[measure.name]
        count += 1
    return count

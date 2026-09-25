"""
Filling the catalog.

Two sources, and they answer different questions. The data source says what
exists -- tables, columns, types, and whatever else the engine will tell us.
The query log says what matters -- which tables anyone uses, which columns
anyone selects, and which joins anyone writes.

Neither is enough alone. A warehouse with three thousand tables and no usage
data ranks them alphabetically; usage data with no schema cannot tell you a
column's type.
"""

import logging

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from sqldesk.ai.catalog.mine import mine_all
from sqldesk.models import (
    CatalogColumn,
    CatalogMeasure,
    CatalogRelationship,
    CatalogTable,
    Query,
    db,
)

logger = logging.getLogger(__name__)

#: Where a description came from. Only the engine's may be replaced by a
#: later harvest; everything else is somebody's words.
ENGINE = "engine"
HUMAN = "human"
FILE = "file"

#: Past this many, a card lists the most-used columns and says how many it left
#: out. A three-hundred column table is most of a prompt otherwise.
CARD_COLUMN_LIMIT = 30


def catalog_metadata_for(data_source):
    """
    What the source knows about itself.

    `get_schema()` -- names, columns, types -- is what every one of the 35+
    runners already implements, so this works everywhere today. A runner that
    can say more implements `get_catalog_metadata()` and is used instead; one
    that cannot is not broken, just less useful.
    """
    runner = data_source.query_runner
    richer = getattr(runner, "get_catalog_metadata", None)
    if callable(richer):
        try:
            return richer()
        except NotImplementedError:
            pass
        except Exception:
            # A runner's optional extra failing must not cost us the schema
            # every runner can give.
            logger.exception("get_catalog_metadata failed for data source %s; falling back", data_source.id)

    return [
        {
            "name": table["name"],
            "columns": table.get("columns", []),
            "description": table.get("description"),
            "properties": {},
        }
        for table in (data_source.get_schema() or [])
    ]


def _column_entries(columns):
    """`get_schema` yields either bare names or dicts, depending on the runner."""
    for column in columns:
        if isinstance(column, dict):
            # MySQL already returns `column_comment` here as "description",
            # and it was being dropped -- a sentence somebody wrote about
            # their own warehouse, thrown away on the way to a model that
            # needed it.
            yield column.get("name"), column.get("type"), column.get("description")
        else:
            yield column, None, None


def build_card(name, usage_count, columns, joins, description=None, measures=()):
    """
    The compact text a model is given for one table.

    DDL-shaped rather than JSON: JSON repeats its keys once per column and
    costs roughly three times as much for the same facts.

    Plain values rather than a model instance, because the harvester writes
    these in bulk and has no ORM objects in hand at that point.

    A description, where there is one, is worth more per character than
    anything else here -- `flag_c2` with a sentence beats forty columns
    without one -- so it goes first and is never truncated away.
    """
    shown = columns[:CARD_COLUMN_LIMIT]
    body = ", ".join(_column_text(column) for column in shown)
    lines = []
    if description:
        lines.append("-- {}".format(" ".join(description.split())))
    lines.append("{}({})".format(name, body))

    hidden = len(columns) - len(shown)
    if hidden > 0:
        lines.append("  +{} more columns".format(hidden))
    if usage_count:
        lines.append("  used by {} saved queries".format(usage_count))
    if joins:
        lines.append("  joined with " + ", ".join("{} ({})".format(other, count) for other, count in joins))
    if measures:
        # Only the approved ones reach here. An agreed definition of revenue
        # is the single most valuable line on a card -- and a guessed one is
        # the most dangerous, which is why nobody's guess gets in.
        lines.append("  measures: " + ", ".join(sorted(measures)))
    return "\n".join(lines)


def _column_text(column):
    """`name type` plus, where the warehouse said what it means, a comment."""
    name, column_type = column[0], column[1]
    description = column[3] if len(column) > 3 else None
    text = "{} {}".format(name, column_type or "?")
    if description:
        text += " /* {} */".format(" ".join(description.split()))
    return text


def _keep_curated(statement, table):
    """
    Take the engine's description, but never over a person's.

    A harvest runs on a schedule and a person writes a sentence once. If the
    two are written the same way, the schedule wins every time and the
    sentence disappears -- quietly, because nobody is watching a cron job. So
    the update is conditional: a row whose description came from a person --
    typed here, or imported from a file they wrote -- keeps it, and a row
    that has none takes whatever the warehouse offers.

    Phrased as "anything the engine did not write" rather than a list of the
    sources that count, so that a new way for a person to say something is
    protected by default instead of the first harvest after it lands.

    The condition is on the *stored* row rather than the incoming one, which
    is what makes it safe to run again.
    """
    stored_source = table.c.description_source
    written_by_a_person = sa.and_(stored_source.isnot(None), stored_source != ENGINE)
    return {
        "description": sa.case(
            [(written_by_a_person, table.c.description)],
            else_=statement.excluded.description,
        ),
        "description_source": sa.case(
            [(written_by_a_person, stored_source)],
            else_=statement.excluded.description_source,
        ),
    }


def _upsert(table, rows, index_elements, update_columns, chunk=500, describe=False):
    """
    Write many rows in a handful of statements instead of one each.

    The first version read then wrote per row: 200 tables of 40 columns came
    to 25,031 statements and 13 seconds, which extrapolates to something like
    375,000 statements on a three-thousand table warehouse. Chunked so one
    enormous statement does not replace one enormous loop.
    """
    if not rows:
        return
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        statement = insert(table).values(batch)
        updates = {name: getattr(statement.excluded, name) for name in update_columns}
        if describe:
            updates.update(_keep_curated(statement, table))
        db.session.execute(statement.on_conflict_do_update(index_elements=index_elements, set_=updates))


def harvest_data_source(data_source):
    """
    Bring one data source's catalog up to date. Safe to run again: everything
    is keyed on names, so a second run updates rather than duplicates.
    """
    org = data_source.org
    entries = [entry for entry in catalog_metadata_for(data_source) if entry.get("name")]

    # `with_entities`, because the text is all that is wanted and a Query row
    # carries its options, its schedule and its latest result with it.
    saved = [
        row.query_text
        for row in Query.query.filter(
            Query.data_source_id == data_source.id, Query.is_archived.is_(False)
        ).with_entities(Query.query_text)
    ]
    usage = mine_all((text, data_source.type) for text in saved)

    def used(name):
        """Names come back qualified or bare depending on the engine, and the
        query log holds whichever spelling the author used. Count both."""
        return usage["tables"].get(name, 0) or usage["tables"].get(name.split(".")[-1], 0)

    now = db.func.now()
    _upsert(
        CatalogTable.__table__,
        [
            {
                "org_id": org.id,
                "data_source_id": data_source.id,
                "name": entry["name"],
                "properties": entry.get("properties") or {},
                "usage_count": used(entry["name"]),
                "description": entry.get("description"),
                "description_source": ENGINE if entry.get("description") else None,
                "created_at": now,
                "updated_at": now,
                "harvested_at": now,
            }
            for entry in entries
        ],
        ["data_source_id", "name"],
        ("properties", "usage_count", "updated_at", "harvested_at"),
        # Descriptions are not in that list on purpose -- see `_keep_curated`.
        describe=True,
    )
    db.session.flush()

    ids = {
        name: row_id
        for row_id, name in db.session.query(CatalogTable.id, CatalogTable.name).filter(
            CatalogTable.data_source_id == data_source.id
        )
    }

    column_rows, cards = [], {}
    for entry in entries:
        name = entry["name"]
        bare = name.split(".")[-1]
        table_id = ids.get(name)
        if table_id is None:
            continue
        columns = []
        for column_name, column_type, column_description in _column_entries(entry.get("columns") or []):
            if not column_name:
                continue
            count = usage["columns"].get((name, column_name), 0) or usage["columns"].get((bare, column_name), 0)
            columns.append((column_name, column_type, count, column_description))
            column_rows.append(
                {
                    "catalog_table_id": table_id,
                    "name": column_name,
                    "type": column_type,
                    "usage_count": count,
                    "description": column_description,
                    "description_source": ENGINE if column_description else None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        cards[name] = columns

    _upsert(
        CatalogColumn.__table__,
        column_rows,
        ["catalog_table_id", "name"],
        ("type", "usage_count", "updated_at"),
        describe=True,
    )

    _store_relationships(data_source, org, usage["joins"])
    _store_measures(data_source, org, usage["measures"])
    _drop_tables_that_went_away(data_source, {entry["name"] for entry in entries})
    _write_cards(data_source, entries, cards, usage["joins"], ids, {e["name"]: used(e["name"]) for e in entries})
    db.session.commit()

    return {
        "tables": len(entries),
        "queries_mined": len(saved),
        "relationships": len(usage["joins"]),
    }


def _store_measures(data_source, org, measures):
    """
    Proposed metrics, with their counts kept current.

    `approved` is deliberately not in the update list: a harvest may discover
    a definition and may revise how popular it is, but whether somebody has
    blessed it is not a harvest's business. Nor is the description, for the
    same reason a table's is not.
    """
    if not measures:
        return

    now = db.func.now()
    rows = [
        {
            "org_id": org.id,
            "data_source_id": data_source.id,
            "table_name": table,
            "name": name,
            "kind": kind,
            "column_name": column,
            "usage_count": count,
            "approved": False,
            "created_at": now,
            "updated_at": now,
        }
        for (table, name, kind, column), count in measures.items()
    ]
    _upsert(
        CatalogMeasure.__table__,
        rows,
        ["data_source_id", "table_name", "name"],
        ("kind", "column_name", "usage_count", "updated_at"),
    )


def _drop_tables_that_went_away(data_source, still_there):
    """
    A table dropped from the warehouse should leave the catalog, or it is
    offered to a model forever and every query written against it fails.
    """
    stale = [
        row.id
        for row in CatalogTable.query.filter(CatalogTable.data_source_id == data_source.id).with_entities(
            CatalogTable.id, CatalogTable.name
        )
        if row.name not in still_there
    ]
    if stale:
        CatalogColumn.query.filter(CatalogColumn.catalog_table_id.in_(stale)).delete(synchronize_session=False)
        CatalogTable.query.filter(CatalogTable.id.in_(stale)).delete(synchronize_session=False)


def _store_relationships(data_source, org, joins):
    now = db.func.now()
    _upsert(
        CatalogRelationship.__table__,
        [
            {
                "org_id": org.id,
                "data_source_id": data_source.id,
                "left_table": left_table,
                "left_column": left_column,
                "right_table": right_table,
                "right_column": right_column,
                "observed_count": count,
                "created_at": now,
                "updated_at": now,
            }
            for ((left_table, left_column), (right_table, right_column)), count in joins.items()
        ],
        ["data_source_id", "left_table", "left_column", "right_table", "right_column"],
        ("observed_count", "updated_at"),
    )


def _stored_descriptions(data_source):
    """
    The descriptions as they now stand, table and column.

    Read back rather than taken from the harvest entry, because the entry
    only ever holds what the *engine* said. A sentence somebody typed here,
    or imported from the semantic repo, is deliberately kept out of the
    engine's answer by the upsert -- so building a card from the entry
    rebuilds it without the very words a person went to the trouble of
    writing, and the curation disappears everywhere it was supposed to show.
    """
    tables = {}
    columns = {}
    rows = (
        db.session.query(CatalogTable.id, CatalogTable.name, CatalogTable.description)
        .filter(CatalogTable.data_source_id == data_source.id)
        .all()
    )
    by_id = {}
    for table_id, name, description in rows:
        tables[name] = description
        by_id[table_id] = name

    if by_id:
        for table_id, name, description in (
            db.session.query(CatalogColumn.catalog_table_id, CatalogColumn.name, CatalogColumn.description)
            .filter(CatalogColumn.catalog_table_id.in_(by_id), CatalogColumn.description.isnot(None))
            .all()
        ):
            columns[(by_id[table_id], name)] = description

    return tables, columns


def _approved_measures(data_source):
    """`name = SUM(column)` per table, for the tables that have any."""
    by_table = {}
    for measure in CatalogMeasure.query.filter(
        CatalogMeasure.data_source_id == data_source.id, CatalogMeasure.approved.is_(True)
    ):
        text = "{} = {}({})".format(measure.name, (measure.kind or "").upper(), measure.column_name)
        by_table.setdefault(measure.table_name, []).append(text)
    return by_table


def _write_cards(data_source, entries, cards, joins, ids, usage):
    neighbours = {}
    for ((left_table, _), (right_table, _)), count in joins.items():
        neighbours.setdefault(left_table, []).append((right_table, count))
        neighbours.setdefault(right_table, []).append((left_table, count))

    now = db.func.now()
    approved = _approved_measures(data_source)
    described, described_columns = _stored_descriptions(data_source)
    rows = []
    for entry in entries:
        name = entry["name"]
        if name not in ids:
            continue
        bare = name.split(".")[-1]
        # Usage came back with the columns, so ranking them costs nothing --
        # the first version asked the database for each table's counts, which
        # is a query per table for something already in hand.
        ranked = [
            (column[0], column[1], column[2], described_columns.get((name, column[0])) or column[3])
            for column in sorted(cards.get(name, []), key=lambda column: -column[2])
        ]
        edges = sorted(neighbours.get(name, neighbours.get(bare, [])), key=lambda edge: -edge[1])[:4]
        rows.append(
            {
                "org_id": data_source.org_id,
                "data_source_id": data_source.id,
                "name": name,
                "card": build_card(
                    name,
                    usage.get(name, 0),
                    ranked,
                    edges,
                    described.get(name),
                    approved.get(name) or approved.get(bare) or (),
                ),
                "updated_at": now,
                "created_at": now,
            }
        )
    _upsert(CatalogTable.__table__, rows, ["data_source_id", "name"], ("card", "updated_at"))

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

from sqlalchemy.dialects.postgresql import insert

from sqldesk.ai.catalog.mine import mine_all
from sqldesk.models import CatalogColumn, CatalogRelationship, CatalogTable, Query, db

logger = logging.getLogger(__name__)

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
        {"name": table["name"], "columns": table.get("columns", []), "properties": {}}
        for table in (data_source.get_schema() or [])
    ]


def _column_entries(columns):
    """`get_schema` yields either bare names or dicts, depending on the runner."""
    for column in columns:
        if isinstance(column, dict):
            yield column.get("name"), column.get("type")
        else:
            yield column, None


def build_card(table, columns, joins):
    """
    The compact text a model is given for one table.

    DDL-shaped rather than JSON: JSON repeats its keys once per column and
    costs roughly three times as much for the same facts.
    """
    shown = columns[:CARD_COLUMN_LIMIT]
    body = ", ".join("{} {}".format(name, type_ or "?") for name, type_ in shown)
    lines = ["{}({})".format(table.name, body)]

    hidden = len(columns) - len(shown)
    if hidden > 0:
        lines.append("  +{} more columns".format(hidden))
    if table.usage_count:
        lines.append("  used by {} saved queries".format(table.usage_count))
    if joins:
        lines.append("  joined with " + ", ".join("{} ({})".format(other, count) for other, count in joins))
    return "\n".join(lines)


def harvest_data_source(data_source):
    """
    Bring one data source's catalog up to date. Safe to run again: everything
    is keyed on names, so a second run updates rather than duplicates.
    """
    org = data_source.org
    tables = catalog_metadata_for(data_source)

    saved = [
        (query.query_text, data_source.type)
        for query in Query.query.filter(Query.data_source_id == data_source.id, Query.is_archived.is_(False)).all()
    ]
    usage = mine_all(saved)

    seen_tables = {}
    for entry in tables:
        name = entry.get("name")
        if not name:
            continue
        row = CatalogTable.query.filter(
            CatalogTable.data_source_id == data_source.id, CatalogTable.name == name
        ).first()
        if row is None:
            row = CatalogTable(org=org, data_source=data_source, name=name)
        row.properties = entry.get("properties") or {}
        # Names come back qualified or bare depending on the engine, and the
        # query log writes them however the author did. Count both spellings.
        row.usage_count = usage["tables"].get(name, 0) or usage["tables"].get(name.split(".")[-1], 0)
        row.harvested_at = db.func.now()
        db.session.add(row)
        seen_tables[name] = (row, list(_column_entries(entry.get("columns") or [])))

    db.session.flush()

    for name, (row, columns) in seen_tables.items():
        bare = name.split(".")[-1]
        for column_name, column_type in columns:
            if not column_name:
                continue
            column = CatalogColumn.query.filter(
                CatalogColumn.catalog_table_id == row.id, CatalogColumn.name == column_name
            ).first()
            if column is None:
                column = CatalogColumn(catalog_table=row, name=column_name)
            column.type = column_type
            column.usage_count = usage["columns"].get((name, column_name), 0) or usage["columns"].get(
                (bare, column_name), 0
            )
            db.session.add(column)

    _store_relationships(data_source, org, usage["joins"])
    db.session.flush()
    _write_cards(data_source, seen_tables, usage["joins"])
    db.session.commit()

    return {
        "tables": len(seen_tables),
        "queries_mined": len(saved),
        "relationships": len(usage["joins"]),
    }


def _store_relationships(data_source, org, joins):
    for ((left_table, left_column), (right_table, right_column)), count in joins.items():
        # `on_conflict_do_update` rather than read-then-write: the harvester
        # runs on a schedule and a query saved between the read and the write
        # would otherwise raise on the unique index.
        statement = (
            insert(CatalogRelationship.__table__)
            .values(
                org_id=org.id,
                data_source_id=data_source.id,
                left_table=left_table,
                left_column=left_column,
                right_table=right_table,
                right_column=right_column,
                observed_count=count,
                created_at=db.func.now(),
                updated_at=db.func.now(),
            )
            .on_conflict_do_update(
                index_elements=["data_source_id", "left_table", "left_column", "right_table", "right_column"],
                set_={"observed_count": count, "updated_at": db.func.now()},
            )
        )
        db.session.execute(statement)


def _write_cards(data_source, seen_tables, joins):
    neighbours = {}
    for ((left_table, _), (right_table, _)), count in joins.items():
        neighbours.setdefault(left_table, []).append((right_table, count))
        neighbours.setdefault(right_table, []).append((left_table, count))

    for name, (row, columns) in seen_tables.items():
        bare = name.split(".")[-1]
        # One query for this table's usage counts, not one per column: a
        # dynamic relationship inside a sort key is a query per comparison.
        counts = {column.name: (column.usage_count or 0) for column in row.columns}
        # Most-used first, so what the card has room for is what people look
        # at; ties keep the order the engine gave, which is usually the
        # table's own.
        ranked = sorted(columns, key=lambda column: -counts.get(column[0], 0))
        edges = sorted(neighbours.get(name, neighbours.get(bare, [])), key=lambda edge: -edge[1])[:4]
        row.card = build_card(row, ranked, edges)
        db.session.add(row)

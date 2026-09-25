"""
Finding the few tables a question is about.

Ranked by what the query log says, not by name: the tables people use are the
tables people ask about. BM25 and embeddings come later -- and only once the
eval set can say they earned their dependency. Usage frequency does most of
the work, which is why the harvester comes first.
"""

from sqlalchemy import or_

from sqldesk.models import CatalogColumn, CatalogRelationship, CatalogTable, db

DEFAULT_LIMIT = 8


def _terms(question):
    return [word.strip().lower() for word in (question or "").split() if len(word.strip()) > 2]


def find_tables(org, question, data_source=None, limit=DEFAULT_LIMIT):
    """
    Candidate tables for a question, most likely first.

    Matched on table *and* column names, because a question is asked in the
    vocabulary of the data rather than of the schema. "Revenue by region"
    names no table: matching table names alone returned `region_targets`, a
    four-row lookup, and missed `orders`, which has a `region` column and
    forty-three queries behind it.

    Ranked by usage, which is the part that is ours. Two tables whose names
    both contain "order" are separated by which one anyone actually queries,
    and no amount of string matching can tell you that.
    """
    base = CatalogTable.query.filter(CatalogTable.org == org)
    if data_source is not None:
        base = base.filter(CatalogTable.data_source_id == data_source.id)

    terms = _terms(question)
    if not terms:
        return base.order_by(CatalogTable.usage_count.desc().nullslast(), CatalogTable.name).limit(limit).all()

    by_name = [CatalogTable.name.ilike("%{}%".format(term)) for term in terms]
    # Joined to `catalog_tables` rather than matched on its own. A
    # `CatalogColumn` carries no org of its own -- it belongs to one through
    # its table -- so an unconstrained subquery scans every organization's
    # columns. The outer filter still makes the result correct, which is
    # exactly what makes it the kind of mistake nobody notices.
    named_column = (
        db.session.query(CatalogColumn.catalog_table_id)
        .join(CatalogTable, CatalogTable.id == CatalogColumn.catalog_table_id)
        .filter(CatalogTable.org_id == org.id)
        .filter(or_(*[CatalogColumn.name.ilike("%{}%".format(term)) for term in terms]))
    )
    if data_source is not None:
        named_column = named_column.filter(CatalogTable.data_source_id == data_source.id)

    matched = base.filter(or_(*by_name, CatalogTable.id.in_(named_column.subquery().select())))

    ranked = matched.order_by(CatalogTable.usage_count.desc().nullslast(), CatalogTable.name).limit(limit).all()
    if ranked:
        return ranked

    # Nothing matched the words. A ranked list of the tables people use beats
    # an empty one -- the question may simply not use the warehouse's
    # vocabulary, which is the normal case before a glossary exists.
    return base.order_by(CatalogTable.usage_count.desc().nullslast(), CatalogTable.name).limit(limit).all()


def neighbours_of(table, limit=5):
    """What this table is joined with, most often first."""
    edges = (
        CatalogRelationship.query.filter(
            CatalogRelationship.data_source_id == table.data_source_id,
            or_(CatalogRelationship.left_table == table.name, CatalogRelationship.right_table == table.name),
        )
        .order_by(CatalogRelationship.observed_count.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "table": edge.right_table if edge.left_table == table.name else edge.left_table,
            "on": str(edge),
            "observed": edge.observed_count,
        }
        for edge in edges
    ]


def context_for(org, question, data_source=None, limit=DEFAULT_LIMIT):
    """
    Everything a model should be told about a question, and nothing else.

    A matched table's neighbours come too. `orders` is no use without
    `region_targets` if the question compares one to the other, and the join
    graph already says which tables go together -- so being joined to a match
    is itself a reason to be included.

    Cards rather than schemas: the card was built at harvest time and is
    already the compact form, so assembling this is concatenation.
    """
    tables = find_tables(org, question, data_source=data_source, limit=limit)
    chosen = {table.name: table for table in tables}

    # Looked up once and kept: the first version asked for a table's
    # neighbours while expanding and again while building the response, which
    # is two queries per table for the same answer.
    edges = {table.name: neighbours_of(table) for table in tables}

    wanted = []
    for table in tables:
        for edge in edges[table.name]:
            if len(chosen) + len(wanted) >= limit:
                break
            if edge["table"] not in chosen:
                wanted.append((table.data_source_id, edge["table"]))

    if wanted:
        names = {name for _, name in wanted}
        for neighbour in CatalogTable.query.filter(
            CatalogTable.data_source_id.in_({source_id for source_id, _ in wanted}),
            CatalogTable.name.in_(names),
        ):
            chosen.setdefault(neighbour.name, neighbour)
            edges.setdefault(neighbour.name, neighbours_of(neighbour))

    ordered = sorted(chosen.values(), key=lambda table: -(table.usage_count or 0))
    return {
        "tables": [
            {
                "name": table.name,
                "card": table.card,
                "usage_count": table.usage_count,
                "joins": edges.get(table.name, []),
            }
            for table in ordered
        ]
    }

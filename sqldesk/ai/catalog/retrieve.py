"""
Finding the few tables a question is about.

Ranked by what the query log says, not by name: the tables people use are the
tables people ask about. BM25 and embeddings come later -- and only once the
eval set can say they earned their dependency. Usage frequency does most of
the work, which is why the harvester comes first.
"""

import re

from sqlalchemy import or_

from sqldesk.models import (
    MEASURE_APPROVED,
    CatalogColumn,
    CatalogMeasure,
    CatalogRelationship,
    CatalogTable,
    CatalogVerifiedQuery,
    Query,
    Visualization,
    db,
)

DEFAULT_LIMIT = 8


#: One ILIKE per word, on two tables: past a dozen the words are noise and
#: the query is a way to keep a web worker busy.
MAX_TERMS = 12

#: Words a question is made of rather than words a warehouse is made of.
#: Kept short on purpose: every word dropped here is a word that can no
#: longer match a column, and `status`, `type` and `value` are all real
#: column names. These are the ones that are only ever grammar.
STOPWORDS = frozenset(
    """
    the and for with from that this these those
    what which who whom whose where when why how
    show list give tell find many much any all
    are was were been being have has had does did
    our their your its about into over per each
    please need want
    """.split()
)

#: Splitting on whitespace alone kept the punctuation: "revenue by region last
#: quarter?" searched for `quarter?`, which matches no column name anywhere, so
#: the one word that said what the question was about was the one word thrown
#: away. The final word of a sentence is the most likely to carry it.
_WORD = re.compile(r"[a-z0-9_]+")


def _terms(question):
    """
    The words of a question, as things that might appear in a schema.

    Plurals are stemmed as *extra* terms rather than replacements: a question
    about "orders" should find a table called `order`, and one about "order"
    should still find `orders` -- ILIKE on a substring already does the
    second, so only the first needs help.
    """
    words = []
    for word in _WORD.findall((question or "").lower()):
        if len(word) <= 2 or word in STOPWORDS or word in words:
            continue
        words.append(word)
        stem = word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else None
        if stem and stem not in words:
            words.append(stem)
    return words[:MAX_TERMS]


def find_tables(org, question, data_source=None, limit=DEFAULT_LIMIT, data_source_ids=None):
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

    `data_source_ids`, when given, is every source the caller may read. The
    catalog is the organization's, but a table's name and columns are
    themselves something a group may not be allowed to see.
    """
    if data_source_ids is not None and not data_source_ids:
        return []
    # Hidden tables are left out of what is offered, because the reason to hide
    # one is that nobody needs it. Asking for one by name still works -- see
    # `tool_expand_table` -- since hiding is not access control.
    base = CatalogTable.query.filter(CatalogTable.org == org, CatalogTable.hidden.is_(False))
    if data_source is not None:
        base = base.filter(CatalogTable.data_source_id == data_source.id)
    if data_source_ids is not None:
        base = base.filter(CatalogTable.data_source_id.in_(list(data_source_ids)))

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
    if data_source_ids is not None:
        named_column = named_column.filter(CatalogTable.data_source_id.in_(list(data_source_ids)))

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


def context_for(org, question, data_source=None, limit=DEFAULT_LIMIT, data_source_ids=None):
    """
    Everything a model should be told about a question, and nothing else.

    A matched table's neighbours come too. `orders` is no use without
    `region_targets` if the question compares one to the other, and the join
    graph already says which tables go together -- so being joined to a match
    is itself a reason to be included.

    Cards rather than schemas: the card was built at harvest time and is
    already the compact form, so assembling this is concatenation.
    """
    # A neighbour is looked up in its own table's data source, so it is
    # never from a source the match itself was not.
    tables = find_tables(org, question, data_source=data_source, limit=limit, data_source_ids=data_source_ids)
    # Keyed by source as well as name: two warehouses both have `users`, and
    # keying on the name alone meant the second one replaced the first -- so a
    # question that matched both was answered about one of them, with nothing
    # on the card to say which.
    chosen = {(table.data_source_id, table.name): table for table in tables}

    # Looked up once and kept: the first version asked for a table's
    # neighbours while expanding and again while building the response, which
    # is two queries per table for the same answer.
    edges = {(table.data_source_id, table.name): neighbours_of(table) for table in tables}

    wanted = []
    for table in tables:
        for edge in edges[(table.data_source_id, table.name)]:
            if len(chosen) + len(wanted) >= limit:
                break
            if (table.data_source_id, edge["table"]) not in chosen:
                wanted.append((table.data_source_id, edge["table"]))

    if wanted:
        names = {name for _, name in wanted}
        for neighbour in CatalogTable.query.filter(
            CatalogTable.data_source_id.in_({source_id for source_id, _ in wanted}),
            CatalogTable.name.in_(names),
            CatalogTable.hidden.is_(False),
        ):
            chosen.setdefault((neighbour.data_source_id, neighbour.name), neighbour)
            edges.setdefault((neighbour.data_source_id, neighbour.name), neighbours_of(neighbour))

    ordered = sorted(chosen.values(), key=lambda table: -(table.usage_count or 0))
    return {
        "tables": [
            {
                "name": table.name,
                "card": table.card,
                "usage_count": table.usage_count,
                "joins": edges.get((table.data_source_id, table.name), []),
                # Which warehouse this is from. The caller decides whether to
                # say so -- it is noise when the question named one source and
                # the answer when it did not.
                "data_source_id": table.data_source_id,
                "data_source": table.data_source.name,
            }
            for table in ordered
        ],
        "measures": approved_measures_for(ordered),
    }


def approved_measures_for(tables):
    """
    The measures somebody has signed off on, for these tables.

    Only approved ones. A proposed measure is a guess mined from somebody's
    SQL, and a guess about what "revenue" means is worse than silence --
    a wrong revenue number is still a revenue number, and it arrives with
    the authority of having been asked for.
    """
    if not tables:
        return []

    by_source = {}
    for table in tables:
        by_source.setdefault(table.data_source_id, set()).add(table.name)

    found = []
    for source_id, names in by_source.items():
        found.extend(
            CatalogMeasure.query.filter(
                CatalogMeasure.data_source_id == source_id,
                CatalogMeasure.table_name.in_(names),
                CatalogMeasure.status == MEASURE_APPROVED,
            ).all()
        )

    # The ones most people compute first: a definition four teams wrote
    # independently is a different proposition from one somebody tried once.
    found.sort(key=lambda m: (-(m.usage_count or 0), m.name or ""))
    return [
        {
            "name": measure.name,
            "kind": measure.kind,
            "column": measure.column_name,
            "table": measure.table_name,
            "description": measure.description,
            "expression": "{}({})".format((measure.kind or "").upper(), measure.column_name),
        }
        for measure in found
    ]


def find_saved_queries(org, question, data_source_ids, limit=10):
    """
    Saved queries that may already answer this, confirmed ones first.

    Here rather than in the MCP handler because retrieval is retrieval: the
    eval command has to measure what a client is actually given, and a copy
    of the ranking in a second place is a copy that drifts. The handler turns
    these rows into text; choosing them is this module's job.

    "Confirmed" means a curator read *this* SQL -- the join matches the hash
    as well as the id -- so a query somebody confirmed and then edited sorts
    with the rest and is labelled like the rest.
    """
    readable = set(data_source_ids or [])
    if not readable:
        return []

    matches = [
        or_(
            Query.name.ilike(like),
            Query.description.ilike(like),
            Query.visualizations.any(or_(Visualization.name.ilike(like), Visualization.description.ilike(like))),
        )
        for like in ("%{}%".format(term) for term in _terms(question))
    ]
    if not matches:
        return []

    return (
        Query.query.outerjoin(
            CatalogVerifiedQuery,
            db.and_(
                CatalogVerifiedQuery.query_id == Query.id,
                CatalogVerifiedQuery.query_hash == Query.query_hash,
                CatalogVerifiedQuery.org_id == org.id,
            ),
        )
        .filter(
            Query.org == org,
            Query.is_archived.is_(False),
            Query.is_draft.is_(False),
            Query.data_source_id.in_(readable),
            *matches,
        )
        .order_by(CatalogVerifiedQuery.id.isnot(None).desc(), Query.updated_at.desc())
        .limit(limit)
        .all()
    )

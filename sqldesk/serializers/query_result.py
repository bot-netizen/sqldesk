import csv
import io
import uuid

import xlsxwriter
from dateutil.parser import isoparse as parse_date
from funcy import project, rpartial

from sqldesk.authentication.org_resolving import current_org
from sqldesk.models import QueryResult
from sqldesk.query_runner import TYPE_BOOLEAN, TYPE_DATE, TYPE_DATETIME
from sqldesk.utils import json_dumps


def _convert_format(fmt):
    return (
        fmt.replace("DD", "%d")
        .replace("MM", "%m")
        .replace("YYYY", "%Y")
        .replace("YY", "%y")
        .replace("HH", "%H")
        .replace("mm", "%M")
        .replace("ss", "%S")
        .replace("SSS", "%f")
    )


def _convert_bool(value):
    if value is True:
        return "true"
    elif value is False:
        return "false"

    return value


def _convert_datetime(value, fmt):
    if not value:
        return value

    try:
        parsed = parse_date(value)
        ret = parsed.strftime(fmt)
    except Exception:
        return value

    return ret


def _get_column_lists(columns):
    date_format = _convert_format(current_org.get_setting("date_format"))
    datetime_format = _convert_format(
        "{} {}".format(
            current_org.get_setting("date_format"),
            current_org.get_setting("time_format"),
        )
    )

    special_types = {
        TYPE_BOOLEAN: _convert_bool,
        TYPE_DATE: rpartial(_convert_datetime, date_format),
        TYPE_DATETIME: rpartial(_convert_datetime, datetime_format),
    }

    fieldnames = []
    special_columns = dict()

    for col in columns:
        fieldnames.append(col["name"])

        for col_type in special_types.keys():
            if col["type"] == col_type:
                special_columns[col["name"]] = special_types[col_type]

    return fieldnames, special_columns


def _envelope(query_result, slot, is_api_user):
    """The result's metadata, with `slot` standing in for the payload.

    Deliberately never reads `query_result.data`: the mapped column is deferred
    on this path, and touching it would trigger the lazy load and decode this
    whole function exists to avoid.
    """
    envelope = {
        "id": query_result.id,
        "query_hash": query_result.query_hash,
        "query": query_result.query_text,
        "data": slot,
        "data_source_id": query_result.data_source_id,
        "runtime": query_result.runtime,
        "retrieved_at": query_result.retrieved_at,
    }
    if is_api_user:
        return project(envelope, ["data", "retrieved_at"])
    return envelope


def serialize_query_result_json(query_result, is_api_user, envelope_key="query_result"):
    """Encode a query result to a JSON body without re-encoding the payload.

    The payload is already JSON in Postgres. The ordinary path decodes it into
    Python objects and encodes them again, which measured ~1s of CPU on a 27MB
    result -- two thirds of it in the encode, and nearly half of that in
    _sanitize_data walking the graph for values that were rejected at write
    time. Here the metadata is encoded normally, which is cheap because it is
    tiny, and the stored bytes are dropped into the slot.

    The slot is a fresh random token per call rather than a fixed sentinel, so
    no payload can contain the string that would displace it -- it cannot know
    the token. Returns a string, not a dict: the point is never to build the
    object graph.
    """
    slot = f"sqldesk-payload-{uuid.uuid4().hex}"
    body = json_dumps({envelope_key: _envelope(query_result, slot, is_api_user)})
    payload = QueryResult.raw_data_text(query_result.id) or "null"
    return body.replace(json_dumps(slot), payload, 1)


def serialize_query_result(query_result, is_api_user):
    if is_api_user:
        publicly_needed_keys = ["data", "retrieved_at"]
        return project(query_result.to_dict(), publicly_needed_keys)
    else:
        return query_result.to_dict()


def serialize_query_result_to_dsv(query_result, delimiter):
    s = io.StringIO()

    query_data = query_result.data

    fieldnames, special_columns = _get_column_lists(query_data["columns"] or [])

    writer = csv.DictWriter(s, extrasaction="ignore", fieldnames=fieldnames, delimiter=delimiter)
    writer.writeheader()

    for row in query_data["rows"]:
        for col_name, converter in special_columns.items():
            if col_name in row:
                row[col_name] = converter(row[col_name])

        writer.writerow(row)

    return s.getvalue()


def serialize_query_result_to_xlsx(query_result):
    output = io.BytesIO()

    query_data = query_result.data
    book = xlsxwriter.Workbook(output, {"constant_memory": True})
    sheet = book.add_worksheet("result")

    column_names = []
    for c, col in enumerate(query_data["columns"]):
        sheet.write(0, c, col["name"])
        column_names.append(col["name"])

    for r, row in enumerate(query_data["rows"]):
        for c, name in enumerate(column_names):
            v = row.get(name)
            if isinstance(v, (dict, list)):
                v = str(v)
            sheet.write(r + 1, c, v)

    book.close()

    return output.getvalue()

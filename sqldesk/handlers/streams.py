"""
A stream's own settings: what it keeps, what it groups by, and whether it
stays on when nobody is looking.

Everything a stream *reads* comes through its data source like any other --
the query editor, the schema browser, permissions. What is here is the handful
of decisions that are only a stream's, and the page that shows what it is
doing.

Reading is for anybody who may use the data source. Changing is for an
administrator: a pin burns a worker and a disk indefinitely, a row budget
decides how much disk, and a rollup definition decides what a chart can ask --
none of those are a reader's to set.
"""

import logging
import os
import re

from flask import request
from flask_restful import abort

from sqldesk import features, models, settings
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import has_access, require_access, require_admin, view_only
from sqldesk.query_runner.kafka_stream import table_name
from sqldesk.streams import activity, decode, rollup, slots, watching, window
from sqldesk.streams.store import Store

logger = logging.getLogger(__name__)


def _stream(data_source_id, org, user):
    source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, org)
    # The data source's own permission, not a new one: a stream is a data
    # source, and who may read it is already decided.
    require_access(source, user, view_only)
    stream = models.Stream.query.filter(models.Stream.data_source_id == source.id).first()
    if stream is None:
        abort(404, message="That data source is not a stream.")
    return stream


#: What Kafka itself accepts in a group id, with the length it allows.
GROUP_NAME = re.compile(r"^[A-Za-z0-9._-]{1,249}$")


def _consumer_settings(stream):
    """How a topic's consumer reads, for the page that sets it."""
    stored = stream.value_schema or {}
    return {
        "consumer_group": stream.consumer_group,
        "save_position": bool(stream.save_position),
        "start_from": stream.start_from or models.START_LATEST,
        "value_format": stream.value_format or decode.AUTO,
        "message_type": stream.message_type,
        # Names, not contents: the page shows what was uploaded and offers the
        # choice of message, and neither needs the text back.
        "schema_files": [item["name"] for item in stored.get("files") or []],
        "message_types": stored.get("message_types") or [],
    }


def _reading(body, options=None):
    """
    The decoder a request's reading settings describe, or a 400 saying why not.

    Shared by analysis, which reads a sample the way it will be stored, and by
    the upload check, which only wants to know the files load.
    """
    try:
        return decode.for_reading(
            body.get("value_format"), body.get("schema_files"), body.get("message_type"), options=options
        )
    except decode.SchemaError as error:
        abort(400, message=str(error))


def apply_consumer_settings(stream, body):
    """
    The consumer group, saving the position and where to start, from a request.

    One function for both places a topic is changed, so the rules cannot drift
    apart. Checked against the *result* rather than field by field, because
    the combinations are what can be wrong: a saved position with no group to
    save it under, or starting from a saved position that is never saved.
    """
    group = stream.consumer_group
    if "consumer_group" in body:
        group = (body.get("consumer_group") or "").strip() or None
        if group and not GROUP_NAME.match(group):
            abort(
                400,
                message="A consumer group name is letters, digits, dots, dashes and underscores, at most 249.",
            )
    save = bool(body["save_position"]) if "save_position" in body else bool(stream.save_position)
    start = body["start_from"] if "start_from" in body else (stream.start_from or models.START_LATEST)
    if start not in models.START_POINTS:
        abort(400, message="Start from is one of: {}.".format(", ".join(models.START_POINTS)))

    # Decided on the whole result before anything is touched, so a refused
    # request leaves the stream exactly as it was rather than half-changed.
    if save and not group:
        abort(400, message="Saving the position needs a consumer group name to save it under.")
    if start == models.START_SAVED and not save:
        abort(400, message="Starting where it left off needs the position to be saved.")

    value_format = body.get("value_format", stream.value_format) or decode.AUTO
    if value_format not in decode.FORMATS:
        abort(400, message="The format is one of: {}.".format(", ".join(decode.FORMATS)))
    schema = None
    if value_format != decode.AUTO:
        # New files if they were sent, the ones already kept if they were not:
        # changing the message type should not mean uploading again.
        files = body["schema_files"] if "schema_files" in body else (stream.value_schema or {}).get("files")
        message_type = body.get("message_type", stream.message_type)
        try:
            schema = decode.load(value_format, files, message_type)
        except decode.SchemaError as error:
            abort(400, message=str(error))

    before = decode.signature(stream)
    stream.consumer_group = group
    stream.save_position = save
    stream.start_from = start
    stream.value_format = value_format
    stream.value_schema = schema.stored() if schema else None
    stream.message_type = schema.message_type if schema else None
    return stream.id is not None and decode.signature(stream) != before


def restart_window(stream):
    """
    Throw away a window read the old way, after the reading changed.

    The columns came from the old reading, so they go too and the next flush
    infers them again. A running consumer resets its own window when it sees
    the change, which is the only safe way while it has the file; this covers
    a stream nobody is consuming.
    """
    from sqldesk.tasks.streams import _being_consumed

    stream.columns = None
    stream.schema_state = models.SCHEMA_INFERRED
    stream.rows = 0
    stream.malformed = 0
    stream.last_error = None
    models.db.session.commit()
    if _being_consumed(stream.id):
        return
    path = stream.store_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("could not remove stream %s's window", stream.id, exc_info=True)


class StreamListResource(BaseResource):
    """
    Every stream in the organisation, for the page that watches them.

    Admin, because the page it feeds carries the pin and the budgets. A reader
    who may use one stream has no business knowing what else is configured.

    The `quiet` sentence is the field this page exists for: three different
    situations look identical on an empty chart -- nobody has looked at it
    lately, the consumer stopped with an error, or the topic genuinely has
    nothing on it -- and only one of them is somebody's problem.
    """

    @require_admin
    def get(self):
        streams = models.Stream.query.filter(models.Stream.org == self.current_org).order_by(models.Stream.topic).all()
        names = dict(
            models.db.session.query(models.DataSource.id, models.DataSource.name).filter(
                models.DataSource.org == self.current_org
            )
        )
        return {
            "streams": [
                {
                    "id": stream.id,
                    "data_source_id": stream.data_source_id,
                    "data_source_name": names.get(stream.data_source_id),
                    "topic": stream.topic,
                    "active": activity.is_active(stream),
                    "pinned": stream.pinned,
                    "quiet": activity.why_it_is_quiet(stream),
                    "rows": stream.rows,
                    "malformed": stream.malformed,
                    "observed_rate": round(stream.observed_rate or 0, 1),
                    "window_seconds": stream.window_seconds,
                    "sample_rate": stream.sample_rate,
                    "sampled": stream.sampled,
                    "describes": window.describe(stream.window_seconds, stream.rows),
                    "schema_state": stream.schema_state,
                    "columns": len(stream.columns or []),
                    "has_rollup": bool(stream.measures),
                    "last_flush_at": stream.last_flush_at,
                }
                for stream in streams
            ],
            # The slot count, which used to live on a page of its own. An
            # administrator looking at why a stream will not start needs the
            # limit beside the list of what is holding it, not a tab away.
            "slots": _slots(),
        }


class StreamResource(BaseResource):
    def get(self, data_source_id):
        """
        What the stream is doing, for its page.

        `quiet` is the field worth having: three different situations look
        identical on an empty chart -- nobody has looked at it lately, the
        consumer stopped with an error, or the topic genuinely has nothing on it
        -- and only one of them is a problem.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        return {
            "id": stream.id,
            "data_source_id": stream.data_source_id,
            "topic": stream.topic,
            "active": activity.is_active(stream),
            "pinned": stream.pinned,
            "quiet": activity.why_it_is_quiet(stream),
            "rows": stream.rows,
            "malformed": stream.malformed,
            "observed_rate": round(stream.observed_rate or 0, 1),
            "window_seconds": stream.window_seconds,
            "sample_rate": stream.sample_rate,
            "sampled": stream.sampled,
            # The line the chart puts above itself. Built here so the page and
            # a chart cannot word the same fact two ways.
            "describes": window.describe(stream.window_seconds, stream.rows),
            "row_budget": stream.budget,
            "events_per_second": stream.ceiling,
            **_consumer_settings(stream),
            "columns": list(stream.columns or []),
            "schema_state": stream.schema_state,
            "group_by": list(stream.group_by or []),
            "measures": list(stream.measures or []),
            "last_flush_at": stream.last_flush_at,
            "last_viewed_at": stream.last_viewed_at,
        }

    @require_admin
    def post(self, data_source_id):
        """
        Change what only an administrator may change.

        A rollup definition is checked against the store's real columns before
        it is saved, because the alternative is a definition that looks accepted
        and then fails in a worker once a minute with nobody reading the log.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        body = request.get_json(silent=True) or {}

        if "pinned" in body:
            stream.pinned = bool(body["pinned"])
        if "row_budget" in body:
            stream.row_budget = max(0, int(body["row_budget"] or 0))
        if "events_per_second" in body:
            stream.events_per_second = max(0, int(body["events_per_second"] or 0))
        reread = apply_consumer_settings(stream, body)

        if "columns" in body:
            columns = body["columns"]
            if not isinstance(columns, list) or not columns:
                abort(400, message="A schema needs at least one column.")
            stream.columns = columns
            # Settling the columns is what freezing means: they are not
            # re-inferred, so a producer adding a field no longer changes the
            # shape of anybody's chart.
            stream.schema_state = models.SCHEMA_FROZEN

        if "group_by" in body or "measures" in body:
            group_by = list(body.get("group_by", stream.group_by or []))
            measures = list(body.get("measures", stream.measures or []))
            if measures:
                problem = rollup.check(group_by, measures, self._columns(stream))
                if problem:
                    abort(400, message=problem)
            stream.group_by = group_by
            stream.measures = measures
            # A definition that was refused last time should stop being
            # complained about once it has been fixed.
            stream.last_error = None

        models.db.session.commit()
        if reread:
            restart_window(stream)
        self.record_event({"action": "edit", "object_id": stream.id, "object_type": "stream"})
        return self.get(data_source_id)

    def _columns(self, stream):
        """
        The columns to check a rollup against: the store's, or the stream's.

        The store's are the truth, but a stream that has never consumed anything
        has none -- and refusing to let somebody define a rollup before the
        first event has arrived would mean setting it up twice.
        """
        try:
            store = Store(stream.store_path(), read_only=True)
            try:
                found = store.columns()
            finally:
                store.close()
            if found:
                return found
        except Exception:
            logger.warning("could not read stream %s's columns", stream.id, exc_info=True)
        return [(column["name"], column.get("type", "VARCHAR")) for column in (stream.columns or [])]


class StreamRollupResource(BaseResource):
    def get(self, data_source_id):
        """
        The per-minute buckets, for a chart asking about more than the window.

        `is_other` and `sample_rate` come with every row, because a chart that
        hid the capped tail or quietly multiplied a sampled count would be
        wrong while looking right.
        """
        stream = _stream(data_source_id, self.current_org, self.current_user)
        minutes = min(int(request.args.get("minutes", 180)), 60 * 48)
        rows = (
            stream.rollups.filter(
                models.StreamRollup.minute
                >= models.db.func.now() - models.db.text("INTERVAL '{} minutes'".format(minutes))
            )
            .order_by(models.StreamRollup.minute)
            .limit(20000)
            .all()
        )
        return {
            "minutes": minutes,
            "rows": [
                {
                    "minute": row.minute,
                    "group": row.group_key,
                    "is_other": row.is_other,
                    "values": row.values,
                    "sample_rate": row.sample_rate,
                }
                for row in rows
            ],
        }


def _cluster(data_source_id, org, user, feature):
    """A Kafka cluster somebody with the given permission may work on."""
    if not features.can(user, feature):
        abort(403, message="Your account may not do that with streams.")
    source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, org)
    require_access(source, user, view_only)
    if source.type != "kafka_stream":
        abort(400, message="That data source is not a Kafka cluster.")
    return source


class ClusterTopicsResource(BaseResource):
    """
    Every topic on a cluster, and which of them are enabled.

    Metadata only -- no consumer, no messages -- so it answers a page load.
    Behind `manage_streams`, because the list of what a cluster carries is
    itself worth not handing to everybody: topic names leak the shape of a
    business.
    """

    def get(self, data_source_id):
        source = _cluster(data_source_id, self.current_org, self.current_user, features.MANAGE_STREAMS)
        from sqldesk.streams.consumer import list_topics

        try:
            topics = list_topics(source.options.to_dict(mask_secrets=False))
        except Exception as error:
            logger.warning("could not list the topics on %s", source.name, exc_info=True)
            abort(502, message="Could not ask the cluster what topics it has: {}".format(error))

        enabled = {stream.topic: stream for stream in source.streams}
        for topic in topics:
            stream = enabled.get(topic["name"])
            topic["enabled"] = stream is not None
            topic["stream_id"] = stream.id if stream else None
            topic["columns"] = len(stream.columns or []) if stream else 0
            topic.update(_consumer_settings(stream) if stream else _consumer_settings(models.Stream()))
        return {"topics": topics}


class TopicAnalysisResource(BaseResource):
    """
    What is actually on a topic: columns, how many do not parse, the rate, and
    what a window of it would hold.

    A POST because it opens a connection to the broker and reads: it is not
    free, and it is not something a browser should repeat on a refresh.
    """

    def post(self, data_source_id, topic):
        source = _cluster(data_source_id, self.current_org, self.current_user, features.MANAGE_STREAMS)
        from sqldesk.streams.analysis import analyse

        options = source.options.to_dict(mask_secrets=False)
        body = dict(request.get_json(force=True, silent=True) or {})
        stream = models.Stream.query.filter(
            models.Stream.data_source_id == source.id, models.Stream.topic == topic
        ).first()
        if stream is not None:
            # Nothing said: read it the way it is already set to. A format with
            # no files: the files it already has, which the page never holds.
            if "value_format" not in body:
                body["value_format"] = stream.value_format
                body.setdefault("message_type", stream.message_type)
            if body["value_format"] == stream.value_format and not body.get("schema_files"):
                body["schema_files"] = (stream.value_schema or {}).get("files")
        decoder = _reading(body, options)
        try:
            found = analyse(options, topic, decoder=decoder)
        except Exception as error:
            logger.warning("could not analyse %s on %s", topic, source.name, exc_info=True)
            abort(502, message=str(error))

        self.record_event(
            {
                "action": "analyse_topic",
                "object_id": source.id,
                "object_type": "data_source",
                "params": {"topic": topic},
            }
        )
        return found


class StreamSchemaResource(BaseResource):
    """
    Whether uploaded schema files load, and which messages they define.

    Asked when somebody uploads them, so a typo in a .proto is a sentence under
    the upload rather than a consumer that stops later; and so the page can
    offer the messages to choose between.
    """

    def post(self, data_source_id):
        _cluster(data_source_id, self.current_org, self.current_user, features.MANAGE_STREAMS)
        body = request.get_json(force=True, silent=True) or {}
        value_format = body.get("value_format")
        if value_format not in (decode.AVRO, decode.PROTOBUF):
            abort(400, message="Only Avro and Protobuf take a schema file.")
        try:
            schema = decode.load(
                value_format, body.get("schema_files"), body.get("message_type"), first_if_unchosen=True
            )
        except decode.SchemaError as error:
            abort(400, message=str(error))
        return {"message_types": schema.message_types, "message_type": schema.message_type}


class EnabledTopicResource(BaseResource):
    """
    Enabling a topic, and turning one off again.

    This is the access decision on a Kafka cluster. The data source permission
    is per cluster, so what somebody enables here is what everybody with access
    to that cluster can then query -- which is why it is behind a permission of
    its own rather than being something any reader can do.
    """

    def post(self, data_source_id, topic):
        source = _cluster(data_source_id, self.current_org, self.current_user, features.MANAGE_STREAMS)
        body = request.get_json(force=True, silent=True) or {}

        stream = models.Stream.query.filter(
            models.Stream.data_source_id == source.id, models.Stream.topic == topic
        ).first()
        if stream is None:
            stream = models.Stream(org=source.org, data_source=source, topic=topic)
            models.db.session.add(stream)

        for field in ("row_budget", "events_per_second"):
            if field in body:
                value = body[field]
                if not isinstance(value, int) or value < 0:
                    abort(400, message="{} has to be a whole number, or 0 for the install's.".format(field))
                setattr(stream, field, value)
        reread = apply_consumer_settings(stream, body)
        if "pinned" in body:
            # A pin keeps a worker and a disk busy with nobody watching, which
            # is an administrator's decision rather than a curator's.
            require_admin_or_abort(self.current_user)
            stream.pinned = bool(body["pinned"])
        if "group_by" in body or "measures" in body:
            problem = rollup.check(
                body.get("group_by") or [],
                body.get("measures") or [],
                [(column["name"], column.get("type", "VARCHAR")) for column in (stream.columns or [])],
            )
            if problem and stream.columns:
                abort(400, message=problem)
            stream.group_by = body.get("group_by") or None
            stream.measures = body.get("measures") or None

        models.db.session.commit()
        if reread:
            restart_window(stream)
        self.record_event(
            {
                "action": "enable_topic",
                "object_id": source.id,
                "object_type": "data_source",
                "params": {"topic": topic},
            }
        )
        return _stream_dict(stream, source.name)

    def delete(self, data_source_id, topic):
        source = _cluster(data_source_id, self.current_org, self.current_user, features.MANAGE_STREAMS)
        stream = models.Stream.query.filter(
            models.Stream.data_source_id == source.id, models.Stream.topic == topic
        ).first()
        if stream is None:
            abort(404, message="That topic is not enabled.")

        # The window goes with it. Keeping a file for a topic nobody can query
        # any more is disk nothing will ever claim back.
        import os

        path = stream.store_path()
        slots.release(stream.id)
        models.db.session.delete(stream)
        models.db.session.commit()
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.warning("could not remove the window for %s", topic, exc_info=True)
        return {"ok": True}


def require_admin_or_abort(user):
    if not user.has_permission("admin"):
        abort(403, message="Pinning a stream is an administrator's decision.")


def _stream_dict(stream, source_name=None):
    state = watching.state(stream)
    return {
        "id": stream.id,
        "topic": stream.topic,
        "table": table_name(stream.topic),
        "data_source_id": stream.data_source_id,
        "data_source_name": source_name,
        "state": state,
        "watchers": watching.watchers(stream.id),
        "started_by": stream.started_by.name if stream.started_by else None,
        "pinned": stream.pinned,
        "rows": stream.rows,
        "malformed": stream.malformed,
        "observed_rate": stream.observed_rate,
        "window_seconds": stream.window_seconds,
        "sample_rate": stream.sample_rate,
        "sampled": (stream.sample_rate or 1) > 1,
        "describes": window.describe(stream.window_seconds, stream.rows),
        "last_flush_at": stream.last_flush_at,
        "last_error": stream.last_error,
        "columns": stream.columns or [],
        # Shown on Running streams, where an administrator wants to know which
        # name -- if any -- the broker will see this under.
        **_consumer_settings(stream),
    }


def _slots():
    """
    How much room is left, in the one shape both callers want.

    A slot is a *topic*, not a viewer: everybody watching one topic shares one
    consumer and takes one slot between them, which is why this number can look
    small next to the number of people using it.
    """
    return {
        "used": len(slots.held()),
        "limit": settings.STREAM_MAX_CONCURRENT,
        "per_user": settings.STREAM_MAX_PER_USER,
        "minutes": settings.STREAM_MAX_MINUTES,
    }


class RunningStreamsResource(BaseResource):
    """
    What is consuming right now, and how much room is left.

    Everybody may read it for the clusters they can read: "all the slots are in
    use" is only actionable if you can see what is using them and who to ask.
    Not for clusters they cannot -- a topic's name, columns and errors are the
    cluster's data, and the page that lists a cluster's topics is behind a
    permission for exactly that reason. The slot count stays whole, since the
    slots are shared. Stopping one is for its owner or an administrator.
    """

    def get(self):
        sources = models.DataSource.query.filter(models.DataSource.org == self.current_org).all()
        readable = {source.id: source.name for source in sources if has_access(source, self.current_user, view_only)}
        streams = (
            models.Stream.query.filter(
                models.Stream.org == self.current_org, models.Stream.data_source_id.in_(list(readable) or [0])
            )
            .order_by(models.Stream.topic)
            .all()
        )
        # The cold ones are left out before any is described: describing reads
        # who started it and asks Redis twice, for every stream on every poll.
        running = [
            _stream_dict(stream, readable.get(stream.data_source_id))
            for stream in streams
            if watching.state(stream) != watching.COLD
        ]
        return {"streams": running, "slots": _slots()}


class StreamWatchResource(BaseResource):
    """
    Saying "I am looking at this", every few seconds, while a tab is open.

    The first check-in takes a slot, which is why starting needs the
    permission; the ones after it only keep the stream alive. A viewer of
    somebody else's running stream needs neither a slot nor the permission --
    they are not choosing what is visible and not taking anything from anybody.
    """

    def post(self, stream_id):
        stream = get_object_or_404(models.Stream.query.get, stream_id)
        if stream.org_id != self.current_org.id:
            abort(404, message="No such stream.")
        require_access(stream.data_source, self.current_user, view_only)

        already = watching.state(stream) == watching.RUNNING
        if not already:
            if not features.can(self.current_user, features.USE_STREAMS):
                abort(403, message="Your account may watch streams but not start them.")
            refused = slots.acquire(stream.id, owner=self.current_user.id)
            if refused:
                abort(429, message=refused)
            stream.started_by = self.current_user

        watching.check_in(stream.id, self.current_user.id)
        activity.note_viewed(stream)
        models.db.session.commit()
        return _stream_dict(stream)

    def delete(self, stream_id):
        """A tab going away, rather than being timed out."""
        stream = get_object_or_404(models.Stream.query.get, stream_id)
        if stream.org_id != self.current_org.id:
            abort(404, message="No such stream.")
        watching.left(stream.id, self.current_user.id)
        return {"ok": True}


class StreamQueryResource(BaseResource):
    """
    Run SQL against a cluster's windows, now, without saving anything.

    Deliberately not the ordinary query path. That one enqueues a job for a
    worker, because a query against a warehouse can take four minutes and
    holding a web worker for four minutes is how a server stops answering. A
    stream query reads a DuckDB file on local disk and returns in
    milliseconds -- and it runs every couple of seconds while somebody watches,
    so a round trip through Redis and a worker per refresh would cost more than
    the query.

    Nothing is stored. No `QueryResult` row, no query, no result: the window is
    what a consumer has seen while somebody was watching, and writing it down
    would be making a copy of the one thing whose point is that it is current.
    """

    #: A page shows a screenful. Anything larger is a question for a warehouse,
    #: and sending it every two seconds would be unkind to everybody.
    MAX_ROWS = 2000

    def _named(self, source, query):
        """The cluster's enabled topics this SQL actually mentions."""
        from sqldesk.query_runner.kafka_stream import names_in, table_name

        return [stream for stream in source.streams if names_in(query, table_name(stream.topic))]

    def _watch(self, source, query):
        """
        Check in on the topics this query names, taking a slot where needed.

        Returns a refusal, or None. A topic already running costs nothing --
        the slot is the topic, not the viewer -- so somebody joining a stream
        their colleague started never needs a slot or the permission to take
        one.
        """
        named = self._named(source, query)
        for stream in named:
            if watching.state(stream) != watching.RUNNING:
                if not features.can(self.current_user, features.USE_STREAMS):
                    return "Your account may read streams somebody else has started, but not start one."
                refused = slots.acquire(stream.id, owner=self.current_user.id)
                if refused:
                    return refused
                stream.started_by = self.current_user
            watching.check_in(stream.id, self.current_user.id)
            activity.note_viewed(stream)
        if named:
            models.db.session.commit()
        return None

    def _waiting_for_events(self, source, query):
        """
        Whether the only thing wrong is that nothing has arrived yet.

        True when every topic the query names is being consumed and has no
        window to read. That is a state, not a fault, and the difference
        matters: a red banner for a topic nobody is producing to sends somebody
        to the broker looking for a problem that is not there.
        """
        named = self._named(source, query)
        if not named:
            return False
        return all(
            watching.state(stream) == watching.RUNNING and not os.path.exists(stream.store_path()) for stream in named
        )

    def delete(self, data_source_id):
        """
        Stop watching the topics this query names.

        The other half of `post`, and it was missing: pressing Stop ended the
        page's own polling and told the server nothing, so the consumer ran on
        until the check-in timed out and every status read still said
        "consuming". A viewer who leaves says so.

        It does not stop the stream -- somebody else may be watching the same
        topic, and a slot is a topic rather than a viewer. It stops *this*
        person watching, which is what makes the stream go quiet when the last
        one leaves.
        """
        source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        require_access(source, self.current_user, view_only)
        if source.type != "kafka_stream":
            abort(400, message="That data source is not a Kafka cluster.")

        query = (request.get_json(force=True, silent=True) or {}).get("query") or ""
        left = []
        for stream in self._named(source, query):
            watching.left(stream.id, self.current_user.id)
            left.append(stream.id)
        return {"left": left}

    def post(self, data_source_id):
        source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        require_access(source, self.current_user, view_only)
        if source.type != "kafka_stream":
            abort(400, message="That data source is not a Kafka cluster.")

        query = (request.get_json(force=True, silent=True) or {}).get("query")
        if not query or not query.strip():
            abort(400, message="No query given.")

        # Running a stream query *is* watching it. Without this the editor
        # could ask a question of a topic nobody had started, get "nothing has
        # arrived yet" for ever, and have no way to start it -- which is how
        # this read before the check-in moved here from the page that used to
        # own it. Checking in here also means every way of reading a stream
        # keeps it alive, rather than only the one page that remembered to.
        refused = self._watch(source, query)
        if refused:
            abort(429, message=refused)

        runner = source.query_runner
        if runner is None:
            # The cluster's rows are here but librdkafka is not, so nothing can
            # read it. Said plainly rather than as a 500: this is what an
            # install looks like after somebody removes the optional dependency
            # group, and the fix is an install decision rather than a bug.
            abort(503, message="This install cannot read Kafka streams: the Kafka client is not installed.")

        data, error = runner.run_query(query, self.current_user)
        if error:
            # A stream that is consuming and has not seen an event yet is the
            # ordinary state of a quiet topic for the first few seconds, and
            # the normal state of one nothing is producing to. Answering 400
            # paints the page red for something that is working: it comes back
            # as an empty result with a note, and the page says so calmly.
            waiting = self._waiting_for_events(source, query)
            if waiting:
                return {"columns": [], "rows": [], "truncated": False, "note": error}
            abort(400, message=error)

        import json

        # The runner already stopped at its own ceiling and says whether it
        # did; this slice only matters if the two are ever set differently.
        parsed = json.loads(data)
        rows = parsed.get("rows") or []
        return {
            "columns": parsed.get("columns") or [],
            "rows": rows[: self.MAX_ROWS],
            "truncated": bool(parsed.get("truncated")) or len(rows) > self.MAX_ROWS,
        }

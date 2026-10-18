import calendar
import datetime
import hashlib
import logging
import numbers
import os
import re
import time

import pytz
from croniter import CroniterBadCronError, croniter
from sqlalchemy import UniqueConstraint, and_, cast, distinct, func, or_
from sqlalchemy.dialects.postgresql import ARRAY, DOUBLE_PRECISION, JSONB
from sqlalchemy.event import listens_for
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    backref,
    contains_eager,
    defer,
    joinedload,
    load_only,
    selectinload,
    subqueryload,
)
from sqlalchemy.orm.exc import NoResultFound  # noqa: F401
from sqlalchemy_utils import EncryptedType, generic_relationship
from sqlalchemy_utils.models import generic_repr
from sqlalchemy_utils.types import TSVectorType
from sqlalchemy_utils.types.encrypted.encrypted_type import FernetEngine

from sqldesk import redis_connection, settings, utils
from sqldesk.destinations import (
    get_configuration_schema_for_destination_type,
    get_destination,
)
from sqldesk.metrics import database  # noqa: F401
from sqldesk.models.base import (
    Column,
    GFKBase,
    SearchBaseQuery,
    db,
    gfk_type,
    key_type,
    primary_key,
)
from sqldesk.models.changes import Change, ChangeTrackingMixin  # noqa
from sqldesk.models.mixins import BelongsToOrgMixin, TimestampMixin
from sqldesk.models.organizations import Organization
from sqldesk.models.parameterized_query import (
    InvalidParameterError,
    ParameterizedQuery,
    QueryDetachedFromDataSourceError,
)
from sqldesk.models.types import (
    Configuration,
    EncryptedConfiguration,
    JSONText,
    MutableDict,
    MutableList,
    json_cast_property,
)
from sqldesk.models.users import (  # noqa
    AccessPermission,
    AnonymousUser,
    ApiUser,
    Group,
    User,
)
from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    BaseQueryRunner,
    get_configuration_schema_for_query_runner_type,
    get_query_runner,
    with_ssh_tunnel,
)
from sqldesk.utils import (
    base_url,
    gen_query_hash,
    generate_token,
    json_dumps,
    json_loads,
    mustache_render,
    mustache_render_escape,
    sentry,
    utcnow,
)
from sqldesk.utils.configuration import ConfigurationContainer

logger = logging.getLogger(__name__)


class ScheduledQueriesExecutions:
    KEY_NAME = "sq:executed_at"

    def __init__(self):
        self.executions = {}

    def refresh(self):
        self.executions = redis_connection.hgetall(self.KEY_NAME)

    def update(self, query_id):
        redis_connection.hset(self.KEY_NAME, mapping={query_id: time.time()})

    def get(self, query_id):
        timestamp = self.executions.get(str(query_id))
        if timestamp:
            timestamp = utils.dt_from_timestamp(timestamp)

        return timestamp


scheduled_queries_executions = ScheduledQueriesExecutions()


@generic_repr("id", "name", "type", "org_id", "created_at")
class DataSource(BelongsToOrgMixin, db.Model):
    id = primary_key("DataSource")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="data_sources")

    name = Column(db.String(255))
    type = Column(db.String(255))
    #: Standing guidance about this source, in words: which tables to prefer,
    #: what is untrusted, what the grain is. It is the one piece of context
    #: that applies to every question asked of it, and it is the only place
    #: anyone can say something a schema cannot.
    description = Column(db.Text, nullable=True)
    options = Column(
        "encrypted_options",
        ConfigurationContainer.as_mutable(
            EncryptedConfiguration(db.Text, settings.DATASOURCE_SECRET_KEY, FernetEngine)
        ),
    )
    queue_name = Column(db.String(255), default="queries")
    scheduled_queue_name = Column(db.String(255), default="scheduled_queries")
    created_at = Column(db.DateTime(True), default=db.func.now())

    data_source_groups = db.relationship("DataSourceGroup", back_populates="data_source", cascade="all")
    __tablename__ = "data_sources"
    __table_args__ = (
        db.Index("data_sources_org_id_name", "org_id", "name"),
        {"extend_existing": True},
    )

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def to_dict(self, all=False, with_permissions_for=None):
        d = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "syntax": self.query_runner.syntax,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "supports_auto_limit": self.query_runner.supports_auto_limit,
            "description": self.description,
        }

        if all:
            schema = get_configuration_schema_for_query_runner_type(self.type)
            self.options.set_schema(schema)
            d["options"] = self.options.to_dict(mask_secrets=True)
            d["queue_name"] = self.queue_name
            d["scheduled_queue_name"] = self.scheduled_queue_name
            d["groups"] = self.groups

        if with_permissions_for is not None:
            d["view_only"] = (
                db.session.query(DataSourceGroup.view_only)
                .filter(
                    DataSourceGroup.group == with_permissions_for,
                    DataSourceGroup.data_source == self,
                )
                .one()[0]
            )

        return d

    def __str__(self):
        return str(self.name)

    @classmethod
    def create_with_group(cls, *args, **kwargs):
        data_source = cls(*args, **kwargs)
        data_source_group = DataSourceGroup(data_source=data_source, group=data_source.org.default_group)
        db.session.add_all([data_source, data_source_group])
        return data_source

    @classmethod
    def all(cls, org, group_ids=None):
        data_sources = cls.query.filter(cls.org == org).order_by(cls.id.asc())

        if group_ids:
            data_sources = data_sources.join(DataSourceGroup).filter(DataSourceGroup.group_id.in_(group_ids))

        return data_sources.distinct()

    @classmethod
    def get_by_id(cls, _id):
        return cls.query.filter(cls.id == _id).one()

    def delete(self):
        Query.query.filter(Query.data_source == self).update(dict(data_source_id=None, latest_query_data_id=None))
        QueryResult.query.filter(QueryResult.data_source == self).delete()
        for upload in UploadedFile.query.filter(UploadedFile.data_source == self):
            upload.delete()
        res = db.session.delete(self)
        db.session.commit()

        redis_connection.delete(self._schema_key)

        return res

    def get_cached_schema(self):
        cache = redis_connection.get(self._schema_key)
        return json_loads(cache) if cache else None

    def get_schema(self, refresh=False):
        out_schema = None
        if not refresh:
            out_schema = self.get_cached_schema()

        if out_schema is None:
            query_runner = self.query_runner
            schema = query_runner.get_schema(get_stats=refresh)

            try:
                out_schema = self._sort_schema(schema)
            except Exception:
                logging.exception("Error sorting schema columns for data_source {}".format(self.id))
                out_schema = schema
            finally:
                ttl = int(datetime.timedelta(minutes=settings.SCHEMAS_REFRESH_SCHEDULE, days=7).total_seconds())
                redis_connection.set(self._schema_key, json_dumps(out_schema), ex=ttl)

        return out_schema

    def _sort_schema(self, schema):
        return [
            {**i, "columns": sorted(i["columns"], key=lambda x: x["name"] if isinstance(x, dict) else x)}
            for i in sorted(schema, key=lambda x: x["name"])
        ]

    @property
    def _schema_key(self):
        return "data_source:schema:{}".format(self.id)

    @property
    def _pause_key(self):
        return "ds:{}:pause".format(self.id)

    @property
    def paused(self):
        return redis_connection.exists(self._pause_key)

    @property
    def pause_reason(self):
        return redis_connection.get(self._pause_key)

    def pause(self, reason=None):
        redis_connection.set(self._pause_key, reason or "")

    def resume(self):
        redis_connection.delete(self._pause_key)

    def add_group(self, group, view_only=False):
        dsg = DataSourceGroup(group=group, data_source=self, view_only=view_only)
        db.session.add(dsg)
        return dsg

    def remove_group(self, group):
        DataSourceGroup.query.filter(DataSourceGroup.group == group, DataSourceGroup.data_source == self).delete()
        db.session.commit()

    def update_group_permission(self, group, view_only):
        dsg = DataSourceGroup.query.filter(DataSourceGroup.group == group, DataSourceGroup.data_source == self).one()
        dsg.view_only = view_only
        db.session.add(dsg)
        return dsg

    @property
    def streams_only(self):
        """Whether this data source belongs in Streams rather than in Queries."""
        runner = get_query_runner(self.type, {})
        return bool(runner is not None and getattr(runner, "streams_only", False))

    @property
    def uses_ssh_tunnel(self):
        return self.options and "ssh_tunnel" in self.options

    @property
    def query_runner(self):
        query_runner = get_query_runner(self.type, self.options)

        if self.uses_ssh_tunnel:
            query_runner = with_ssh_tunnel(query_runner, self.options.get("ssh_tunnel"))

        if hasattr(query_runner, "for_data_source"):
            # A stream's window belongs to the data source, not to the
            # connection, and this is the only place that knows which row the
            # runner was built from.
            query_runner.for_data_source(self.id)
        if hasattr(query_runner, "confine_to"):
            query_runner.confine_to(os.path.join(settings.UPLOAD_ROOT, str(self.org_id), str(self.id)))
        if hasattr(query_runner, "register_uploaded_files"):
            uploads = UploadedFile.query.filter(UploadedFile.data_source_id == self.id)
            # The third element says whether to create the view now. An
            # unloaded file is still handed over, name and path, so a query
            # that names it can bring it back -- see the runner.
            query_runner.register_uploaded_files(
                [(upload.view_name, upload.path, upload.unloaded_at is None) for upload in uploads]
            )

        return query_runner

    @classmethod
    def get_by_name(cls, name):
        return cls.query.filter(cls.name == name).one()

    @property
    def groups(self):
        # Through the relationship rather than a fresh query: every permission
        # check on every query reads this, and a dashboard asks once per
        # widget. The relationship is loaded once per session and can be
        # eager-loaded with the rest of a dashboard (see
        # Dashboard.loaded_widgets).
        return dict([(dsg.group_id, dsg.view_only) for dsg in self.data_source_groups])


@generic_repr("id", "data_source_id", "group_id", "view_only")
class DataSourceGroup(db.Model):
    # XXX drop id, use datasource/group as PK
    id = primary_key("DataSourceGroup")
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(DataSource, back_populates="data_source_groups")
    group_id = Column(key_type("Group"), db.ForeignKey("groups.id"))
    group = db.relationship(Group, back_populates="data_sources")
    view_only = Column(db.Boolean, default=False)

    __tablename__ = "data_source_groups"
    __table_args__ = ({"extend_existing": True},)


@generic_repr("id", "org_id", "data_source_id", "filename", "size")
class UploadedFile(TimestampMixin, BelongsToOrgMixin, db.Model):
    id = primary_key("UploadedFile")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="uploaded_files")

    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(DataSource, backref="uploaded_files")

    created_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    # `foreign_keys` is required now that `kept_by_id` is a second path to
    # `users`: without it SQLAlchemy cannot tell which column this relationship
    # means and refuses to map the class at all.
    created_by = db.relationship(User, foreign_keys=[created_by_id])

    filename = Column(db.String(255))
    stored_filename = Column(db.String(255))
    # User-supplied name for the resulting table (e.g. "quarterly_sales"). Falls back to
    # the original filename when not provided.
    display_name = Column(db.String(255), nullable=True)
    content_type = Column(db.String(255), nullable=True)
    size = Column(db.Integer, default=0)

    #: When this file goes. Null means it stays until somebody deletes it --
    #: either because the install has turned the lifecycle off, or because
    #: somebody with `keep_uploads` said to keep it.
    #:
    #: An uploaded file is the only copy of itself. A warehouse answer can be
    #: fetched again; this cannot, so it expires on a clock people can see and
    #: stop, and never silently.
    expires_at = Column(db.DateTime(True), nullable=True)
    kept_at = Column(db.DateTime(True), nullable=True)
    kept_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    kept_by = db.relationship(User, foreign_keys=[kept_by_id])

    #: When a query last named this file's view. Drives the unload step, and is
    #: the one number that makes Admin -> Storage worth looking at: a list of
    #: files with no "last used" column cannot tell you which to remove.
    last_queried_at = Column(db.DateTime(True), nullable=True)

    #: When it stopped being registered with DuckDB. Reversible: the next query
    #: that names it registers it again. The file is untouched.
    unloaded_at = Column(db.DateTime(True), nullable=True)

    #: When its uploader was told it is about to go, so they are told once.
    expiry_warning_sent_at = Column(db.DateTime(True), nullable=True)

    __tablename__ = "uploaded_files"
    #: The two columns the hourly lifecycle scan reads.
    __table_args__ = (
        db.Index("uploaded_files_expires_at", "expires_at"),
        db.Index("uploaded_files_last_queried_at", "last_queried_at"),
    )

    @property
    def expires_in_days(self):
        """Whole days until it goes, or None where it does not."""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - utcnow()
        return max(0, remaining.days + (1 if remaining.seconds else 0))

    @property
    def kept(self):
        return self.expires_at is None

    def keep(self, user):
        """Make it permanent. Who did it is recorded; it is a decision."""
        self.expires_at = None
        self.kept_at = utcnow()
        self.kept_by = user
        self.expiry_warning_sent_at = None

    @staticmethod
    def default_expiry():
        if settings.UPLOAD_LIFETIME_DAYS <= 0:
            return None
        return utcnow() + datetime.timedelta(days=settings.UPLOAD_LIFETIME_DAYS)

    def to_dict(self):
        return {
            "id": self.id,
            "data_source_id": self.data_source_id,
            "filename": self.filename,
            "display_name": self.display_name,
            "view_name": self.view_name,
            "content_type": self.content_type,
            "size": self.size,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expires_in_days": self.expires_in_days,
            "kept": self.kept,
            "kept_by": self.kept_by.name if self.kept_by else None,
            "last_queried_at": self.last_queried_at,
            "unloaded": self.unloaded_at is not None,
            # A row whose file is not on the disk any more. It should not
            # happen -- deleting an upload deletes both -- but it does when the
            # volume holding uploads is replaced underneath an install, and the
            # only symptom otherwise is a data source whose schema is silently
            # empty: queries find no table, the catalog harvests nothing, and
            # every page goes on reporting the upload as though it were there.
            "missing": not os.path.exists(self.path),
        }

    @staticmethod
    def sanitize_view_name(name):
        base = name.rsplit(".", 1)[0]
        base = re.sub(r"[^a-zA-Z0-9_]", "_", base).strip("_").lower() or "file"
        if base[0].isdigit():
            base = "t_" + base
        return base

    @property
    def view_name(self):
        # This is the literal table name a user sees and queries against, so it's
        # not auto-suffixed for uniqueness (see the handler's collision check on
        # create) -- the user owns the exact name.
        return self.sanitize_view_name(self.display_name or self.filename)

    @property
    def directory(self):
        return os.path.join(settings.UPLOAD_ROOT, str(self.org_id), str(self.data_source_id))

    @property
    def path(self):
        return os.path.join(self.directory, self.stored_filename)

    def delete(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
            os.removedirs(self.directory)
        except OSError:
            # removedirs raises if the directory still has other files/isn't empty, or didn't exist; both are fine to ignore.
            pass
        db.session.delete(self)
        db.session.commit()


@generic_repr("id", "org_id", "data_source_id", "query_hash", "runtime", "retrieved_at")
def _row_count_of(data):
    """Row count of a result payload, or None when it cannot be determined.

    Runners hand back {"columns": [...], "rows": [...]}, but a failed or
    empty run may pass None. None is stored rather than 0 so the UI can say
    "unknown" instead of asserting a query returned nothing.
    """
    if isinstance(data, dict):
        rows = data.get("rows")
        if rows is not None:
            try:
                return len(rows)
            except TypeError:
                return None
    return None


class QueryResult(db.Model, BelongsToOrgMixin):
    id = primary_key("QueryResult")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization)
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(DataSource, backref=backref("query_results"))
    query_hash = Column(db.String(32), index=True)
    query_text = Column("query", db.Text)
    data = Column(JSONText, nullable=True)
    runtime = Column(DOUBLE_PRECISION)
    # Denormalised at write time so list views never have to load `data`.
    # Nullable: results stored before this column existed read as unknown.
    row_count = Column(db.Integer, nullable=True)
    retrieved_at = Column(db.DateTime(True))

    __tablename__ = "query_results"
    # What `get_latest` asks for, in the order it asks: this hash, this data
    # source, newest first. With only `query_hash` indexed it found every
    # result for the hash, filtered by data source and sorted the remainder --
    # on every cache lookup.
    __table_args__ = (
        db.Index(
            "ix_query_results_lookup",
            "query_hash",
            "data_source_id",
            retrieved_at.desc(),
        ),
    )

    def __str__(self):
        return "%d | %s | %s" % (self.id, self.query_hash, self.retrieved_at)

    def to_dict(self):
        return {
            "id": self.id,
            "query_hash": self.query_hash,
            "query": self.query_text,
            "data": self.data,
            "data_source_id": self.data_source_id,
            "runtime": self.runtime,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def unused(cls, days=7):
        age_threshold = datetime.datetime.now() - datetime.timedelta(days=days)
        return (cls.query.filter(Query.id.is_(None), cls.retrieved_at < age_threshold).outerjoin(Query)).options(
            load_only("id")
        )

    @classmethod
    def raw_data_text(cls, result_id):
        """The stored payload as the JSON text it already is on disk.

        `data` goes through JSONText, which json_loads the column as the row is
        fetched and whose value is then json_dumps'd again on the way out to the
        client -- a full decode and re-encode of bytes that were already JSON.
        On a 27MB cached result that round trip measures ~1s of CPU, all of it
        on a worker that can serve nothing else meanwhile.

        Callers that only need to hand the payload back out read it through
        here instead, and pair it with a query that defers the mapped column so
        the decode never happens at all.
        """
        row = db.session.execute(db.text("SELECT data FROM query_results WHERE id = :id"), {"id": result_id}).scalar()
        return row

    @classmethod
    def get_by_id_and_org_deferred_data(cls, object_id, org):
        """Load a result without decoding its payload.

        Deferring is transparent: anything that does touch `.data` afterwards
        triggers an ordinary lazy load, so the CSV and Excel paths are
        unaffected. Only the JSON path, which never touches it, saves the work.
        """
        return cls.query.options(defer("data")).filter(cls.id == object_id, cls.org == org).one()

    @classmethod
    def get_latest(cls, data_source, query, max_age=0):
        query_hash = gen_query_hash(query)

        if max_age == -1 and settings.QUERY_RESULTS_EXPIRED_TTL_ENABLED:
            max_age = settings.QUERY_RESULTS_EXPIRED_TTL

        if max_age == -1:
            query = cls.query.filter(cls.query_hash == query_hash, cls.data_source == data_source)
        else:
            query = cls.query.filter(
                cls.query_hash == query_hash,
                cls.data_source == data_source,
                (
                    db.func.timezone("utc", cls.retrieved_at) + datetime.timedelta(seconds=max_age)
                    >= db.func.timezone("utc", db.func.now())
                ),
            )

        return query.options(defer("data")).order_by(cls.retrieved_at.desc()).first()

    @classmethod
    def latest_ids(cls, data_source_id, query_hashes, max_age=-1):
        """
        {query hash: id of its newest result}, for several hashes at once.

        `get_latest` answers one question per call, which is right for the one
        query a person is running. A live dashboard asks the same question
        once per widget per viewer per check-in -- so a ten-widget dashboard
        with four people watching was forty statements every few seconds, for
        ten answers. This is one.

        Hashes with no result, or none young enough, are absent rather than
        mapped to None: the caller is asking which results exist.
        """
        hashes = list({h for h in query_hashes if h})
        if not hashes:
            return {}

        if max_age == -1 and settings.QUERY_RESULTS_EXPIRED_TTL_ENABLED:
            max_age = settings.QUERY_RESULTS_EXPIRED_TTL

        rows = db.session.query(cls.query_hash, cls.id).filter(
            cls.data_source_id == data_source_id, cls.query_hash.in_(hashes)
        )
        if max_age != -1:
            rows = rows.filter(
                db.func.timezone("utc", cls.retrieved_at) + datetime.timedelta(seconds=max_age)
                >= db.func.timezone("utc", db.func.now())
            )
        # DISTINCT ON the hash, newest first: Postgres takes the first row of
        # each group, which is what `get_latest` does one hash at a time. The
        # ordering matches ix_query_results_lookup, so it is an index scan.
        rows = rows.distinct(cls.query_hash).order_by(cls.query_hash, cls.retrieved_at.desc())
        return {query_hash: result_id for query_hash, result_id in rows}

    @classmethod
    def store_result(cls, org, data_source, query_hash, query, data, run_time, retrieved_at):
        query_result = cls(
            org_id=org,
            query_hash=query_hash,
            query_text=query,
            runtime=run_time,
            data_source=data_source,
            retrieved_at=retrieved_at,
            data=data,
            row_count=_row_count_of(data),
        )

        db.session.add(query_result)
        logging.info("Inserted query (%s) data; id=%s", query_hash, query_result.id)

        return query_result

    @property
    def groups(self):
        return self.data_source.groups


def is_valid_cron(expression):
    """Whether croniter will accept this expression.

    Worth checking before a schedule is stored: outdated_queries disables the
    schedule of any query whose next run it cannot work out, so an expression
    that does not parse would silently stop the query refreshing rather than
    report anything.
    """
    if not isinstance(expression, str) or not expression.strip():
        return False
    try:
        croniter(expression.strip())
    except (CroniterBadCronError, ValueError, KeyError):
        return False
    return True


def should_schedule_next(previous_iteration, now, interval, time=None, day_of_week=None, failures=0, cron=None):
    # if previous_iteration is None, it means the query has never been run before
    # so we should schedule it immediately
    if previous_iteration is None:
        return True

    if cron:
        # get_next returns the first match strictly after the datetime it is
        # given, which is the question being asked: has another slot come round
        # since the query last ran. interval, time and day_of_week are ignored
        # -- the expression says everything.
        next_iteration = croniter(cron, previous_iteration).get_next(datetime.datetime)
        if failures:
            try:
                next_iteration += datetime.timedelta(minutes=2**failures)
            except OverflowError:
                return False
        return now > next_iteration

    # if time exists then interval > 23 hours (82800s)
    # if day_of_week exists then interval > 6 days (518400s)
    if time is None:
        ttl = int(interval)
        next_iteration = previous_iteration + datetime.timedelta(seconds=ttl)
    else:
        hour, minute = time.split(":")
        hour, minute = int(hour), int(minute)

        # The following logic is needed for cases like the following:
        # - The query scheduled to run at 23:59.
        # - The scheduler wakes up at 00:01.
        # - Using naive implementation of comparing timestamps, it will skip the execution.
        normalized_previous_iteration = previous_iteration.replace(hour=hour, minute=minute)

        if normalized_previous_iteration > previous_iteration:
            previous_iteration = normalized_previous_iteration - datetime.timedelta(days=1)

        days_delay = int(interval) / 60 / 60 / 24

        days_to_add = 0
        if day_of_week is not None:
            days_to_add = list(calendar.day_name).index(day_of_week) - normalized_previous_iteration.weekday()

        next_iteration = (
            previous_iteration + datetime.timedelta(days=days_delay) + datetime.timedelta(days=days_to_add)
        ).replace(hour=hour, minute=minute)
    if failures:
        try:
            next_iteration += datetime.timedelta(minutes=2**failures)
        except OverflowError:
            return False
    return now > next_iteration


@gfk_type
@generic_repr(
    "id",
    "name",
    "query_hash",
    "version",
    "user_id",
    "org_id",
    "data_source_id",
    "query_hash",
    "last_modified_by_id",
    "is_archived",
    "is_draft",
    "schedule",
    "schedule_failures",
)
class Query(ChangeTrackingMixin, TimestampMixin, BelongsToOrgMixin, db.Model):
    id = primary_key("Query")
    version = Column(db.Integer, default=1)
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="queries")
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"), nullable=True)
    data_source = db.relationship(DataSource, backref="queries")
    latest_query_data_id = Column(key_type("QueryResult"), db.ForeignKey("query_results.id"), nullable=True)
    latest_query_data = db.relationship(QueryResult)
    name = Column(db.String(255))
    description = Column(db.String(4096), nullable=True)
    query_text = Column("query", db.Text)
    query_hash = Column(db.String(32))
    api_key = Column(db.String(40), default=lambda: generate_token(40))
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, foreign_keys=[user_id])
    last_modified_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    last_modified_by = db.relationship(User, backref="modified_queries", foreign_keys=[last_modified_by_id])
    is_archived = Column(db.Boolean, default=False, index=True)
    is_draft = Column(db.Boolean, default=True, index=True)
    schedule = Column(MutableDict.as_mutable(JSONB), nullable=True)
    interval = json_cast_property(db.Integer, "schedule", "interval", default=0)
    schedule_failures = Column(db.Integer, default=0)
    visualizations = db.relationship("Visualization", cascade="all, delete-orphan")
    options = Column(MutableDict.as_mutable(JSONB), default={})
    search_vector = Column(
        TSVectorType(
            "id",
            "name",
            "description",
            "query",
            weights={"name": "A", "id": "B", "description": "C", "query": "D"},
        ),
        nullable=True,
    )
    tags = Column("tags", MutableList.as_mutable(ARRAY(db.Unicode)), nullable=True)

    query_class = SearchBaseQuery
    __tablename__ = "queries"
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}

    #: On top of the mixin's own. The API key is a credential, and a change
    #: record is a copy of it that nothing ever expires -- it is not part of
    #: what a version of a query says, and the history endpoint would have to
    #: remember not to serve it. The search vector is a derived blob nobody
    #: reads in this form.
    skipped_fields = ChangeTrackingMixin.skipped_fields + ("api_key", "search_vector")

    def __str__(self):
        return str(self.id)

    def archive(self, user=None):
        db.session.add(self)
        self.is_archived = True
        self.schedule = None

        for vis in self.visualizations:
            for w in vis.widgets:
                db.session.delete(w)

        for a in self.alerts:
            db.session.delete(a)

        if user:
            self.record_changes(user)

    def regenerate_api_key(self):
        self.api_key = generate_token(40)

    @classmethod
    def create(cls, **kwargs):
        query = cls(**kwargs)
        db.session.add(
            Visualization(
                query_rel=query,
                name="Table",
                description="",
                type="TABLE",
                options={},
            )
        )
        return query

    @classmethod
    def all_queries(cls, group_ids, user_id=None, include_drafts=False, include_archived=False):
        query_ids = (
            db.session.query(distinct(cls.id))
            .join(DataSourceGroup, Query.data_source_id == DataSourceGroup.data_source_id)
            .filter(Query.is_archived.is_(include_archived))
            .filter(DataSourceGroup.group_id.in_(group_ids))
        )
        queries = (
            cls.query.options(
                joinedload(Query.user),
                joinedload(Query.latest_query_data).load_only("runtime", "retrieved_at", "row_count"),
            )
            .filter(cls.id.in_(query_ids))
            # Adding outer joins to be able to order by relationship
            .outerjoin(User, User.id == Query.user_id)
            .outerjoin(QueryResult, QueryResult.id == Query.latest_query_data_id)
            .options(contains_eager(Query.user), contains_eager(Query.latest_query_data))
        )

        if not include_drafts:
            queries = queries.filter(or_(Query.is_draft.is_(False), Query.user_id == user_id))
        return queries

    @classmethod
    def favorites(cls, user, base_query=None):
        if base_query is None:
            base_query = cls.all_queries(user.group_ids, user.id, include_drafts=True)
        return base_query.join(
            (
                Favorite,
                and_(Favorite.object_type == "Query", Favorite.object_id == Query.id),
            )
        ).filter(Favorite.user_id == user.id)

    @classmethod
    def all_tags(cls, user, include_drafts=False):
        queries = cls.all_queries(group_ids=user.group_ids, user_id=user.id, include_drafts=include_drafts)

        tag_column = func.unnest(cls.tags).label("tag")
        usage_count = func.count(1).label("usage_count")

        query = (
            db.session.query(tag_column, usage_count)
            .group_by(tag_column)
            .filter(Query.id.in_(queries.options(load_only("id"))))
            .order_by(tag_column)
        )
        return query

    @classmethod
    def by_user(cls, user):
        return cls.all_queries(user.group_ids, user.id).filter(Query.user == user)

    @classmethod
    def by_api_key(cls, api_key):
        return cls.query.filter(cls.api_key == api_key).one()

    @classmethod
    def past_scheduled_queries(cls):
        now = utils.utcnow()
        queries = Query.query.filter(func.jsonb_typeof(Query.schedule) != "null").order_by(Query.id)
        return [
            query
            for query in queries
            if "until" in query.schedule
            and query.schedule["until"] is not None
            and pytz.utc.localize(datetime.datetime.strptime(query.schedule["until"], "%Y-%m-%d")) <= now
        ]

    @classmethod
    def outdated_queries(cls):
        queries = (
            Query.query.options(joinedload(Query.latest_query_data).load_only("retrieved_at"))
            .filter(func.jsonb_typeof(Query.schedule) != "null")
            .order_by(Query.id)
            .all()
        )

        now = utils.utcnow()
        outdated_queries = {}
        scheduled_queries_executions.refresh()

        for query in queries:
            try:
                if query.schedule.get("disabled"):
                    continue

                # Skip queries that have None for all schedule values. It's unclear whether this
                # something that can happen in practice, but we have a test case for it.
                if all(value is None for value in query.schedule.values()):
                    continue

                if query.schedule.get("until"):
                    schedule_until = pytz.utc.localize(datetime.datetime.strptime(query.schedule["until"], "%Y-%m-%d"))

                    if schedule_until <= now:
                        continue

                retrieved_at = scheduled_queries_executions.get(query.id) or (
                    query.latest_query_data and query.latest_query_data.retrieved_at
                )

                # .get() rather than []: a cron schedule carries no interval,
                # and a KeyError here is caught below and disables the
                # schedule outright.
                if should_schedule_next(
                    retrieved_at,
                    now,
                    query.schedule.get("interval"),
                    query.schedule.get("time"),
                    query.schedule.get("day_of_week"),
                    query.schedule_failures,
                    cron=query.schedule.get("cron"),
                ):
                    key = "{}:{}".format(query.query_hash, query.data_source_id)
                    outdated_queries[key] = query
            except Exception as e:
                query.schedule["disabled"] = True
                db.session.commit()

                message = (
                    "Could not determine if query %d is outdated due to %s. The schedule for this query has been disabled."
                    % (query.id, repr(e))
                )
                logging.info(message)
                sentry.capture_exception(type(e)(message).with_traceback(e.__traceback__))

        return list(outdated_queries.values())

    @classmethod
    def _do_multi_byte_search(cls, all_queries, term, limit=None):
        # term examples:
        #    - word
        #    - name:word
        #    - query:word
        #    - "multiple words"
        #    - name:"multiple words"
        #    - word1 word2 word3
        #    - word1 "multiple word" query:"select foo"
        tokens = re.findall(r'(?:([^:\s]+):)?(?:"([^"]+)"|(\S+))', term)
        conditions = []
        for token in tokens:
            key = None
            if token[0]:
                key = token[0]

            if token[1]:
                value = token[1]
            else:
                value = token[2]

            pattern = f"%{value}%"

            if key == "id" and value.isdigit():
                conditions.append(cls.id.equal(int(value)))
            elif key == "name":
                conditions.append(cls.name.ilike(pattern))
            elif key == "query":
                conditions.append(cls.query_text.ilike(pattern))
            elif key == "description":
                conditions.append(cls.description.ilike(pattern))
            else:
                conditions.append(or_(cls.name.ilike(pattern), cls.description.ilike(pattern)))

        return all_queries.filter(and_(*conditions)).order_by(Query.id).limit(limit)

    @classmethod
    def search(
        cls,
        term,
        group_ids,
        user_id=None,
        include_drafts=False,
        limit=None,
        include_archived=False,
        multi_byte_search=False,
    ):
        all_queries = cls.all_queries(
            group_ids,
            user_id=user_id,
            include_drafts=include_drafts,
            include_archived=include_archived,
        )

        if multi_byte_search:
            # Since tsvector doesn't work well with CJK languages, use `ilike` too
            return cls._do_multi_byte_search(all_queries, term, limit)

        # sort the result using the weight as defined in the search vector column
        return all_queries.search(term, sort=True).limit(limit)

    @classmethod
    def search_by_user(cls, term, user, limit=None, multi_byte_search=False):
        if multi_byte_search:
            # Since tsvector doesn't work well with CJK languages, use `ilike` too
            return cls._do_multi_byte_search(cls.by_user(user), term, limit)

        return cls.by_user(user).search(term, sort=True).limit(limit)

    @classmethod
    def recent(cls, group_ids, user_id=None, limit=20):
        query = (
            cls.query.filter(Event.created_at > (db.func.current_date() - 7))
            .join(Event, Query.id == Event.object_id.cast(db.Integer))
            .join(DataSourceGroup, Query.data_source_id == DataSourceGroup.data_source_id)
            .filter(
                Event.action.in_(["edit", "execute", "edit_name", "edit_description", "view_source"]),
                Event.object_id is not None,
                Event.object_type == "query",
                DataSourceGroup.group_id.in_(group_ids),
                or_(Query.is_draft.is_(False), Query.user_id is user_id),
                Query.is_archived.is_(False),
            )
            .group_by(Event.object_id, Query.id)
            .order_by(db.desc(db.func.count(0)))
        )

        if user_id:
            query = query.filter(Event.user_id == user_id)

        query = query.limit(limit)

        return query

    @classmethod
    def get_by_id(cls, _id):
        return cls.query.filter(cls.id == _id).one()

    @classmethod
    def all_groups_for_query_ids(cls, query_ids):
        query = """SELECT group_id, view_only
                   FROM queries
                   JOIN data_source_groups ON queries.data_source_id = data_source_groups.data_source_id
                   WHERE queries.id in :ids"""

        return db.session.execute(query, {"ids": tuple(query_ids)}).fetchall()

    def update_latest_result_by_query_hash(self):
        query_hash = self.query_hash
        data_source_id = self.data_source_id
        query_result = (
            QueryResult.query.options(load_only("id"))
            .filter(
                QueryResult.query_hash == query_hash,
                QueryResult.data_source_id == data_source_id,
            )
            .order_by(QueryResult.retrieved_at.desc())
            .first()
        )
        if query_result:
            latest_query_data_id = query_result.id
            self.latest_query_data_id = latest_query_data_id
            db.session.add(self)

    @classmethod
    def update_latest_result(cls, query_result):
        # TODO: Investigate how big an impact this select-before-update makes.
        queries = Query.query.filter(
            Query.query_hash == query_result.query_hash,
            Query.data_source == query_result.data_source,
            Query.is_archived.is_(False),
        )

        for q in queries:
            q.latest_query_data = query_result
            # don't auto-update the updated_at timestamp
            q.skip_updated_at = True
            db.session.add(q)

        query_ids = [q.id for q in queries]
        logging.info(
            "Updated %s queries with result (%s).",
            len(query_ids),
            query_result.query_hash,
        )

        return query_ids

    def fork(self, user):
        forked_list = [
            "org",
            "data_source",
            "latest_query_data",
            "description",
            "query_text",
            "query_hash",
            "options",
            "tags",
        ]
        kwargs = {a: getattr(self, a) for a in forked_list}

        # Query.create will add default TABLE visualization, so use constructor to create bare copy of query
        forked_query = Query(name="Copy of (#{}) {}".format(self.id, self.name), user=user, **kwargs)

        for v in sorted(self.visualizations, key=lambda v: v.id):
            forked_v = v.copy()
            forked_v["query_rel"] = forked_query
            fv = Visualization(**forked_v)  # it will magically add it to `forked_query.visualizations`
            db.session.add(fv)

        db.session.add(forked_query)
        return forked_query

    @property
    def runtime(self):
        return self.latest_query_data.runtime

    @property
    def retrieved_at(self):
        return self.latest_query_data.retrieved_at

    @property
    def groups(self):
        if self.data_source is None:
            return {}

        return self.data_source.groups

    @hybrid_property
    def lowercase_name(self):
        "Optional property useful for sorting purposes."
        return self.name.lower()

    @lowercase_name.expression
    def lowercase_name(cls):
        "The SQLAlchemy expression for the property above."
        return func.lower(cls.name)

    @property
    def parameters(self):
        return self.options.get("parameters", [])

    @property
    def parameterized(self):
        return ParameterizedQuery(self.query_text, self.parameters, self.org)

    @property
    def dashboard_ids(self):
        """
        The dashboards this query is drawn on.

        The same walk as `dashboard_api_keys` below, minus the api_keys table:
        that one can only answer for dashboards somebody has shared, and a
        render pass has to work for the ones nobody has.
        """
        rows = db.session.execute(
            """SELECT DISTINCT dashboards.id
               FROM dashboards
               JOIN widgets ON dashboards.id = widgets.dashboard_id
               JOIN visualizations ON widgets.visualization_id = visualizations.id
               WHERE visualizations.query_id = :id""",
            {"id": self.id},
        ).fetchall()
        return [row[0] for row in rows]

    @property
    def dashboard_api_keys(self):
        query = """SELECT api_keys.api_key
                   FROM api_keys
                   JOIN dashboards ON object_id = dashboards.id
                   JOIN widgets ON dashboards.id = widgets.dashboard_id
                   JOIN visualizations ON widgets.visualization_id = visualizations.id
                   WHERE object_type='dashboards'
                     AND active=true
                     AND visualizations.query_id = :id"""

        api_keys = db.session.execute(query, {"id": self.id}).fetchall()
        return [api_key[0] for api_key in api_keys]

    def update_query_hash(self):
        should_apply_auto_limit = self.options.get("apply_auto_limit", False) if self.options else False
        query_runner = self.data_source.query_runner if self.data_source else BaseQueryRunner({})
        query_text = self.query_text

        parameters_dict = {p["name"]: p.get("value") for p in self.parameters} if self.options else {}
        if any(parameters_dict):
            try:
                query_text = self.parameterized.apply(parameters_dict).query
            except InvalidParameterError as e:
                logging.info(f"Unable to update hash for query {self.id} because of invalid parameters: {str(e)}")
            except QueryDetachedFromDataSourceError as e:
                logging.info(
                    f"Unable to update hash for query {self.id} because of dropdown query {e.query_id} is unattached from datasource"
                )

        self.query_hash = query_runner.gen_query_hash(query_text, should_apply_auto_limit)


@listens_for(Query, "before_insert")
@listens_for(Query, "before_update")
def receive_before_insert_update(mapper, connection, target):
    target.update_query_hash()


@listens_for(Query.user_id, "set")
def query_last_modified_by(target, val, oldval, initiator):
    target.last_modified_by_id = val


@generic_repr("id", "object_type", "object_id", "user_id", "org_id")
class Favorite(TimestampMixin, db.Model):
    id = primary_key("Favorite")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))

    object_type = Column(db.Unicode(255))
    object_id = Column(key_type("Favorite"))
    object = generic_relationship(object_type, object_id)

    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, backref="favorites")

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("object_type", "object_id", "user_id", name="unique_favorite"),)

    @classmethod
    def is_favorite(cls, user, object):
        return cls.query.filter(cls.object == object, cls.user_id == user).count() > 0

    @classmethod
    def are_favorites(cls, user, objects):
        objects = list(objects)
        if not objects:
            return []

        object_type = str(objects[0].__class__.__name__)
        return [
            fav.object_id
            for fav in cls.query.filter(
                cls.object_id.in_([o.id for o in objects]),
                cls.object_type == object_type,
                cls.user_id == user,
            )
        ]


OPERATORS = {
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
    "==": lambda v, t: v == t,
    "!=": lambda v, t: v != t,
    # backward compatibility
    "greater than": lambda v, t: v > t,
    "less than": lambda v, t: v < t,
    "equals": lambda v, t: v == t,
}


def next_state(op, value, threshold):
    if isinstance(value, bool):
        # If it's a boolean cast to string and lower case, because upper cased
        # boolean value is Python specific and most likely will be confusing to
        # users.
        value = str(value).lower()
        value_is_number = False
    else:
        try:
            value = float(value)
            value_is_number = True
        except ValueError:
            value_is_number = isinstance(value, numbers.Number)

        if value_is_number:
            try:
                threshold = float(threshold)
            except ValueError:
                return Alert.UNKNOWN_STATE
        else:
            value = str(value)

    if op(value, threshold):
        new_state = Alert.TRIGGERED_STATE
    elif not value_is_number and op not in [OPERATORS.get("!="), OPERATORS.get("=="), OPERATORS.get("equals")]:
        new_state = Alert.UNKNOWN_STATE
    else:
        new_state = Alert.OK_STATE

    return new_state


@generic_repr("id", "name", "query_id", "user_id", "state", "last_triggered_at", "rearm")
class Alert(TimestampMixin, BelongsToOrgMixin, db.Model):
    UNKNOWN_STATE = "unknown"
    OK_STATE = "ok"
    TRIGGERED_STATE = "triggered"
    TEST_STATE = "test"

    id = primary_key("Alert")
    name = Column(db.String(255))
    query_id = Column(key_type("Query"), db.ForeignKey("queries.id"))
    query_rel = db.relationship(Query, backref=backref("alerts", cascade="all"))
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, backref="alerts")
    options = Column(MutableDict.as_mutable(JSONB), nullable=True)
    state = Column(db.String(255), default=UNKNOWN_STATE)
    subscriptions = db.relationship("AlertSubscription", cascade="all, delete-orphan")
    last_triggered_at = Column(db.DateTime(True), nullable=True)
    rearm = Column(db.Integer, nullable=True)

    __tablename__ = "alerts"

    @classmethod
    def all(cls, group_ids):
        return (
            cls.query.options(joinedload(Alert.user), joinedload(Alert.query_rel))
            .join(Query)
            .join(DataSourceGroup, DataSourceGroup.data_source_id == Query.data_source_id)
            .filter(DataSourceGroup.group_id.in_(group_ids))
        )

    @classmethod
    def get_by_id_and_org(cls, object_id, org):
        return super(Alert, cls).get_by_id_and_org(object_id, org, Query)

    def evaluate(self):
        data = self.query_rel.latest_query_data.data if self.query_rel.latest_query_data else None
        new_state = self.UNKNOWN_STATE

        if data and data["rows"] and self.options["column"] in data["rows"][0]:
            op = OPERATORS.get(self.options["op"], lambda v, t: False)

            if "selector" not in self.options:
                selector = "first"
            else:
                selector = self.options["selector"]

            try:
                if selector == "max":
                    max_val = float("-inf")
                    for i in range(len(data["rows"])):
                        max_val = max(max_val, float(data["rows"][i][self.options["column"]]))
                    value = max_val
                elif selector == "min":
                    min_val = float("inf")
                    for i in range(len(data["rows"])):
                        min_val = min(min_val, float(data["rows"][i][self.options["column"]]))
                    value = min_val
                else:
                    value = data["rows"][0][self.options["column"]]

            except ValueError:
                return self.UNKNOWN_STATE

            threshold = self.options["value"]

            if value is not None:
                new_state = next_state(op, value, threshold)

        return new_state

    def subscribers(self):
        return User.query.join(AlertSubscription).filter(AlertSubscription.alert == self)

    def render_template(self, template):
        if template is None:
            return ""

        data = self.query_rel.latest_query_data.data
        host = base_url(self.query_rel.org)

        col_name = self.options["column"]
        if data["rows"] and col_name in data["rows"][0]:
            result_value = data["rows"][0][col_name]
        else:
            result_value = None

        result_table = []  # A two-dimensional array which can rendered as a table in Mustache
        for row in data["rows"]:
            result_table.append([row[col["name"]] for col in data["columns"]])
        context = {
            "ALERT_NAME": self.name,
            "ALERT_URL": "{host}/alerts/{alert_id}".format(host=host, alert_id=self.id),
            "ALERT_STATUS": self.state.upper(),
            "ALERT_SELECTOR": self.options["selector"],
            "ALERT_CONDITION": self.options["op"],
            "ALERT_THRESHOLD": self.options["value"],
            "QUERY_NAME": self.query_rel.name,
            "QUERY_URL": "{host}/queries/{query_id}".format(host=host, query_id=self.query_rel.id),
            "QUERY_RESULT_VALUE": result_value,
            "QUERY_RESULT_ROWS": data["rows"],
            "QUERY_RESULT_COLS": data["columns"],
            "QUERY_RESULT_TABLE": result_table,
        }
        return mustache_render_escape(template, context)

    @property
    def custom_body(self):
        template = self.options.get("custom_body", self.options.get("template"))
        return self.render_template(template)

    @property
    def custom_subject(self):
        template = self.options.get("custom_subject")
        return self.render_template(template)

    @property
    def groups(self):
        return self.query_rel.groups

    @property
    def muted(self):
        return self.options.get("muted", False)


def generate_slug(ctx):
    slug = utils.slugify(ctx.current_parameters["name"])
    tries = 1
    while Dashboard.query.filter(Dashboard.slug == slug).first() is not None:
        slug = utils.slugify(ctx.current_parameters["name"]) + "_" + str(tries)
        tries += 1
    return slug


@generic_repr("id", "name", "org_id", "locked")
class DashboardFolder(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A set of dashboards with a stated meaning.

    Dashboards accumulate, and the ones that matter get lost among the ones
    somebody made on a Tuesday. A folder says what belongs in it -- "business
    KPIs", "operational metrics for the line" -- so that "is this a KPI" has an
    answer rather than an argument.

    **Locked is the point.** A locked folder is one only administrators can
    change: a dashboard inside it cannot be edited, renamed, archived or have a
    widget added by anybody else, including the person who made it. A set
    called "business KPIs" that anybody can edit is a set of dashboards with a
    label on it; one only administrators curate is a statement about what has
    been through review.

    Everybody can read them, favourite them and put them on a screen. The lock
    is on changing, not on seeing.
    """

    id = primary_key("DashboardFolder")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"), nullable=False)
    org = db.relationship(Organization)
    name = Column(db.String(100), nullable=False)

    #: What belongs in it, written when it is made. The field that turns a
    #: folder from a label into a definition.
    meaning = Column(db.Text, nullable=True)

    #: Whether only administrators may change what is in it, and the
    #: dashboards that are.
    locked = Column(db.Boolean, nullable=False, default=False)

    #: Whether it appears in the Dashboards menu. Most installs end up with
    #: more folders than fit in a dropdown, and a menu of thirty is a menu
    #: nobody reads -- so the few that people use daily are chosen, and the
    #: rest live on the folders page.
    in_menu = Column(db.Boolean, nullable=False, default=False)

    created_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    created_by = db.relationship(User)

    __tablename__ = "dashboard_folders"
    __table_args__ = (db.Index("dashboard_folders_org_name", "org_id", "name", unique=True),)

    def __str__(self):
        return self.name

    def to_dict(self, counts=None):
        return {
            "id": self.id,
            "name": self.name,
            "meaning": self.meaning,
            "locked": self.locked,
            "in_menu": self.in_menu,
            "created_by": self.created_by.name if self.created_by else None,
            "dashboards": counts if counts is not None else None,
        }


@gfk_type
@generic_repr("id", "name", "slug", "user_id", "org_id", "version", "is_archived", "is_draft")
class Dashboard(ChangeTrackingMixin, TimestampMixin, BelongsToOrgMixin, db.Model):
    id = primary_key("Dashboard")
    version = Column(db.Integer)
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="dashboards")
    slug = Column(db.String(140), index=True, default=generate_slug)
    name = Column(db.String(100))
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User)
    # layout is no longer used, but kept so we know how to render old dashboards.
    layout = Column(MutableList.as_mutable(JSONB), default=[])
    dashboard_filters_enabled = Column(db.Boolean, default=False)
    is_archived = Column(db.Boolean, default=False, index=True)
    is_draft = Column(db.Boolean, default=True, index=True)
    widgets = db.relationship("Widget", backref="dashboard", lazy="dynamic")
    tags = Column("tags", MutableList.as_mutable(ARRAY(db.Unicode)), nullable=True)
    options = Column(MutableDict.as_mutable(JSONB), default={})
    # Vestigial: dashboard scheduling was added in 0.2.0 and taken out again in
    # 0.3.2. Nothing reads or writes it. The column is left in place rather than
    # dropped by migration, because dropping it would destroy whatever anyone
    # set while it existed, and an unused nullable column costs nothing.
    schedule = Column(MutableDict.as_mutable(JSONB), nullable=True)
    # A live dashboard: {"interval": seconds, "paused": bool, "paused_by": ...,
    # "paused_at": ...}. Null for an ordinary one. See sqldesk/live.py.
    live = Column(MutableDict.as_mutable(JSONB), nullable=True)

    #: `"streaming"` or `"saved"`, chosen when the dashboard is made.
    #:
    #: Stored rather than worked out from the widgets, which is how it used to
    #: be. A dashboard with no widgets yet has no widgets to ask, so a new one
    #: always looked ordinary and then changed kind the moment its first
    #: streaming widget arrived -- which, now that the two lists are halves of
    #: a partition rather than two filters, reads as "my dashboard has
    #: disappeared".
    #:
    #: Declaring it also lets the widget guard say *why* a visualization does
    #: not belong here instead of refusing after the fact, and takes a
    #: three-table EXISTS off every dashboard list query.
    kind = Column(db.String(20), nullable=False, server_default="saved", default="saved", index=True)

    #: The folder this is filed under, if any. Unfiled is the normal case and
    #: stays normal: a folder is something somebody chooses, never something
    #: they have to pick before saving.
    folder_id = Column(
        key_type("DashboardFolder"), db.ForeignKey("dashboard_folders.id", ondelete="SET NULL"), nullable=True
    )
    folder = db.relationship(DashboardFolder, backref="dashboards")

    @property
    def is_locked(self):
        """Whether only an administrator may change this dashboard."""
        return bool(self.folder is not None and self.folder.locked)

    @property
    def is_streaming(self):
        """
        Whether this dashboard is made of streams.

        One kind or the other, never both -- see `handlers/widgets.py` for why:
        a dashboard has a single refresh interval, and a stream wants seconds
        where a warehouse query wants half a minute. Mixing them means either
        hammering the warehouse or showing a stale stream.

        Read from `kind`, which is declared when the dashboard is made. It used
        to be worked out from the widgets, on the reasoning that a derived
        answer cannot be forgotten -- true, but it also cannot answer for a
        dashboard that has no widgets yet, and that silence is what moved a
        new dashboard between two lists under its author.
        """
        return self.kind == "streaming"

    __tablename__ = "dashboards"
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        # The live sweep runs every ten seconds and asks for exactly this set.
        # Partial, because almost no dashboard is live: the index holds the
        # handful that are rather than a row per dashboard.
        db.Index(
            "ix_dashboards_live",
            "id",
            postgresql_where=db.text("live IS NOT NULL AND is_archived = false"),
        ),
    )

    def __str__(self):
        return "%s=%s" % (self.id, self.name)

    @property
    def name_as_slug(self):
        return utils.slugify(self.name)

    def loaded_widgets(self):
        """
        This dashboard's widgets with everything needed to show or refresh
        them already loaded.

        `widgets` is a dynamic relationship, so iterating it runs a statement
        every time, and each widget then lazily fetches its visualization, its
        query, that query's data source and author, and the data source's
        groups for the permission check. A twelve-widget dashboard cost 65
        statements to serialize and 74 for every live viewer's check-in, most
        of them the same rows over and over.
        """
        return (
            self.widgets.options(
                joinedload(Widget.visualization)
                .joinedload(Visualization.query_rel)
                .options(
                    joinedload(Query.user),
                    joinedload(Query.last_modified_by),
                    joinedload(Query.data_source).selectinload(DataSource.data_source_groups),
                )
            )
            .order_by(Widget.id)
            .all()
        )

    @classmethod
    def all(cls, org, group_ids, user_id):
        query = (
            Dashboard.query.options(joinedload(Dashboard.user).load_only("id", "name", "details", "email"))
            .distinct(cls.lowercase_name, Dashboard.created_at, Dashboard.slug)
            .outerjoin(Widget)
            .outerjoin(Visualization)
            .outerjoin(Query)
            .outerjoin(DataSourceGroup, Query.data_source_id == DataSourceGroup.data_source_id)
            .filter(
                Dashboard.is_archived.is_(False),
                (DataSourceGroup.group_id.in_(group_ids) | (Dashboard.user_id == user_id)),
                Dashboard.org == org,
            )
        )

        query = query.filter(or_(Dashboard.user_id == user_id, Dashboard.is_draft.is_(False)))

        return query

    @classmethod
    def search(cls, org, groups_ids, user_id, search_term):
        # TODO: switch to FTS
        return cls.all(org, groups_ids, user_id).filter(cls.name.ilike("%{}%".format(search_term)))

    @classmethod
    def search_by_user(cls, term, user, limit=None):
        return cls.by_user(user).filter(cls.name.ilike("%{}%".format(term))).limit(limit)

    @classmethod
    def all_tags(cls, org, user):
        dashboards = cls.all(org, user.group_ids, user.id)

        tag_column = func.unnest(cls.tags).label("tag")
        usage_count = func.count(1).label("usage_count")

        query = (
            db.session.query(tag_column, usage_count)
            .group_by(tag_column)
            .filter(Dashboard.id.in_(dashboards.options(load_only("id"))))
            .order_by(tag_column)
        )
        return query

    @classmethod
    def favorites(cls, user, base_query=None):
        if base_query is None:
            base_query = cls.all(user.org, user.group_ids, user.id)
        return (
            base_query.distinct(cls.lowercase_name, Dashboard.created_at, Dashboard.slug, Favorite.created_at)
            .join(
                (
                    Favorite,
                    and_(
                        Favorite.object_type == "Dashboard",
                        Favorite.object_id == Dashboard.id,
                    ),
                )
            )
            .filter(Favorite.user_id == user.id)
        )

    @classmethod
    def content_counts(cls, dashboard_ids):
        """Panel and distinct-query counts for a set of dashboards.

        One grouped query for the whole page, not a lazy load per dashboard:
        reading `len(dashboard.widgets)` while serializing a list would issue
        a query per row, and another per widget to reach its visualization.

        Text widgets have no visualization, so they count as panels but
        contribute nothing to the query count (COUNT DISTINCT skips NULL).
        Two panels charting the same query count once, which is the point —
        it says how many queries the dashboard actually costs to refresh.
        """
        if not dashboard_ids:
            return {}

        rows = (
            db.session.query(
                Widget.dashboard_id,
                func.count(Widget.id).label("widget_count"),
                func.count(distinct(Visualization.query_id)).label("query_count"),
            )
            .outerjoin(Visualization, Visualization.id == Widget.visualization_id)
            .filter(Widget.dashboard_id.in_(dashboard_ids))
            .group_by(Widget.dashboard_id)
            .all()
        )
        return {row.dashboard_id: {"widget_count": row.widget_count, "query_count": row.query_count} for row in rows}

    @classmethod
    def by_user(cls, user):
        return cls.all(user.org, user.group_ids, user.id).filter(Dashboard.user == user)

    @classmethod
    def get_by_slug_and_org(cls, slug, org):
        return cls.query.filter(cls.slug == slug, cls.org == org).one()

    def fork(self, user, keep=lambda widget: True):
        forked_list = ["org", "layout", "dashboard_filters_enabled", "tags"]

        kwargs = {a: getattr(self, a) for a in forked_list}
        forked_dashboard = Dashboard(name="Copy of (#{}) {}".format(self.id, self.name), user=user, **kwargs)

        for w in self.widgets:
            if not keep(w):
                continue
            forked_w = w.copy(forked_dashboard.id)
            fw = Widget(**forked_w)
            db.session.add(fw)

        forked_dashboard.slug = forked_dashboard.id
        db.session.add(forked_dashboard)
        return forked_dashboard

    @hybrid_property
    def lowercase_name(self):
        "Optional property useful for sorting purposes."
        return self.name.lower()

    @lowercase_name.expression
    def lowercase_name(cls):
        "The SQLAlchemy expression for the property above."
        return func.lower(cls.name)


@generic_repr("id", "name", "type", "query_id")
class Visualization(TimestampMixin, BelongsToOrgMixin, db.Model):
    id = primary_key("Visualization")
    type = Column(db.String(100))
    query_id = Column(key_type("Query"), db.ForeignKey("queries.id"))
    # query_rel and not query, because db.Model already has query defined.
    query_rel = db.relationship(Query, back_populates="visualizations")
    name = Column(db.String(255))
    description = Column(db.String(4096), nullable=True)
    options = Column(MutableDict.as_mutable(JSONB), nullable=True)

    __tablename__ = "visualizations"

    def __str__(self):
        return "%s %s" % (self.id, self.type)

    @classmethod
    def get_by_id_and_org(cls, object_id, org):
        return super(Visualization, cls).get_by_id_and_org(object_id, org, Query)

    def copy(self):
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "options": self.options,
        }


#: What an MCP client is allowed to ask for. One scope, because the tools are
#: read-only and a scope a person cannot reason about is a consent screen
#: nobody reads. If a writing tool is ever added it gets its own scope and
#: existing tokens cannot reach it, which is the point of naming this one.
OAUTH_SCOPE = "mcp:read"

#: How long an access token lasts. Short, because it travels in every request
#: and the refresh token is there to make shortness cheap.
OAUTH_ACCESS_TOKEN_SECONDS = 3600

#: And a refresh token. Sliding: used within the window, it is replaced and
#: the window starts again, so an active client never asks anyone to sign in
#: again and an abandoned one stops working within a month.
OAUTH_REFRESH_TOKEN_SECONDS = 60 * 60 * 24 * 30


def _token_digest(value):
    """
    A bearer token as stored.

    Hashed, because a token is a password: it is presented as proof, so
    anything that can read the table can authenticate as its owner. Plain
    SHA-256 with no salt on purpose -- the value is 32 random bytes, so there
    is no dictionary to stretch against, and the lookup has to be by index.
    """
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


#: What a stream's schema is: inferred from the first flush, or settled by a
#: person. A frozen schema is not re-inferred, which is the point -- a chart
#: should not change shape because a producer shipped a field.
SCHEMA_INFERRED = "inferred"
SCHEMA_FROZEN = "frozen"


#: Where a stream starts from cold. See `Stream.start_from`.
START_LATEST = "latest"
START_EARLIEST = "earliest"
START_SAVED = "saved"
START_POINTS = (START_LATEST, START_EARLIEST, START_SAVED)


class Stream(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A Kafka topic, as a data source.

    One row per topic, alongside the `DataSource` that holds the broker and its
    credentials -- the data source is what a person picks in the query editor
    and what the permission system already understands; this is the state that
    is only a stream's: its window, the rate it is doing, whether anybody is
    watching, and what its columns are.

    Everything here is a window onto now. The raw events live in DuckDB and are
    truncated continuously; these columns are the numbers a page reads and the
    settings a person sets. Nothing in this table is the data.
    """

    id = primary_key("Stream")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"), nullable=False)
    org = db.relationship(Organization)
    data_source_id = Column(
        key_type("DataSource"), db.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    # Many per data source: the data source is a *cluster*, and each enabled
    # topic on it is a stream of its own. It was one-to-one while a data source
    # meant a single topic, and adding a second stream silently orphaned the
    # first -- SQLAlchemy nulled its `data_source_id` to keep the one-to-one
    # true, which the column does not allow.
    data_source = db.relationship(DataSource, backref=db.backref("streams", cascade="all, delete-orphan"))
    topic = Column(db.String(255), nullable=False)

    #: Who started it, for the per-person limit and so the Running streams
    #: page can say whose it is -- the difference between "stop this, it is
    #: yours" and "stop this, somebody else is looking at it". Null for a
    #: stream a schedule or a pin started rather than a person.
    started_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    started_by = db.relationship(User, foreign_keys=[started_by_id])

    #: Overrides for this stream alone, where 0 means "use the install's".
    row_budget = Column(db.Integer, nullable=False, default=0)
    events_per_second = Column(db.Integer, nullable=False, default=0)

    #: How the consumer reads, which is mostly about how it looks to the broker.
    #:
    #: **No name, the default, means the broker never sees a group at all.** The
    #: client insists on a `group.id`, so one is set -- but the consumer assigns
    #: itself every partition rather than joining, and commits nothing, so no
    #: group is ever registered. Until 0.7.3 it joined `sqldesk-stream-<id>` as
    #: a live member that never committed, which is precisely what lag
    #: monitoring alarms on.
    #:
    #: **A name joins that group**, for an install whose monitoring ignores
    #: consumers by prefix and wants to see ours under one.
    consumer_group = Column(db.String(249), nullable=True)
    #: Commit offsets as they are consumed, so a stream resumes where it
    #: stopped. Off by default, because a window is meant to be *now*; needs a
    #: consumer group to commit under.
    save_position = Column(db.Boolean, nullable=False, default=False)
    #: Where a stream begins when it starts from cold: `latest`, `earliest`, or
    #: `saved`. A hand-over from one job to the next carries its position
    #: across instead, so this does not replay a topic every few minutes.
    start_from = Column(db.String(16), nullable=False, default="latest")

    #: What the consumer last measured and decided. Read by the page and by the
    #: chart's "last 6 minutes · 4.9M events" line; written once a flush.
    observed_rate = Column(DOUBLE_PRECISION, nullable=False, default=0)
    window_seconds = Column(db.Integer, nullable=False, default=0)
    sample_rate = Column(db.Integer, nullable=False, default=1)
    rows = Column(db.BigInteger, nullable=False, default=0)
    #: Counted, never kept. A malformed message is worth a number on the page
    #: and nothing more; a consumer that stopped for one is a consumer somebody
    #: restarts at 3am.
    malformed = Column(db.BigInteger, nullable=False, default=0)

    #: The columns, as `[{"name": ..., "type": ...}]`, and whether a person has
    #: settled them.
    columns = Column(MutableList.as_mutable(JSONB), nullable=True)
    schema_state = Column(db.String(16), nullable=False, default=SCHEMA_INFERRED)

    #: The rollup: which columns to group by and what to measure. Empty means
    #: no rollup, which is a reasonable thing for a stream nobody charts over
    #: time.
    group_by = Column(MutableList.as_mutable(ARRAY(db.Unicode)), nullable=True)
    measures = Column(MutableList.as_mutable(JSONB), nullable=True)

    #: When something using this stream was last looked at. The consumer runs
    #: while this is recent, or while `pinned` is set.
    last_viewed_at = Column(db.DateTime(True), nullable=True)
    pinned = Column(db.Boolean, nullable=False, default=False)
    #: Set when the consumer stops for a reason that is not inactivity, so the
    #: page can say why rather than looking merely quiet.
    last_error = Column(db.Text, nullable=True)
    last_flush_at = Column(db.DateTime(True), nullable=True)

    __tablename__ = "streams"
    #: One row per topic per cluster. Unique on the pair rather than on the
    #: data source: a cluster has as many streams as it has enabled topics, and
    #: enabling the same topic twice is the mistake worth refusing.
    __table_args__ = (db.Index("streams_data_source_topic", "data_source_id", "topic", unique=True),)

    def __str__(self):
        return self.topic

    @property
    def budget(self):
        return self.row_budget or settings.STREAM_ROW_BUDGET

    @property
    def ceiling(self):
        return self.events_per_second or settings.STREAM_EVENTS_PER_SECOND

    @property
    def frozen(self):
        return self.schema_state == SCHEMA_FROZEN

    @property
    def sampled(self):
        return (self.sample_rate or 1) > 1

    def directory(self):
        """Where its DuckDB file lives: under the uploads sandbox, like an upload."""
        return os.path.join(settings.UPLOAD_ROOT, str(self.org_id), "streams")

    def store_path(self):
        return os.path.join(self.directory(), "stream-{}.duckdb".format(self.id))


class StreamRollup(TimestampMixin, db.Model):
    """
    One minute of one stream, per group.

    In Postgres rather than beside the raw events, because this is the part that
    outlives a restart and the part a question about this morning reads. It is
    small by construction -- 1,440 rows a day per group, and the group count is
    capped -- which is what makes keeping it in the application's own database
    reasonable where keeping the raw events there would not be.
    """

    id = primary_key("StreamRollup")
    stream_id = Column(key_type("Stream"), db.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False)
    stream = db.relationship(Stream, backref=db.backref("rollups", cascade="all, delete-orphan", lazy="dynamic"))
    minute = Column(db.DateTime(True), nullable=False)
    #: The group's values, in the stream's `group_by` order. A dict so a chart
    #: can name them, and because the columns are the stream's own.
    group_key = Column(JSONB, nullable=True)
    #: Whether this row is the capped tail rather than one group. Shown on the
    #: chart, never hidden: a total missing its tail is wrong while looking
    #: right.
    is_other = Column(db.Boolean, nullable=False, default=False)
    #: The measures, by name.
    values = Column(JSONB, nullable=True)
    #: What the stream was sampling at when this minute was rolled up, so a
    #: count can be scaled back up honestly -- and so a chart can say it is an
    #: estimate rather than quietly multiplying.
    sample_rate = Column(db.Integer, nullable=False, default=1)

    __tablename__ = "stream_rollups"
    __table_args__ = (db.Index("stream_rollups_stream_minute", "stream_id", "minute"),)


class SlackWorkspace(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    The Slack app an administrator installed, and its bot token.

    One per organisation, which is why `org_id` is unique: a second token for
    the same workspace would be two answers to "who are we posting as", and
    SQLDesk has nothing useful to do with the second one.

    The token is encrypted with the same key as a data source's credentials.
    It is exactly that kind of secret -- it posts as the app in every channel
    the app is in, and it does not expire -- so storing it in the
    organisation's JSONB settings, which every settings read hands back in
    plain text, would have been the wrong place by a wide margin.

    Why a bot token at all rather than a public link Slack previews: an install
    on a VPN is not reachable from Slack's servers, so a preview would show a
    bare URL. SQLDesk draws the picture and uploads it, and then nothing has to
    reach in.
    """

    id = primary_key("SlackWorkspace")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"), nullable=False)
    org = db.relationship(Organization, backref=db.backref("slack", uselist=False))
    bot_token = Column(
        "encrypted_bot_token",
        EncryptedType(db.Text, settings.DATASOURCE_SECRET_KEY, FernetEngine),
        nullable=False,
    )
    #: What Slack said the workspace and the app are called, so the settings
    #: page can show which workspace this is without another API call.
    team_name = Column(db.String(255), nullable=True)
    app_name = Column(db.String(255), nullable=True)
    installed_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    installed_by = db.relationship(User, foreign_keys=[installed_by_id])
    #: The last thing Slack refused, and when we last asked. A token that has
    #: been revoked in Slack looks identical to a working one from here until
    #: something is sent, so the failure is kept where somebody can see it
    #: rather than only in a worker's log.
    last_error = Column(db.Text, nullable=True)
    last_checked_at = Column(db.DateTime(True), nullable=True)

    __tablename__ = "slack_workspaces"
    __table_args__ = (db.Index("slack_workspaces_org_id", "org_id", unique=True),)

    def __str__(self):
        return self.team_name or "Slack"

    @property
    def working(self):
        return self.last_error is None


class OAuthClient(TimestampMixin, db.Model):
    """
    An MCP client that may ask a person for access.

    Public clients only: a desktop or CLI client cannot keep a secret, and the
    MCP specification says so plainly. What stands in for one is PKCE -- the
    client proves on the token request that it is the same software that
    started the flow -- which is why `code_challenge` is required rather than
    optional below.

    Not scoped to an organisation. The same client software is used by
    everybody, registration carries no authority on its own, and what a
    registration *can* reach is decided entirely by whose token it holds.
    """

    id = primary_key("OAuthClient")
    #: What the client calls itself at registration. Shown on the consent
    #: page, and therefore never trusted: anyone may register anything, so
    #: the page says the name is the client's own claim.
    name = Column(db.String(255), nullable=False)
    client_id = Column(db.String(48), unique=True, nullable=False)
    #: Where a code may be sent back. Exact string matching, no wildcards and
    #: no prefix rules: a loose redirect URI is how an authorization code is
    #: handed to somebody else.
    redirect_uris = Column(MutableList.as_mutable(ARRAY(db.Unicode)), nullable=False)
    client_uri = Column(db.String(1024), nullable=True)
    #: Where the registration came from, for an administrator reading the list.
    registered_from = Column(db.String(64), nullable=True)

    __tablename__ = "oauth_clients"

    def __str__(self):
        return self.name

    # --- the interface authlib's grants ask for -----------------------------

    def get_client_id(self):
        return self.client_id

    def get_default_redirect_uri(self):
        return self.redirect_uris[0] if self.redirect_uris else None

    def get_allowed_scope(self, scope):
        # One scope, and asking for anything else gets nothing rather than an
        # error: a client that asks for too much still works, read-only.
        requested = set((scope or "").split())
        return OAUTH_SCOPE if OAUTH_SCOPE in requested or not requested else ""

    def check_redirect_uri(self, redirect_uri):
        return redirect_uri in (self.redirect_uris or [])

    def check_client_secret(self, secret):
        # There is no secret. Saying so is not the same as accepting any.
        return False

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type == "code"

    def check_grant_type(self, grant_type):
        return grant_type in ("authorization_code", "refresh_token")


class OAuthAuthorizationCode(TimestampMixin, db.Model):
    """
    A code issued at the end of the consent page, exchanged once for a token.

    Hashed and single-use, like the tokens. Five minutes, which is the
    specification's recommendation and about as long as a redirect back to a
    waiting client can honestly take.
    """

    id = primary_key("OAuthAuthorizationCode")
    code_digest = Column(db.String(64), unique=True, nullable=False)
    client_id = Column(db.String(48), nullable=False)
    user_id = Column(key_type("User"), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = db.relationship(User)
    redirect_uri = Column(db.String(1024), nullable=True)
    scope = Column(db.String(255), nullable=True)
    #: PKCE. Required, not optional: without it an intercepted code can be
    #: spent by whoever intercepted it.
    code_challenge = Column(db.String(128), nullable=False)
    code_challenge_method = Column(db.String(10), nullable=False)
    expires_at = Column(db.DateTime(True), nullable=False)

    __tablename__ = "oauth_authorization_codes"

    def is_expired(self):
        return self.expires_at <= utcnow()

    def get_redirect_uri(self):
        return self.redirect_uri

    def get_scope(self):
        return self.scope or ""

    def get_nonce(self):
        # OpenID Connect only. We are not an identity provider.
        return None

    def get_auth_time(self):
        return None


class OAuthToken(TimestampMixin, db.Model):
    """
    A token a client holds on somebody's behalf.

    One row per grant rather than one per access token: refreshing replaces
    the pair in place, so "Connected apps" lists the connections a person has
    made and not a log of every hour since. Revoking is a column rather than a
    delete, so an administrator asking "did that client have access last
    Tuesday" has an answer.
    """

    id = primary_key("OAuthToken")
    client_id = Column(db.String(48), nullable=False)
    #: Carried for the audit and the admin list. A token's authority comes
    #: from the user, so this is never consulted to decide anything.
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"), nullable=False)
    org = db.relationship(Organization)
    user_id = Column(key_type("User"), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = db.relationship(User, backref=db.backref("oauth_tokens", cascade="all, delete-orphan"))
    access_token_digest = Column(db.String(64), unique=True, nullable=False)
    refresh_token_digest = Column(db.String(64), unique=True, nullable=True)
    scope = Column(db.String(255), nullable=True)
    access_expires_at = Column(db.DateTime(True), nullable=False)
    refresh_expires_at = Column(db.DateTime(True), nullable=True)
    revoked_at = Column(db.DateTime(True), nullable=True)
    #: So a person can tell a client they still use from one they forgot.
    #: Written at most once a minute; see sqldesk.oauth.
    last_used_at = Column(db.DateTime(True), nullable=True)

    __tablename__ = "oauth_tokens"

    # --- the interface authlib asks for -------------------------------------

    def get_client_id(self):
        return self.client_id

    def check_client(self, client):
        """
        Whether this token belongs to the client presenting it.

        Asked on a refresh, and it is the check that stops one registered
        client refreshing another's token -- registration is open, so without
        it anybody could register a client and extend somebody else's grant
        with a refresh token they got hold of.
        """
        return self.client_id == client.get_client_id()

    def get_scope(self):
        return self.scope or ""

    def get_expires_in(self):
        return OAUTH_ACCESS_TOKEN_SECONDS

    def is_expired(self):
        return self.access_expires_at <= utcnow()

    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def refresh_token_expired(self):
        return self.refresh_expires_at is not None and self.refresh_expires_at <= utcnow()

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = utcnow()


class McpEvent(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    One thing an MCP client asked for, and what happened.

    Written for every request including the refused ones. An audit that only
    records what succeeded answers "what did this work do" and not "who has
    been trying", and the second question is the one somebody asks at two in
    the morning.

    Arguments are summarised rather than stored whole: a question is worth
    keeping and a megabyte of SQL is not, and neither is anything a caller
    chose to put in a field we did not design.
    """

    id = primary_key("McpEvent")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="mcp_events")
    #: Null for a request that was refused before anyone was identified --
    #: which is exactly the row worth having.
    user_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    user = db.relationship(User, backref="mcp_events")

    #: The client's session, issued at initialize. Lets "who is connected"
    #: mean something on a transport that holds no connection open.
    session_id = Column(db.String(64), nullable=True)
    client = Column(db.String(255), nullable=True)
    method = Column(db.String(64))
    tool = Column(db.String(64), nullable=True)
    #: ok | error | refused
    outcome = Column(db.String(16))
    detail = Column(db.String(1024), nullable=True)
    duration_ms = Column(db.Integer, nullable=True)
    remote_addr = Column(db.String(64), nullable=True)

    __tablename__ = "mcp_events"
    __table_args__ = (
        # Every read of this table is "the most recent, for this org", and it
        # is the fastest-growing thing 0.6 adds.
        db.Index("ix_mcp_events_org_created_at", "org_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "at": self.created_at,
            "user": self.user.name if self.user else None,
            "user_email": self.user.email if self.user else None,
            "session_id": self.session_id,
            "client": self.client,
            "method": self.method,
            "tool": self.tool,
            "outcome": self.outcome,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
            "remote_addr": self.remote_addr,
        }


class CatalogTable(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    What we know about one table, kept somewhere we can rank it.

    Today's schema cache is a JSON blob in Redis with a TTL: you cannot search
    it, join against it, or ask which tables are used together. This is that
    knowledge in a shape those questions can be asked of.

    A derived index, not a system of record. Every row can be dropped and
    rebuilt from the data source and the query log, and nothing here is typed
    in by a person -- the moment it is, this becomes a catalog product that
    has to be migrated rather than a cache that can be thrown away.
    """

    id = primary_key("CatalogTable")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="catalog_tables")
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(DataSource, backref=db.backref("catalog_tables", cascade="all, delete-orphan"))

    name = Column(db.String(1024))
    #: Whatever the source told us that does not fit in a column of its own --
    #: partition spec, sort order, file counts. Shapes differ per engine and
    #: pretending otherwise would mean a migration per engine.
    properties = Column(MutableDict.as_mutable(JSONB), default={})
    #: How many saved queries mention it. The single most useful ranking
    #: signal there is, and it costs a parse of things already stored.
    usage_count = Column(db.Integer, default=0)
    #: What this table is *for*, in words. Structure comes from the engine and
    #: usage comes from the query log, but neither says what a table means,
    #: and meaning is the thing a model most needs and least can guess.
    description = Column(db.Text, nullable=True)
    #: Where that sentence came from: "engine" for a comment the warehouse
    #: already carried, "human" for one somebody wrote here. Harvesting must
    #: never overwrite a human's words with an engine's silence, and without
    #: recording the origin there is no way to tell the two apart.
    description_source = Column(db.String(16), nullable=True)
    #: The compact text handed to a model, built at harvest rather than per
    #: request so assembling a prompt is concatenation.
    card = Column(db.Text, nullable=True)
    harvested_at = Column(db.DateTime(True), nullable=True)
    #: Kept out of the catalog page and out of what MCP offers a model, because
    #: nobody needs it -- a Mimir cluster has hundreds of metrics, and a list of
    #: them is noise to a person and to an agent alike. Not access control: the
    #: table can still be queried, and still be asked for by name. Survives a
    #: harvest, which updates rows in place.
    hidden = Column(db.Boolean, nullable=False, default=False)

    __tablename__ = "catalog_tables"
    __table_args__ = (db.Index("ix_catalog_tables_source_name", "data_source_id", "name", unique=True),)

    def __str__(self):
        return self.name


class CatalogColumn(TimestampMixin, db.Model):
    id = primary_key("CatalogColumn")
    catalog_table_id = Column(key_type("CatalogTable"), db.ForeignKey("catalog_tables.id"))
    catalog_table = db.relationship(
        CatalogTable, backref=db.backref("columns", cascade="all, delete-orphan", lazy="dynamic")
    )

    name = Column(db.String(1024))
    type = Column(db.String(255), nullable=True)
    #: What the column means. `status` is guessable; `flag_c2` is not, and no
    #: amount of usage data makes it so.
    description = Column(db.Text, nullable=True)
    description_source = Column(db.String(16), nullable=True)
    #: How often anyone selects or filters on it. A 300-column table usually
    #: has twenty columns anyone touches, and this is how the other 280 are
    #: kept out of a prompt.
    usage_count = Column(db.Integer, default=0)

    __tablename__ = "catalog_columns"
    __table_args__ = (db.Index("ix_catalog_columns_table_name", "catalog_table_id", "name", unique=True),)

    def __str__(self):
        return "{}.{}".format(self.catalog_table.name, self.name)


MEASURE_PROPOSED = "proposed"
MEASURE_APPROVED = "approved"
MEASURE_DENIED = "denied"
MEASURE_STATUSES = (MEASURE_PROPOSED, MEASURE_APPROVED, MEASURE_DENIED)


class CatalogMeasure(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A number somebody already computes, proposed as a metric.

    Mined from saved SQL rather than declared: `SUM(amount) AS gross_revenue`
    is a person telling us what that number is called, and a warehouse's
    dashboards are full of such statements. It is the one part of a semantic
    layer that can be found rather than asked for.

    Proposed, not true. Nothing reaches a model or an export until somebody
    says it is right -- a metric definition that is merely plausible is worse
    than none, because the wrong revenue number is still a revenue number.
    """

    id = primary_key("CatalogMeasure")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization)
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(DataSource)

    table_name = Column(db.String(1024))
    #: The alias the author used where there was one, so `gross_revenue`
    #: rather than `sum_amount`.
    name = Column(db.String(255))
    #: sum, count, avg, min, max -- the words cube uses for the same thing.
    kind = Column(db.String(32))
    column_name = Column(db.String(1024))
    #: How many distinct saved queries compute it this way. A definition four
    #: teams wrote independently is a different proposition from one somebody
    #: tried once.
    usage_count = Column(db.Integer, default=0)
    #: proposed -> approved, or proposed -> denied. Three states rather than
    #: an `approved` flag, because "nobody has looked at this yet" and "we
    #: looked and it is wrong" are different answers and only one of them
    #: should keep reappearing on somebody's worklist. A harvest never
    #: changes this: what the SQL says is the harvest's business, what the
    #: organisation stands behind is not.
    status = Column(db.String(16), default=MEASURE_PROPOSED, nullable=False)
    description = Column(db.Text, nullable=True)

    @property
    def approved(self):
        return self.status == MEASURE_APPROVED

    __tablename__ = "catalog_measures"
    __table_args__ = (
        db.Index(
            "catalog_measures_source_table_name",
            "data_source_id",
            "table_name",
            "name",
            unique=True,
        ),
    )


class CatalogVerifiedQuery(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A saved query a curator says is the right answer to a question.

    The strongest thing a catalog can offer. A measure says what a number
    means; a verified query says "this whole question, including which rows
    to exclude and which join is the right one, has been answered correctly,
    and a person checked". Nothing a schema contains comes close.

    Verification is of *particular SQL*, which is why `query_hash` is stored
    alongside. A curator who verifies query #42 is making a claim about the
    text they read. If somebody then edits it, the claim is about SQL that no
    longer exists -- so the record stays, saying when it was made and about
    what, and stops counting as verified until a person looks again. An
    editable "verified" badge is worse than no badge: it is a claim with
    nobody behind it.

    `question` is the question in the curator's words, which is often not the
    query's name. Names drift towards the technical ("daily_active_v3"); the
    question is what somebody would type.
    """

    id = primary_key("CatalogVerifiedQuery")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="verified_queries")
    query_id = Column(key_type("Query"), db.ForeignKey("queries.id", ondelete="CASCADE"))
    query_rel = db.relationship("Query", backref=db.backref("verification", uselist=False, cascade="all, delete"))
    verified_by_id = Column(key_type("User"), db.ForeignKey("users.id"))
    verified_by = db.relationship(User, foreign_keys=[verified_by_id])
    verified_at = Column(db.DateTime(True), default=db.func.now(), nullable=False)
    #: The query's hash when a person read it and said yes. Compared, never
    #: trusted on its own.
    query_hash = Column(db.String(32), nullable=False)
    question = Column(db.Text, nullable=True)
    note = Column(db.Text, nullable=True)

    __tablename__ = "catalog_verified_queries"
    __table_args__ = (db.Index("catalog_verified_queries_query_id", "query_id", unique=True),)

    @property
    def still_current(self):
        """Whether the SQL is the SQL that was verified."""
        return self.query_rel is not None and self.query_rel.query_hash == self.query_hash


class CatalogRelationship(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A join somebody actually wrote, and how often.

    Mined rather than declared: a warehouse rarely has foreign keys, and
    nobody is going to fill in a modelling tool. What people join on is
    already written down in the queries they saved.
    """

    id = primary_key("CatalogRelationship")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="catalog_relationships")
    data_source_id = Column(key_type("DataSource"), db.ForeignKey("data_sources.id"))
    data_source = db.relationship(
        DataSource, backref=db.backref("catalog_relationships", cascade="all, delete-orphan")
    )

    left_table = Column(db.String(1024))
    left_column = Column(db.String(1024))
    right_table = Column(db.String(1024))
    right_column = Column(db.String(1024))
    #: How many distinct saved queries join this way. Confidence is a count,
    #: not a score: a number somebody can check beats one they have to trust.
    observed_count = Column(db.Integer, default=0)

    __tablename__ = "catalog_relationships"
    __table_args__ = (
        db.Index(
            "ix_catalog_relationships_edge",
            "data_source_id",
            "left_table",
            "left_column",
            "right_table",
            "right_column",
            unique=True,
        ),
    )

    def __str__(self):
        return "{}.{} = {}.{}".format(self.left_table, self.left_column, self.right_table, self.right_column)


@generic_repr("id", "visualization_id", "dashboard_id")
class Widget(TimestampMixin, BelongsToOrgMixin, db.Model):
    id = primary_key("Widget")
    visualization_id = Column(key_type("Visualization"), db.ForeignKey("visualizations.id"), nullable=True)
    visualization = db.relationship(Visualization, backref=backref("widgets", cascade="delete"))
    text = Column(db.Text, nullable=True)
    width = Column(db.Integer)
    options = Column(MutableDict.as_mutable(JSONB), default={})
    dashboard_id = Column(key_type("Dashboard"), db.ForeignKey("dashboards.id"), index=True)

    __tablename__ = "widgets"

    def __str__(self):
        return "%s" % self.id

    @classmethod
    def get_by_id_and_org(cls, object_id, org):
        return super(Widget, cls).get_by_id_and_org(object_id, org, Dashboard)

    def copy(self, dashboard_id):
        return {
            "options": self.options,
            "width": self.width,
            "text": self.text,
            "visualization_id": self.visualization_id,
            "dashboard_id": dashboard_id,
        }


@generic_repr("id", "object_type", "object_id", "action", "user_id", "org_id", "created_at")
class Event(db.Model):
    id = primary_key("Event")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, back_populates="events")
    user_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    user = db.relationship(User, backref="events")
    action = Column(db.String(255))
    object_type = Column(db.String(255))
    object_id = Column(db.String(255), nullable=True)
    additional_properties = Column(MutableDict.as_mutable(JSONB), nullable=True, default={})
    created_at = Column(db.DateTime(True), default=db.func.now())

    __tablename__ = "events"
    # This table gets a row every time anyone runs a query and had no index
    # but its primary key. The admin overview asks it who has been running
    # queries in the last hour, which is exactly this: one organization, one
    # kind of event, a window of time.
    __table_args__ = (db.Index("ix_events_org_action_created_at", "org_id", "action", "created_at"),)

    def __str__(self):
        return "%s,%s,%s,%s" % (
            self.user_id,
            self.action,
            self.object_type,
            self.object_id,
        )

    def to_dict(self):
        return {
            "org_id": self.org_id,
            "user_id": self.user_id,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "additional_properties": self.additional_properties,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def record(cls, event):
        org_id = event.pop("org_id")
        user_id = event.pop("user_id", None)
        action = event.pop("action")
        object_type = event.pop("object_type")
        object_id = event.pop("object_id", None)

        created_at = datetime.datetime.utcfromtimestamp(event.pop("timestamp"))

        event = cls(
            org_id=org_id,
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            additional_properties=event,
            created_at=created_at,
        )
        db.session.add(event)
        return event


@generic_repr("id", "created_by_id", "org_id", "active")
class ApiKey(TimestampMixin, GFKBase, db.Model):
    id = primary_key("ApiKey")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization)
    api_key = Column(db.String(255), index=True, default=lambda: generate_token(40))
    active = Column(db.Boolean, default=True)
    # 'object' provided by GFKBase
    object_id = Column(key_type("ApiKey"))
    created_by_id = Column(key_type("User"), db.ForeignKey("users.id"), nullable=True)
    created_by = db.relationship(User)

    __tablename__ = "api_keys"
    __table_args__ = (db.Index("api_keys_object_type_object_id", "object_type", "object_id"),)

    @classmethod
    def get_by_api_key(cls, api_key, org=None):
        """A token is good in the organization that issued it, and no other."""
        found = cls.query.filter(cls.api_key == api_key, cls.active.is_(True))
        if org is not None:
            found = found.filter(cls.org == org)
        return found.one()

    @classmethod
    def get_by_object(cls, object):
        return cls.query.filter(
            cls.object_type == object.__class__.__tablename__,
            cls.object_id == object.id,
            cls.active.is_(True),
        ).first()

    @classmethod
    def create_for_object(cls, object, user):
        k = cls(org=user.org, object=object, created_by=user)
        db.session.add(k)
        return k


@generic_repr("id", "name", "type", "user_id", "org_id", "created_at")
class NotificationDestination(BelongsToOrgMixin, db.Model):
    id = primary_key("NotificationDestination")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="notification_destinations")
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, backref="notification_destinations")
    name = Column(db.String(255))
    type = Column(db.String(255))
    options = Column(
        "encrypted_options",
        ConfigurationContainer.as_mutable(
            EncryptedConfiguration(db.Text, settings.DATASOURCE_SECRET_KEY, FernetEngine)
        ),
    )
    created_at = Column(db.DateTime(True), default=db.func.now())

    __tablename__ = "notification_destinations"
    __table_args__ = (db.Index("notification_destinations_org_id_name", "org_id", "name", unique=True),)

    def __str__(self):
        return str(self.name)

    def to_dict(self, all=False):
        d = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "icon": self.destination.icon(),
        }

        if all:
            schema = get_configuration_schema_for_destination_type(self.type)
            self.options.set_schema(schema)
            d["options"] = self.options.to_dict(mask_secrets=True)

        return d

    @property
    def destination(self):
        return get_destination(self.type, self.options)

    @classmethod
    def all(cls, org):
        notification_destinations = cls.query.filter(cls.org == org).order_by(cls.id.asc())

        return notification_destinations

    def notify(self, alert, query, user, new_state, app, host, metadata):
        schema = get_configuration_schema_for_destination_type(self.type)
        self.options.set_schema(schema)
        return self.destination.notify(alert, query, user, new_state, app, host, metadata, self.options)


@generic_repr("id", "dashboard_id", "user_id", "format", "active")
class DashboardSubscription(TimestampMixin, BelongsToOrgMixin, db.Model):
    """
    A dashboard, mailed to some people, on a schedule.

    Named for the dashboard because `Alert.subscriptions` is already something
    else -- who hears about an alert. These two have nothing to do with each
    other and sharing a word would cost somebody an afternoon.

    What it sends is the latest stored results, and the email says how old
    they are. Refreshing every query first would turn a subscription into a
    warehouse bill nobody asked for; an owner who wants fresh numbers gives
    the queries a schedule.
    """

    PNG = "png"
    PDF = "pdf"
    FORMATS = (PNG, PDF)

    id = primary_key("DashboardSubscription")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="dashboard_subscriptions")

    dashboard_id = Column(key_type("Dashboard"), db.ForeignKey("dashboards.id"))
    dashboard = db.relationship(Dashboard, backref=backref("subscriptions", cascade="all, delete-orphan"))

    #: Whose sight of the dashboard this is. The picture is rendered as them,
    #: and it stops being sent if they lose access.
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, backref="dashboard_subscriptions")

    #: The same shape a query's schedule has -- interval, time, day_of_week --
    #: so the two are described the same way in the interface and answered by
    #: the same `should_schedule_next`.
    schedule = Column(MutableDict.as_mutable(JSONB), nullable=True)

    format = Column(db.String(10), default=PNG)

    #: User ids, never addresses: a subscription that could name an address
    #: would be a way to mail a dashboard's contents anywhere. Stored as a
    #: list rather than a join table because the only question ever asked of
    #: it is "who, now" -- and that has to be re-answered at send time anyway,
    #: since access changes and people leave.
    recipient_ids = Column(MutableList.as_mutable(JSONB), default=list)

    active = Column(db.Boolean, default=True, nullable=False)
    last_sent_at = Column(db.DateTime(True), nullable=True)

    #: Why the last send did not happen, shown to the owner. Cleared by a send
    #: that works, so it never describes a problem that has gone away.
    last_error = Column(db.Text, nullable=True)

    __tablename__ = "dashboard_subscriptions"

    def __str__(self):
        return "%s: %s" % (self.id, self.dashboard_id)

    @classmethod
    def all(cls, org):
        return cls.query.filter(cls.org == org)

    @classmethod
    def for_dashboard(cls, dashboard):
        return cls.query.filter(cls.dashboard_id == dashboard.id).order_by(cls.id)

    def recipients(self):
        """
        The people who would be mailed, as they are now.

        Resolved rather than stored, so somebody deleted or disabled since
        simply stops being one. Whether each may *see* the dashboard is a
        separate question, asked at send time by the sender -- this is only
        who was asked for.
        """
        if not self.recipient_ids:
            return []
        return (
            User.query.filter(
                User.id.in_(self.recipient_ids),
                User.org_id == self.org_id,
            )
            .order_by(User.id)
            .all()
        )


@generic_repr("id", "user_id", "destination_id", "alert_id")
class AlertSubscription(TimestampMixin, db.Model):
    id = primary_key("AlertSubscription")
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User)
    destination_id = Column(
        key_type("NotificationDestination"), db.ForeignKey("notification_destinations.id"), nullable=True
    )
    destination = db.relationship(NotificationDestination)
    alert_id = Column(key_type("Alert"), db.ForeignKey("alerts.id"))
    alert = db.relationship(Alert, back_populates="subscriptions")

    __tablename__ = "alert_subscriptions"
    __table_args__ = (
        db.Index(
            "alert_subscriptions_destination_id_alert_id",
            "destination_id",
            "alert_id",
            unique=True,
        ),
    )

    def to_dict(self):
        d = {"id": self.id, "user": self.user.to_dict(), "alert_id": self.alert_id}

        if self.destination:
            d["destination"] = self.destination.to_dict()

        return d

    @classmethod
    def all(cls, alert_id):
        return AlertSubscription.query.join(User).filter(AlertSubscription.alert_id == alert_id)

    def notify(self, alert, query, user, new_state, app, host, metadata):
        if self.destination:
            return self.destination.notify(alert, query, user, new_state, app, host, metadata)
        else:
            # User email subscription, so create an email destination object
            config = {"addresses": self.user.email}
            schema = get_configuration_schema_for_destination_type("email")
            options = ConfigurationContainer(config, schema)
            destination = get_destination("email", options)
            return destination.notify(alert, query, user, new_state, app, host, metadata, options)


@generic_repr("id", "trigger", "user_id", "org_id")
class QuerySnippet(TimestampMixin, db.Model, BelongsToOrgMixin):
    id = primary_key("QuerySnippet")
    org_id = Column(key_type("Organization"), db.ForeignKey("organizations.id"))
    org = db.relationship(Organization, backref="query_snippets")
    trigger = Column(db.String(255), unique=True)
    description = Column(db.Text)
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship(User, backref="query_snippets")
    snippet = Column(db.Text)

    __tablename__ = "query_snippets"

    @classmethod
    def all(cls, org):
        return cls.query.filter(cls.org == org)

    def to_dict(self):
        d = {
            "id": self.id,
            "trigger": self.trigger,
            "description": self.description,
            "snippet": self.snippet,
            "user": self.user.to_dict(),
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

        return d


def init_db():
    default_org = Organization(name="Default", slug="default", settings={})
    admin_group = Group(
        name="admin",
        permissions=Group.ADMIN_PERMISSIONS,
        org=default_org,
        type=Group.BUILTIN_GROUP,
    )
    default_group = Group(
        name="default",
        permissions=Group.DEFAULT_PERMISSIONS,
        org=default_org,
        type=Group.BUILTIN_GROUP,
    )

    db.session.add_all([default_org, admin_group, default_group])
    # XXX remove after fixing User.group_ids
    db.session.commit()
    return default_org, admin_group, default_group


def streaming_source_types():
    """
    The data source types whose tables are windows rather than tables.

    Asked of the registered runners rather than hard-coded, so a second
    streaming connector needs no second list to be remembered.
    """
    from sqldesk.query_runner import query_runners

    return [name for name, runner in query_runners.items() if getattr(runner, "streams_only", False)] or ["__none__"]

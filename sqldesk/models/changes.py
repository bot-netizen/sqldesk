from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.inspection import inspect
from sqlalchemy_utils.models import generic_repr

from .base import Column, GFKBase, db, key_type, primary_key


@generic_repr("id", "object_type", "object_id", "created_at")
class Change(GFKBase, db.Model):
    id = primary_key("Change")
    # 'object' defined in GFKBase
    object_id = Column(key_type("Change"))
    object_version = Column(db.Integer, default=0)
    user_id = Column(key_type("User"), db.ForeignKey("users.id"))
    user = db.relationship("User", backref="changes")
    change = Column(JSONB)
    created_at = Column(db.DateTime(True), default=db.func.now())

    __tablename__ = "changes"
    #: What the history endpoint asks for: this object's changes, newest
    #: first. Nothing was indexed at all, so every version history scanned
    #: every change ever recorded.
    __table_args__ = (db.Index("ix_changes_object_id_desc", "object_type", "object_id", db.text("id DESC")),)

    def to_dict(self, full=True):
        d = {
            "id": self.id,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "change_type": self.change_type,
            "object_version": self.object_version,
            "change": self.change,
            "created_at": self.created_at,
        }

        if full:
            d["user"] = self.user.to_dict()
        else:
            d["user_id"] = self.user_id

        return d

    @classmethod
    def last_change(cls, obj):
        """
        The most recent record for this object.

        Ordered by id as well as by version, and the id is what actually
        decides it: `object_version` comes from the object's own `version`
        column, which is there for optimistic locking and does **not** move
        when a query is edited. Every record for a query therefore says version
        1, and ordering by version alone returned whichever row the database
        felt like -- in practice the oldest, so "last_change" meant "the record
        of its creation".
        """
        return (
            cls.query.filter(cls.object_id == obj.id, cls.object_type == obj.__class__.__tablename__)
            .order_by(cls.object_version.desc(), cls.id.desc())
            .first()
        )


class ChangeTrackingMixin:
    skipped_fields = ("id", "created_at", "updated_at", "version")
    _clean_values = None

    def __init__(self, *a, **kw):
        super(ChangeTrackingMixin, self).__init__(*a, **kw)
        self.record_changes(self.user)

    def prep_cleanvalues(self):
        """
        Remember what every column says now, before anything changes it.

        Once per edit, not once per assignment, and that is the whole of the
        fix: an earlier version re-read every column inside `__setattr__`, so
        setting a second field overwrote the first field's "previous" with the
        value it had just been given. A change record saying a name went from
        its new value to its new value is worse than no record, because it
        looks like one.
        """
        values = {}
        for attr in inspect(self.__class__).column_attrs:
            (col,) = attr.columns
            # 'query' is col name but not attr name
            values[col.name] = getattr(self, attr.key, None)
        self.__dict__["_clean_values"] = values

    def __setattr__(self, key, value):
        if self._clean_values is None:
            self.prep_cleanvalues()

        super(ChangeTrackingMixin, self).__setattr__(key, value)

    def pending_changes(self):
        """
        The tracked fields that differ from what they said at the last record.

        For a caller deciding whether there is anything to record at all. A
        save that changed nothing -- the editor sends the whole query whether
        or not anything in it moved -- should not leave a version behind that
        says nothing happened.
        """
        if self._clean_values is None:
            return {}
        return {name: pair for name, pair in self._changes().items() if pair["previous"] != pair["current"]}

    def _changes(self):
        if self._clean_values is None:
            self.prep_cleanvalues()
        changes = {}
        for attr in inspect(self.__class__).column_attrs:
            (col,) = attr.columns
            if attr.key not in self.skipped_fields:
                changes[col.name] = {
                    "previous": self._clean_values[col.name],
                    "current": getattr(self, attr.key),
                }
        return changes

    def record_changes(self, changed_by):
        """
        Write one version of this object.

        Every tracked field, not only the ones that moved: a record that holds
        the whole of what the object said is a version somebody can be shown
        and restore, where a record of the differences alone can only be read
        by replaying every record before it.
        """
        db.session.add(self)
        db.session.flush()
        changes = self._changes()

        db.session.add(
            Change(
                object=self,
                object_version=self.version,
                user=changed_by,
                change=changes,
            )
        )
        # The next edit is a new version, measured from what the object says
        # now rather than from whatever it said before this one.
        self.__dict__["_clean_values"] = None

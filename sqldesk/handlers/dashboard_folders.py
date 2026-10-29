"""
Folders for dashboards, and the lock that makes one mean something.

A folder says what belongs in it. A **locked** folder is one only
administrators can change: the dashboards inside it cannot be edited, renamed,
archived or have a widget added by anybody else, including whoever made them.
That rule lives in `permissions.can_modify`, where every one of those four
paths already goes, rather than in these handlers -- a lock that covered three
of the four would be worse than no lock.

What is here is the folders themselves, and moving a dashboard between them,
which is the one act the lock cannot be enforced from the other side: taking a
dashboard *out* of a locked folder has to be an administrator's decision too,
or the lock is a doorway with a sign on it.
"""

import logging

from flask import request
from flask_restful import abort

from sqldesk import models
from sqldesk.handlers.base import BaseResource, get_object_or_404, require_fields
from sqldesk.permissions import require_admin, require_object_modify_permission

logger = logging.getLogger(__name__)

MAX_NAME = 100


def _counts(org, user):
    """How many dashboards each folder holds that this person may see."""
    rows = (
        models.db.session.query(models.Dashboard.folder_id, models.db.func.count(models.Dashboard.id))
        .filter(
            models.Dashboard.org == org,
            models.Dashboard.folder_id.isnot(None),
            models.Dashboard.is_archived.is_(False),
        )
        .group_by(models.Dashboard.folder_id)
        .all()
    )
    return dict(rows)


class DashboardFolderListResource(BaseResource):
    def get(self):
        """
        Every folder, with what it means and how much is in it.

        `?in_menu=true` asks only for the ones chosen for the Dashboards menu,
        which is what the navbar fetches: an install with thirty folders has a
        dropdown nobody reads, and the folders page is where the rest live.

        Readable by anybody: the point of a folder is that people can find what
        is in it, and a locked one is about who may *change* it rather than who
        may see it.
        """
        counts = _counts(self.current_org, self.current_user)
        query = models.DashboardFolder.query.filter(models.DashboardFolder.org == self.current_org)
        if (request.args.get("in_menu") or "").lower() in ("1", "true", "yes"):
            query = query.filter(models.DashboardFolder.in_menu.is_(True))
        folders = query.order_by(models.DashboardFolder.name).all()
        return [folder.to_dict(counts=counts.get(folder.id, 0)) for folder in folders]

    @require_admin
    def post(self):
        """Make one. An administrator's act, because a folder is a statement."""
        body = request.get_json(force=True, silent=True) or {}
        require_fields(body, ("name",))
        name = (body.get("name") or "").strip()
        if not name or len(name) > MAX_NAME:
            abort(400, message="A folder needs a name, of at most {} characters.".format(MAX_NAME))
        if models.DashboardFolder.query.filter(
            models.DashboardFolder.org == self.current_org, models.DashboardFolder.name == name
        ).first():
            abort(400, message="There is already a folder called {!r}.".format(name))

        folder = models.DashboardFolder(
            org=self.current_org,
            name=name,
            meaning=(body.get("meaning") or "").strip() or None,
            locked=bool(body.get("locked")),
            in_menu=bool(body.get("in_menu")),
            created_by=self.current_user,
        )
        models.db.session.add(folder)
        models.db.session.commit()
        self.record_event({"action": "create", "object_id": folder.id, "object_type": "dashboard_folder"})
        return folder.to_dict(counts=0)


class DashboardFolderResource(BaseResource):
    def _folder(self, folder_id):
        folder = get_object_or_404(models.DashboardFolder.query.get, folder_id)
        if folder.org_id != self.current_org.id:
            abort(404, message="No such folder.")
        return folder

    @require_admin
    def post(self, folder_id):
        folder = self._folder(folder_id)
        body = request.get_json(force=True, silent=True) or {}
        if "name" in body:
            name = (body["name"] or "").strip()
            if not name or len(name) > MAX_NAME:
                abort(400, message="A folder needs a name, of at most {} characters.".format(MAX_NAME))
            folder.name = name
        if "meaning" in body:
            folder.meaning = (body["meaning"] or "").strip() or None
        if "locked" in body:
            folder.locked = bool(body["locked"])
        if "in_menu" in body:
            folder.in_menu = bool(body["in_menu"])
        models.db.session.commit()
        self.record_event({"action": "edit", "object_id": folder.id, "object_type": "dashboard_folder"})
        return folder.to_dict(counts=_counts(self.current_org, self.current_user).get(folder.id, 0))

    @require_admin
    def delete(self, folder_id):
        folder = self._folder(folder_id)
        # Archived dashboards do not count: the page shows the folder as empty
        # and nothing lists archived dashboards to move them out, so a folder
        # holding only those could never be deleted. They are unfiled with it.
        held = models.Dashboard.query.filter(
            models.Dashboard.folder_id == folder.id, models.Dashboard.is_archived.is_(False)
        ).count()
        if held:
            # Rather than quietly unfiling them. Deleting a folder that holds a
            # set somebody curated should be a decision about those dashboards,
            # taken with them in front of you.
            abort(
                400,
                message="That folder still holds {} dashboard{}. Move them out first.".format(
                    held, "" if held == 1 else "s"
                ),
            )
        # The archived ones it still holds are unfiled first, straight on the
        # rows so none of them gets a new version for it.
        models.db.session.execute(
            models.Dashboard.__table__.update().where(models.Dashboard.folder_id == folder.id).values(folder_id=None)
        )
        models.db.session.delete(folder)
        models.db.session.commit()
        self.record_event({"action": "delete", "object_id": folder_id, "object_type": "dashboard_folder"})
        return {"ok": True}


class DashboardFolderAssignmentResource(BaseResource):
    """
    Filing a dashboard, and taking it out again.

    The one act the lock cannot be enforced from the other side. Putting a
    dashboard into a locked folder, and taking one out of it, are both
    administrators' decisions -- otherwise anybody could remove a dashboard
    from the folder that protects it, change it, and put it back, and the lock
    would be a doorway with a sign on it.
    """

    def post(self, dashboard_id):
        dashboard = get_object_or_404(models.Dashboard.get_by_id_and_org, dashboard_id, self.current_org)
        body = request.get_json(force=True, silent=True) or {}
        folder_id = body.get("folder_id")

        was = dashboard.folder
        target = None
        if folder_id is not None:
            target = get_object_or_404(models.DashboardFolder.query.get, folder_id)
            if target.org_id != self.current_org.id:
                abort(404, message="No such folder.")

        admin = self.current_user.has_permission("admin")
        if (was is not None and was.locked) or (target is not None and target.locked):
            if not admin:
                abort(403, message="Only an administrator moves a dashboard in or out of a locked folder.")
        else:
            require_object_modify_permission(dashboard, self.current_user)

        # Without a new version, so whoever is editing it is not told their
        # save conflicts with a move they cannot see.
        from sqldesk.handlers.dashboards import _write_without_a_new_version

        _write_without_a_new_version(dashboard, folder_id=target.id if target else None)
        self.record_event(
            {
                "action": "move_to_folder",
                "object_id": dashboard.id,
                "object_type": "dashboard",
                "params": {
                    "from": was.name if was else None,
                    "to": target.name if target else None,
                },
            }
        )
        return {"folder_id": target.id if target else None, "folder": target.to_dict() if target else None}

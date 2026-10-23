import functools

from flask_login import current_user
from flask_restful import abort
from funcy import flatten

view_only = True
not_view_only = False

ACCESS_TYPE_VIEW = "view"
ACCESS_TYPE_MODIFY = "modify"
ACCESS_TYPE_DELETE = "delete"

ACCESS_TYPES = (ACCESS_TYPE_VIEW, ACCESS_TYPE_MODIFY, ACCESS_TYPE_DELETE)


def has_access(obj, user, need_view_only):
    if getattr(user, "is_render_pass", False):
        # Imported here rather than at the top: render_pass reaches models,
        # and models reaches this.
        from sqldesk import render_pass

        return render_pass.allows(obj, user, need_view_only)

    if hasattr(obj, "api_key") and user.is_api_user():
        return has_access_to_object(obj, user.id, need_view_only)
    else:
        return has_access_to_groups(obj, user, need_view_only)


def has_access_to_object(obj, api_key, need_view_only):
    if obj.api_key == api_key:
        return need_view_only
    elif hasattr(obj, "dashboard_api_keys"):
        # check if api_key belongs to a dashboard containing this query
        return api_key in obj.dashboard_api_keys and need_view_only
    else:
        return False


def has_access_to_groups(obj, user, need_view_only):
    groups = obj.groups if hasattr(obj, "groups") else obj

    if "admin" in user.permissions:
        return True

    matching_groups = set(groups.keys()).intersection(user.group_ids)

    if not matching_groups:
        return False

    required_level = 1 if need_view_only else 2

    group_level = 1 if all(flatten([groups[group] for group in matching_groups])) else 2

    return required_level <= group_level


def require_access(obj, user, need_view_only):
    if not has_access(obj, user, need_view_only):
        abort(403)


def can_see_dashboard(dashboard_id, org, user):
    """
    Whether this person may see this dashboard at all.

    Not `has_access`, which reads `obj.groups` -- a Dashboard has none. What
    decides it is whether the dashboard appears in the list this person is
    shown, which `Dashboard.all` already works out from the data sources behind
    its widgets. Here rather than beside one of the features that asks, because
    two now do: subscribing somebody to a dashboard and sending one to Slack
    are both "may you hand its contents to other people", and the answer has to
    be the same.
    """
    # Imported here: models reaches this module.
    from sqldesk import models

    return (
        user.has_permission("admin")
        or models.Dashboard.all(org, user.group_ids, user.id).filter(models.Dashboard.id == dashboard_id).count() > 0
    )


def sees_all_of_dashboard(dashboard, user):
    """
    Whether this person may see *everything* on this dashboard.

    Stricter than `can_see_dashboard`, which is true when the data source
    behind any one widget is theirs -- the dashboard is listed for them, and
    the widgets they cannot read show as locked panels. A picture drawn as one
    person and handed to another has no locked panels: whatever the drawer can
    read is in it. So anybody receiving one has to be able to read every data
    source on the dashboard, or the picture shows them what the app would not.
    """
    if user.has_permission("admin"):
        return True
    for widget in dashboard.loaded_widgets():
        query = widget.visualization.query_rel if widget.visualization else None
        if query is None or query.data_source is None:
            continue
        if not has_access(query.data_source, user, True):
            return False
    return True


class require_permissions:
    def __init__(self, permissions, allow_one=False):
        self.permissions = permissions
        self.allow_one = allow_one

    def __call__(self, fn):
        @functools.wraps(fn)
        def decorated(*args, **kwargs):
            if self.allow_one:
                has_permissions = any([current_user.has_permission(permission) for permission in self.permissions])
            else:
                has_permissions = current_user.has_permissions(self.permissions)

            if has_permissions:
                return fn(*args, **kwargs)
            else:
                abort(403)

        return decorated


def require_permission(permission):
    return require_permissions((permission,))


def require_any_of_permission(permissions):
    return require_permissions(permissions, True)


def require_admin(fn):
    return require_permission("admin")(fn)


def require_super_admin(fn):
    return require_permission("super_admin")(fn)


def require_feature(name):
    """
    A feature an administrator hands to a group -- see sqldesk/features.py.

    Not `require_permission`, because a feature is refused on two counts: the
    group was not granted it, or this install does not offer it at all. The
    second is why a catalog endpoint stops answering when MCP is switched
    off, rather than answering anyone who happens to still carry the row.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def decorated(*args, **kwargs):
            from sqldesk import features

            if not features.can(current_user, name):
                abort(403)
            return fn(*args, **kwargs)

        return decorated

    return decorator


def has_permission_or_owner(permission, object_owner_id):
    return int(object_owner_id) == current_user.id or current_user.has_permission(permission)


def is_admin_or_owner(object_owner_id):
    return has_permission_or_owner("admin", object_owner_id)


def require_permission_or_owner(permission, object_owner_id):
    if not has_permission_or_owner(permission, object_owner_id):
        abort(403)


def require_admin_or_owner(object_owner_id):
    if not is_admin_or_owner(object_owner_id):
        abort(403, message="You don't have permission to edit this resource.")


def can_modify(obj, user):
    # A dashboard in a locked folder is an administrator's to change, and
    # nobody else's -- not even the person who made it. Checked here rather
    # than in each handler because editing, renaming, archiving and adding a
    # widget are four different ones, and a lock that covered three of them
    # would be worse than no lock at all.
    if getattr(obj, "is_locked", False) and not user.has_permission("admin"):
        return False
    return is_admin_or_owner(obj.user_id) or user.has_access(obj, ACCESS_TYPE_MODIFY)


def require_object_modify_permission(obj, user):
    if not can_modify(obj, user):
        abort(403)

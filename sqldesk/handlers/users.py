from disposable_email_domains import blacklist
from flask import request
from flask_login import current_user, login_user
from flask_restful import abort
from funcy import flatten, partial, project
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from sqldesk import features, limiter, models, oauth, screenshots, settings
from sqldesk.authentication.account import (
    invite_link_for_user,
    send_invite_email,
    send_password_reset_email,
    send_verify_email,
)
from sqldesk.handlers.base import (
    BaseResource,
    get_object_or_404,
    paginate,
    require_fields,
)
from sqldesk.handlers.base import order_results as _order_results
from sqldesk.permissions import (
    is_admin_or_owner,
    require_admin,
    require_admin_or_owner,
    require_permission,
    require_permission_or_owner,
)
from sqldesk.settings import parse_boolean

# Ordering map for relationships
order_map = {
    "name": "name",
    "-name": "-name",
    "active_at": "active_at",
    "-active_at": "-active_at",
    "created_at": "created_at",
    "-created_at": "-created_at",
    "groups": "group_ids",
    "-groups": "-group_ids",
}

order_results = partial(_order_results, default_order="-created_at", allowed_orders=order_map)


def invite_user(org, inviter, user, send_email=True):
    d = user.to_dict()

    invite_url = invite_link_for_user(user)
    if settings.email_server_is_configured() and send_email:
        send_invite_email(inviter, user, invite_url, org)
    else:
        d["invite_link"] = invite_url

    return d


def require_allowed_email(email):
    # `example.com` and `example.com.` are equal - last dot stands for DNS root but usually is omitted
    _, domain = email.lower().rstrip(".").split("@", 1)

    if domain in blacklist or domain in settings.BLOCKED_DOMAINS:
        abort(400, message="Bad email address.")


class UserListResource(BaseResource):
    decorators = BaseResource.decorators + [limiter.limit("200/day;50/hour", methods=["POST"])]

    def get_users(self, disabled, pending, search_term):
        if disabled:
            users = models.User.all_disabled(self.current_org)
        else:
            users = models.User.all(self.current_org)

        if pending is not None:
            users = models.User.pending(users, pending)

        if search_term:
            users = models.User.search(users, search_term)
            self.record_event(
                {
                    "action": "search",
                    "object_type": "user",
                    "term": search_term,
                    "pending": pending,
                }
            )
        else:
            self.record_event({"action": "list", "object_type": "user", "pending": pending})

        # order results according to passed order parameter,
        # special-casing search queries where the database
        # provides an order by search rank
        return order_results(users, fallback=not bool(search_term))

    @require_permission("list_users")
    def get(self):
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 25, type=int)

        groups = {group.id: group for group in models.Group.all(self.current_org)}

        def serialize_user(user):
            d = user.to_dict()
            user_groups = []
            for group_id in set(d["groups"]):
                group = groups.get(group_id)

                if group:
                    user_groups.append({"id": group.id, "name": group.name})

            d["groups"] = user_groups

            return d

        search_term = request.args.get("q", "")

        disabled = request.args.get("disabled", "false")  # get enabled users by default
        disabled = parse_boolean(disabled)

        pending = request.args.get("pending", None)  # get both active and pending by default
        if pending is not None:
            pending = parse_boolean(pending)

        users = self.get_users(disabled, pending, search_term)

        return paginate(users, page, page_size, serialize_user)

    @require_admin
    def post(self):
        req = request.get_json(force=True)
        require_fields(req, ("name", "email"))

        if "@" not in req["email"]:
            abort(400, message="Bad email address.")
        require_allowed_email(req["email"])

        user = models.User(
            org=self.current_org,
            name=req["name"],
            email=req["email"],
            is_invitation_pending=True,
            group_ids=[self.current_org.default_group.id],
        )

        try:
            models.db.session.add(user)
            models.db.session.commit()
        except IntegrityError as e:
            if "email" in str(e):
                abort(400, message="Email already taken.")
            abort(500)

        self.record_event({"action": "create", "object_id": user.id, "object_type": "user"})

        should_send_invitation = "no_invite" not in request.args
        return invite_user(self.current_org, self.current_user, user, send_email=should_send_invitation)


class UserInviteResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        return invite_user(self.current_org, self.current_user, user)


class UserResetPasswordResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        if user.is_disabled:
            abort(404, message="Not found")
        reset_link = send_password_reset_email(user)

        return {"reset_link": reset_link}


class UserRegenerateApiKeyResource(BaseResource):
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        if user.is_disabled:
            abort(404, message="Not found")
        if not is_admin_or_owner(user_id):
            abort(403)

        user.regenerate_api_key()
        models.db.session.commit()

        self.record_event({"action": "regnerate_api_key", "object_id": user.id, "object_type": "user"})

        return user.to_dict(with_api_key=True)


class UserResource(BaseResource):
    decorators = BaseResource.decorators + [limiter.limit("50/hour", methods=["POST"])]

    def get(self, user_id):
        require_permission_or_owner("list_users", user_id)
        user = get_object_or_404(models.User.get_by_id_and_org, user_id, self.current_org)

        self.record_event({"action": "view", "object_id": user_id, "object_type": "user"})

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    def post(self, user_id):  # noqa: C901
        require_admin_or_owner(user_id)
        user = models.User.get_by_id_and_org(user_id, self.current_org)

        req = request.get_json(True)

        params = project(req, ("email", "name", "password", "old_password", "group_ids"))

        if "password" in params and "old_password" not in params:
            abort(403, message="Must provide current password to update password.")

        if "old_password" in params and not user.verify_password(params["old_password"]):
            abort(403, message="Incorrect current password.")

        if "password" in params:
            user.hash_password(params.pop("password"))
            params.pop("old_password")

        if "group_ids" in params:
            if not self.current_user.has_permission("admin"):
                abort(403, message="Must be admin to change groups membership.")

            for group_id in params["group_ids"]:
                try:
                    models.Group.get_by_id_and_org(group_id, self.current_org)
                except NoResultFound:
                    abort(400, message="Group id {} is invalid.".format(group_id))

            if len(params["group_ids"]) == 0:
                params.pop("group_ids")

        if "email" in params:
            require_allowed_email(params["email"])

        email_address_changed = "email" in params and params["email"] != user.email
        needs_to_verify_email = email_address_changed and settings.email_server_is_configured()
        if needs_to_verify_email:
            user.is_email_verified = False

        try:
            self.update_model(user, params)
            models.db.session.commit()

            if needs_to_verify_email:
                send_verify_email(user, self.current_org)

            # The user has updated their email or password. This should invalidate all _other_ sessions,
            # forcing them to log in again. Since we don't want to force _this_ session to have to go
            # through login again, we call `login_user` in order to update the session with the new identity details.
            if current_user.id == user.id:
                login_user(user, remember=True)
        except IntegrityError as e:
            if "email" in str(e):
                message = "Email already taken."
            else:
                message = "Error updating record"

            abort(400, message=message)

        self.record_event(
            {
                "action": "edit",
                "object_id": user.id,
                "object_type": "user",
                "updated_fields": list(params.keys()),
            }
        )

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    @require_admin
    def delete(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        # admin cannot delete self; current user is an admin (`@require_admin`)
        # so just check user id
        if user.id == current_user.id:
            abort(
                403,
                message="You cannot delete your own account. "
                "Please ask another admin to do this for you.",  # fmt: skip
            )
        elif not user.is_invitation_pending:
            abort(
                403,
                message="You cannot delete activated users. "
                "Please disable the user instead.",  # fmt: skip
            )
        models.db.session.delete(user)
        models.db.session.commit()

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))


class UserAccessResource(BaseResource):
    """
    What this person may do, and where it comes from.

    Read-only on purpose. Access is a property of the groups somebody is in,
    so a page that let you tick a feature here would be a page that quietly
    disagreed with the Groups page. What it does instead is name the group
    that grants each thing, so whoever is looking knows where to go.
    """

    def get(self, user_id):
        require_permission_or_owner("list_users", user_id)
        user = get_object_or_404(models.User.get_by_id_and_org, user_id, self.current_org)

        groups = models.Group.query.filter(
            models.Group.id.in_(user.group_ids), models.Group.org == self.current_org
        ).all()
        is_admin = user.has_permission("admin")

        offered = []
        for feature in features.grantable():
            granted_by = [group.name for group in groups if feature.name in (group.permissions or [])]
            offered.append(
                {
                    "name": feature.name,
                    "label": feature.label,
                    "description": feature.description,
                    "granted": features.can(user, feature.name),
                    # An administrator has everything without being granted
                    # it, and saying which group would be a lie.
                    "granted_by": ["Administrator"] if is_admin and not granted_by else granted_by,
                }
            )

        sources = []
        for source in models.DataSource.query.filter(models.DataSource.org == self.current_org).order_by(
            models.DataSource.name
        ):
            if is_admin:
                sources.append({"name": source.name, "access": "full"})
                continue
            matching = set(source.groups.keys()) & set(user.group_ids)
            if matching:
                view_only = all(flatten([source.groups[group] for group in matching]))
                sources.append({"name": source.name, "access": "view only" if view_only else "full"})

        return {"features": offered, "data_sources": sources, "is_admin": is_admin}


class UserScreenResource(BaseResource):
    def post(self, user_id):
        """
        Remember how wide this person's dashboards are, and their time zone,
        so the pictures sent in their name -- Send to Slack, subscriptions,
        an alert's attachment -- are drawn the way their own screen shows the
        dashboard. See `screenshots.screen_of`.

        Your own and nobody else's: it describes a screen, which only its
        owner's browser can see.

        :<json number width: the dashboard's width in CSS pixels
        :<json string time_zone: an IANA time zone, such as America/Toronto
        """
        if not isinstance(self.current_user, models.User) or str(self.current_user.id) != str(user_id):
            abort(403, message="You can only describe your own screen.")

        body = request.get_json(force=True, silent=True) or {}
        if not isinstance(body, dict) or ("width" not in body and "dashboard_id" not in body):
            abort(400, message="Send `width`, or `dashboard_id` with `table_orders`, or both.")

        user = self.current_user
        changed = False

        if "width" in body:
            width = screenshots.clean_screen_width(body.get("width"))
            if width is None:
                abort(
                    400,
                    message="`width` is the dashboard's width in pixels, between {} and {}.".format(
                        screenshots.MIN_SCREEN_WIDTH, screenshots.MAX_SCREEN_WIDTH
                    ),
                )
            screen = {"width": width}
            time_zone = screenshots.clean_time_zone(body.get("time_zone"))
            if time_zone:
                screen["time_zone"] = time_zone
            if (user.details or {}).get("screen") != screen:
                if user.details is None:
                    user.details = {}
                user.details["screen"] = screen
                changed = True

        orders = None
        if "dashboard_id" in body:
            dashboard_id = body.get("dashboard_id")
            if isinstance(dashboard_id, bool) or not str(dashboard_id).isdigit():
                abort(400, message="`dashboard_id` is the id of the dashboard on screen.")
            orders = screenshots.clean_table_orders(body.get("table_orders"))
            changed = screenshots.remember_table_orders(user, dashboard_id, orders) or changed

        if changed:
            models.db.session.commit()
        result = {"screen": (user.details or {}).get("screen")}
        if orders is not None:
            result["table_orders"] = orders
        return result


class UserDisableResource(BaseResource):
    @require_admin
    def post(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        # admin cannot disable self; current user is an admin (`@require_admin`)
        # so just check user id
        if user.id == current_user.id:
            abort(
                403,
                message="You cannot disable your own account. "
                "Please ask another admin to do this for you.",  # fmt: skip
            )
        user.disable()
        models.db.session.commit()
        # Disabling an account has to end its connected MCP clients, not only
        # its ability to sign in. `/mcp` refuses a disabled user's token
        # anyway, so this is not what makes it safe -- it is what makes the
        # person's "Connected apps" list and the admin list honest, and it
        # removes the refresh token so a client cannot sit holding a grant
        # against the account being enabled again.
        oauth.revoke_for_user(user, "account disabled")

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

    @require_admin
    def delete(self, user_id):
        user = models.User.get_by_id_and_org(user_id, self.current_org)
        user.enable()
        models.db.session.commit()

        return user.to_dict(with_api_key=is_admin_or_owner(user_id))

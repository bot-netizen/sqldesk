import logging

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.orm.exc import NoResultFound

from sqldesk import __version__, features, limiter, models, settings, unsubscribe
from sqldesk import uploads as sqldesk_uploads
from sqldesk.authentication import current_org, get_login_url, get_next_path
from sqldesk.authentication.account import (
    INVITE,
    RESET,
    VERIFY,
    TokenUsed,
    send_password_reset_email,
    send_user_disabled_email,
    send_verify_email,
    user_for_token,
)
from sqldesk.handlers import routes
from sqldesk.handlers.base import json_response, org_scoped_rule
from sqldesk.security import csrf
from sqldesk.settings.organization import settings as org_settings
from sqldesk.version_check import get_latest_version

logger = logging.getLogger(__name__)


def get_google_auth_url(next_path):
    if settings.MULTI_ORG:
        google_auth_url = url_for("google_oauth.authorize_org", next=next_path, org_slug=current_org.slug)
    else:
        google_auth_url = url_for("google_oauth.authorize", next=next_path)
    return google_auth_url


def render_token_login_page(template, org_slug, token, invite):
    error_message = None
    # The token itself stays out of the log: a log line is not the place for
    # a credential, however briefly valid.
    try:
        user = user_for_token(token, INVITE if invite else RESET, current_org._get_current_object())
    except NoResultFound:
        logger.warning("Token for a user not in this organization. org=%s", org_slug)
        error_message = "Your invite link is invalid. Bad user id in token. Please ask for a new one."
    except SignatureExpired:
        logger.info("Expired token. org=%s", org_slug)
        error_message = "Your invite link has expired. Please ask for a new one."
    except TokenUsed:
        logger.info("Token already used, or overtaken by a newer link. org=%s", org_slug)
        error_message = "This link has already been used, or a newer one was sent. Please ask for a new one."
    except BadSignature:
        logger.warning("Bad token signature. org=%s", org_slug)
        error_message = "Your invite link is invalid. Bad signature. Please double-check the token."

    if not error_message and user.is_disabled:
        error_message = "This account is disabled. Please ask an administrator to enable it."

    if error_message:
        return (
            render_template(
                "error.html",
                error_message=error_message,
            ),
            400,
        )

    if invite and user.details.get("is_invitation_pending") is False:
        return (
            render_template(
                "error.html",
                error_message=(
                    "This invitation has already been accepted. Please try resetting your password instead."
                ),
            ),
            400,
        )

    status_code = 200
    if request.method == "POST":
        if "password" not in request.form:
            flash("Bad Request")
            status_code = 400
        elif not request.form["password"]:
            flash("Cannot use empty password.")
            status_code = 400
        elif len(request.form["password"]) < 6:
            flash("Password length is too short (<6).")
            status_code = 400
        else:
            if invite or user.is_invitation_pending:
                user.is_invitation_pending = False
            user.hash_password(request.form["password"])
            models.db.session.add(user)
            login_user(user)
            models.db.session.commit()
            return redirect(url_for("sqldesk.index", org_slug=org_slug))

    google_auth_url = get_google_auth_url(url_for("sqldesk.index", org_slug=org_slug))

    return (
        render_template(
            template,
            show_google_openid=settings.GOOGLE_OAUTH_ENABLED,
            google_auth_url=google_auth_url,
            show_saml_login=current_org.get_setting("auth_saml_enabled"),
            show_remote_user_login=settings.REMOTE_USER_LOGIN_ENABLED,
            show_ldap_login=settings.LDAP_LOGIN_ENABLED,
            org_slug=org_slug,
            user=user,
        ),
        status_code,
    )


@routes.route(org_scoped_rule("/invite/<token>"), methods=["GET", "POST"])
def invite(token, org_slug=None):
    return render_token_login_page("invite.html", org_slug, token, True)


@routes.route(org_scoped_rule("/reset/<token>"), methods=["GET", "POST"])
def reset(token, org_slug=None):
    return render_token_login_page("reset.html", org_slug, token, False)


# Taking yourself off a dashboard subscription, from the link in the email.
#
# Exempt from CSRF, for two reasons that point the same way. A mail client's
# own Unsubscribe button posts here with no page behind it (RFC 8058), so a
# CSRF token is not something it could have. And the token in the URL *is* the
# credential: anybody who could mount a CSRF attack here already has the link,
# and all it does is take its holder off one subscription.
#
# What CSRF would have protected against is protected instead by not acting on
# a GET -- mail clients and scanners fetch links before anybody reads them.
@csrf.exempt
@routes.route(org_scoped_rule("/unsubscribe/<token>"), methods=["GET", "POST"])
def unsubscribe_from_dashboard(token, org_slug=None):
    subscription, user = unsubscribe.load(token)
    dashboard = subscription.dashboard if subscription else None

    if subscription is None or dashboard is None:
        return render_template("unsubscribe.html", subscription=None, done=False), 404

    if request.method == "POST":
        unsubscribe.remove(subscription, user)
        models.db.session.add(subscription)
        models.db.session.commit()
        return render_template(
            "unsubscribe.html",
            subscription=subscription,
            dashboard_name=dashboard.name,
            recipient_name=user.name,
            done=True,
        )

    return render_template(
        "unsubscribe.html",
        subscription=subscription,
        dashboard_name=dashboard.name,
        recipient_name=user.name,
        done=False,
    )


# Signed in, unlike unsubscribe. Keeping a file costs disk indefinitely and is
# a permission somebody holds, so the page has to know who is asking -- and the
# person reading the mail is the one who uploaded the file, so they have an
# account here by definition.
#
# CSRF-exempt and refusing to act on a GET, for the same reason unsubscribe is:
# mail clients and scanners fetch links before anybody reads them, and a GET
# that kept the file would keep files nobody chose to keep.
@csrf.exempt
@routes.route(org_scoped_rule("/uploads/keep/<token>"), methods=["GET", "POST"])
@login_required
def keep_uploaded_file(token, org_slug=None):
    upload = sqldesk_uploads.upload_from_token(token)
    if upload is None or upload.org_id != current_org.id:
        # Expired, deleted, or a token for another organisation. All three say
        # the same true thing rather than pretending the link is malformed.
        return render_template("upload_kept.html", upload=None, done=False), 404

    filename = upload.display_name or upload.filename
    may_keep = features.can(current_user, features.KEEP_UPLOADS)
    context = {
        "upload": upload,
        "filename": filename,
        "may_keep": may_keep,
        "kept_already": upload.kept,
        "expires": upload.expires_at.date().isoformat() if upload.expires_at else None,
        "done": False,
    }

    if request.method == "POST" and may_keep and not upload.kept:
        upload.keep(current_user._get_current_object())
        models.db.session.add(upload)
        models.db.session.commit()
        context["done"] = True

    status = 403 if not may_keep else 200
    return render_template("upload_kept.html", **context), status


@routes.route(org_scoped_rule("/verify/<token>"), methods=["GET"])
def verify(token, org_slug=None):
    try:
        user = user_for_token(token, VERIFY, current_org._get_current_object())
    except (BadSignature, NoResultFound):
        logger.warning("Bad email verification token. org=%s", org_slug)
        return (
            render_template(
                "error.html",
                error_message="Your verification link is invalid. Please ask for a new one.",
            ),
            400,
        )

    user.is_email_verified = True
    models.db.session.add(user)
    models.db.session.commit()

    template_context = {"org_slug": org_slug} if settings.MULTI_ORG else {}
    next_url = url_for("sqldesk.index", **template_context)

    return render_template("verify.html", next_url=next_url)


@routes.route(org_scoped_rule("/forgot"), methods=["GET", "POST"])
@limiter.limit(settings.THROTTLE_PASS_RESET_PATTERN)
def forgot_password(org_slug=None):
    if not current_org.get_setting("auth_password_login_enabled"):
        abort(404)

    submitted = False
    if request.method == "POST" and request.form["email"]:
        submitted = True
        email = request.form["email"]
        try:
            org = current_org._get_current_object()
            user = models.User.get_by_email_and_org(email, org)
            if user.is_disabled:
                send_user_disabled_email(user)
            else:
                send_password_reset_email(user)
        except NoResultFound:
            logging.error("No user found for forgot password: %s", email)

    return render_template("forgot.html", submitted=submitted)


@routes.route(org_scoped_rule("/verification_email/"), methods=["POST"])
def verification_email(org_slug=None):
    if not current_user.is_email_verified:
        send_verify_email(current_user, current_org)

    return json_response({"message": "Please check your email inbox in order to verify your email address."})


@routes.route(org_scoped_rule("/login"), methods=["GET", "POST"])
@limiter.limit(settings.THROTTLE_LOGIN_PATTERN)
def login(org_slug=None):
    # We intentionally use == as otherwise it won't actually use the proxy. So weird :O
    # noinspection PyComparisonWithNone
    if current_org == None and not settings.MULTI_ORG:  # noqa: E711
        return redirect("/setup")
    elif current_org == None:  # noqa: E711
        return redirect("/")

    index_url = url_for("sqldesk.index", org_slug=org_slug)
    unsafe_next_path = request.args.get("next", index_url)
    next_path = get_next_path(unsafe_next_path)
    if current_user.is_authenticated:
        return redirect(next_path)

    if request.method == "POST" and current_org.get_setting("auth_password_login_enabled"):
        try:
            org = current_org._get_current_object()
            user = models.User.get_by_email_and_org(request.form["email"], org)
            if user and not user.is_disabled and user.verify_password(request.form["password"]):
                remember = "remember" in request.form
                login_user(user, remember=remember)
                return redirect(next_path)
            else:
                flash("Wrong email or password.")
        except NoResultFound:
            flash("Wrong email or password.")
    elif request.method == "POST" and not current_org.get_setting("auth_password_login_enabled"):
        flash("Password login is not enabled for your organization.")

    google_auth_url = get_google_auth_url(next_path)

    return render_template(
        "login.html",
        org_slug=org_slug,
        next=next_path,
        email=request.form.get("email", ""),
        show_google_openid=settings.GOOGLE_OAUTH_ENABLED,
        google_auth_url=google_auth_url,
        show_password_login=current_org.get_setting("auth_password_login_enabled"),
        show_saml_login=current_org.get_setting("auth_saml_enabled"),
        show_remote_user_login=settings.REMOTE_USER_LOGIN_ENABLED,
        show_ldap_login=settings.LDAP_LOGIN_ENABLED,
    )


@routes.route(org_scoped_rule("/logout"))
def logout(org_slug=None):
    logout_user()
    return redirect(get_login_url(next=None))


def _org_setting(key):
    """
    An organization's setting, or the install's default where there is no
    organization yet.

    Everything `/api/config` assembles reads settings off `current_org`, which
    is a proxy that resolves to None until `/setup` has created the first
    organization. Reading a setting off it raised, so the first thing a browser
    asks for on a brand new install answered 500 with a traceback rather than
    something it could act on. Nobody meets it on the path people take --
    a fresh install is sent to `/setup`, which is server-rendered -- but a
    client holding the SPA from a previous install asks for this first.

    `== None` rather than `is None`: the proxy is never identical to None.
    `login()` and `/setup` compare it the same way, for the same reason.

    The fallback is where `Organization.get_setting` ends up anyway when an
    organization has not overridden a setting, so an install before setup and
    one that has changed nothing answer alike.
    """
    if current_org == None:  # noqa: E711
        return org_settings.get(key)
    return current_org.get_setting(key)


def base_href():
    if settings.MULTI_ORG:
        # Under multi-org the index route is org-scoped, so with no
        # organization resolved there is no URL to build -- not even an
        # unscoped one, because that rule does not exist here. The root is
        # where the browser is going anyway, and `get_login_url` answers the
        # same case the same way. Reading `.slug` off nothing used to raise,
        # which is most of why `/api/config` met a new install with a
        # traceback.
        if current_org == None:  # noqa: E711
            return "/"
        return url_for("sqldesk.index", _external=True, org_slug=current_org.slug)

    return url_for("sqldesk.index", _external=True)


def date_time_format_config():
    date_format = _org_setting("date_format")
    date_format_list = set(["DD/MM/YY", "MM/DD/YY", "YYYY-MM-DD", settings.DATE_FORMAT])
    time_format = _org_setting("time_format")
    time_format_list = set(["HH:mm", "HH:mm:ss", "HH:mm:ss.SSS", settings.TIME_FORMAT])
    return {
        "dateFormat": date_format,
        "dateFormatList": list(date_format_list),
        "timeFormatList": list(time_format_list),
        "dateTimeFormat": "{0} {1}".format(date_format, time_format),
    }


def number_format_config():
    return {
        "integerFormat": _org_setting("integer_format"),
        "floatFormat": _org_setting("float_format"),
        "thousandsSeparator": _org_setting("thousands_separator"),
        "decimalSeparator": _org_setting("decimal_separator"),
    }


def null_value_config():
    return {
        "nullValue": _org_setting("null_value"),
    }


def _slack_is_connected():
    """
    Whether this organisation has a Slack token stored.

    One indexed row by org, asked on every page load alongside the rest of the
    client config -- which is why it is a count and not the row itself: nothing
    here needs the token, and a config endpoint is the last place it should be
    able to reach.
    """
    if current_org == None:  # noqa: E711
        # No organization yet, so nobody can have connected a workspace to it.
        return False
    return models.SlackWorkspace.query.filter(models.SlackWorkspace.org_id == current_org.id).count() > 0


def client_config():
    if not current_user.is_api_user() and current_user.is_authenticated:
        client_config = {
            "newVersionAvailable": bool(get_latest_version()),
            "version": __version__,
        }
    else:
        client_config = {}

    # Only worth asking when there is a version-check endpoint to send the
    # counts to. With none configured -- the default -- the setting governs
    # nothing, so the prompt would be asking about something that cannot happen.
    if settings.VERSION_CHECK_URL and current_user.has_permission("admin") and _org_setting("beacon_consent") is None:
        client_config["showBeaconConsentMessage"] = True

    defaults = {
        "showPermissionsControl": _org_setting("feature_show_permissions_control"),
        "disablePublicUrls": _org_setting("disable_public_urls"),
        "multiByteSearchEnabled": _org_setting("multi_byte_search_enabled"),
        "autoPublishNamedQueries": settings.FEATURE_AUTO_PUBLISH_NAMED_QUERIES,
        # Both halves: the flag, and somewhere to send the request. Without a
        # renderer there is nothing to turn on, so the editor should not offer it.
        "alertScreenshots": settings.FEATURE_ALERT_SCREENSHOTS and bool(settings.SCREENSHOT_URL),
        "maxAlertAttachments": settings.MAX_ALERT_ATTACHMENTS,
        "mailSettingsMissing": not settings.email_server_is_configured(),
        "dashboardRefreshIntervals": settings.DASHBOARD_REFRESH_INTERVALS,
        "queryRefreshIntervals": settings.QUERY_REFRESH_INTERVALS,
        "googleLoginEnabled": settings.GOOGLE_OAUTH_ENABLED,
        "ldapLoginEnabled": settings.LDAP_LOGIN_ENABLED,
        "pageSize": settings.PAGE_SIZE,
        "pageSizeOptions": settings.PAGE_SIZE_OPTIONS,
        "tableCellMaxJSONSize": settings.TABLE_CELL_MAX_JSON_SIZE,
        # Gates the MCP pages and the catalog.
        "mcpEnabled": settings.FEATURE_AI,
        # So the MCP page can offer signing in rather than only a pasted key.
        "mcpOAuthEnabled": settings.FEATURE_AI and settings.MCP_OAUTH_ENABLED,
        # Whether an administrator has connected a Slack workspace. The Share
        # menu asks, because its dialog's first act is to ask Slack for
        # channels -- offering it with nothing connected is offering a dialog
        # whose only content is an error.
        "slackConfigured": _slack_is_connected(),
        # The name this had before, still sent: during an upgrade a browser
        # holding the previous bundle reads it from a server already running
        # the new one.
        "aiEnabled": settings.FEATURE_AI,
        # What an admin may grant a group, so the Group page does not keep
        # its own copy of the list and drift from it.
        "grantableFeatures": [feature.to_dict() for feature in features.grantable()],
    }

    client_config.update(defaults)
    client_config.update({"basePath": base_href()})
    client_config.update(date_time_format_config())
    client_config.update(number_format_config())
    client_config.update(null_value_config())

    return client_config


def messages():
    messages = []

    if not current_user.is_email_verified:
        messages.append("email-not-verified")

    if settings.ALLOW_PARAMETERS_IN_EMBEDS:
        messages.append("using-deprecated-embed-feature")

    return messages


@routes.route("/api/config", methods=["GET"])
def config(org_slug=None):
    # `setup_required` rather than a 500: this is the first thing a browser
    # holding a cached SPA asks for, and on a brand new install it used to get
    # a traceback. A client can act on a flag; it can do nothing with a 500.
    if current_org == None:  # noqa: E711
        return json_response({"org_slug": None, "setup_required": True, "client_config": client_config()})
    return json_response({"org_slug": current_org.slug, "client_config": client_config()})


@routes.route(org_scoped_rule("/api/session"), methods=["GET"])
@login_required
def session(org_slug=None):
    if current_user.is_api_user():
        user = {"permissions": [], "apiKey": current_user.id}
    else:
        user = {
            "profile_image_url": current_user.profile_image_url,
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "groups": current_user.group_ids,
            "permissions": current_user.permissions,
        }

    return json_response(
        {
            "user": user,
            "messages": messages(),
            "org_slug": current_org.slug,
            "client_config": client_config(),
        }
    )

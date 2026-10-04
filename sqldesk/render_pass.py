"""
A pass that lets the renderer open one page, for five minutes, read-only.

Before this, a picture of a dashboard could only be had by giving the renderer
the dashboard's *public* link -- so attaching a dashboard to an alert meant
first making it readable by anyone on the internet who guessed or was given
the token. That is a large decision to take for a picture in an email, and it
is why the alert editor had to say "this dashboard has not been shared" and
give up.

A pass is not a link anybody keeps:

- **One object.** It names the dashboard or query it was issued for, and
  resolves to a user scoped to that object. It cannot be pointed at another.
- **Five minutes.** The signature carries its own timestamp and is refused
  after that, whatever the holder does with it.
- **Read-only.** It resolves to an `ApiUser`, whose permissions are
  `view_query` and nothing else -- the same thing a public link resolves to,
  so no new path through the authorization code.
- **Withdrawn when the render finishes.** The signature alone would stay valid
  for the rest of its five minutes; a record in Redis, deleted as soon as the
  renderer answers, means a pass that leaked out of a log is already spent.

"Single use" cannot mean one HTTP request: the page is a single-page
application and fetches its own session, the dashboard and every widget's
results, each with the same credential. It means one rendering, and the record
below is what ends it.
"""

import logging
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from sqldesk import models, redis_connection, settings

logger = logging.getLogger(__name__)

#: Long enough for a slow dashboard, short enough that a leaked pass is
#: already useless by the time anybody reads the log it leaked into.
TTL_SECONDS = 300

#: Its own salt, so a pass cannot be presented anywhere else a signed token is
#: accepted -- password resets and invitations each have their own for the
#: same reason.
SALT = "sqldesk.render-pass"

#: How a pass announces itself. Nothing else in the api-key position starts
#: with this, so telling them apart costs a string comparison rather than an
#: attempt to verify every credential as every kind.
PREFIX = "rp."

_REDIS_PREFIX = "render-pass:"

DASHBOARD = "dashboard"
QUERY = "query"


def _serializer():
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt=SALT)


def kind_of(obj):
    return DASHBOARD if isinstance(obj, models.Dashboard) else QUERY


def issue(user, obj):
    """
    A pass for this person to have this object drawn, or None.

    None when Redis cannot be reached. The caller treats that the way it
    treats every other rendering failure -- send the alert without a picture --
    because a pass that cannot be withdrawn is not one worth issuing.
    """
    nonce = secrets.token_urlsafe(18)
    try:
        redis_connection.set(_REDIS_PREFIX + nonce, obj.id, ex=TTL_SECONDS)
    except Exception:
        logger.exception("Could not record a render pass; not issuing one.")
        return None

    return PREFIX + _serializer().dumps(
        {
            "n": nonce,
            "user": user.id,
            "kind": kind_of(obj),
            "id": obj.id,
        }
    )


def looks_like_one(token):
    return isinstance(token, str) and token.startswith(PREFIX)


def load(token, org):
    """
    The scoped, read-only user this pass stands for, or None.

    Every reason to refuse -- a bad signature, an expired one, a pass for
    another organization, one already spent, an object since deleted -- gives
    the same answer, because the caller does the same thing with all of them.
    """
    if not looks_like_one(token) or org is None:
        return None

    try:
        payload = _serializer().loads(token[len(PREFIX) :], max_age=TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

    if not isinstance(payload, dict):
        return None

    try:
        if not redis_connection.exists(_REDIS_PREFIX + payload["n"]):
            return None
    except Exception:
        # Redis is how a pass is withdrawn. Without it there is no way to know
        # whether this one has been spent, and the safe answer is no.
        logger.exception("Could not check a render pass; refusing it.")
        return None

    obj = _object(payload, org)
    if obj is None:
        return None

    user = models.ApiUser(token, org, [], name="Render pass: {} {}".format(payload["kind"], payload["id"]))
    user.object = obj
    # What tells the public-dashboard handler that this is not a public link,
    # and so is not affected by an organization switching those off.
    user.is_render_pass = True
    return user


def _object(payload, org):
    """
    The object this pass names, in this organization, or None.

    The organization is enforced here and nowhere else. An earlier version
    also compared the org in the payload, which sounds like defence in depth
    and is really a second rule that can disagree with the first: no test
    could tell the two apart, because a scoped lookup already refuses a
    dashboard belonging to somebody else.
    """
    try:
        if payload.get("kind") == DASHBOARD:
            return models.Dashboard.get_by_id_and_org(payload["id"], org)
        return models.Query.get_by_id_and_org(payload["id"], org)
    except (models.NoResultFound, KeyError):
        return None


def withdraw(token):
    """Spend a pass, so what is left of its five minutes is worth nothing."""
    if not looks_like_one(token):
        return
    try:
        payload = _serializer().loads(token[len(PREFIX) :], max_age=TTL_SECONDS)
        redis_connection.delete(_REDIS_PREFIX + payload["n"])
    except (BadSignature, SignatureExpired, KeyError, TypeError):
        pass
    except Exception:
        logger.exception("Could not withdraw a render pass.")


def allows(obj, user, need_view_only):
    """
    Whether this pass may see `obj`, read-only.

    The set is exactly what the public link it replaces granted: the dashboard
    the pass names, and the queries drawn on it. A dashboard's page fetches a
    result for every widget, so without the second half the picture is a grid
    of permission errors -- which is what the first version of this produced,
    and what rendering one on the cluster showed.

    Deliberately *not* narrowed to what the pass's owner may run. A public
    link showed every widget on the dashboard to anybody who had it, so this
    is the same reach with an expiry on it and nothing made public. Narrowing
    it to the owner would quietly blank widgets in pictures that arrive today.

    Never for writing: `need_view_only` false is somebody asking to change
    something, and a pass exists to take a photograph.
    """
    if not need_view_only:
        return False

    target = getattr(user, "object", None)
    if target is None:
        return False

    if type(obj) is type(target) and obj.id == target.id:
        return True

    if isinstance(target, models.Dashboard) and isinstance(obj, models.Query):
        return target.id in obj.dashboard_ids

    # The data source behind what it may see.
    #
    # `/api/queries/<id>/results/<id>.json` checks access to the *data source*,
    # not to the query, so a pass for a query could fetch the query and was
    # then refused its stored result: the embed page sat at "Loading..." until
    # the renderer timed out, and the alert went out without its picture --
    # silently, because a failed render is meant to cost the picture and not
    # the alert. Every query attachment ever added to an alert was blank.
    #
    # A dashboard never showed it. Its public handler serves each widget's
    # data itself and never asks that endpoint.
    #
    # This grants reading one data source's *results for pages this pass may
    # already see*, which is what a public link granted and what the rule
    # above already allows for the queries themselves.
    if isinstance(obj, models.DataSource):
        if isinstance(target, models.Query):
            return obj.id == target.data_source_id
        if isinstance(target, models.Dashboard):
            return any(
                widget.visualization is not None
                and widget.visualization.query_rel is not None
                and widget.visualization.query_rel.data_source_id == obj.id
                for widget in target.loaded_widgets()
            )

    return False

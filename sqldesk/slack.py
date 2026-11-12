"""
Talking to Slack, for sharing a dashboard to a channel.

Why SQLDesk posts the picture rather than letting Slack fetch a link: an
install behind a VPN is not reachable from Slack's servers, so a pasted link
would unfurl into a bare URL and nothing else. Drawing the picture here and
uploading it means nothing has to reach in, which is the difference between a
feature that works on most installs and one that works on the ones with a
public address.

Four calls, and no SDK. `requests` is already a dependency, Slack's Web API is
form-encoded POSTs returning JSON, and a client library for four endpoints is
a dependency to upgrade forever in exchange for nothing.

Every function returns `(value, error)` where `error` is a sentence somebody
can act on, rather than raising. A Slack token is somebody else's service's
credential: it can be revoked, the app can be removed from a channel, and the
workspace can be on a plan that refuses an upload. None of those are bugs here
and all of them have to reach a person as words.
"""

import json
import logging

import requests

logger = logging.getLogger(__name__)

API = "https://slack.com/api"

#: Slack is not in the path of anybody's query, so a slow answer should fail
#: rather than hold a web worker. Generous enough for an image upload on a
#: domestic connection.
TIMEOUT = 20
UPLOAD_TIMEOUT = 60

#: What Slack's own errors mean, in words. Its `error` strings are terse
#: identifiers meant for code -- shown raw they send somebody to a search
#: engine, which is a poor substitute for a sentence.
EXPLANATIONS = {
    "invalid_auth": "Slack rejected the token. It may have been revoked, or belong to another workspace.",
    "account_inactive": "The Slack app has been removed from that workspace. Install it again and paste the new token.",
    "token_revoked": "That token has been revoked in Slack. Create a new one and paste it here.",
    "not_authed": "No token was sent. Enter a bot token under Settings.",
    "missing_scope": "The Slack app is missing a permission it needs. Check its scopes and reinstall it.",
    "channel_not_found": "Slack cannot see that channel. For a private channel, invite the app to it first.",
    "not_in_channel": "The app is not in that channel. Invite it, then try again.",
    "is_archived": "That channel is archived.",
    "msg_too_long": "The message is too long for Slack.",
    "rate_limited": "Slack is rate-limiting us. Try again in a minute.",
    "ratelimited": "Slack is rate-limiting us. Try again in a minute.",
    "upload_limit_reached": "The workspace has reached its file storage limit.",
}


def _explain(code):
    return EXPLANATIONS.get(code) or "Slack refused the request: {}.".format(code or "no reason given")


def _call(method, token, timeout=TIMEOUT, **payload):
    """
    One Web API call. Returns `(body, error)`.

    The token goes in the Authorization header rather than the form body, which
    is what Slack documents and keeps it out of anything that logs a request
    body.
    """
    try:
        response = requests.post(
            "{}/{}".format(API, method),
            headers={"Authorization": "Bearer {}".format(token)},
            data=payload,
            timeout=timeout,
        )
    except requests.RequestException as error:
        logger.warning("slack %s failed: %s", method, error)
        return None, "Could not reach Slack: {}.".format(error.__class__.__name__)

    if response.status_code == 429:
        return None, EXPLANATIONS["rate_limited"]
    try:
        body = response.json()
    except ValueError:
        return None, "Slack answered something that was not JSON ({}).".format(response.status_code)

    if not body.get("ok"):
        return None, _explain(body.get("error"))
    return body, None


def check(token):
    """
    Whether this token works, and who it belongs to.

    Called when somebody saves a token, so a wrong one is refused while they
    are still looking at the field rather than the first time a dashboard fails
    to send.
    """
    body, error = _call("auth.test", token)
    if error:
        return None, error
    return {"team": body.get("team"), "app": body.get("user"), "team_id": body.get("team_id")}, None


def channels(token, limit=1000):
    """
    The channels this app has been added to -- the only ones it can post to.

    `users.conversations`, not `conversations.list`. For a bot token it
    answers with the channels the app is a member of and nothing else, which
    is the list that matters: the app has `chat:write` and not
    `chat:write.public`, so a public channel it has not joined refuses a post
    with `not_in_channel`. Listing every public channel offered, in a
    workspace of hundreds, mostly choices that would fail -- and hid the few
    that would not among them.

    It is also the cheaper call: one page for the dozen channels an app is
    usually in, rather than paging through the whole workspace.
    """
    found = []
    cursor = ""
    while True:
        body, error = _call(
            "users.conversations",
            token,
            types="public_channel,private_channel",
            exclude_archived="true",
            limit=200,
            cursor=cursor,
        )
        if error:
            return None, error
        for channel in body.get("channels") or []:
            found.append(
                {
                    "id": channel.get("id"),
                    "name": channel.get("name"),
                    "private": bool(channel.get("is_private")),
                }
            )
        cursor = ((body.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor or len(found) >= limit:
            break
    found.sort(key=lambda channel: (channel["private"], channel["name"] or ""))
    return found, None


def find_channel(token, channel_id):
    """
    The channel with this id among the ones the app is in, or an error.

    Asked before anything is saved that will post to a channel later -- a
    subscription, an alert -- so a channel the app has been removed from is
    refused while somebody is choosing it, not discovered at three in the
    morning when the first post fails.
    """
    found, error = channels(token)
    if error:
        return None, error
    for channel in found:
        if channel["id"] == channel_id:
            return channel, None
    return None, "The app is not in that channel. Invite it in Slack (/invite), then pick it again."


def upload(token, filename, content):
    """
    Put an image in the workspace and return its file id.

    Three steps, because that is what Slack's current upload is: ask for a URL,
    PUT the bytes at it, then tell Slack the upload finished. `files.upload`,
    which was one call, is deprecated and being switched off.

    No `channel_id` here. Sharing it is done by the message below, so the
    picture arrives inside a message with a button rather than as a bare file
    with a comment attached.
    """
    body, error = _call("files.getUploadURLExternal", token, filename=filename, length=len(content))
    if error:
        return None, error

    upload_url = body.get("upload_url")
    file_id = body.get("file_id")
    if not upload_url or not file_id:
        return None, "Slack did not give us somewhere to upload the picture."

    try:
        posted = requests.post(upload_url, data=content, timeout=UPLOAD_TIMEOUT)
        posted.raise_for_status()
    except requests.RequestException as error:
        logger.warning("slack upload failed: %s", error)
        return None, "Could not upload the picture to Slack: {}.".format(error.__class__.__name__)

    # `files` is JSON even though everything else here is form-encoded.
    _body, error = _call(
        "files.completeUploadExternal",
        token,
        files=json.dumps([{"id": file_id, "title": filename}]),
    )
    if error:
        return None, error
    return file_id, None


def post(token, channel, text, file_id=None, button=None, footer=None):
    """
    One message: the sender's words, the picture, and a button.

    Blocks rather than `initial_comment` on the upload, because a comment
    cannot carry a button and the button is the point -- a picture of a
    dashboard without a way to open the real one is a dead end.
    """
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    if file_id:
        # `slack_file` rather than `image_url`: an uploaded file has no
        # publicly fetchable URL, which is the whole reason we uploaded it.
        blocks.append(
            {
                "type": "image",
                "slack_file": {"id": file_id},
                "alt_text": "A picture of the dashboard",
            }
        )
    if footer:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    if button:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": button["text"]},
                        "url": button["url"],
                    }
                ],
            }
        )

    body, error = _call(
        "chat.postMessage",
        token,
        channel=channel,
        # The fallback for notifications and for anything that cannot render
        # blocks. Without it Slack shows an empty message in a phone banner.
        text=text,
        blocks=json.dumps(blocks),
        unfurl_links="false",
        unfurl_media="false",
    )
    if error:
        return None, error
    return {"channel": body.get("channel"), "ts": body.get("ts")}, None


def post_dashboard(token, channel, filename, picture, text, link, footer=None):
    """
    A dashboard's picture in a channel, with a button that opens it.

    Shared by Send to Slack and by a subscription to a channel, so the two
    arrive looking the same: the picture is uploaded first, and nothing is
    posted if it will not go -- a message about a dashboard with no dashboard
    in it reads as the feature being broken.
    """
    file_id, error = upload(token, filename, picture)
    if error:
        return None, error
    return post(
        token,
        channel,
        text,
        file_id=file_id,
        footer=footer,
        button={"text": "Open dashboard", "url": link},
    )


def dashboard_link(org, dashboard):
    """
    Where a dashboard's button goes.

    The public link when there is one, so anybody in the channel can open it
    without an account here. Otherwise the dashboard's own address, where they
    sign in -- the honest fallback rather than a link that half the channel
    cannot use and nobody told them about.
    """
    # Here rather than at the top: this module is the Web API client first,
    # and the destination that imports it is loaded while the models are.
    from sqldesk import models
    from sqldesk.utils import base_url

    if not org.get_setting("disable_public_urls"):
        # A dashboard's public link is an `ApiKey` row against it, not a
        # column: there is one only if somebody turned sharing on.
        key = models.ApiKey.get_by_object(dashboard)
        if key is not None:
            return "{}/public/dashboards/{}".format(base_url(org), key.api_key)
    return "{}/dashboards/{}".format(base_url(org), dashboard.slug or dashboard.id)


def as_of(dashboard):
    """ "as of" the oldest result on the dashboard, which is the honest figure."""
    oldest = None
    for widget in dashboard.widgets:
        query = widget.visualization.query_rel if widget.visualization else None
        retrieved = query.latest_query_data.retrieved_at if query and query.latest_query_data else None
        if retrieved and (oldest is None or retrieved < oldest):
            oldest = retrieved
    return "as of {}".format(oldest.strftime("%H:%M on %-d %B")) if oldest else None

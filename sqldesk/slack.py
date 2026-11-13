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

import ipaddress
import json
import logging
import time
from urllib.parse import urlparse

import requests

#: Every step of every exchange with Slack is logged here, at INFO when it
#: works and WARNING when it does not, with Slack's own reason. Sharing to
#: Slack crosses three systems -- the renderer, the upload, the message --
#: and "it did not arrive" is otherwise unanswerable from outside. Never the
#: token and never the words of a message: ids, sizes, timings and Slack's
#: error codes, which are enough to say which step failed and why.
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
    "invalid_blocks": "Slack refused the message's layout.",
    "invalid_blocks_format": "Slack refused the message's layout.",
    "not_allowed_token_type": "That is not a bot token. Paste the one that starts with xoxb-.",
}

#: Refusals of the message's shape rather than of who sent it or where. For
#: these the picture can still be delivered another way -- see
#: `post_dashboard`.
LAYOUT_REFUSALS = ("invalid_blocks", "invalid_blocks_format")


def _explain(code, details=()):
    """
    Slack's refusal in words, with Slack's own detail when it sent some.

    For a refused layout Slack says which part and why -- "must be a valid
    URL [json-pointer:/blocks/3/elements/0/url]" -- and that sentence is the
    whole diagnosis, so it is passed on rather than summarised away.
    """
    explained = EXPLANATIONS.get(code) or "Slack refused the request: {}.".format(code or "no reason given")
    if details:
        explained = "{} Slack said: {}".format(explained, "; ".join(details[:3]))
    return explained


def _request(method, token, timeout=TIMEOUT, **payload):
    """
    One Web API call. Returns `(body, code, error)`: Slack's own error code
    when it refused, and that refusal in words.

    The token goes in the Authorization header rather than the form body, which
    is what Slack documents and keeps it out of anything that logs a request
    body.
    """
    started = time.monotonic()
    try:
        response = requests.post(
            "{}/{}".format(API, method),
            headers={"Authorization": "Bearer {}".format(token)},
            data=payload,
            timeout=timeout,
        )
    except requests.RequestException as error:
        logger.warning("slack %s: could not reach Slack after %.1fs: %s", method, time.monotonic() - started, error)
        return None, "unreachable", "Could not reach Slack: {}.".format(error.__class__.__name__)
    took = time.monotonic() - started

    if response.status_code == 429:
        logger.warning(
            "slack %s: rate limited (HTTP 429, retry after %ss)", method, response.headers.get("Retry-After", "?")
        )
        return None, "rate_limited", EXPLANATIONS["rate_limited"]
    try:
        body = response.json()
    except ValueError:
        logger.warning("slack %s: HTTP %s in %.1fs, and not JSON", method, response.status_code, took)
        return None, "not_json", "Slack answered something that was not JSON ({}).".format(response.status_code)

    metadata = body.get("response_metadata") or {}
    for warning in [body.get("warning")] + list(metadata.get("warnings") or []):
        if warning:
            logger.info("slack %s: Slack warns: %s", method, warning)

    if not body.get("ok"):
        code = body.get("error")
        details = list(metadata.get("messages") or [])
        logger.warning(
            "slack %s: refused in %.1fs: %s%s", method, took, code, " -- " + "; ".join(details) if details else ""
        )
        return None, code, _explain(code, details)

    logger.info("slack %s: ok in %.1fs", method, took)
    return body, None, None


def _call(method, token, timeout=TIMEOUT, **payload):
    """One Web API call. Returns `(body, error)`."""
    body, _code, error = _request(method, token, timeout=timeout, **payload)
    return body, error


def public_link(url):
    """
    `url` if people in a Slack channel could open it, else None.

    The button on a message opens in the reader's own browser, so its address
    has to mean something there. `localhost` is the machine *reading* the
    message, and a bare name like `http://sqldesk:5000` is a container's name
    on somebody else's Docker network: a button to either is a dead end at
    best -- and Slack may refuse the whole message over it. An install whose
    SQLDESK_HOST is one of those is being tried out, and its messages go
    without a button rather than with a broken one.

    A private address or an internal name with a dot in it is kept: an install
    behind a VPN is exactly the case this feature exists for, and the people in
    its channel are on the VPN too.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return None if (address.is_loopback or address.is_unspecified or address.is_link_local) else url
    if "." not in host:
        return None
    return url


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
    logger.info("slack: the app is in %s channel(s)", len(found))
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


def upload(token, filename, content, channel=None, comment=None):
    """
    Put an image in the workspace and return its file id.

    Three steps, because that is what Slack's current upload is: ask for a URL,
    PUT the bytes at it, then tell Slack the upload finished. `files.upload`,
    which was one call, is deprecated and being switched off.

    Ordinarily no `channel`: sharing it is done by the message `post` sends,
    so the picture arrives inside a message with a button rather than as a
    bare file with a comment attached. Given a channel, the file is shared
    straight into it with `comment` above it -- the way `post_dashboard`
    still delivers the picture when Slack refuses the message around it.
    """
    logger.info(
        "slack: uploading %s (%s bytes)%s", filename, len(content), " to {}".format(channel) if channel else ""
    )
    body, error = _call("files.getUploadURLExternal", token, filename=filename, length=len(content))
    if error:
        return None, error

    upload_url = body.get("upload_url")
    file_id = body.get("file_id")
    if not upload_url or not file_id:
        logger.warning("slack files.getUploadURLExternal: answered ok with no upload_url or file_id")
        return None, "Slack did not give us somewhere to upload the picture."

    started = time.monotonic()
    try:
        posted = requests.post(upload_url, data=content, timeout=UPLOAD_TIMEOUT)
        posted.raise_for_status()
    except requests.RequestException as error:
        # The URL is a one-off upload address; the reason is enough.
        logger.warning("slack upload of %s failed after %.1fs: %s", file_id, time.monotonic() - started, error)
        return None, "Could not upload the picture to Slack: {}.".format(error.__class__.__name__)
    logger.info(
        "slack upload of %s: %s bytes in %.1fs (HTTP %s)",
        file_id,
        len(content),
        time.monotonic() - started,
        posted.status_code,
    )

    # `files` is JSON even though everything else here is form-encoded.
    complete = {"files": json.dumps([{"id": file_id, "title": filename}])}
    if channel:
        complete["channel_id"] = channel
        if comment:
            complete["initial_comment"] = comment
    _body, error = _call("files.completeUploadExternal", token, **complete)
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
    posted, _code, error = _post(token, channel, text, _blocks(text, file_id, footer, button))
    return posted, error


def post_message(token, channel, text, file_id=None, button=None, footer=None):
    """`post`, with Slack's own error code as well: `(posted, code, error)`."""
    return _post(token, channel, text, _blocks(text, file_id, footer, button))


def _blocks(text, file_id=None, footer=None, button=None):
    """The message: the words, the picture, the footer, the button."""
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    if file_id:
        # `slack_file` rather than `image_url`: an uploaded file has no
        # publicly fetchable URL, which is the whole reason we uploaded it.
        blocks.append({"type": "image", "slack_file": {"id": file_id}, "alt_text": "A picture of the dashboard"})
    if footer:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    if button:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": button["text"]}, "url": button["url"]}
                ],
            }
        )
    return blocks


def _blocks_described(blocks):
    """What a message is made of, for the log: never the words in it."""
    return ", ".join(block["type"] for block in blocks)


def _post(token, channel, text, blocks):
    """`chat.postMessage`. Returns `(posted, code, error)`."""
    logger.info("slack: posting to %s: %s", channel, _blocks_described(blocks))
    body, code, error = _request(
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
        return None, code, error
    logger.info("slack: posted to %s at %s", body.get("channel"), body.get("ts"))
    return {"channel": body.get("channel"), "ts": body.get("ts")}, None, None


def post_dashboard(token, channel, filename, picture, text, link, footer=None):
    """
    A dashboard's picture in a channel, with a button that opens it.

    Shared by Send to Slack and by a subscription to a channel, so the two
    arrive looking the same: the picture is uploaded first, and nothing is
    posted if it will not go -- a message about a dashboard with no dashboard
    in it reads as the feature being broken.

    No button where `link` is None: `dashboard_link` gives None for an
    address nobody in the channel could open, such as localhost.

    If Slack refuses the message's *layout* -- an image block it will not
    take, a button it does not like -- the picture is not given up on: it is
    uploaded again and shared straight into the channel as a file, with the
    message's words above it. Plainer, but it arrives, and the log says which
    way it went and what Slack objected to.
    """
    file_id, error = upload(token, filename, picture)
    if error:
        return None, error

    button = {"text": "Open dashboard", "url": link} if link else None
    posted, code, error = _post(token, channel, text, _blocks(text, file_id, footer, button))
    if not error:
        return posted, None
    if code not in LAYOUT_REFUSALS:
        return None, error

    logger.warning(
        "slack: %s refused the message around the picture (%s); sharing the picture into it as a file instead",
        channel,
        code,
    )
    comment = "\n".join(part for part in (text, footer, link) if part)
    _file_id, retry_error = upload(token, filename, picture, channel=channel, comment=comment)
    if retry_error:
        return None, "{} Sharing it as a file failed too: {}".format(error, retry_error)
    logger.info("slack: shared %s into %s as a file", filename, channel)
    return {"channel": channel, "ts": None, "as_file": True}, None


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

    link = "{}/dashboards/{}".format(base_url(org), dashboard.slug or dashboard.id)
    if not org.get_setting("disable_public_urls"):
        # A dashboard's public link is an `ApiKey` row against it, not a
        # column: there is one only if somebody turned sharing on.
        key = models.ApiKey.get_by_object(dashboard)
        if key is not None:
            link = "{}/public/dashboards/{}".format(base_url(org), key.api_key)

    # None for an address nobody in a channel could open -- see `public_link`.
    if public_link(link) is None:
        logger.info(
            "slack: no button on dashboard %s: %s is not an address people in Slack can open (set SQLDESK_HOST)",
            dashboard.id,
            base_url(org) or "an empty SQLDESK_HOST",
        )
        return None
    return link


def as_of(dashboard):
    """ "as of" the oldest result on the dashboard, which is the honest figure."""
    oldest = None
    for widget in dashboard.widgets:
        query = widget.visualization.query_rel if widget.visualization else None
        retrieved = query.latest_query_data.retrieved_at if query and query.latest_query_data else None
        if retrieved and (oldest is None or retrieved < oldest):
            oldest = retrieved
    return "as of {}".format(oldest.strftime("%H:%M on %-d %B")) if oldest else None

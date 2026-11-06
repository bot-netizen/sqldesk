"""
What an alert actually says, in words, for the places that send it.

An alert message that reads "Orders just triggered" has told you the one
thing you already knew from the fact that it arrived. What somebody woken by
it needs is the number: *orders fell to 87, and the line is 100.* That is the
difference between a notification you act on and one you have to open a
browser to understand -- and since 0.7.9 recorded the value behind every fire,
there is no longer any excuse for leaving it out.

Shared by the Slack destinations rather than written twice. The email
destination has its own templates and a whole HTML body to put this in; Slack
has one line and has to spend it well.

Everything here is defensive to the point of looking paranoid, and that is
deliberate. This runs at the moment an alert has something to say, which is
the worst possible moment for the formatting of a message to be the thing
that fails. Every helper returns something printable or nothing at all;
nothing here raises.
"""

import logging

logger = logging.getLogger(__name__)

#: How an operator reads out loud. `>=` as "at or above" rather than
#: "greater than or equal to", which nobody says.
SAID = {
    ">": "above",
    ">=": "at or above",
    "<": "below",
    "<=": "at or below",
    "==": "equal to",
    "!=": "not equal to",
}

#: Past this, a number stops being readable at a glance and the message is
#: better off naming the column and leaving the value to the query page.
MAX_VALUE = 40


def _short(value):
    text = str(value)
    return text if len(text) <= MAX_VALUE else text[: MAX_VALUE - 1] + "…"


def condition(alert):
    """
    The rule, as one phrase: `orders below 100`.

    `{"column": "orders", "op": "<", "value": 100}` is three keys that have to
    be read together before they mean anything.
    """
    try:
        options = alert.options or {}
        column, op, value = options.get("column"), options.get("op"), options.get("value")
        if not column or op is None:
            return None
        return "{} {} {}".format(column, SAID.get(op, op), _short(value))
    except Exception:
        logger.warning("could not describe the condition on alert %s", getattr(alert, "id", "?"), exc_info=True)
        return None


def latest_value(alert):
    """
    What the column reads now, or None.

    From the query's stored result, which is the same thing the evaluation
    used -- so the number in the message is the number the decision was made
    on, rather than whatever the query would return if it were run again.
    """
    try:
        column = (alert.options or {}).get("column")
        data = alert.query_rel.latest_query_data.data
        rows = (data or {}).get("rows") or []
        if not column or not rows or column not in rows[0]:
            return None
        return rows[0][column]
    except Exception:
        logger.warning("could not read the value behind alert %s", getattr(alert, "id", "?"), exc_info=True)
        return None


def headline(alert, new_state):
    """
    The first line: what happened, with the number in it.

    A custom subject wins -- somebody who wrote one has said what they want
    this to read, and appending to it would be rewriting it.
    """
    try:
        custom = alert.subject_for(escape=False)
        if custom:
            return custom
    except Exception:
        logger.warning("could not render the subject for alert %s", getattr(alert, "id", "?"), exc_info=True)

    name = getattr(alert, "name", "An alert")
    if new_state != "triggered":
        return "{} went back to normal".format(name)

    value = latest_value(alert)
    rule = condition(alert)
    if value is not None and rule:
        # "Orders: 87, below 100" -- the state, the reading and the line it
        # crossed, in the order somebody checks them.
        return "{}: {}, {}".format(name, _short(value), rule)
    if rule:
        return "{}: {}".format(name, rule)
    return "{} just triggered".format(name)


def how_often(alert, fires_24h=None):
    """
    A flapping signal, or nothing.

    Four fires and four recoveries in an afternoon is a different problem from
    one fire that stayed, and the two are indistinguishable from a single
    message. Said only when it is more than one, because "fired 1 time in the
    last 24 hours" is noise on the alert that just fired.
    """
    try:
        if fires_24h is None:
            return None
        if fires_24h > 1:
            return "{} times in the last 24 hours".format(fires_24h)
        return None
    except Exception:
        return None


def links(alert, query, host):
    """The alert and its query, as Slack writes a link."""
    try:
        return "<{host}/alerts/{alert}|the alert> · <{host}/queries/{query}|the query>".format(
            host=host, alert=alert.id, query=query.id
        )
    except Exception:
        return None

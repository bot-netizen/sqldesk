import logging

import requests

from sqldesk.destinations import BaseDestination, register
from sqldesk.utils import json_dumps


class Slack(BaseDestination):
    @classmethod
    def configuration_schema(cls):
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "title": "Slack Webhook URL"},
            },
            "secret": ["url"],
        }

    @classmethod
    def icon(cls):
        return "fa-slack"

    def notify(self, alert, query, user, new_state, app, host, metadata, options):
        # Documentation: https://api.slack.com/docs/attachments
        fields = [
            {
                "title": "Query",
                "type": "mrkdwn",
                "value": "{host}/queries/{query_id}".format(host=host, query_id=query.id),
            },
            {
                "title": "Alert",
                "type": "mrkdwn",
                "value": "{host}/alerts/{alert_id}".format(host=host, alert_id=alert.id),
            },
        ]
        # Unescaped, and rendered once. Slack is not HTML, so a result
        # containing `&` should arrive as `&` rather than `&amp;` -- and
        # filling a template in is a query result read and a render, not
        # something to do twice to find out whether it is empty.
        body = alert.body_for(escape=False)
        if body:
            fields.append({"title": "Description", "value": body})
        if new_state == "triggered":
            text = alert.subject_for(escape=False) or alert.name + " just triggered"
            color = "#c0392b"
        else:
            text = alert.name + " went back to normal"
            color = "#27ae60"

        payload = {"attachments": [{"text": text, "color": color, "fields": fields}]}

        try:
            resp = requests.post(options.get("url"), data=json_dumps(payload).encode("utf-8"), timeout=5.0)
            logging.warning(resp.text)
            if resp.status_code != 200:
                logging.error("Slack send ERROR. status_code => {status}".format(status=resp.status_code))
        except Exception:
            logging.exception("Slack send ERROR.")


register(Slack)

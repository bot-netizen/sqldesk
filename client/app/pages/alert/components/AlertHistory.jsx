import React from "react";
import PropTypes from "prop-types";

import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { STATE_CLASS } from "../../alerts/AlertsList";

/*
  What this alert has actually been doing: its last ten changes of state.

  The page could already say where the alert is now and when it last moved,
  which answers "is this firing" and nothing else. An alert that has gone off
  six times since breakfast and one that went off once and stayed there look
  identical by that measure, and telling them apart is usually the question
  somebody opened the page to answer.

  Every state change, not only the fires: a recovery is how you read the shape
  of a flap. The count above the list is fires only, because "it went off
  twice" is what people mean.

  Each one says *when* as a time, not as "2 days ago": the question is
  usually "did it fire at 14:32, when the deploy went out", and a relative
  time cannot be matched against anything. The relative time is still there,
  underneath, for the glance.

  And each says what every destination did with it. "It fired but nothing
  arrived" used to be answerable only from the worker's log; the history now
  carries the answer -- sent to #ops, or not sent and Slack's reason why.
*/

/** "Thu, 13 Nov 2026, 14:32:05 EST" -- the viewer's own time, with its zone. */
export function firedAt(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  try {
    return new Intl.DateTimeFormat("en-GB", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZoneName: "short",
    }).format(date);
  } catch (error) {
    return date.toISOString();
  }
}

function Delivery({ delivery }) {
  const sent = !!delivery.ok;
  const mark = (
    <span className={`alert-history-delivery ${sent ? "is-sent" : "is-failed"}`} data-test="AlertHistoryDelivery">
      <i className={`fa ${sent ? "fa-check" : "fa-times"}`} aria-hidden="true" />
      <span className="sr-only">{sent ? "Sent to" : "Not sent to"}</span> {delivery.destination}
      {!sent && delivery.detail && <span className="alert-history-reason">: {delivery.detail}</span>}
    </span>
  );
  // A sent one's detail -- "with 1 of 1 picture" -- is a hover, not a line.
  return sent && delivery.detail ? <Tooltip title={delivery.detail}>{mark}</Tooltip> : mark;
}

Delivery.propTypes = {
  delivery: PropTypes.shape({
    destination: PropTypes.string,
    ok: PropTypes.bool,
    detail: PropTypes.string,
  }).isRequired,
};

function Sent({ fire }) {
  const triggered = fire.state === "triggered";
  if (!fire.notified) {
    // A muted alert still changes state. Showing it the same as a sent one
    // would have somebody hunting for a message that was never sent. A
    // recovery that sent nothing is the usual first reading, not news.
    return triggered ? (
      <Tooltip title="Nothing was sent: the alert was muted at the time.">
        <span className="alert-history-silent">
          <i className="fa fa-bell-slash-o" aria-hidden="true" /> Not sent: muted
        </span>
      </Tooltip>
    ) : null;
  }
  if (!Array.isArray(fire.deliveries)) {
    // From before the outcome was kept: something was sent, and that is all
    // that is known.
    return null;
  }
  if (fire.deliveries.length === 0) {
    return (
      <span className="alert-history-delivery is-failed" data-test="AlertHistoryNobody">
        <i className="fa fa-times" aria-hidden="true" /> Sent to nobody: this alert has no destinations
      </span>
    );
  }
  return fire.deliveries.map((delivery, index) => (
    // eslint-disable-next-line react/no-array-index-key
    <Delivery key={`${delivery.destination}-${index}`} delivery={delivery} />
  ));
}

function Fire({ fire }) {
  return (
    <li className="alert-history-item" data-test="AlertHistoryItem">
      <div className="alert-history-line">
        <span className={`label ${STATE_CLASS[fire.state]} alert-history-state`}>{fire.state}</span>
        {fire.value !== null && fire.value !== undefined && (
          // The number the decision was made on. "It fired" is a fact; "it
          // fired at 412" is the one worth being woken for.
          <span className="alert-history-value">{fire.value}</span>
        )}
        <time className="alert-history-when" dateTime={fire.created_at}>
          {firedAt(fire.created_at)}
        </time>
      </div>
      <div className="alert-history-detail">
        <span className="alert-history-ago">
          <TimeAgo date={fire.created_at} />
        </span>
        <Sent fire={fire} />
      </div>
    </li>
  );
}

Fire.propTypes = {
  fire: PropTypes.shape({
    state: PropTypes.string.isRequired,
    value: PropTypes.string,
    notified: PropTypes.bool,
    deliveries: PropTypes.arrayOf(PropTypes.object),
    created_at: PropTypes.string,
  }).isRequired,
};

export default function AlertHistory({ history, fires24h }) {
  if (!history || history.length === 0) {
    return (
      <div className="alert-history">
        <h4 className="alert-history-title">History</h4>
        <p className="alert-history-empty">
          Nothing yet. This fills in as the alert changes state, so a new alert is blank rather than broken.
        </p>
      </div>
    );
  }

  return (
    <div className="alert-history">
      <h4 className="alert-history-title">
        History <span className="alert-history-scope">the last {history.length} changes</span>
      </h4>
      {fires24h > 0 && (
        <p className="alert-history-count">
          Fired <strong>{fires24h}</strong> {fires24h === 1 ? "time" : "times"} in the last 24 hours.
        </p>
      )}
      <ul className="alert-history-list">
        {history.map((fire, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <Fire key={`${fire.created_at}-${index}`} fire={fire} />
        ))}
      </ul>
    </div>
  );
}

AlertHistory.propTypes = {
  history: PropTypes.arrayOf(PropTypes.object),
  fires24h: PropTypes.number,
};

AlertHistory.defaultProps = {
  history: [],
  fires24h: 0,
};

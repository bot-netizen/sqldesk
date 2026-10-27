import React from "react";
import PropTypes from "prop-types";

import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { STATE_CLASS } from "../../alerts/AlertsList";

/*
  What this alert has actually been doing.

  The page could already say where the alert is now and when it last moved,
  which answers "is this firing" and nothing else. An alert that has gone off
  six times since breakfast and one that went off once and stayed there look
  identical by that measure, and telling them apart is usually the question
  somebody opened the page to answer.

  Every state change, not only the fires: a recovery is how you read the shape
  of a flap. The count above the list is fires only, because "it went off
  twice" is what people mean.
*/

function Fire({ fire }) {
  const triggered = fire.state === "triggered";
  return (
    <li className="alert-history-item">
      <span className={`label ${STATE_CLASS[fire.state]} alert-history-state`}>{fire.state}</span>
      {fire.value !== null && fire.value !== undefined && (
        // The number the decision was made on. "It fired" is a fact; "it
        // fired at 412" is the one worth being woken for.
        <span className="alert-history-value">{fire.value}</span>
      )}
      <span className="alert-history-when">
        <TimeAgo date={fire.created_at} />
      </span>
      {triggered && !fire.notified && (
        <Tooltip title="Nothing was sent: the alert was muted at the time.">
          <span className="alert-history-silent">
            <i className="fa fa-bell-slash-o" aria-hidden="true" />
            <span className="sr-only">Not sent</span>
          </span>
        </Tooltip>
      )}
    </li>
  );
}

Fire.propTypes = {
  fire: PropTypes.shape({
    state: PropTypes.string.isRequired,
    value: PropTypes.string,
    notified: PropTypes.bool,
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
      <h4 className="alert-history-title">History</h4>
      {fires24h > 0 && (
        <p className="alert-history-count">
          Fired <strong>{fires24h}</strong> {fires24h === 1 ? "time" : "times"} in the last 24 hours.
        </p>
      )}
      <ul className="alert-history-list">
        {history.map((fire, index) => (
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

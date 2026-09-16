import React from "react";
import PropTypes from "prop-types";
import { get } from "lodash";
import Tooltip from "@/components/Tooltip";

import "./QueryHealth.less";

// A scheduled query is called stale once it has missed its window by a clear
// margin. Two intervals rather than one, so a run that merely starts late
// does not flap the whole list into a warning state.
export const STALE_INTERVAL_MULTIPLIER = 2;

/*
  Derives a query's execution health from what the list endpoint already
  serves — schedule_failures, retrieved_at and schedule — so a list view
  never has to fetch a result to say whether a query is healthy.

  Returns null when the caller did not request stats (schedule_failures
  undefined), so the column can render nothing rather than claim a query is
  fine when we simply do not know.
*/
export function getQueryHealth(query, now = Date.now()) {
  if (!query || query.schedule_failures === undefined) {
    return null;
  }

  const failures = query.schedule_failures || 0;
  if (failures > 0) {
    return {
      key: "failing",
      label: "Failing",
      tone: "critical",
      detail: `Last ${failures} scheduled ${failures === 1 ? "run" : "runs"} failed`,
    };
  }

  if (!query.retrieved_at) {
    return { key: "never", label: "Never run", tone: "neutral", detail: "This query has no results yet" };
  }

  const interval = get(query, "schedule.interval");
  if (interval) {
    const ageSeconds = (now - Date.parse(query.retrieved_at)) / 1000;
    if (ageSeconds > interval * STALE_INTERVAL_MULTIPLIER) {
      return {
        key: "stale",
        label: "Stale",
        tone: "warning",
        detail: "Older than its refresh schedule — the last scheduled run may not have completed",
      };
    }
  }

  return { key: "ok", label: "OK", tone: "good", detail: "Last run completed successfully" };
}

export default function QueryHealth({ query }) {
  const health = getQueryHealth(query);
  if (!health) {
    return null;
  }

  return (
    <Tooltip title={health.detail}>
      <span className={`query-health query-health-${health.tone}`}>
        <span className="query-health-dot" aria-hidden="true" />
        {health.label}
      </span>
    </Tooltip>
  );
}

QueryHealth.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  query: PropTypes.object,
};

QueryHealth.defaultProps = {
  query: null,
};

import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "@/components/Tooltip";
import { formatDateTime } from "@/lib/utils";

import "./LiveBadge.less";

export const LIVE_INTERVAL_LABELS = {
  30: "every 30 seconds",
  60: "every minute",
  120: "every 2 minutes",
  300: "every 5 minutes",
};

/**
 * "● Live · every 30 seconds", or "Paused by Iqbal". The dot pulses while
 * live, and stays still for anyone who prefers reduced motion.
 */
export default function LiveBadge({ live }) {
  if (!live) {
    return null;
  }
  const paused = !!live.paused;
  const who = paused && live.paused_by && live.paused_by.name;
  const detail = paused ? (who ? `by ${who}` : "") : LIVE_INTERVAL_LABELS[live.interval] || "";
  const badge = (
    <span className={cx("live-badge", { "live-badge-paused": paused })} data-test="LiveBadge" role="status">
      <span className="live-badge-dot" aria-hidden="true" />
      <span className="live-badge-state">{paused ? "Paused" : "Live"}</span>
      {detail && <span className="live-badge-detail">{detail}</span>}
    </span>
  );
  return paused && live.paused_at ? (
    <Tooltip title={`Paused ${formatDateTime(live.paused_at)}`}>{badge}</Tooltip>
  ) : (
    badge
  );
}

LiveBadge.propTypes = {
  live: PropTypes.shape({
    interval: PropTypes.number,
    paused: PropTypes.bool,
    paused_by: PropTypes.shape({ name: PropTypes.string }),
    paused_at: PropTypes.string,
  }),
};

LiveBadge.defaultProps = {
  live: null,
};

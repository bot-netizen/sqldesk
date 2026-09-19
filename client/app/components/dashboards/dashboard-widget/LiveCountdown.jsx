import React, { useEffect, useState } from "react";
import PropTypes from "prop-types";
import moment from "moment";
import TimeAgo from "@/components/TimeAgo";
import { serverNow } from "@/lib/serverClock";

export function formatRemaining(seconds) {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

/*
  One line under a live widget: how long until the server refreshes it, or
  when it last did if the dashboard is paused -- never both.
*/
export default function LiveCountdown({ updatedAt, interval }) {
  const [now, setNow] = useState(serverNow);

  useEffect(() => {
    if (!interval) {
      return undefined;
    }
    const timer = setInterval(() => setNow(serverNow()), 1000);
    return () => clearInterval(timer);
  }, [interval]);

  // Paused: nothing is coming, so say how old what is on screen is.
  if (!interval) {
    return (
      <span className="small hidden-print" data-test="LiveCountdown">
        updated <TimeAgo date={updatedAt} />
      </span>
    );
  }

  const due = moment(updatedAt).valueOf() + interval * 1000;
  const remaining = Math.ceil((due - now) / 1000);
  return (
    <span className="small hidden-print" data-test="LiveCountdown">
      {remaining > 0 ? `next in ${formatRemaining(remaining)}` : "refreshing…"}
    </span>
  );
}

LiveCountdown.propTypes = {
  updatedAt: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.object]).isRequired,
  // Seconds between refreshes while running; null while paused.
  interval: PropTypes.number,
};

LiveCountdown.defaultProps = { interval: null };

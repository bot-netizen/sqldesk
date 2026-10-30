import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import Tooltip from "@/components/Tooltip";

import "./StreamMarker.less";

/*
  What this panel's topic is doing, in the corner of the panel.

  Small on purpose. Every number the stream editor shows would turn each panel
  into a status board, and a dashboard of eight of those is unreadable. So the
  corner carries the one thing that changes how you read the chart, and the
  rest is a hover away.

  The order matters, because it is the order somebody needs it in:

  1. **sampled** -- loudest, and never silent. A count from a sampled stream
     is an estimate; a chart that does not say so is quietly lying.
  2. **not consuming** -- paused, or quiet, or stopped with an error. A chart
     that stopped moving twenty minutes ago looks exactly like one keeping up,
     and this is the only thing on the page that tells them apart.
  3. **consuming** -- the rate, quietly, because a number that moves is how
     somebody sees at a glance that data is still arriving.
*/

/** A rate a person can read, rather than seventeen digits of false precision. */
export function rate(events) {
  const n = Number(events) || 0;
  if (n === 0) {
    return "0";
  }
  if (n >= 10000) {
    return `${Math.round(n / 1000)}k`;
  }
  if (n >= 100) {
    return String(Math.round(n));
  }
  if (n >= 10) {
    return n.toFixed(1);
  }
  return n.toFixed(2).replace(/\.?0+$/, "");
}

export function detail(stream) {
  const lines = [`${stream.topic} · ${rate(stream.observed_rate)} events a second`];
  if (stream.describes) {
    lines.push(stream.describes);
  }
  if (stream.sampled) {
    lines.push(`Sampled 1 in ${stream.sample_rate}: counts drawn from this are estimates.`);
  }
  if (stream.watchers) {
    lines.push(`${stream.watchers} ${stream.watchers === 1 ? "person is" : "people are"} watching it.`);
  }
  if (stream.last_error) {
    lines.push(stream.last_error);
  }
  return lines.join("\n");
}

export default function StreamMarker({ stream }) {
  if (!stream) {
    return null;
  }
  const consuming = stream.state === "running";
  const sampled = !!stream.sampled;
  const label = sampled ? `1 in ${stream.sample_rate}` : consuming ? `${rate(stream.observed_rate)}/s` : "paused";

  return (
    <Tooltip title={detail(stream)}>
      <span
        className={cx("stream-marker", {
          "stream-marker-sampled": sampled,
          "stream-marker-paused": !consuming,
        })}
        data-test="StreamMarker"
        role="status"
      >
        <span className="stream-marker-dot" aria-hidden="true" />
        <span className="stream-marker-label">{label}</span>
        {sampled && <span className="sr-only"> sampled, so counts from this chart are estimates</span>}
        {!consuming && <span className="sr-only"> this topic is not being consumed</span>}
      </span>
    </Tooltip>
  );
}

StreamMarker.propTypes = {
  stream: PropTypes.shape({
    topic: PropTypes.string,
    state: PropTypes.string,
    observed_rate: PropTypes.number,
    sampled: PropTypes.bool,
    sample_rate: PropTypes.number,
    describes: PropTypes.string,
    watchers: PropTypes.number,
    last_error: PropTypes.string,
  }),
};

StreamMarker.defaultProps = { stream: null };

/*
  The same thing for the whole board, beside the Live badge.

  Honest when the panels disagree: "2 of 3 streams consuming" rather than a
  badge that describes the redraw and lets somebody assume it describes the
  data.
*/
export function StreamRollup({ summary }) {
  if (!summary) {
    return null;
  }
  return (
    <span
      className={cx("stream-rollup", {
        "stream-rollup-partial": summary.consuming < summary.total,
        "stream-rollup-sampled": summary.sampled > 0,
      })}
      data-test="StreamRollup"
      role="status"
    >
      {summary.state}
      {summary.sampling && <span className="stream-rollup-sampling">{summary.sampling}</span>}
    </span>
  );
}

StreamRollup.propTypes = {
  summary: PropTypes.shape({
    state: PropTypes.string,
    consuming: PropTypes.number,
    total: PropTypes.number,
    sampled: PropTypes.number,
    sampling: PropTypes.string,
  }),
};

StreamRollup.defaultProps = { summary: null };

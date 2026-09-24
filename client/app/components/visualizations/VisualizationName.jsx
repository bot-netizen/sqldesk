import React from "react";
import PropTypes from "prop-types";
import { VisualizationType, registeredVisualizations } from "@sqldesk/viz/lib";

import "./VisualizationName.less";

function sameName(a, b) {
  return (
    String(a || "")
      .trim()
      .toLowerCase() ===
    String(b || "")
      .trim()
      .toLowerCase()
  );
}

/**
 * A visualization's own name, or null when it does not have one worth saying:
 * the type's default ("Chart"), or the query's name over again.
 *
 * Exported because a caller sometimes has to know *whether* there is one
 * before deciding what else to draw -- a dashboard widget shows the query's
 * name only when the visualization has none.
 */
export function visualizationNameOf(visualization, queryName) {
  const config = visualization && registeredVisualizations[visualization.type];
  if (!config || !visualization.name) {
    return null;
  }
  if (visualization.name === config.name || sameName(visualization.name, queryName)) {
    return null;
  }
  return visualization.name;
}

// Shown before the query's name, and only when it says something the query's
// name does not.
function VisualizationName({ visualization, queryName }) {
  return <span className="visualization-name">{visualizationNameOf(visualization, queryName)}</span>;
}

VisualizationName.propTypes = {
  visualization: VisualizationType.isRequired,
  queryName: PropTypes.string,
};

VisualizationName.defaultProps = { queryName: null };

export default VisualizationName;

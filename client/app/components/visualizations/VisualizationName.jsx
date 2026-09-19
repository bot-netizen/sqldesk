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

// Shown before the query's name, and only when it says something the query's
// name does not: not the type's default name, and not the query's name again.
function VisualizationName({ visualization, queryName }) {
  const config = registeredVisualizations[visualization.type];
  const shown = config && visualization.name !== config.name && !sameName(visualization.name, queryName);
  return <span className="visualization-name">{shown ? visualization.name : null}</span>;
}

VisualizationName.propTypes = {
  visualization: VisualizationType.isRequired,
  queryName: PropTypes.string,
};

VisualizationName.defaultProps = { queryName: null };

export default VisualizationName;

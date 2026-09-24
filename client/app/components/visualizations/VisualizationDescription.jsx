import React from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import { trim } from "lodash";
import Tooltip from "@/components/Tooltip";
import PlainButton from "@/components/PlainButton";

import "./VisualizationDescription.less";

/*
  What a visualization is of, when its name does not say it.

  `Visualization.description` has been a column, serialized by the API and
  accepted on save, since before the fork -- and has never been editable or
  shown anywhere. A chart called "By week" on a dashboard beside four others
  needs somewhere to say which weeks, and which of the query's columns it is
  counting.

  An icon rather than a line of text, because a widget's header is already
  the query's name, the query's own description and the parameters, and the
  point of a dashboard is the charts. The table's column headers do the same
  thing with the same icon -- except that they leave the text unreachable to
  anyone not using a mouse, since a tooltip on an `aria-hidden` icon is
  nothing at all. Here the words are in the document, and the icon is a real
  button, so it can be reached by keyboard and tapped on a phone, where
  hovering is not a thing that happens.
*/
export default function VisualizationDescription({ description, className }) {
  const text = trim(description || "");
  if (!text) {
    return null;
  }

  return (
    <Tooltip placement="top" title={text}>
      <PlainButton className={cx("visualization-description", className)} data-test="VisualizationDescription">
        <i className="fa fa-info-circle" aria-hidden="true" />
        <span className="sr-only">{text}</span>
      </PlainButton>
    </Tooltip>
  );
}

VisualizationDescription.propTypes = {
  description: PropTypes.string,
  className: PropTypes.string,
};

VisualizationDescription.defaultProps = {
  description: "",
  className: null,
};

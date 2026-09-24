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

  A mark rather than a line of text, because a widget's header is already
  the name, the query's own description and the parameters, and the point of
  a dashboard is the charts. The table's column headers do the same thing --
  except that they leave the text unreachable to anyone not using a mouse,
  since a tooltip on an `aria-hidden` icon is nothing at all. Here the words
  are in the document, and the mark is a real button, so it can be reached by
  keyboard and tapped on a phone, where hovering is not a thing that happens.

  A ring rather than Font Awesome's filled disc. At the size a header wants
  it, a solid circle is a dark blot that pulls the eye off the name it is
  attached to; a hairline ring says the same thing and sits still.
*/
export default function VisualizationDescription({ description, className }) {
  const text = trim(description || "");
  if (!text) {
    return null;
  }

  return (
    <Tooltip placement="top" title={text}>
      <PlainButton className={cx("visualization-description", className)} data-test="VisualizationDescription">
        <span className="visualization-description-mark" aria-hidden="true">
          i
        </span>
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

import React from "react";
import "./problem.less";

/*
  What a visualization draws when it cannot draw itself.

  There were three of these -- gauge, progress and status-grid -- each with its
  own class, its own CSS and the same words, and three more visualizations
  (funnel, sunburst, sankey) that rendered an empty box and said nothing at
  all. One condition, four behaviours.

  The style deliberately works in both places it is used: a box with a height
  of its own (a gauge fills its widget) centres the message vertically, and a
  box that grows with its content (progress) just gets a padded paragraph.
*/

/** The one wording for "there is nothing here yet", so it reads the same everywhere. */
export const NO_ROWS = "No rows to show.";

interface ProblemProps {
  children: React.ReactNode;
}

export default function Problem({ children }: ProblemProps) {
  // A live region: the message usually appears when a result arrives, which is
  // after the page has been read, and it is the whole of what the widget says.
  return (
    <p className="visualization-problem" role="status" data-test="VisualizationProblem">
      {children}
    </p>
  );
}

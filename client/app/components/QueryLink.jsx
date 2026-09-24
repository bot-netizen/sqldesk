import React from "react";
import PropTypes from "prop-types";
import { VisualizationType } from "@sqldesk/viz/lib";
import Link from "@/components/Link";
import { visualizationNameOf } from "@/components/visualizations/VisualizationName";

import "./QueryLink.less";

/*
  The title of a dashboard widget.

  One name, not two. Five widgets over one query used to carry that query's
  name five times, which told a reader nothing they could not see from the
  five widgets sitting together -- and pushed the name that *does* distinguish
  them into second place. So the visualization's own name is the title when it
  has one, and the query's name is the title when it does not.

  Nothing is lost: the whole title is still a link to the query, and the
  query's name is on the link's tooltip.

  The expanded dialog and the standalone embed page still show both. Neither
  of them has the repetition problem -- each is one visualization on its own --
  and on an embed the query's name is the only context there is.
*/
function QueryLink({ query, visualization, readOnly }) {
  const getUrl = () => {
    let hash = null;
    if (visualization) {
      if (visualization.type === "TABLE") {
        // link to hard-coded table tab instead of the (hidden) visualization tab
        hash = "table";
      } else {
        hash = visualization.id;
      }
    }

    return query.getUrl(false, hash);
  };

  const name = visualizationNameOf(visualization, query.name);

  const QueryLinkWrapper = (props) => (readOnly ? <span {...props} /> : <Link href={getUrl()} {...props} />);

  return (
    <QueryLinkWrapper className="query-link" title={name ? query.name : null}>
      {name ? <span className="visualization-name">{name}</span> : <span>{query.name}</span>}
    </QueryLinkWrapper>
  );
}

QueryLink.propTypes = {
  query: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  visualization: VisualizationType,
  readOnly: PropTypes.bool,
};

QueryLink.defaultProps = {
  visualization: null,
  readOnly: false,
};

export default QueryLink;

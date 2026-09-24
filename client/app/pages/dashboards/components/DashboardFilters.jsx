import React from "react";
import PropTypes from "prop-types";
import { isEmpty } from "lodash";
import useMedia from "use-media";
import Badge from "antd/lib/badge";
import Button from "antd/lib/button";
import Popover from "antd/lib/popover";
import Parameters from "@/components/Parameters";
import Filters from "@/components/Filters";

import "./DashboardFilters.less";

/*
  A dashboard's filters, in the header rather than in a band of their own.

  They used to get a full-width white card above the grid: measured, 93px
  plus its margin for a single 92-pixel dropdown, pushing the first widget
  down by a tenth of a screen on every dashboard that had one parameter.

  A few controls fit beside the Refresh button and cost nothing. More than a
  few would wrap the header, so past that they collapse into one button with
  a count -- which is also what happens on a narrow screen, and whenever
  there are column filters, because those are laid out as half-width rows and
  have no compact form.
*/

/** Above this many, the header would start wrapping. */
const INLINE_LIMIT = 3;

export default function DashboardFilters({ dashboardConfiguration, onParametersEdit }) {
  const { globalParameters, refreshDashboard, filters, setFilters, live } = dashboardConfiguration;

  // A live dashboard shows the result the server makes, from the saved
  // parameter values; offering a viewer a control that changes nothing would
  // be a lie.
  const parameters = live ? [] : globalParameters;
  const roomForInline = useMedia({ minWidth: 992 });

  const total = parameters.length + filters.length;
  if (total === 0) {
    return null;
  }

  const inline = roomForInline && isEmpty(filters) && parameters.length <= INLINE_LIMIT;

  if (inline) {
    return (
      <span className="dashboard-filters dashboard-filters-inline hidden-print" data-test="DashboardFilters">
        <Parameters parameters={parameters} onValuesChange={refreshDashboard} onParametersEdit={onParametersEdit} />
      </span>
    );
  }

  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      overlayClassName="dashboard-filters-popover"
      content={
        <div className="dashboard-filters-panel" data-test="DashboardFiltersPanel">
          {!isEmpty(parameters) && (
            <Parameters parameters={parameters} onValuesChange={refreshDashboard} onParametersEdit={onParametersEdit} />
          )}
          {!isEmpty(filters) && <Filters filters={filters} onChange={setFilters} />}
        </div>
      }
    >
      <Button className="m-r-5 dashboard-filters-button" data-test="DashboardFiltersButton">
        <i className="fa fa-filter m-r-5" aria-hidden="true" />
        Filters
        <Badge className="m-l-5" count={total} showZero={false} overflowCount={99} />
      </Button>
    </Popover>
  );
}

DashboardFilters.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  onParametersEdit: PropTypes.func,
};

DashboardFilters.defaultProps = {
  onParametersEdit: () => {},
};

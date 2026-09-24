import React from "react";
import PropTypes from "prop-types";
import { isEmpty } from "lodash";
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
  Column filters got a second card under it.

  One button, whatever is behind it. Laying a few of them out inline and the
  rest in a panel meant the header changed shape with the dashboard -- and a
  dashboard that gained a fourth parameter rearranged its own header. A
  count on a button says the same thing in the same place every time.

  While the layout is being edited they go back to a row: there they are
  dragged into order, and drag handles want the room -- see DashboardPage.
*/
export default function DashboardFilters({ dashboardConfiguration, onParametersEdit }) {
  const { globalParameters, refreshDashboard, filters, setFilters, live } = dashboardConfiguration;

  // A live dashboard shows the result the server makes, from the saved
  // parameter values; offering a viewer a control that changes nothing would
  // be a lie. Column filters still work, because those filter rows that are
  // already in the browser.
  const parameters = live ? [] : globalParameters;

  const total = parameters.length + filters.length;
  if (total === 0) {
    return null;
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

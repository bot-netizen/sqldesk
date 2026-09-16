import React from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import SchedulePhrase from "@/components/queries/SchedulePhrase";

import "./QueryScheduleControl.less";

// The editor's left rail is for things you read while writing SQL (schema,
// lineage). A refresh schedule is something you act on, so it lives with the
// other header actions instead, next to "Show Results Only".
export default function QueryScheduleControl({ query, onEditSchedule, disabled }) {
  return (
    <Button
      className="query-schedule-control m-r-5"
      onClick={onEditSchedule}
      disabled={disabled}
      data-test="QueryPageScheduleControl"
    >
      <i className="zmdi zmdi-refresh" aria-hidden="true" />
      <span className="query-schedule-control-label">Refresh Schedule</span>
      <span className="query-schedule-control-value">
        <SchedulePhrase isNew={query.isNew()} schedule={query.schedule} />
      </span>
    </Button>
  );
}

QueryScheduleControl.propTypes = {
  query: PropTypes.shape({
    schedule: PropTypes.object, // eslint-disable-line react/forbid-prop-types
    isNew: PropTypes.func.isRequired,
  }).isRequired,
  onEditSchedule: PropTypes.func,
  disabled: PropTypes.bool,
};

QueryScheduleControl.defaultProps = {
  onEditSchedule: () => {},
  disabled: false,
};

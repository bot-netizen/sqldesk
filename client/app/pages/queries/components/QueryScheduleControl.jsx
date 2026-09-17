import { map } from "lodash";
import React, { useMemo } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import DownOutlinedIcon from "@ant-design/icons/DownOutlined";
import CheckOutlinedIcon from "@ant-design/icons/CheckOutlined";
import SchedulePhrase from "@/components/queries/SchedulePhrase";
import { durationHumanize } from "@/lib/utils";

import "./QueryScheduleControl.less";

const NEVER = "never";
const CUSTOM = "custom";

// The editor's left rail is for things you read while writing SQL (schema,
// lineage). A refresh schedule is something you act on, so it lives with the
// other header actions instead.
//
// Picking an interval is the whole job nine times out of ten, so it happens in
// the menu. The dialog stays for what a menu cannot hold: a time of day, a
// weekday, and an end date.
export default function QueryScheduleControl({ query, refreshOptions, onSelectInterval, onEditSchedule, disabled }) {
  const currentInterval = (query.schedule && query.schedule.interval) || null;

  const menu = useMemo(() => {
    const selected = (value) =>
      value === currentInterval ? (
        <CheckOutlinedIcon className="query-schedule-control-check" aria-hidden="true" />
      ) : (
        <span className="query-schedule-control-check-placeholder" aria-hidden="true" />
      );

    const onClick = ({ key }) => {
      if (key === CUSTOM) {
        onEditSchedule();
      } else if (key === NEVER) {
        onSelectInterval(null);
      } else {
        onSelectInterval(Number(key));
      }
    };

    return (
      <Menu onClick={onClick} selectedKeys={[currentInterval ? String(currentInterval) : NEVER]}>
        <Menu.Item key={NEVER}>
          {selected(null)}
          Never
        </Menu.Item>
        <Menu.Divider />
        {map(refreshOptions, (seconds) => (
          <Menu.Item key={String(seconds)}>
            {selected(seconds)}
            Every {durationHumanize(seconds, { omitSingleValueNumber: true })}
          </Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item key={CUSTOM} data-test="EditSchedule">
          <span className="query-schedule-control-check-placeholder" aria-hidden="true" />
          At a set time&hellip;
        </Menu.Item>
      </Menu>
    );
  }, [currentInterval, refreshOptions, onSelectInterval, onEditSchedule]);

  return (
    <Dropdown overlay={menu} trigger={["click"]} disabled={disabled} placement="bottomRight">
      <Button className="query-schedule-control m-r-5" disabled={disabled} data-test="QueryPageScheduleControl">
        <i className="zmdi zmdi-refresh" aria-hidden="true" />
        <span className="query-schedule-control-label">Refresh</span>
        <span className="query-schedule-control-value">
          <SchedulePhrase isNew={query.isNew()} schedule={query.schedule} />
        </span>
        <DownOutlinedIcon className="query-schedule-control-caret" aria-hidden="true" />
      </Button>
    </Dropdown>
  );
}

QueryScheduleControl.propTypes = {
  query: PropTypes.shape({
    schedule: PropTypes.object, // eslint-disable-line react/forbid-prop-types
    isNew: PropTypes.func.isRequired,
  }).isRequired,
  refreshOptions: PropTypes.arrayOf(PropTypes.number),
  onSelectInterval: PropTypes.func,
  onEditSchedule: PropTypes.func,
  disabled: PropTypes.bool,
};

QueryScheduleControl.defaultProps = {
  refreshOptions: [],
  onSelectInterval: () => {},
  onEditSchedule: () => {},
  disabled: false,
};

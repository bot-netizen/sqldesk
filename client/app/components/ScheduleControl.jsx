import { includes, map } from "lodash";
import React, { useMemo } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import DownOutlinedIcon from "@ant-design/icons/DownOutlined";
import CheckOutlinedIcon from "@ant-design/icons/CheckOutlined";
import SchedulePhrase from "@/components/queries/SchedulePhrase";
import { durationHumanize } from "@/lib/utils";

import "./ScheduleControl.less";

const NEVER = "never";
const CUSTOM = "custom";

// The five people actually reach for. The full list this installation allows
// runs to twenty-one entries, from a minute to a month, which is a scrolling
// menu to choose something everybody picks from the first handful of. Anything
// else is a crontab expression, which says it exactly rather than approximately.
const COMMON_INTERVALS = [300, 600, 900, 1800, 3600];

// Shared by the query editor and the dashboard header. A query's schedule runs
// the query; a dashboard's runs every query behind its widgets. Same shape,
// same expression, same menu.
export default function ScheduleControl({ schedule, isNew, label, refreshOptions, onSelectInterval, onEditCron, disabled }) {
  const current = schedule || {};
  const currentCron = current.cron || null;
  const currentInterval = (!currentCron && current.interval) || null;

  // An installation can narrow what it allows, and a policy can narrow it
  // further; offering an interval that would be refused is worse than a shorter
  // menu. An empty list means no restriction has been expressed.
  const intervals = useMemo(
    () =>
      refreshOptions && refreshOptions.length > 0
        ? COMMON_INTERVALS.filter((seconds) => includes(refreshOptions, seconds))
        : COMMON_INTERVALS,
    [refreshOptions]
  );

  const menu = useMemo(() => {
    const tick = (isSelected) =>
      isSelected ? (
        <CheckOutlinedIcon className="query-schedule-control-check" aria-hidden="true" />
      ) : (
        <span className="query-schedule-control-check-placeholder" aria-hidden="true" />
      );

    const onClick = ({ key }) => {
      if (key === CUSTOM) {
        onEditCron();
      } else if (key === NEVER) {
        onSelectInterval(null);
      } else {
        onSelectInterval(Number(key));
      }
    };

    let selectedKey = NEVER;
    if (currentCron) {
      selectedKey = CUSTOM;
    } else if (currentInterval) {
      selectedKey = String(currentInterval);
    }

    return (
      <Menu onClick={onClick} selectedKeys={[selectedKey]}>
        <Menu.Item key={NEVER}>
          {tick(selectedKey === NEVER)}
          Never
        </Menu.Item>
        <Menu.Divider />
        {map(intervals, (seconds) => (
          <Menu.Item key={String(seconds)}>
            {tick(selectedKey === String(seconds))}
            Every {durationHumanize(seconds, { omitSingleValueNumber: true })}
          </Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item key={CUSTOM} data-test="EditSchedule">
          {tick(selectedKey === CUSTOM)}
          Custom&hellip;
        </Menu.Item>
      </Menu>
    );
  }, [currentCron, currentInterval, intervals, onSelectInterval, onEditCron]);

  return (
    <Dropdown overlay={menu} trigger={["click"]} disabled={disabled} placement="bottomRight">
      <Button className="query-schedule-control m-r-5" disabled={disabled} data-test="QueryPageScheduleControl">
        <i className="zmdi zmdi-refresh" aria-hidden="true" />
        <span className="query-schedule-control-label">{label}</span>
        <span className="query-schedule-control-value">
          <SchedulePhrase isNew={isNew} schedule={schedule} />
        </span>
        <DownOutlinedIcon className="query-schedule-control-caret" aria-hidden="true" />
      </Button>
    </Dropdown>
  );
}

ScheduleControl.propTypes = {
  schedule: PropTypes.object, // eslint-disable-line react/forbid-prop-types
  isNew: PropTypes.bool,
  label: PropTypes.string,
  refreshOptions: PropTypes.arrayOf(PropTypes.number),
  onSelectInterval: PropTypes.func,
  onEditCron: PropTypes.func,
  disabled: PropTypes.bool,
};

ScheduleControl.defaultProps = {
  schedule: null,
  isNew: false,
  label: "Refresh",
  refreshOptions: [],
  onSelectInterval: () => {},
  onEditCron: () => {},
  disabled: false,
};

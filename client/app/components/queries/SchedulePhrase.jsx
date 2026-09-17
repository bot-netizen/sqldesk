import React from "react";
import PropTypes from "prop-types";
import Tooltip from "@/components/Tooltip";
import PlainButton from "@/components/PlainButton";
import { localizeTime, durationHumanize } from "@/lib/utils";
import { RefreshScheduleType, RefreshScheduleDefault } from "../proptypes";

import "./SchedulePhrase.less";

export default class SchedulePhrase extends React.Component {
  static propTypes = {
    schedule: RefreshScheduleType,
    isNew: PropTypes.bool.isRequired,
    isLink: PropTypes.bool,
    onClick: PropTypes.func,
  };

  static defaultProps = {
    schedule: RefreshScheduleDefault,
    isLink: false,
    onClick: () => {},
  };

  get content() {
    const schedule = this.props.schedule || SchedulePhrase.defaultProps.schedule;

    // A custom schedule is shown as what was typed. Nothing here turns cron
    // into prose: a half-right paraphrase of "0 9 * * 1-5" is worse than the
    // expression, because the person who wrote it can read it back and check.
    if (schedule.cron) {
      return [schedule.cron, `Refreshes on the crontab schedule ${schedule.cron} (UTC)`];
    }

    const { interval: seconds } = schedule;
    if (!seconds) {
      return ["Never"];
    }
    const humanized = durationHumanize(seconds, {
      omitSingleValueNumber: true,
    });
    const short = `Every ${humanized}`;
    let full = `Refreshes every ${humanized}`;

    const { time, day_of_week: dayOfWeek } = this.props.schedule;
    if (time) {
      full += ` at ${localizeTime(time)}`;
    }
    if (dayOfWeek) {
      full += ` on ${dayOfWeek}`;
    }

    return [short, full];
  }

  render() {
    if (this.props.isNew) {
      return "Never";
    }

    const [short, full] = this.content;
    const content = full ? <Tooltip title={full}>{short}</Tooltip> : short;

    return this.props.isLink ? (
      <PlainButton type="link" className="schedule-phrase" onClick={this.props.onClick} data-test="EditSchedule">
        {content}
      </PlainButton>
    ) : (
      content
    );
  }
}

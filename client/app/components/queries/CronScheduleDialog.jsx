import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import Typography from "antd/lib/typography";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

import "./CronScheduleDialog.less";

const FIELD_COUNT = 5;

// Named values croniter accepts in the month and weekday fields.
const MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec";
const WEEKDAYS = "sun|mon|tue|wed|thu|fri|sat";

// Ranges each field allows. Day-of-week takes 0-7 because both 0 and 7 mean
// Sunday, which is the one place cron is not zero-based in the obvious way.
const FIELDS = [
  { name: "minute", min: 0, max: 59, names: null },
  { name: "hour", min: 0, max: 23, names: null },
  { name: "day of the month", min: 1, max: 31, names: null },
  { name: "month", min: 1, max: 12, names: MONTHS },
  { name: "day of the week", min: 0, max: 7, names: WEEKDAYS },
];

function isValidValue(value, field) {
  if (field.names && new RegExp(`^(${field.names})$`, "i").test(value)) {
    return true;
  }
  if (!/^\d+$/.test(value)) {
    return false;
  }
  const number = Number(value);
  return number >= field.min && number <= field.max;
}

function isValidPart(part, field) {
  // A step may be attached to anything: */5, 10-30/5, 5/10.
  const [range, step, ...rest] = part.split("/");
  if (rest.length > 0 || step === "") {
    return false;
  }
  if (step !== undefined && !/^\d+$/.test(step)) {
    return false;
  }
  if (step !== undefined && Number(step) < 1) {
    return false;
  }

  if (range === "*") {
    return true;
  }

  const bounds = range.split("-");
  if (bounds.length > 2) {
    return false;
  }
  return bounds.every((bound) => isValidValue(bound, field));
}

/**
 * Why this exists rather than a cron library: the server validates with
 * croniter and is the authority. This is only here so somebody is told what is
 * wrong while they type, instead of after a round trip. It is deliberately
 * lenient about anything croniter might accept that it does not know about --
 * the cost of being wrong here is a 400 with the same message.
 *
 * @returns {string|null} what is wrong with the expression, or null if nothing is
 */
export function describeCronProblem(expression) {
  const trimmed = (expression || "").trim();
  if (!trimmed) {
    return "Enter a schedule.";
  }

  const parts = trimmed.split(/\s+/);
  if (parts.length !== FIELD_COUNT) {
    return `A crontab line has five fields; this has ${parts.length}.`;
  }

  for (let i = 0; i < FIELD_COUNT; i += 1) {
    const field = FIELDS[i];
    const ok = parts[i].split(",").every((part) => part !== "" && isValidPart(part, field));
    if (!ok) {
      return `“${parts[i]}” is not a valid ${field.name}.`;
    }
  }

  return null;
}

function CronScheduleDialog({ dialog, cron }) {
  const [value, setValue] = useState(cron || "");
  const problem = describeCronProblem(value);
  // Nothing is said about an untouched field: the message belongs next to a
  // mistake, not in front of somebody who has not typed yet.
  const showProblem = value.trim() !== "" && problem !== null;

  const save = useCallback(() => {
    if (!describeCronProblem(value)) {
      dialog.close(value.trim());
    }
  }, [dialog, value]);

  return (
    <Modal
      {...dialog.props}
      title="Custom refresh schedule"
      okText="Save"
      okButtonProps={{ disabled: problem !== null }}
      onOk={save}
      width={460}
      className="cron-schedule-dialog"
    >
      <Input
        value={value}
        placeholder="0 9 * * 1-5"
        onChange={(e) => setValue(e.target.value)}
        onPressEnter={save}
        autoFocus
        aria-label="Crontab expression"
        aria-describedby="cron-schedule-help"
        status={showProblem ? "error" : ""}
      />

      <div id="cron-schedule-help" className="cron-schedule-dialog-help">
        {showProblem ? (
          <Typography.Text type="danger">{problem}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">
            Use crontab format: minute, hour, day of the month, month, day of the week.
          </Typography.Text>
        )}
      </div>

      <dl className="cron-schedule-dialog-examples">
        <dt>
          <code>*/15 * * * *</code>
        </dt>
        <dd>every 15 minutes</dd>
        <dt>
          <code>0 9 * * 1-5</code>
        </dt>
        <dd>at 09:00, Monday to Friday</dd>
        <dt>
          <code>30 2 1 * *</code>
        </dt>
        <dd>at 02:30 on the first of the month</dd>
      </dl>

      <Typography.Text type="secondary" className="cron-schedule-dialog-note">
        Times are UTC. The scheduler checks every 30 seconds, so a run may start up to a minute after its slot.
      </Typography.Text>
    </Modal>
  );
}

CronScheduleDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  cron: PropTypes.string,
};

CronScheduleDialog.defaultProps = {
  cron: "",
};

export default wrapDialog(CronScheduleDialog);

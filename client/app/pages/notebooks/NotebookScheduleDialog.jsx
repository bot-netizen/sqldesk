import React, { useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Radio from "antd/lib/radio";
import Input from "antd/lib/input";
import Alert from "antd/lib/alert";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

/*
  When a notebook should run itself.

  Cron, because that is the question somebody is actually asking -- "every
  morning before the standup" -- where a query's interval/time/day_of_week
  answers "keep this no more than an hour stale". The two look similar and
  are not the same thing.

  The presets exist because almost nobody writes cron from memory, and the
  box underneath exists because the people who do should not be made to use a
  dropdown instead. Whatever is chosen is checked by the server before it is
  stored: an expression that does not parse would otherwise quietly mean
  "never", which is the worst answer a schedule can give.
*/
export const PRESETS = [
  { label: "Every hour", cron: "0 * * * *" },
  { label: "Every day at 6am", cron: "0 6 * * *" },
  { label: "Every weekday at 7am", cron: "0 7 * * 1-5" },
  { label: "Every Monday at 8am", cron: "0 8 * * 1" },
];

export function matchingPreset(cron) {
  return PRESETS.some((one) => one.cron === cron) ? cron : "custom";
}

export function NotebookScheduleDialog({ dialog, notebook }) {
  const existing = notebook.schedule || "";
  const [choice, setChoice] = useState(existing ? matchingPreset(existing) : "");
  const [custom, setCustom] = useState(existing && matchingPreset(existing) === "custom" ? existing : "");

  const chosen = choice === "custom" ? custom.trim() : choice;

  return (
    <Modal
      {...dialog.props}
      title="When should this notebook run?"
      okText={chosen ? "Save schedule" : "Run only when asked"}
      okButtonProps={{ disabled: notebook.is_draft, "data-test": "SaveSchedule" }}
      // "" is a meaning here -- take the schedule away -- so it is sent
      // rather than treated as nothing to do.
      onOk={() => dialog.close(chosen)}
      data-test="NotebookScheduleDialog"
    >
      {notebook.is_draft && (
        <Alert
          className="notebook-schedule-notice"
          type="warning"
          showIcon
          message="Publish this notebook first."
          description="A draft is what you are still building, and it should not start running itself overnight."
          data-test="ScheduleNeedsPublishing"
        />
      )}

      <Radio.Group value={choice} onChange={(e) => setChoice(e.target.value)} className="notebook-schedule-choices">
        <Radio value="" data-test="ScheduleNever">
          Only when somebody asks
        </Radio>
        {PRESETS.map((one) => (
          <Radio key={one.cron} value={one.cron} data-test={`SchedulePreset-${one.cron}`}>
            {one.label}
          </Radio>
        ))}
        <Radio value="custom" data-test="ScheduleCustom">
          A cron expression
        </Radio>
      </Radio.Group>

      {choice === "custom" && (
        <Input
          className="notebook-schedule-cron"
          placeholder="0 6 * * *"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          data-test="ScheduleCronInput"
        />
      )}

      <p className="notebook-schedule-said">
        It runs as you, with your data source access, and stops at the first cell that fails — the same as Run all.
      </p>
    </Modal>
  );
}

NotebookScheduleDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  notebook: PropTypes.object.isRequired,
};

export default wrapDialog(NotebookScheduleDialog);

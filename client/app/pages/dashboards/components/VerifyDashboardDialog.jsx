import React, { useState } from "react";
import PropTypes from "prop-types";
import Modal from "antd/lib/modal";
import Input from "antd/lib/input";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";

/*
  Saying what was checked.

  The note is the whole point, so the button stays off until there is one: a
  badge with no reason is a badge nobody can weigh, and "verified" on its own
  invites exactly the trust it has not earned.
*/
function VerifyDashboardDialog({ dialog, current }) {
  const [note, setNote] = useState((current && current.note) || "");
  const ready = note.trim().length > 0;

  return (
    <Modal
      {...dialog.props}
      title={current ? "Update the verification" : "Verify this dashboard"}
      okText={current ? "Save" : "Verify"}
      okButtonProps={{ disabled: !ready, "data-test": "VerifyDashboardOk" }}
      onOk={() => dialog.close(note.trim())}
    >
      <p className="text-muted">
        Say what you checked, so whoever relies on it knows what it covers &mdash; and what it does not. If the charts
        or their queries change afterwards, the badge will say so.
      </p>
      <Input.TextArea
        autoFocus
        autoSize={{ minRows: 3, maxRows: 8 }}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="e.g. Revenue ties out to finance's monthly close. Excludes the test tenant."
        data-test="VerifyDashboardNote"
      />
    </Modal>
  );
}

VerifyDashboardDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  current: PropTypes.shape({ note: PropTypes.string }),
};

VerifyDashboardDialog.defaultProps = {
  current: null,
};

export default wrapDialog(VerifyDashboardDialog);

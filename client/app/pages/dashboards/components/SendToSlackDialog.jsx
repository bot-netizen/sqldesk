import React, { useCallback, useState } from "react";
import PropTypes from "prop-types";
import { get } from "lodash";
import Alert from "antd/lib/alert";
import Input from "antd/lib/input";
import Modal from "antd/lib/modal";

import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import SlackChannelSelect from "@/components/SlackChannelSelect";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import { rememberScreen } from "@/services/screen";
import SendableNotice, { useSendable } from "./SendableNotice";

/*
  Send this dashboard to a Slack channel, now.

  Channels come from Slack rather than being typed, and only the ones the app
  has been added to, so a typo or a channel the app cannot post in cannot
  produce a message that goes nowhere.

  Whether the dashboard is small enough to send is asked as the dialog opens,
  not when Send is pressed: somebody should learn it has fifteen widgets
  before they have picked a channel and typed a message, and be told what to
  do about it.

  Sending happens while the dialog is open and waits for the answer. A
  dashboard takes a few seconds to draw, and the thing somebody needs to know
  after pressing Send is whether it arrived -- on a queue, a revoked token or an
  archived channel becomes a log line nobody reads.
*/
function SendToSlackDialog({ dialog, dashboard }) {
  const check = useSendable(dashboard);
  const [problem, setProblem] = useState(null);
  const [channel, setChannel] = useState(undefined);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const tooBig = !!check && !check.fits;

  const send = useCallback(() => {
    setSending(true);
    setProblem(null);
    // First, so the picture is drawn at this screen's width: the one Export
    // as image would give. It cannot fail the send.
    rememberScreen({ dashboardId: dashboard.id })
      .then(() => axios.post(`api/dashboards/${dashboard.id}/share/slack`, { channel, text }))
      .then(() => {
        notification.success(`Sent to Slack.`);
        dialog.close();
      })
      .catch((error) => {
        setProblem(get(error, "response.data.message") || "Could not send it.");
      })
      .finally(() => setSending(false));
  }, [channel, text, dashboard.id, dialog]);

  return (
    <Modal
      {...dialog.props}
      title="Send to Slack"
      okText={sending ? "Sending…" : "Send"}
      okButtonProps={{ disabled: !channel || sending || tooBig, loading: sending }}
      onOk={send}
      data-test="SendToSlackDialog"
    >
      <SendableNotice dashboard={dashboard} check={check} />
      {problem && <Alert className="m-b-15" type="error" showIcon message={problem} />}

      <p className="text-muted">
        The channel gets a picture of <strong>{dashboard.name}</strong> as it looks now, with a button that opens it.
        SQLDesk draws and uploads the picture, so Slack never has to reach this install.
      </p>

      <label htmlFor="slack-channel">Channel</label>
      <SlackChannelSelect id="slack-channel" value={channel} onChange={setChannel} />

      <label className="m-t-15" htmlFor="slack-text">
        Anything you want to say (optional)
      </label>
      <Input.TextArea
        id="slack-text"
        rows={2}
        value={text}
        placeholder="Q3 came in ahead of plan."
        maxLength={1000}
        onChange={(event) => setText(event.target.value)}
      />
    </Modal>
  );
}

SendToSlackDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  dashboard: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }).isRequired,
};

export default wrapDialog(SendToSlackDialog);

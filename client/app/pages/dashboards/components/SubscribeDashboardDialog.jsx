import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import { map } from "lodash";
import Modal from "antd/lib/modal";
import Select from "antd/lib/select";
import Radio from "antd/lib/radio";
import Table from "antd/lib/table";
import Tooltip from "antd/lib/tooltip";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import SlackOutlinedIcon from "@ant-design/icons/SlackOutlined";
import { axios } from "@/services/axios";
import { wrap as wrapDialog, DialogPropType } from "@/components/DialogWrapper";
import SlackChannelSelect from "@/components/SlackChannelSelect";
import notification from "@/services/notification";
import { clientConfig } from "@/services/auth";
import { formatDateTime } from "@/lib/utils";
import User from "@/services/user";
import SendableNotice, { useSendable } from "./SendableNotice";

/*
  Who gets this dashboard mailed to them, and when.

  Recipients are chosen from the people in this organization rather than typed
  as addresses. An address box would be a way to mail a dashboard's contents
  anywhere; a name is somebody the server can check has the right to see it.

  The server checks that anyway, and says who it left off. That answer is
  shown here rather than swallowed -- somebody who is quietly dropped asks a
  fortnight later why they never get it.

  Or a Slack channel, where Slack is set up: for a dashboard a team watches,
  a picture in their channel every hour is the version they will look at. The
  channel is picked from the ones the app is in, and gets a picture -- a PDF
  in a channel is a file to download, not something to glance at.
*/

const INTERVALS = [
  { value: 3600, label: "Every hour" },
  { value: 86400, label: "Every day" },
  { value: 604800, label: "Every week" },
];

function describe(schedule) {
  const interval = (INTERVALS.find((i) => i.value === (schedule || {}).interval) || {}).label;
  return interval || "On a schedule";
}

function Who({ subscription }) {
  if (subscription.slack_channel) {
    return (
      <span>
        <SlackOutlinedIcon className="m-r-5" aria-label="Slack" />#{subscription.slack_channel_name}
      </span>
    );
  }
  return map(subscription.recipients, "name").join(", ") || "Nobody";
}

Who.propTypes = {
  subscription: PropTypes.shape({
    slack_channel: PropTypes.string,
    slack_channel_name: PropTypes.string,
    recipients: PropTypes.arrayOf(PropTypes.shape({ name: PropTypes.string })),
  }).isRequired,
};

function SubscribeDashboardDialog({ dialog, dashboard }) {
  const check = useSendable(dashboard);
  const [subscriptions, setSubscriptions] = useState([]);
  const [people, setPeople] = useState([]);
  const [via, setVia] = useState("people");
  const [channel, setChannel] = useState(undefined);
  const [recipients, setRecipients] = useState([]);
  const [interval, setInterval] = useState(86400);
  const [format, setFormat] = useState("png");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState(null);

  const url = `api/dashboards/${dashboard.id}/subscriptions`;

  const load = useCallback(() => {
    axios
      .get(url)
      .then(setSubscriptions)
      .catch(() => setProblem("Could not load the subscriptions to this dashboard."));
  }, [url]);

  useEffect(() => {
    load();
    User.query({ page_size: 250 })
      .then(({ results }) => setPeople(results))
      .catch(() => setPeople([]));
  }, [load]);

  const toSlack = via === "slack";
  const tooBig = !!check && !check.fits;

  const subscribe = useCallback(() => {
    setSaving(true);
    setProblem(null);
    const body = toSlack
      ? { schedule: { interval }, slack_channel: channel }
      : { schedule: { interval }, format, recipients };
    axios
      .post(url, body)
      .then((created) => {
        setRecipients([]);
        setChannel(undefined);
        load();
        // The server decides who may actually be sent this, and says who it
        // left off. Silence here is how somebody ends up never receiving it
        // and nobody knowing why.
        const left = created.left_out || [];
        if (left.length > 0) {
          notification.warning(
            "Subscribed, with some people left off",
            left.map((r) => `${r.name}: ${r.why}`).join(" "),
            { duration: 10 }
          );
        } else if (created.slack_channel) {
          notification.success("Subscribed", `#${created.slack_channel_name} will be sent this dashboard.`);
        } else {
          notification.success("Subscribed", "They will be sent this dashboard.");
        }
      })
      .catch((error) => {
        setProblem((error.response && error.response.data && error.response.data.message) || "Could not subscribe.");
      })
      .finally(() => setSaving(false));
  }, [url, interval, format, recipients, channel, toSlack, load]);

  const stop = useCallback(
    (subscription) => {
      axios
        .delete(`api/subscriptions/${subscription.id}`)
        .then(() => {
          notification.success("Stopped", "That subscription will not send again.");
          load();
        })
        .catch(() => notification.error("Could not stop that subscription."));
    },
    [load]
  );

  const columns = [
    {
      title: "Who",
      key: "who",
      render: (subscription) => <Who subscription={subscription} />,
    },
    { title: "When", key: "when", render: (s) => describe(s.schedule) },
    { title: "As", key: "as", render: (s) => (s.format === "pdf" ? "PDF" : "Picture") },
    {
      title: "Last sent",
      key: "last",
      render: (s) =>
        s.last_error ? (
          // The reason a subscription has stopped sending belongs where
          // somebody looks for it, not only in a worker's log.
          <Tooltip title={s.last_error}>
            <span className="text-danger">Not sending</span>
          </Tooltip>
        ) : (
          formatDateTime(s.last_sent_at) || "Not yet"
        ),
    },
    {
      title: "",
      key: "stop",
      render: (subscription) => (
        <Button type="link" onClick={() => stop(subscription)} data-test="StopSubscription">
          Stop
        </Button>
      ),
    },
  ];

  return (
    <Modal
      {...dialog.props}
      title="Send this dashboard"
      okText="Subscribe"
      okButtonProps={{ loading: saving, disabled: tooBig || (toSlack ? !channel : recipients.length === 0) }}
      onOk={subscribe}
      width={640}
      data-test="SubscribeDashboardDialog"
    >
      <SendableNotice dashboard={dashboard} check={check} />
      {problem && <Alert type="error" message={problem} className="m-b-15" />}

      {clientConfig.slackConfigured && (
        <div className="m-b-10">
          <Radio.Group value={via} onChange={(e) => setVia(e.target.value)} data-test="SubscribeVia">
            <Radio value="people">People, by email</Radio>
            <Radio value="slack">
              <SlackOutlinedIcon className="m-r-5" aria-hidden="true" />A Slack channel
            </Radio>
          </Radio.Group>
        </div>
      )}

      <div className="m-b-10">
        <div className="m-b-5">Send to</div>
        {toSlack ? (
          <SlackChannelSelect value={channel} onChange={setChannel} data-test="SubscribeChannel" />
        ) : (
          <Select
            mode="multiple"
            className="w-100"
            placeholder="People in your organization"
            value={recipients}
            onChange={setRecipients}
            optionFilterProp="label"
            data-test="SubscribeRecipients"
            options={people.map((user) => ({ value: user.id, label: `${user.name} (${user.email})` }))}
          />
        )}
      </div>

      <div className="m-b-10">
        <div className="m-b-5">How often</div>
        <Select className="w-100" value={interval} onChange={setInterval} options={INTERVALS} />
      </div>

      {!toSlack && (
        <div className="m-b-15">
          <div className="m-b-5">As</div>
          <Radio.Group value={format} onChange={(e) => setFormat(e.target.value)}>
            <Radio value="png">A picture in the email</Radio>
            <Radio value="pdf">A PDF to print</Radio>
          </Radio.Group>
        </div>
      )}

      <div className="text-muted m-b-15" style={{ fontSize: 12 }}>
        The latest saved results are sent, and the {toSlack ? "message" : "email"} says how old they are. Give the
        queries a refresh schedule if you want the numbers current.
      </div>

      <Table
        size="small"
        rowKey="id"
        dataSource={subscriptions}
        columns={columns}
        pagination={false}
        locale={{ emptyText: "Nobody is subscribed to this dashboard." }}
        data-test="SubscriptionList"
      />
    </Modal>
  );
}

SubscribeDashboardDialog.propTypes = {
  dialog: DialogPropType.isRequired,
  // eslint-disable-next-line react/forbid-prop-types
  dashboard: PropTypes.object.isRequired,
};

export default wrapDialog(SubscribeDashboardDialog);

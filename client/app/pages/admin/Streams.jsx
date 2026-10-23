import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Input from "antd/lib/input";
import Switch from "antd/lib/switch";
import Progress from "antd/lib/progress";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import Layout from "@/components/admin/Layout";
import Link from "@/components/Link";
import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";

import "./streams.less";

/*
  Admin → Streams: what each topic is doing, and the two settings that decide
  what it costs.

  The column this page exists for is **State**. An empty chart on a dashboard
  says nothing about why: nobody has looked at the stream lately, the consumer
  stopped with an error, or the topic genuinely has nothing on it. Only one of
  those is somebody's problem, and the server works out which -- see
  `activity.why_it_is_quiet`. A page that just said "0 events" would send
  people to the broker for a problem that was a paused consumer.
*/

function Numbers({ stream }) {
  return (
    <div>
      {/* The window moves with the rate, so it is stated rather than assumed. */}
      <div>{stream.describes}</div>
      <div className="streams-muted">
        {stream.observed_rate ? `${stream.observed_rate}/sec` : "nothing arriving"}
        {stream.sampled && (
          <Tooltip title="Over the ceiling, so events are kept one in N. Counts on charts built from this are estimates and say so.">
            <Tag color="orange" className="m-l-5">
              1-in-{stream.sample_rate}
            </Tag>
          </Tooltip>
        )}
        {stream.malformed > 0 && (
          <Tooltip title="Messages SQLDesk could not read. Counted and skipped; the consumer never stops for one.">
            <Tag className="m-l-5">{stream.malformed} malformed</Tag>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

Numbers.propTypes = { stream: PropTypes.object.isRequired }; // eslint-disable-line react/forbid-prop-types

function State({ stream }) {
  if (stream.quiet) {
    // The sentence the server worked out. Shown in full rather than reduced to
    // a badge: "Paused" and "the broker refused the credentials" need
    // different things done about them.
    const broken = !stream.quiet.startsWith("Paused") && !stream.quiet.startsWith("Nothing has used");
    return (
      <span>
        <Tag color={broken ? "red" : null}>{broken ? "not working" : "paused"}</Tag>
        <div className="streams-muted">{stream.quiet}</div>
      </span>
    );
  }
  return (
    <span>
      <Tag color="green">consuming</Tag>
      {stream.last_flush_at && (
        <div className="streams-muted">
          last flush <TimeAgo date={stream.last_flush_at} />
        </div>
      )}
    </span>
  );
}

State.propTypes = { stream: PropTypes.object.isRequired }; // eslint-disable-line react/forbid-prop-types

function Budgets({ stream, onSaved }) {
  const [budget, setBudget] = useState(String(stream.row_budget || ""));
  const [ceiling, setCeiling] = useState(String(stream.events_per_second || ""));
  const [saving, setSaving] = useState(false);

  const save = useCallback(() => {
    setSaving(true);
    axios
      .post(`api/data_sources/${stream.data_source_id}/stream/${stream.id}`, {
        row_budget: Number(budget) || 0,
        events_per_second: Number(ceiling) || 0,
      })
      .then(() => {
        notification.success(`Saved ${stream.topic}.`);
        onSaved();
      })
      .catch(() => notification.error("Could not save that."))
      .finally(() => setSaving(false));
  }, [budget, ceiling, stream.data_source_id, stream.topic, onSaved]);

  const budgetId = `stream-${stream.id}-budget`;
  const ceilingId = `stream-${stream.id}-ceiling`;

  return (
    <div className="streams-budgets">
      <label htmlFor={budgetId}>
        Rows to keep
        <Input
          id={budgetId}
          size="small"
          value={budget}
          placeholder="default"
          onChange={(e) => setBudget(e.target.value)}
        />
      </label>
      <label htmlFor={ceilingId}>
        Events a second
        <Input
          id={ceilingId}
          size="small"
          value={ceiling}
          placeholder="default"
          onChange={(e) => setCeiling(e.target.value)}
        />
      </label>
      <Button size="small" loading={saving} onClick={save}>
        Save
      </Button>
    </div>
  );
}

Budgets.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  stream: PropTypes.object.isRequired,
  onSaved: PropTypes.func.isRequired,
};

/*
  How much room is left, and what is holding it.

  This was a page of its own, readable by everybody. It is here because the
  question it answers -- why will another stream not start -- is answered by
  the limit and by the list of what is using it, and those were a tab apart.
  The number everybody else needs is on the stream editor's status strip,
  beside the button that will not start.
*/
function Slots({ slots, onRefresh }) {
  if (!slots) {
    return null;
  }
  const full = !!slots.limit && slots.used >= slots.limit;
  return (
    <div className="streams-slots" data-test="StreamSlots">
      <div className="streams-slot-bar">
        <Progress
          percent={slots.limit ? Math.round((slots.used / slots.limit) * 100) : 0}
          status={full ? "exception" : "normal"}
          showInfo={false}
        />
      </div>
      <div>
        <strong>
          {slots.used} of {slots.limit || "\u221e"}
        </strong>{" "}
        <span className="streams-muted">
          slots in use &middot; {slots.per_user || "\u221e"} per person &middot; a stream runs for up to {slots.minutes}{" "}
          minutes before somebody says they still want it
        </span>
      </div>
      <Button size="small" onClick={onRefresh}>
        Refresh
      </Button>
    </div>
  );
}

Slots.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  slots: PropTypes.object,
  onRefresh: PropTypes.func.isRequired,
};

Slots.defaultProps = { slots: null };

export default function Streams() {
  const [streams, setStreams] = useState(null);
  const [slots, setSlots] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    axios
      .get("api/streams")
      .then((data) => {
        setStreams(data.streams);
        setSlots(data.slots);
        setError(null);
      })
      .catch(() => setError("Could not read the streams."));
  }, []);

  useEffect(() => {
    recordEvent("view", "page", "admin/streams");
    load();
  }, [load]);

  // Polled, because every number here moves on its own -- unlike the rest of
  // the admin pages, where nothing changes unless somebody does something.
  useEffect(() => {
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const pin = useCallback(
    (stream, pinned) => {
      axios
        .post(`api/data_sources/${stream.data_source_id}/stream/${stream.id}`, { pinned })
        .then(() => {
          notification.success(
            pinned
              ? `${stream.topic} will stay on whether anybody is looking or not.`
              : `${stream.topic} will pause when nobody is looking.`
          );
          load();
        })
        .catch(() => notification.error("Could not save that."));
    },
    [load]
  );

  const columns = [
    {
      title: "Topic",
      dataIndex: "topic",
      render: (topic, row) => (
        <span>
          <strong>{topic}</strong>
          <div className="streams-muted">
            <Link href={`data_sources/${row.data_source_id}`}>{row.data_source_name}</Link>
            {row.schema_state === "frozen" ? (
              <Tooltip title="The columns have been settled by a person. A field a producer adds is ignored until somebody re-infers them.">
                <Tag className="m-l-5">schema frozen</Tag>
              </Tooltip>
            ) : (
              <span className="m-l-5">{row.columns} columns, inferred</span>
            )}
          </div>
        </span>
      ),
    },
    { title: "State", dataIndex: "quiet", width: 280, render: (_q, row) => <State stream={row} /> },
    { title: "Window", dataIndex: "rows", width: 220, render: (_r, row) => <Numbers stream={row} /> },
    {
      title: (
        <Tooltip title="Keep consuming even when nobody is looking. A stream costs continuously, unlike a query, so this is a deliberate decision rather than a default.">
          <span>Always on</span>
        </Tooltip>
      ),
      dataIndex: "pinned",
      width: 110,
      align: "center",
      render: (pinned, row) => <Switch size="small" checked={pinned} onChange={(on) => pin(row, on)} />,
    },
  ];

  return (
    <Layout activeTab="streams">
      <div className="p-15 streams-page">
        {error && <Alert type="error" showIcon message={error} className="m-b-15" />}

        <Slots slots={slots} onRefresh={load} />

        {streams && streams.length === 0 && (
          <div className="streams-empty">
            <p>No streams yet.</p>
            <p className="streams-muted">
              Add a <strong>Kafka stream</strong> data source and SQLDesk keeps the last few minutes of the topic,
              rolling everything older into per-minute buckets. For history, land the topic in your warehouse and point
              SQLDesk at that.
            </p>
          </div>
        )}

        {streams && streams.length > 0 && (
          <React.Fragment>
            <p className="streams-muted">
              Each stream keeps a window of raw events, sized by its row budget and the rate it is seeing, plus
              per-minute rollups. A stream is consumed while something using it has been looked at recently, or while it
              is pinned here.
            </p>
            <Table
              dataSource={streams}
              columns={columns}
              rowKey="id"
              size="small"
              pagination={false}
              expandable={{
                expandedRowRender: (row) => <Budgets stream={row} onSaved={load} />,
                rowExpandable: () => true,
              }}
            />
          </React.Fragment>
        )}

        <div className="m-t-15">
          <Button size="small" onClick={load}>
            Refresh
          </Button>
        </div>
      </div>
    </Layout>
  );
}

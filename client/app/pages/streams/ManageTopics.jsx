import React, { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Checkbox from "antd/lib/checkbox";
import Input from "antd/lib/input";
import Select from "antd/lib/select";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";

import TimeAgo from "@/components/TimeAgo";
import Link from "@/components/Link";
import wrapSettingsTab from "@/components/SettingsWrapper";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";

import "./streams.less";

/*
  Choosing which of a cluster's topics can be queried.

  This is the access decision on a Kafka cluster: the data source permission is
  per cluster, so whatever is enabled here is what everybody with access to
  that cluster can then query. Hence its own permission, and hence a page
  rather than a field on the data source -- an administrator registers the
  cluster, somebody who knows the data decides what is worth keeping.

  **Analyse before enabling.** The three things nobody can guess from a topic's
  name are what the messages contain, how fast they arrive, and what that means
  for how much history a window will hold. Enabling one blind and finding out
  an hour later that it is unparseable, or so fast that everything is sampled,
  is the afternoon this page exists to prevent.
*/

function seconds(value) {
  if (!value) {
    return "—";
  }
  if (value < 120) {
    return `${Math.round(value)} seconds`;
  }
  return `${Math.round(value / 60)} minutes`;
}

function Figure({ label, children }) {
  return (
    <span className="streams-figure">
      <strong>{children}</strong>
      <span className="streams-muted">{label}</span>
    </span>
  );
}

/*
  One in how many events would be kept, and why.

  Sampling is not a percentage and not random: the ceiling divides the rate,
  rounded up, and the decision per event is a hash of the message key's raw
  bytes. That matters to whoever is reading the number -- the same keys stay in
  across every flush, so a per-key count can be scaled back up honestly, which
  a random sample could not promise.
*/
function Sampling({ found }) {
  if (!found.ceiling) {
    return (
      <p className="streams-muted">
        No events-a-second ceiling is set on this install, so every event is kept however fast the topic runs. That is
        the setting to use if a window ever costs more disk than it is worth.
      </p>
    );
  }
  if (!found.sampled) {
    return (
      <p className="streams-muted">
        <strong>Everything is kept.</strong> {found.events_per_second} events a second is under the ceiling of{" "}
        {(found.ceiling || 0).toLocaleString()}, so nothing is dropped. Past the ceiling SQLDesk keeps one event in
        however many times over it the topic runs.
      </p>
    );
  }
  return (
    <p className="streams-muted">
      <strong>1 event in {found.sample_rate} would be kept.</strong> {found.events_per_second} events a second against a
      ceiling of {(found.ceiling || 0).toLocaleString()}, and the ceiling divides the rate. Which events is decided by a
      hash of the message key, not at random, so the same keys stay in from one second to the next and a count per key
      can be scaled back up. Counts across all keys are estimates, and every chart drawn from this stream says so.
    </p>
  );
}

/*
  The schema, however many columns there are.

  A row of tags wrapped into an unreadable block the moment a topic had more
  than a handful, and a topic with forty fields is ordinary. One per line,
  monospaced so the types line up, in a box that scrolls rather than pushing
  the button that enables the topic off the bottom of the screen.
*/
function Schema({ columns }) {
  const [open, setOpen] = useState(true);

  if (columns.length === 0) {
    return (
      <div className="streams-schema-block">
        <p className="streams-muted m-b-0">
          Nothing could be read from this topic. It may be empty, or it may not be JSON.
        </p>
      </div>
    );
  }

  return (
    <div className="streams-schema">
      <button type="button" className="streams-schema-head" onClick={() => setOpen((on) => !on)}>
        <i className={`fa fa-caret-${open ? "down" : "right"} m-r-5`} aria-hidden="true" />
        <strong>Columns</strong>
        <span className="streams-muted m-l-5">
          {columns.length} field{columns.length === 1 ? "" : "s"}
        </span>
      </button>
      {open && (
        <div className="streams-schema-block" data-test="TopicSchema">
          {columns.map((column) => (
            <div className="streams-schema-row" key={column.name}>
              <span className="streams-schema-name">{column.name}</span>
              <span className="streams-schema-type">{column.type}</span>
            </div>
          ))}
          <div className="streams-schema-row streams-schema-given">
            <span className="streams-schema-name">_received_at</span>
            <span className="streams-schema-type">datetime</span>
          </div>
        </div>
      )}
    </div>
  );
}

/*
  How the consumer reads, which is mostly about how it looks to the broker.

  Lag monitoring alarmed on SQLDesk because every stream joined a consumer
  group it never committed under. So the default is no group the broker can
  see, and the page says so in words rather than leaving it to be inferred from
  an empty box. A name, saving the position and where to start are each a
  choice made here, per topic.
*/
const START_POINTS = [
  { value: "latest", label: "Latest: only what arrives from now" },
  { value: "earliest", label: "Earliest: everything still on the topic" },
  { value: "saved", label: "Where it left off" },
];

export function readingSettings(group, save, start) {
  const named = group.trim().length > 0;
  const saving = named && save;
  return {
    consumer_group: group.trim(),
    save_position: saving,
    start_from: start === "saved" && !saving ? "latest" : start,
  };
}

export function HowItReads({ topic, onChange }) {
  const [group, setGroup] = useState((topic && topic.consumer_group) || "");
  const [save, setSave] = useState(!!(topic && topic.save_position));
  const [start, setStart] = useState((topic && topic.start_from) || "latest");

  const settings = readingSettings(group, save, start);
  const named = settings.consumer_group.length > 0;

  useEffect(() => {
    onChange(settings);
    // `settings` is rebuilt every render; its three fields are what change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.consumer_group, settings.save_position, settings.start_from]);

  return (
    <div className="streams-reading m-t-15" data-test="HowItReads">
      <strong>How it reads</strong>

      <div className="m-t-5">
        <label htmlFor="consumer-group">Consumer group</label>
        <Input
          id="consumer-group"
          value={group}
          onChange={(event) => setGroup(event.target.value)}
          placeholder="None"
          data-test="ConsumerGroup"
        />
        <p className="streams-muted m-b-5" data-test="ConsumerGroupMeaning">
          {named
            ? `Joins "${settings.consumer_group}" on the broker. Lag monitoring that ignores consumers by prefix will see it under this name.`
            : "No consumer group is joined and nothing is committed, so the broker never sees one and lag monitoring has nothing to alarm on."}
        </p>
      </div>

      <div className="m-t-5">
        <Checkbox
          checked={settings.save_position}
          disabled={!named}
          onChange={(event) => setSave(event.target.checked)}
          data-test="SavePosition"
        >
          Save position
        </Checkbox>
        <p className="streams-muted m-b-5" data-test="SavePositionMeaning">
          {settings.save_position
            ? "Offsets are committed after each flush, so it resumes where it stopped."
            : named
              ? "Nothing is saved. Each time it starts, it reads from the point below."
              : "Nothing is saved. Saving needs a consumer group name to save under."}
        </p>
      </div>

      <div className="m-t-5">
        <label htmlFor="start-from">Start from</label>
        <Select
          id="start-from"
          value={settings.start_from}
          onChange={setStart}
          style={{ width: "100%" }}
          data-test="StartFrom"
        >
          {START_POINTS.map((point) => (
            <Select.Option
              key={point.value}
              value={point.value}
              disabled={point.value === "saved" && !settings.save_position}
            >
              {point.value === "saved" && !settings.save_position
                ? `${point.label} (needs Save position)`
                : point.label}
            </Select.Option>
          ))}
        </Select>
        <p className="streams-muted m-b-5">
          Applies when it starts from cold. Between one job and the next it carries on from where it stopped.
        </p>
        {settings.start_from === "earliest" && (
          <Alert
            type="warning"
            showIcon
            data-test="EarliestWarning"
            message="Reads everything still on the topic each time it starts from cold."
            description="The row budget keeps only the newest rows, but every message is still read to get there."
          />
        )}
      </div>
    </div>
  );
}

function Analysis({ found, topic, onEnable, onAgain, saving, analysing, enabled }) {
  const [reading, setReading] = useState(readingSettings("", false, "latest"));
  return (
    <div className="streams-analysis" data-test="TopicAnalysis">
      <div className="streams-figures">
        <Figure label="messages read">{found.read}</Figure>
        <Figure label="could not be parsed">{found.malformed}</Figure>
        <Figure label="events a second">
          <span className="streams-rate">{found.events_per_second}</span>
        </Figure>
        <Figure label="of history that buys">{seconds(found.window_seconds)}</Figure>
        {/*
          A reading of the last few hundred messages at a moment, not a figure
          the server keeps. Without the time on it, it reads as something
          precomputed and nobody thinks to take it again after the topic has
          changed.
        */}
        <span className="streams-measured">
          measured <TimeAgo date={found.measured_at} />
          <Button size="small" className="m-l-10" loading={analysing} onClick={onAgain} data-test="AnalyseAgain">
            Analyse again
          </Button>
        </span>
      </div>

      {found.malformed > 0 && (
        <Alert
          className="m-t-10"
          type="warning"
          showIcon
          message={`${found.malformed} of ${found.read} messages could not be read as JSON objects.`}
          description="Those are not stored and not counted. A schema inferred from the rest may be missing fields that only appear in them."
        />
      )}

      <div className="m-t-15">
        <strong>How much would be kept</strong>
        <p className="streams-muted m-b-5">
          A window is a row budget divided by the rate: {(found.row_budget || 0).toLocaleString()} rows at{" "}
          {found.events_per_second} a second is {seconds(found.window_seconds)}, held between five minutes and half an
          hour. Both numbers are per topic and are set under Admin &rarr; Streaming Queries.
        </p>
        <Sampling found={found} />
      </div>

      <div className="m-t-15">
        <Schema columns={found.columns} />
      </div>

      <HowItReads topic={topic} onChange={setReading} />

      {/* Already on: offering to enable it again would do nothing, and the
          control that matters is Turn off, which is in the row above. What it
          can still do is change how it reads. */}
      <div className="streams-enable">
        {enabled ? (
          <Button onClick={() => onEnable(reading)} loading={saving} data-test="SaveHowItReads">
            Save how it reads
          </Button>
        ) : (
          <Button type="primary" onClick={() => onEnable(reading)} loading={saving} data-test="EnableTopic">
            Enable this topic
          </Button>
        )}
      </div>
    </div>
  );
}

function ManageTopics() {
  const [clusters, setClusters] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [topics, setTopics] = useState(null);
  const [problem, setProblem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("");
  const [analysing, setAnalysing] = useState(null);
  const [analysis, setAnalysis] = useState({});
  const [saving, setSaving] = useState(null);

  useEffect(() => {
    recordEvent("view", "page", "streams/topics");
    axios
      .get("api/data_sources")
      .then((sources) => {
        const kafka = sources.filter((source) => source.streams_only);
        setClusters(kafka);
        if (kafka.length) {
          setChosen(kafka[0].id);
        }
      })
      .catch(() => setClusters([]));
  }, []);

  const load = useCallback((clusterId) => {
    setLoading(true);
    setProblem(null);
    axios
      .get(`api/data_sources/${clusterId}/topics`)
      .then((data) => setTopics(data.topics))
      .catch((error) => {
        setTopics([]);
        setProblem((error && error.message) || "Could not ask the cluster what topics it has.");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (chosen) {
      load(chosen);
    }
  }, [chosen, load]);

  const analyse = useCallback(
    (topic) => {
      setAnalysing(topic);
      axios
        .post(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}/analyse`)
        .then((found) => setAnalysis((all) => ({ ...all, [topic]: { ...found, measured_at: new Date() } })))
        .catch((error) => notification.error("Could not read that topic", (error && error.message) || ""))
        .finally(() => setAnalysing(null));
    },
    [chosen]
  );

  const enable = useCallback(
    (topic, body, alreadyEnabled) => {
      setSaving(topic);
      axios
        .post(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}`, body || {})
        .then(() => {
          notification.success(alreadyEnabled ? `How ${topic} is read was saved.` : `${topic} can now be queried.`);
          load(chosen);
        })
        .catch((error) => notification.error("Could not enable that topic", (error && error.message) || ""))
        .finally(() => setSaving(null));
    },
    [chosen, load]
  );

  const disable = useCallback(
    (topic) => {
      setSaving(topic);
      axios
        .delete(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}`)
        .then(() => {
          notification.success(`${topic} can no longer be queried, and its window is gone.`);
          load(chosen);
        })
        .catch(() => notification.error("Could not turn that topic off"))
        .finally(() => setSaving(null));
    },
    [chosen, load]
  );

  const shown = useMemo(
    () => (topics || []).filter((topic) => topic.name.toLowerCase().includes(filter.toLowerCase())),
    [topics, filter]
  );

  const columns = [
    {
      title: "Topic",
      dataIndex: "name",
      render: (name, row) => (
        <span>
          <strong>{name}</strong>
          <div className="streams-muted">
            {row.partitions} partition{row.partitions === 1 ? "" : "s"}
            {row.problem && <span className="streams-error"> &middot; {row.problem}</span>}
          </div>
        </span>
      ),
    },
    {
      title: "",
      dataIndex: "enabled",
      width: 120,
      render: (enabled, row) =>
        enabled ? (
          <span>
            <Tag color="green">enabled</Tag>
            {row.columns > 0 && <div className="streams-muted">{row.columns} columns</div>}
          </span>
        ) : null,
    },
    {
      title: "",
      width: 220,
      align: "right",
      render: (_, row) => (
        <span>
          <Button
            size="small"
            loading={analysing === row.name}
            onClick={() => analyse(row.name)}
            data-test="AnalyseTopic"
          >
            Analyse
          </Button>
          {row.enabled ? (
            <Button
              size="small"
              danger
              className="m-l-5"
              loading={saving === row.name}
              onClick={() => disable(row.name)}
            >
              Turn off
            </Button>
          ) : (
            <Button
              size="small"
              type="primary"
              className="m-l-5"
              loading={saving === row.name}
              onClick={() => enable(row.name)}
            >
              Enable
            </Button>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="streams-page" data-test="ManageTopics">
      <div className="streams-header">
        <h2>Streaming Data Sources</h2>
        <p className="streams-muted">
          What a cluster carries, and which of it can be queried. A cluster itself is added under{" "}
          <Link href="data_sources">Data Sources</Link>, like any other connection; this is where its topics become
          tables. Everybody with access to the cluster can query whatever is enabled here, so this is the decision that
          matters.
        </p>
      </div>

      {clusters && clusters.length === 0 && (
        <Alert
          type="info"
          showIcon
          message="No Kafka clusters yet."
          description="An administrator adds one under Data Sources, with the brokers and whatever the cluster needs to let us in. Its topics are chosen here afterwards."
        />
      )}

      {clusters && clusters.length > 0 && (
        <React.Fragment>
          <div className="m-b-15">
            <Select
              value={chosen}
              onChange={setChosen}
              style={{ minWidth: 240 }}
              data-test="ChooseCluster"
              options={clusters.map((cluster) => ({ value: cluster.id, label: cluster.name }))}
            />
            <Input.Search
              placeholder="Find a topic"
              className="m-l-10"
              style={{ maxWidth: 260 }}
              allowClear
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>

          {problem && <Alert type="warning" showIcon message={problem} className="m-b-15" />}

          <Table
            className="streams-table"
            dataSource={shown}
            columns={columns}
            rowKey="name"
            size="small"
            loading={loading}
            pagination={{ pageSize: 20, hideOnSinglePage: true }}
            expandable={{
              expandedRowKeys: Object.keys(analysis),
              expandedRowRender: (row) =>
                analysis[row.name] ? (
                  <Analysis
                    found={analysis[row.name]}
                    topic={row}
                    enabled={row.enabled}
                    saving={saving === row.name}
                    analysing={analysing === row.name}
                    onEnable={(reading) => enable(row.name, reading, row.enabled)}
                    onAgain={() => analyse(row.name)}
                  />
                ) : null,
              rowExpandable: (row) => !!analysis[row.name],
            }}
          />
        </React.Fragment>
      )}
    </div>
  );
}

export default wrapSettingsTab(ManageTopics);

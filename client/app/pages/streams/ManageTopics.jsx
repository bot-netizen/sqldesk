import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

/*
  What a message's bytes are.

  Automatic covers what most topics need with nothing to set: JSON as it is,
  and anything a producer wrote through a schema registry -- Avro, Protobuf or
  JSON Schema -- decoded by what the registry on the data source says it is.
  The other two are for producers that skip the registry and send the bare
  encoding, which cannot be read without the schema it was written with.
*/
const FORMATS = [
  { value: "auto", label: "Automatic: JSON, or anything with a schema registry header" },
  { value: "avro", label: "Avro, read with an .avsc file" },
  { value: "protobuf", label: "Protobuf, read with .proto files" },
];

const FORMAT_HELP = {
  auto: "JSON is read as it is. Avro, Protobuf and JSON Schema messages written through a schema registry are decoded with the registry set on this Kafka data source.",
  avro: "For Avro messages with no schema registry header. Upload the .avsc the producer writes with.",
  protobuf:
    "For Protobuf messages with no schema registry header. Upload the .proto file and any it imports; the google/protobuf types are built in.",
};

export function readingFormat(format, files, messageType) {
  if (format === "auto") {
    return { value_format: "auto" };
  }
  const body = { value_format: format };
  // Sent only when somebody uploaded them here. Left out, the server keeps
  // the files it already has, so choosing another message is not a re-upload.
  if (files) {
    body.schema_files = files;
  }
  if (messageType) {
    body.message_type = messageType;
  }
  return body;
}

function readText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ name: file.name, content: reader.result });
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function MessageFormat({ topic, dataSourceId, onChange }) {
  const [format, setFormat] = useState((topic && topic.value_format) || "auto");
  const [files, setFiles] = useState(null);
  const [names, setNames] = useState((topic && topic.schema_files) || []);
  const [types, setTypes] = useState((topic && topic.message_types) || []);
  const [type, setType] = useState((topic && topic.message_type) || null);
  const [problem, setProblem] = useState(null);
  const [checking, setChecking] = useState(false);
  const picker = useRef(null);

  // Whether the topic already has a schema for this format, kept on the server.
  const kept = topic && topic.value_format === format && (topic.schema_files || []).length > 0;
  const ready = format === "auto" || (!problem && !checking && (files !== null || kept) && !!type);

  useEffect(() => {
    onChange({ ...readingFormat(format, files, type), ready });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [format, files, type, ready]);

  const choose = (value) => {
    setFormat(value);
    setProblem(null);
    if (topic && topic.value_format === value) {
      setFiles(null);
      setNames(topic.schema_files || []);
      setTypes(topic.message_types || []);
      setType(topic.message_type || null);
    } else {
      setFiles(null);
      setNames([]);
      setTypes([]);
      setType(null);
    }
  };

  const upload = (event) => {
    const chosen = Array.from((event.target && event.target.files) || []);
    if (!chosen.length) {
      return;
    }
    setChecking(true);
    setProblem(null);
    Promise.all(chosen.map(readText))
      .then((read) => {
        setFiles(read);
        setNames(read.map((item) => item.name));
        return axios.post(`api/data_sources/${dataSourceId}/stream_schema`, {
          value_format: format,
          schema_files: read,
        });
      })
      .then((checked) => {
        setTypes(checked.message_types || []);
        setType(checked.message_type || null);
      })
      .catch((error) => {
        setTypes([]);
        setType(null);
        setProblem((error && error.message) || "Those files could not be read.");
      })
      .finally(() => {
        setChecking(false);
        // The same file again after fixing it is a change too.
        if (picker.current) {
          picker.current.value = "";
        }
      });
  };

  return (
    <div className="m-t-5" data-test="MessageFormat">
      <label htmlFor="value-format">Message format</label>
      <Select id="value-format" value={format} onChange={choose} style={{ width: "100%" }} data-test="ValueFormat">
        {FORMATS.map((item) => (
          <Select.Option key={item.value} value={item.value}>
            {item.label}
          </Select.Option>
        ))}
      </Select>
      <p className="streams-muted m-b-5" data-test="ValueFormatMeaning">
        {FORMAT_HELP[format]}
      </p>

      {format !== "auto" && (
        <div className="m-b-5">
          <input
            ref={picker}
            type="file"
            accept={format === "avro" ? ".avsc" : ".proto"}
            multiple={format === "protobuf"}
            onChange={upload}
            style={{ display: "none" }}
            data-test="SchemaFiles"
          />
          <Button size="small" loading={checking} onClick={() => picker.current && picker.current.click()}>
            {names.length ? "Replace" : "Upload"} {format === "avro" ? ".avsc" : ".proto files"}
          </Button>
          {names.length > 0 && (
            <span className="streams-muted m-l-10" data-test="SchemaFileNames">
              {names.join(", ")}
            </span>
          )}
          {problem && <Alert className="m-t-5" type="error" showIcon message={problem} data-test="SchemaProblem" />}
          {types.length > 0 && (
            <div className="m-t-5">
              <label htmlFor="message-type">Message type</label>
              <Select
                id="message-type"
                value={type}
                onChange={setType}
                style={{ width: "100%" }}
                showSearch
                data-test="MessageType"
              >
                {types.map((name) => (
                  <Select.Option key={name} value={name}>
                    {name}
                  </Select.Option>
                ))}
              </Select>
              <p className="streams-muted m-b-5">Which of the schema&apos;s messages each message on the topic is.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function HowItReads({ topic, onChange, dataSourceId }) {
  const [group, setGroup] = useState((topic && topic.consumer_group) || "");
  const [save, setSave] = useState(!!(topic && topic.save_position));
  const [start, setStart] = useState((topic && topic.start_from) || "latest");
  const [reading, setReading] = useState({ value_format: "auto", ready: true });

  const settings = readingSettings(group, save, start);
  const named = settings.consumer_group.length > 0;

  useEffect(() => {
    onChange({ ...settings, ...reading });
    // `settings` is rebuilt every render; its three fields are what change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.consumer_group, settings.save_position, settings.start_from, reading]);

  return (
    <div className="streams-reading m-t-15" data-test="HowItReads">
      <strong>How it reads</strong>

      <MessageFormat topic={topic} dataSourceId={dataSourceId} onChange={setReading} />

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

function sendable(reading) {
  // `ready` is the page's, not the server's.
  const { ready, ...body } = reading; // eslint-disable-line no-unused-vars
  return body;
}

function formatsFound(formats) {
  return Object.entries(formats || {})
    .map(([name, count]) => `${name} ${count}`)
    .join(", ");
}

function Analysis({ found, topic, dataSourceId, onEnable, onAgain, saving, analysing, enabled }) {
  const [reading, setReading] = useState({
    ...readingSettings("", false, "latest"),
    value_format: "auto",
    ready: true,
  });
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
          <Button
            size="small"
            className="m-l-10"
            loading={analysing}
            disabled={!reading.ready}
            onClick={() => onAgain(sendable(reading))}
            data-test="AnalyseAgain"
          >
            Analyse again
          </Button>
        </span>
      </div>

      {formatsFound(found.formats) && (
        <p className="streams-muted m-t-5 m-b-0" data-test="FormatsFound">
          Read as: {formatsFound(found.formats)}
        </p>
      )}

      {found.problem ? (
        <Alert
          className="m-t-10"
          type="error"
          showIcon
          data-test="ReadingProblem"
          message={found.problem}
          description="Change the message format below and analyse again."
        />
      ) : (
        found.malformed > 0 && (
          <Alert
            className="m-t-10"
            type="warning"
            showIcon
            message={`${found.malformed} of ${found.read} messages could not be read.`}
            description="Those are not stored and not counted. A schema inferred from the rest may be missing fields that only appear in them."
          />
        )
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

      <HowItReads topic={topic} dataSourceId={dataSourceId} onChange={setReading} />

      {/* Already on: offering to enable it again would do nothing, and the
          control that matters is Turn off, which is in the row above. What it
          can still do is change how it reads. */}
      <div className="streams-enable">
        {enabled ? (
          <Button
            onClick={() => onEnable(sendable(reading))}
            loading={saving}
            disabled={!reading.ready}
            data-test="SaveHowItReads"
          >
            Save how it reads
          </Button>
        ) : (
          <Button
            type="primary"
            onClick={() => onEnable(sendable(reading))}
            loading={saving}
            disabled={!reading.ready}
            data-test="EnableTopic"
          >
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
    (topic, reading) => {
      setAnalysing(topic);
      // Only the format matters to a reading; the consumer group does not
      // change what the messages are. With none, the server reads the topic
      // the way it is already set to, or automatically.
      const body = reading
        ? { value_format: reading.value_format, schema_files: reading.schema_files, message_type: reading.message_type }
        : {};
      axios
        .post(`api/data_sources/${chosen}/topics/${encodeURIComponent(topic)}/analyse`, body)
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
                    dataSourceId={chosen}
                    onEnable={(reading) => enable(row.name, reading, row.enabled)}
                    onAgain={(reading) => analyse(row.name, reading)}
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

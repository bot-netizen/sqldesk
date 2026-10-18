import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Checkbox from "antd/lib/checkbox";
import Input from "antd/lib/input";
import Radio from "antd/lib/radio";
import Select from "antd/lib/select";
import Switch from "antd/lib/switch";
import Table from "antd/lib/table";
import Tabs from "antd/lib/tabs";
import Tag from "antd/lib/tag";

import HelpTrigger from "@/components/HelpTrigger";
import TimeAgo from "@/components/TimeAgo";
import Tooltip from "@/components/Tooltip";
import { axios } from "@/services/axios";
import notification from "@/services/notification";

import "./catalog.less";

/*
  Reviewing what the MCP tools will say about your warehouse.

  Sorted by usage and filtered to the undescribed, because the job is
  otherwise impossible: nobody writes three thousand sentences, and the
  twenty tables anyone actually queries are most of the value. The point of
  the page is to make the work finite.
*/

/*
  What a useful description says, as greyed text in an empty box -- a shape to
  fill in rather than a blank to stare at. The grain, how it is partitioned and
  what the key looks like are what somebody writing a query against a table
  they have never seen gets wrong first.
*/
export const DESCRIPTION_SHAPE = [
  "What it is for, and what nobody should trust about it.",
  "Grain: one row per …   Partitioned by: …",
  "Key: … (format, e.g. string / epoch ms / UUID)",
].join("\n");

function DescriptionCell({ table, onSaved }) {
  const [value, setValue] = useState(table.description || "");
  const [saving, setSaving] = useState(false);
  const dirty = value !== (table.description || "");

  const save = useCallback(() => {
    setSaving(true);
    axios
      .post(`/api/catalog/tables/${table.id}`, { description: value })
      .then((saved) => {
        onSaved(table.id, saved);
        notification.success(`Described ${table.name}.`);
      })
      .catch(() => notification.error("Could not save that."))
      .finally(() => setSaving(false));
  }, [table.id, table.name, value, onSaved]);

  return (
    <div className="catalog-describe">
      <Input.TextArea
        autoSize={{ minRows: 3, maxRows: 8 }}
        value={value}
        placeholder={DESCRIPTION_SHAPE}
        onChange={(event) => setValue(event.target.value)}
        data-test="TableDescription"
      />
      <div className="catalog-describe-actions">
        {/* Where the sentence came from, because it decides what happens to
            it next: a harvest may replace the engine's, never a person's. */}
        {table.description_source === "human" && <Tag>yours</Tag>}
        {table.description_source === "engine" && <Tag color="blue">from the warehouse</Tag>}
        <Button size="small" type="primary" disabled={!dirty} loading={saving} onClick={save}>
          Save
        </Button>
      </div>
    </div>
  );
}

//: What each state is called where somebody reads it, rather than in the
//: database. "Denied" is a decision, not an error, so it is not red.
const SAID = { proposed: "back on the list", approved: "agreed", denied: "denied" };

function Measures({ sourceId }) {
  const [measures, setMeasures] = useState([]);
  const [pending, setPending] = useState(true);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = [];
    if (sourceId) {
      params.push(`data_source_id=${sourceId}`);
    }
    if (pending) {
      params.push("pending=1");
    }
    axios
      .get(`/api/catalog/measures${params.length ? `?${params.join("&")}` : ""}`)
      .then((data) => setMeasures(data.measures))
      .catch(() => notification.error("Could not load the measures."))
      .finally(() => setLoading(false));
  }, [sourceId, pending]);

  useEffect(() => {
    load();
  }, [load]);

  const review = useCallback((measure, status) => {
    axios
      .post(`/api/catalog/measures/${measure.id}`, { status })
      .then((saved) => {
        setMeasures((current) => current.map((m) => (m.id === saved.id ? { ...m, ...saved } : m)));
        notification.success(`${measure.name} ${SAID[saved.status]}.`);
      })
      .catch(() => notification.error("Could not save that."));
  }, []);

  const columns = [
    {
      title: "Table",
      dataIndex: "table_name",
      width: 200,
      render: (name) => <span className="catalog-name">{name}</span>,
    },
    {
      title: "Definition",
      dataIndex: "name",
      render: (name, row) => (
        <span className="catalog-name">
          {name} = {(row.kind || "").toUpperCase()}({row.column_name})
        </span>
      ),
    },
    {
      title: "Written in",
      dataIndex: "usage_count",
      width: 130,
      align: "right",
      // Four teams writing the same definition independently is a different
      // proposition from one person trying it once.
      render: (count) => (count ? `${count} queries` : <span className="catalog-muted">—</span>),
    },
    {
      title: "",
      dataIndex: "status",
      width: 210,
      align: "right",
      // Three states, because "nobody has looked at this" and "we looked and
      // it is wrong" are different answers -- and only one of them should
      // keep coming back on the worklist.
      render: (status, row) => {
        if (status === "proposed") {
          return (
            <span className="catalog-review">
              <Button size="small" type="primary" onClick={() => review(row, "approved")}>
                Agree
              </Button>
              <Button size="small" danger onClick={() => review(row, "denied")}>
                Deny
              </Button>
            </span>
          );
        }
        return (
          <span className="catalog-review">
            <Tag color={status === "approved" ? "green" : null}>{SAID[status]}</Tag>
            <Button size="small" onClick={() => review(row, "proposed")}>
              Undo
            </Button>
          </span>
        );
      },
    },
  ];

  return (
    <div>
      <p className="catalog-muted">
        <HelpTrigger type="MCP_MEASURES" /> Numbers people already compute, found in saved SQL. Nothing here reaches a
        model until you agree it &mdash; a definition that is merely plausible is worse than none, because the wrong
        revenue figure is still a revenue figure.
      </p>
      <div className="catalog-controls">
        <span className="catalog-toggle">
          <Switch
            size="small"
            checked={pending}
            onChange={setPending}
            aria-label="Show only measures nobody has decided on"
          />{" "}
          Only ones nobody has decided on
        </span>
        <Button size="small" onClick={load} loading={loading}>
          Refresh
        </Button>
      </div>
      <Table
        dataSource={measures}
        columns={columns}
        rowKey="id"
        size="small"
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

/*
  The last retrieval score, where somebody will see it.

  The failure this guards against is quiet: a model that cannot find `orders`
  writes something plausible against `order_archive_2019` and returns a
  number, and nobody questions a number. A harvest dropping a table, a column
  renamed upstream, a measure denied by mistake -- all of them look like
  nothing until weeks later.

  So: a number on this page, and the questions that failed by name, because
  "eleven of twelve" with no list is a number nobody can act on. Nothing is
  shown at all where no questions file is configured; an empty widget saying
  "not set up" is a permanent piece of furniture nobody removes.
*/
function EvalScore() {
  const [score, setScore] = useState(null);

  useEffect(() => {
    axios
      .get("/api/catalog/score")
      .then((data) => setScore(data.score))
      // Silent. It decorates the page; failing to read it must never be the
      // reason somebody cannot see their catalog.
      .catch(() => {});
  }, []);

  if (!score || !score.questions) {
    return null;
  }

  const missed = score.questions - score.passed;
  return (
    <Alert
      className="catalog-score"
      type={missed ? "warning" : "success"}
      showIcon
      message={
        <span>
          {score.passed} of {score.questions} questions answered from the catalog
          {score.at && (
            <span className="catalog-muted">
              {" \u00b7 checked "}
              <TimeAgo date={score.at} />
            </span>
          )}
        </span>
      }
      description={
        missed ? (
          <span>
            Not found for: {score.missed.join("; ")}. Nothing calls a model to decide this &mdash; these are questions
            whose tables, measures or confirmed queries were simply not in what an AI client was handed.
          </span>
        ) : null
      }
    />
  );
}

/*
  The queries somebody has confirmed as the right answer to a question.

  The strongest thing this page can give a model, and the one part of the
  catalog that cannot be mined: a person reads the SQL and says yes. Which
  makes it the one part that can go quietly wrong -- the claim is about the
  text they read, so an edit afterwards leaves a signature on a document
  nobody has seen.

  Those come first here, and they are the reason the tab exists. Everywhere
  else in the product they are invisible: the MCP tools drop them rather than
  describe them as stale, because a model reading "verified, but" reads the
  first word. So if this list does not put them in front of somebody,
  re-confirming never happens.
*/
function VerifiedQueries() {
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("/api/catalog/queries")
      .then((data) => setQueries(data.queries))
      .catch(() => notification.error("Could not load the confirmed queries."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const withdraw = useCallback((row) => {
    axios
      .delete(`/api/catalog/queries/${row.query_id}`)
      .then(() => {
        setQueries((current) => current.filter((q) => q.query_id !== row.query_id));
        notification.success(`${row.query_name} is no longer confirmed.`);
      })
      .catch(() => notification.error("Could not save that."));
  }, []);

  const reconfirm = useCallback((row) => {
    // The same call that confirms it the first time. Rewriting the hash is
    // the person saying they have read the new version -- which is why this
    // button says "read it again" and not "refresh".
    axios
      .post(`/api/catalog/queries/${row.query_id}`, { question: row.question, note: row.note })
      .then(() => {
        setQueries((current) => current.map((q) => (q.query_id === row.query_id ? { ...q, current: true } : q)));
        notification.success(`${row.query_name} confirmed again.`);
      })
      .catch(() => notification.error("Could not save that."));
  }, []);

  // Drifted first: they are the work. Within each group, most recent first,
  // which is the order the server returns.
  const ordered = useMemo(() => [...queries].sort((a, b) => Number(a.current) - Number(b.current)), [queries]);

  const columns = [
    {
      title: "Question",
      dataIndex: "question",
      render: (question, row) => (
        <span>
          <a href={`queries/${row.query_id}`}>{question || row.query_name}</a>
          {question && <div className="catalog-muted">{row.query_name}</div>}
          {row.note && <div className="catalog-muted">{row.note}</div>}
        </span>
      ),
    },
    {
      title: "Confirmed",
      dataIndex: "verified_at",
      width: 220,
      render: (at, row) => (
        <span className="catalog-muted">
          {row.verified_by ? `${row.verified_by}, ` : ""}
          <TimeAgo date={at} />
        </span>
      ),
    },
    {
      title: "",
      dataIndex: "current",
      width: 240,
      align: "right",
      render: (current, row) =>
        current ? (
          <span className="catalog-review">
            <Tag color="green">confirmed</Tag>
            <Button size="small" onClick={() => withdraw(row)}>
              Withdraw
            </Button>
          </span>
        ) : (
          <span className="catalog-review">
            <Tooltip title="The SQL has changed since this was confirmed, so no model is being told about it.">
              <Tag color="orange">edited since</Tag>
            </Tooltip>
            <Button size="small" type="primary" onClick={() => reconfirm(row)}>
              I have read it again
            </Button>
          </span>
        ),
    },
  ];

  const drifted = queries.filter((row) => !row.current).length;

  return (
    <div>
      <p className="catalog-muted">
        Queries somebody has read and confirmed as the right answer to a question. An AI client is told to prefer one of
        these, unchanged, over SQL of its own &mdash; it is the strongest thing this catalog carries.
      </p>
      {drifted > 0 && (
        <Alert
          type="warning"
          showIcon
          className="catalog-drifted"
          // Not `plural`, which would say "querys".
          message={
            drifted === 1
              ? "1 query has been edited since it was confirmed"
              : `${drifted} queries have been edited since they were confirmed`
          }
          description="Nothing is being told they are confirmed while that is true. Read the SQL and confirm it again, or withdraw it."
        />
      )}
      <div className="catalog-controls">
        <Button size="small" onClick={load} loading={loading}>
          Refresh
        </Button>
      </div>
      <Table
        dataSource={ordered}
        columns={columns}
        rowKey="query_id"
        size="small"
        loading={loading}
        locale={{
          emptyText: "Nothing confirmed yet. Open a query you trust and confirm it from its page.",
        }}
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

/*
  Harvesting now rather than at the next scheduled run: for a data source
  added this morning, or a schema that changed an hour ago.

  "Only what has not been harvested" is the default, because it is the cheap
  answer to the common case: a source with nothing in the catalog yet, filled
  without re-reading every other one. Each source is its own job on the
  worker, so the page asks the server what is still waiting rather than
  guessing, and stops asking once nothing is.
*/
function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function useHarvest(onFinished) {
  const [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(false);

  const loadSources = useCallback(
    () =>
      axios
        .get("/api/catalog/sources")
        .then((data) => setSources(data.sources))
        .catch(() => {}),
    []
  );

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const inFlight = sources.some((source) => source.state);

  useEffect(() => {
    if (!inFlight) {
      return undefined;
    }
    const timer = setInterval(loadSources, 3000);
    return () => clearInterval(timer);
  }, [inFlight, loadSources]);

  // The moment the last harvest in flight finishes, the tables it wrote are
  // worth showing -- without anybody pressing Refresh to find out.
  const wasInFlight = useRef(false);
  useEffect(() => {
    if (wasInFlight.current && !inFlight) {
      notification.success("Harvest finished.");
      onFinished();
    }
    wasInFlight.current = inFlight;
  }, [inFlight, onFinished]);

  const harvest = useCallback(
    (body) => {
      setBusy(true);
      return axios
        .post("/api/catalog/harvest", body)
        .then(({ queued, skipped }) => {
          if (queued.length) {
            notification.success(`Harvesting ${plural(queued.length, "data source")}.`);
          }
          if (skipped.length) {
            notification.info(
              "Not harvested",
              skipped.map((source) => `${source.name}: ${source.reason}`).join(". ") + "."
            );
          }
          if (!queued.length && !skipped.length) {
            notification.info("Every data source is already in the catalog.");
          }
          return loadSources();
        })
        .catch(() => notification.error("Could not start the harvest."))
        .finally(() => setBusy(false));
    },
    [loadSources]
  );

  // Not harvested: nothing in the catalog, not paused, and not already on its way.
  const unharvested = sources.filter((source) => !source.tables && !source.paused && !source.state);

  return { sources, busy, inFlight, unharvested, harvest };
}

function HarvestButton({ harvesting, sourceId }) {
  const { sources, busy, unharvested, harvest } = harvesting;

  if (sourceId) {
    const source = sources.find((candidate) => candidate.id === sourceId);
    return (
      <Button
        size="small"
        type="primary"
        loading={busy}
        disabled={!source || source.paused || !!source.state}
        onClick={() => harvest({ data_source_id: sourceId })}
      >
        {source && source.state ? "Harvesting…" : `Harvest ${source ? source.name : "this data source"}`}
      </Button>
    );
  }

  const button = (
    <Button
      size="small"
      type="primary"
      loading={busy}
      disabled={!unharvested.length}
      onClick={() => harvest({ only: "unharvested" })}
    >
      {unharvested.length ? `Harvest ${plural(unharvested.length, "new data source")}` : "Harvest new data sources"}
    </Button>
  );
  if (unharvested.length) {
    return button;
  }
  return (
    <Tooltip title="Every data source is in the catalog already. Pick one to harvest it again, or use the Data sources tab.">
      {/* A disabled button swallows the hover its tooltip needs. */}
      <span className="catalog-harvest-disabled">{button}</span>
    </Tooltip>
  );
}

function Sources({ harvesting }) {
  const { sources, busy, harvest } = harvesting;

  const columns = [
    {
      title: "Data source",
      dataIndex: "name",
      render: (name, row) => (
        <div>
          <div>{name}</div>
          <div className="catalog-muted">{row.type}</div>
        </div>
      ),
    },
    {
      title: "In the catalog",
      dataIndex: "tables",
      width: 150,
      align: "right",
      render: (tables) => (tables ? plural(tables, "table") : <span className="catalog-muted">not harvested</span>),
    },
    {
      title: "Last harvested",
      dataIndex: "harvested_at",
      width: 230,
      // "Stale" is the server's judgement, not a threshold invented here: it
      // is the same policy the MCP tools warn a model with, and two places
      // deciding it separately is two places that disagree after a settings
      // change. A source never harvested is not stale -- there is nothing to
      // be out of date, and the column already says "not harvested".
      render: (when, row) =>
        when ? (
          <span>
            <TimeAgo date={when} />
            {row.stale_for && (
              <Tooltip
                title={`Nothing has been harvested for ${row.stale_for}. AI clients are being warned that what this describes may have changed.`}
              >
                <Tag color="orange" className="m-l-5">
                  stale
                </Tag>
              </Tooltip>
            )}
          </span>
        ) : (
          <span className="catalog-muted">—</span>
        ),
    },
    {
      title: "",
      dataIndex: "state",
      width: 140,
      align: "right",
      render: (state, row) => {
        if (state === "running") {
          return <Tag color="blue">Harvesting…</Tag>;
        }
        if (state === "queued") {
          return <Tag>Waiting</Tag>;
        }
        if (row.paused) {
          return <Tag>Paused</Tag>;
        }
        return (
          <Button size="small" onClick={() => harvest({ data_source_id: row.id })}>
            Harvest
          </Button>
        );
      },
    },
  ];

  return (
    <div>
      <p className="catalog-muted">
        Harvesting reads each data source&apos;s schema and the saved SQL that ran against it recently. It happens on a
        schedule; harvest here when you would rather not wait. It never touches a description somebody wrote.
      </p>
      <div className="catalog-controls">
        <Button size="small" loading={busy} onClick={() => harvest({})}>
          Harvest every data source again
        </Button>
      </div>
      <Table dataSource={sources} columns={columns} rowKey="id" size="small" pagination={false} />
    </div>
  );
}

//: Which tables, by whether anybody has written what they are for.
const DESCRIBED = [
  { value: "all", label: "All" },
  { value: "described", label: "With a description" },
  { value: "undescribed", label: "Missing one" },
];

export default function Catalog() {
  const [tables, setTables] = useState([]);
  const [sources, setSources] = useState([]);
  const [sourceId, setSourceId] = useState(null);
  const [described, setDescribed] = useState("all");
  const [showHidden, setShowHidden] = useState(false);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [counts, setCounts] = useState({ total: 0, limit: 0, hidden: 0 });
  const [loading, setLoading] = useState(true);

  // Asked of the server, which searches every table rather than the 200 this
  // page holds -- so a keystroke is not a request; a pause is.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(typed.trim()), 300);
    return () => clearTimeout(timer);
  }, [typed]);

  const undescribed = described === "undescribed";

  const load = useCallback(() => {
    setLoading(true);
    const params = [];
    if (sourceId) {
      params.push(`data_source_id=${sourceId}`);
    }
    if (described === "undescribed") {
      params.push("undescribed=1");
    } else if (described === "described") {
      params.push("described=1");
    }
    if (showHidden) {
      params.push("hidden=1");
    }
    if (search) {
      params.push(`q=${encodeURIComponent(search)}`);
    }
    axios
      .get(`/api/catalog${params.length ? `?${params.join("&")}` : ""}`)
      .then((data) => {
        setTables(data.tables);
        setCounts({ total: data.total || 0, limit: data.limit || 0, hidden: data.hidden_count || 0 });
      })
      .catch(() => notification.error("Could not load the catalog."))
      .finally(() => setLoading(false));
  }, [sourceId, described, showHidden, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    axios
      .get("api/data_sources")
      .then(setSources)
      .catch(() => {});
  }, []);

  const onSaved = useCallback((id, saved) => {
    setTables((current) =>
      current.map((table) =>
        table.id === id
          ? { ...table, description: saved.description, description_source: saved.description_source }
          : table
      )
    );
  }, []);

  const setHidden = useCallback(
    (table, hidden) => {
      axios
        .post(`/api/catalog/tables/${table.id}`, { hidden })
        .then(() => {
          setCounts((current) => ({ ...current, hidden: current.hidden + (hidden ? 1 : -1) }));
          setTables((current) =>
            showHidden
              ? current.map((t) => (t.id === table.id ? { ...t, hidden } : t))
              : current.filter((t) => t.id !== table.id)
          );
          notification.success(
            hidden
              ? `Hid ${table.name}. It is no longer listed here or offered to MCP, and can still be queried.`
              : `${table.name} is back.`
          );
        })
        .catch(() => notification.error("Could not save that."));
    },
    [showHidden]
  );

  const missing = useMemo(() => tables.filter((table) => !table.description).length, [tables]);
  const harvesting = useHarvest(load);

  const columns = [
    {
      title: "Table",
      dataIndex: "name",
      width: 260,
      render: (name, row) => (
        <div>
          <div className="catalog-name">
            {name} {row.hidden && <Tag>hidden</Tag>}
          </div>
          <div className="catalog-muted">{row.column_count} columns</div>
        </div>
      ),
    },
    {
      title: "Used by",
      dataIndex: "usage_count",
      width: 110,
      align: "right",
      // The ranking signal, and worth showing rather than only sorting by:
      // it is the answer to "is this worth my time to describe".
      render: (count) => (count ? `${count} queries` : <span className="catalog-muted">—</span>),
    },
    {
      title: "What it is for",
      dataIndex: "description",
      render: (_, row) => <DescriptionCell table={row} onSaved={onSaved} />,
    },
    {
      title: "Hide",
      dataIndex: "hidden",
      width: 70,
      align: "center",
      render: (hidden, row) => (
        <Tooltip title="Hidden tables are left off this page and out of what MCP offers. They can still be queried.">
          <Checkbox
            checked={!!hidden}
            onChange={(event) => setHidden(row, event.target.checked)}
            aria-label={`Hide ${row.name}`}
            data-test="HideTable"
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <React.Fragment>
      <div className="p-15 catalog-page" data-test="AdminCatalog">
        <div className="catalog-header">
          <h3>
            Catalog <HelpTrigger type="MCP_CATALOG" />
          </h3>
          <p className="catalog-muted">
            What the MCP tools know about your warehouse. Structure and usage are harvested; what a table is{" "}
            <em>for</em> is the part only a person can write, and{" "}
            <HelpTrigger type="MCP_SEMANTIC" showTooltip={false} renderAsLink>
              kept in git
            </HelpTrigger>{" "}
            if you would rather review it as a pull request &mdash; download the YAML here, or write it straight into a
            checkout with <code>manage ai export</code>.
          </p>
        </div>

        <div className="catalog-controls">
          <Select
            allowClear
            className="catalog-source"
            placeholder="Every data source"
            value={sourceId}
            onChange={setSourceId}
            options={sources.map((source) => ({ value: source.id, label: source.name }))}
          />
          <Input.Search
            allowClear
            className="catalog-search"
            placeholder="Search every table, by name or description"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            data-test="CatalogSearch"
          />
          <Radio.Group
            size="small"
            value={described}
            onChange={(event) => setDescribed(event.target.value)}
            optionType="button"
            buttonStyle="solid"
            options={DESCRIBED}
            data-test="DescribedFilter"
          />
          <span className="catalog-toggle">
            <Switch
              size="small"
              checked={showHidden}
              onChange={setShowHidden}
              aria-label="Show hidden tables"
              data-test="ShowHidden"
            />{" "}
            Show hidden{counts.hidden ? ` (${counts.hidden})` : ""}
          </span>
          <Button size="small" onClick={load} loading={loading}>
            Refresh
          </Button>
          <HarvestButton harvesting={harvesting} sourceId={sourceId} />
          {/*
            A plain link rather than a fetch: the browser handles the file,
            the session cookie authenticates it, and nothing has to hold the
            zip in memory to hand it straight back. Absolute, like every
            /api/admin/ path in the admin pages: those routes are registered
            at the root only, not per organization. (The data source list
            this page loads is per organization, so that one is relative.)

            `download` is load-bearing, not decoration. The app puts a click
            handler on the whole body and turns any anchor into a client-side
            route -- so without it the router swallowed this click, pushed
            /<org>/api/catalog/export, and drew its own "page cannot be
            found" over a download that had in fact already succeeded.
            handleNavigationIntent skips anchors carrying it.
          */}
          <a
            download
            className="catalog-download"
            href={`/api/catalog/export${sourceId ? `?data_source_id=${sourceId}` : ""}`}
          >
            <Button size="small">Download YAML</Button>
          </a>
        </div>

        <EvalScore />

        <Tabs defaultActiveKey="tables" className="catalog-tabs">
          <Tabs.TabPane tab="Tables" key="tables">
            {!loading && tables.length === 0 && (
              <Alert
                type="info"
                showIcon
                message={harvesting.inFlight ? "Harvesting" : "Nothing harvested yet"}
                description={
                  harvesting.inFlight
                    ? "The tables appear here as soon as it finishes."
                    : "The catalog fills on a schedule. Harvest now to fill it straight away."
                }
                action={
                  !harvesting.inFlight && (
                    <Button
                      size="small"
                      type="primary"
                      loading={harvesting.busy}
                      onClick={() => harvesting.harvest({ only: "unharvested" })}
                    >
                      Harvest now
                    </Button>
                  )
                }
              />
            )}

            {counts.total > tables.length && (
              <p className="catalog-muted catalog-count" data-test="CatalogTruncated">
                Showing the {tables.length} most used of {counts.total.toLocaleString()}.{" "}
                {search ? "Narrow the search to see the rest." : "Search to find any of them."}
              </p>
            )}

            {tables.length > 0 && missing > 0 && !undescribed && (
              <p className="catalog-muted catalog-count">
                {missing} of these {tables.length} have no description.
              </p>
            )}

            <Table
              className="catalog-table"
              dataSource={tables}
              columns={columns}
              rowKey="id"
              size="small"
              loading={loading}
              pagination={{ pageSize: 20, showSizeChanger: false }}
            />
          </Tabs.TabPane>
          <Tabs.TabPane tab="Measures" key="measures">
            <Measures sourceId={sourceId} />
          </Tabs.TabPane>
          <Tabs.TabPane tab="Confirmed queries" key="verified">
            <VerifiedQueries />
          </Tabs.TabPane>
          <Tabs.TabPane tab="Data sources" key="sources">
            <Sources harvesting={harvesting} />
          </Tabs.TabPane>
        </Tabs>
      </div>
    </React.Fragment>
  );
}

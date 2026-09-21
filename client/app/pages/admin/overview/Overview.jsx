import React, { useCallback, useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Table from "antd/lib/table";
import Modal from "antd/lib/modal";
import Tooltip from "@/components/Tooltip";

import Layout from "@/components/admin/Layout";
import Link from "@/components/Link";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";
import routes from "@/services/routes";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";

import { pressure, formatBytes, formatElapsed, formatRatio, UNKNOWN } from "./pressure";

import "./overview.less";

const REFRESH_MS = 60 * 1000;

/*
  The admin overview.

  One endpoint, polled, because the page shows a single moment: five calls
  would show five, which is how a dashboard starts contradicting itself.

  It is careful about one distinction throughout. "Running" comes from RQ and
  includes the scheduler's own refreshes; "asking" comes from the events
  table, which only records what people ran. They are different populations
  and the page says so rather than letting someone add them together.
*/

function Meter({ label, detail, used, limit }) {
  const { level, fraction } = pressure(used, limit);
  const percent = fraction === null ? 0 : Math.min(100, Math.round(fraction * 100));

  return (
    <div className="admin-meter" data-level={level}>
      <div className="admin-meter-head">
        <span className="admin-meter-label">{label}</span>
        <span className="admin-meter-value">{detail}</span>
      </div>
      <div className="admin-meter-track">
        <div className="admin-meter-fill" style={{ width: `${percent}%` }} />
      </div>
      {level === UNKNOWN && <div className="admin-meter-note">No limit configured</div>}
    </div>
  );
}

Meter.propTypes = {
  label: PropTypes.string.isRequired,
  detail: PropTypes.node,
  used: PropTypes.number,
  limit: PropTypes.number,
};

Meter.defaultProps = { detail: null, used: null, limit: null };

function Panel({ title, note, children, actions }) {
  return (
    <section className="admin-panel">
      <header className="admin-panel-head">
        <h2>{title}</h2>
        {actions}
      </header>
      {note && <p className="admin-panel-note">{note}</p>}
      {children}
    </section>
  );
}

Panel.propTypes = {
  title: PropTypes.string.isRequired,
  note: PropTypes.node,
  children: PropTypes.node,
  actions: PropTypes.node,
};

Panel.defaultProps = { note: null, children: null, actions: null };

function RunningQueries({ rows, onKill }) {
  const columns = [
    {
      title: "Query",
      dataIndex: "query_name",
      render: (name, row) =>
        row.query_id ? (
          <Link href={`queries/${row.query_id}`}>{name || `Query ${row.query_id}`}</Link>
        ) : (
          <span className="admin-muted">Ad-hoc</span>
        ),
    },
    {
      title: "Who",
      dataIndex: "user_name",
      // A scheduled refresh has no user. Saying so beats an empty cell,
      // because "nobody is waiting for this" changes what you do about it.
      render: (name, row) => name || <span className="admin-muted">{row.scheduled ? "Scheduler" : "—"}</span>,
    },
    { title: "Data source", dataIndex: "data_source", render: (name) => name || "—" },
    {
      title: "Running for",
      dataIndex: "elapsed",
      align: "right",
      render: (elapsed) => <span className="admin-elapsed">{formatElapsed(elapsed)}</span>,
    },
    {
      title: "",
      dataIndex: "job_id",
      align: "right",
      render: (jobId, row) => (
        <Button size="small" danger onClick={() => onKill(row)} data-test="KillQueryButton">
          Kill
        </Button>
      ),
    },
  ];

  return (
    <Table
      size="small"
      rowKey="job_id"
      dataSource={rows}
      columns={columns}
      pagination={false}
      locale={{ emptyText: "Nothing is running." }}
    />
  );
}

RunningQueries.propTypes = {
  rows: PropTypes.arrayOf(PropTypes.object), // eslint-disable-line react/forbid-prop-types
  onKill: PropTypes.func.isRequired,
};

RunningQueries.defaultProps = { rows: [] };

function TopUsers({ rows, windowMinutes }) {
  if (!rows.length) {
    return <p className="admin-muted">Nobody has run a query in the last {windowMinutes} minutes.</p>;
  }
  const most = Math.max(...rows.map((r) => r.executions));
  return (
    <ul className="admin-top-users">
      {rows.map((user) => (
        <li key={user.id}>
          <span className="admin-top-user-name">{user.name}</span>
          <span className="admin-top-user-bar">
            <span style={{ width: `${Math.round((user.executions / most) * 100)}%` }} />
          </span>
          <span className="admin-top-user-count">{user.executions}</span>
        </li>
      ))}
    </ul>
  );
}

TopUsers.propTypes = {
  rows: PropTypes.arrayOf(PropTypes.object), // eslint-disable-line react/forbid-prop-types
  windowMinutes: PropTypes.number,
};

TopUsers.defaultProps = { rows: [], windowMinutes: 60 };

export default function Overview({ onError }) {
  const [overview, setOverview] = useState(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const load = useCallback(
    () =>
      axios
        .get("/api/admin/overview")
        .then(setOverview)
        .catch((error) => onErrorRef.current(error)),
    []
  );

  useEffect(() => {
    recordEvent("view", "page", "admin/overview");
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const kill = (row) => {
    Modal.confirm({
      title: "Stop this query?",
      content: `${row.query_name || "This query"} has been running for ${formatElapsed(row.elapsed)}${
        row.user_name ? ` for ${row.user_name}` : ""
      }. Stopping it is recorded.`,
      okText: "Kill it",
      okType: "danger",
      onOk: () =>
        axios
          .delete(`/api/admin/jobs/${row.job_id}`)
          .then(() => {
            notification.success("Query stopped.");
            return load();
          })
          .catch(() => notification.error("Could not stop that query.")),
    });
  };

  const cleanup = (what, label) =>
    axios
      .post(`/api/admin/cleanup/${what}`)
      .then(() => notification.success(`${label} cleanup started.`))
      .catch(() => notification.error(`Could not start the ${label.toLowerCase()} cleanup.`));

  if (!overview) {
    return (
      <Layout activeTab="overview">
        <div className="admin-overview-page admin-muted">Loading…</div>
      </Layout>
    );
  }

  const { running, queues, workers, limits, storage, activity } = overview;
  const queued = Object.values(queues).reduce((total, q) => total + q.queued, 0);

  return (
    <Layout activeTab="overview">
      <div className="admin-overview-page">
        <div className="admin-overview-columns">
          <Panel title="Running now" note="From the job queue, so this includes the scheduler's own refreshes.">
            <RunningQueries rows={running} onKill={kill} />
          </Panel>

          <Panel title="Headroom">
            <Meter
              label="Postgres connections"
              detail={`${limits.postgres.used} / ${limits.postgres.max}`}
              used={limits.postgres.used}
              limit={limits.postgres.max}
            />
            <Meter
              label="Redis (app)"
              detail={
                limits.redis.app.max_memory
                  ? `${formatBytes(limits.redis.app.used_memory)} / ${formatBytes(limits.redis.app.max_memory)}`
                  : formatBytes(limits.redis.app.used_memory)
              }
              used={limits.redis.app.used_memory}
              limit={limits.redis.app.max_memory}
            />
            <Meter
              label="Redis (jobs)"
              detail={
                limits.redis.rq.max_memory
                  ? `${formatBytes(limits.redis.rq.used_memory)} / ${formatBytes(limits.redis.rq.max_memory)}`
                  : formatBytes(limits.redis.rq.used_memory)
              }
              used={limits.redis.rq.used_memory}
              limit={limits.redis.rq.max_memory}
            />
            <Meter
              label="Workers busy"
              detail={`${workers.busy} / ${workers.total}`}
              used={workers.busy}
              limit={workers.total}
            />
            <div className="admin-queued" data-backing-up={queued > workers.total}>
              {queued} waiting in the queues
              {queued > workers.total && " — more than there are workers"}
            </div>
          </Panel>

          <Panel
            title={`Who is asking (last ${activity.window_minutes} minutes)`}
            note="From recorded events, which cover what people ran — not the scheduler."
          >
            <div className="admin-activity-summary">
              <span>
                <strong>{activity.executions}</strong> executions
              </span>
              <Tooltip title="Results served from a stored result rather than re-run.">
                <span>
                  <strong>{formatRatio(activity.cache_hit_ratio)}</strong> from cache
                </span>
              </Tooltip>
            </div>
            <TopUsers rows={activity.top_users} windowMinutes={activity.window_minutes} />
          </Panel>

          <Panel title="Storage">
            <dl className="admin-storage">
              <dt>Database</dt>
              <dd>{formatBytes(storage.database)}</dd>
              <dt>Query results</dt>
              <dd>
                {formatBytes(storage.query_results)}
                <Button size="small" onClick={() => cleanup("query_results", "Query result")}>
                  Clean up now
                </Button>
              </dd>
              <dt>
                Events
                <span className="admin-muted"> — one row per execution</span>
              </dt>
              <dd>
                {formatBytes(storage.events)}
                <Button size="small" onClick={() => cleanup("events", "Events")}>
                  Prune old
                </Button>
              </dd>
            </dl>
          </Panel>
        </div>
      </div>
    </Layout>
  );
}

Overview.propTypes = { onError: PropTypes.func };
Overview.defaultProps = { onError: () => {} };

routes.register(
  "Admin.Overview",
  routeWithUserSession({
    path: "/admin/overview",
    title: "Admin Overview",
    render: (pageProps) => <Overview {...pageProps} />,
  })
);

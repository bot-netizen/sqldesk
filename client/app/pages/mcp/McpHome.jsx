import React, { useCallback, useEffect, useState } from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Table from "antd/lib/table";
import Tag from "antd/lib/tag";
import Tooltip from "@/components/Tooltip";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import TimeAgo from "@/components/TimeAgo";
import { axios } from "@/services/axios";
import { currentUser, clientConfig } from "@/services/auth";
import routes from "@/services/routes";

import "./mcp.less";

/*
  MCP: how to connect, who is connected, and what they have been asking for.

  The audit is the reason this page exists. A tool server that answers
  questions about somebody's warehouse, to a client nobody can see, is a thing
  an administrator has to be able to look at -- so the log is the page rather
  than a tab on it.
*/

const OUTCOME = {
  ok: { colour: null, label: "ok" },
  error: { colour: "red", label: "error" },
  refused: { colour: "orange", label: "refused" },
};

function ConnectPanel({ origin }) {
  return (
    <div className="mcp-panel">
      <h3>Connecting a client</h3>
      <p className="mcp-muted">
        One endpoint, JSON-RPC over HTTP, authenticated with a SQLDesk API key — the one on your profile page. Every
        call runs as that user and sees only the data sources that user can read.
      </p>
      <pre className="mcp-pre">{`${origin}/mcp

Authorization: Bearer <your SQLDesk API key>`}</pre>
      <p className="mcp-muted">With Claude Code:</p>
      <pre className="mcp-pre">{`claude mcp add --transport http sqldesk ${origin}/mcp \\
  --header "Authorization: Bearer <your API key>"`}</pre>
      <p className="mcp-muted">
        Eight tools, in the order they are meant to be used: <code>find_queries</code> and <code>find_dashboards</code>{" "}
        to look for work that already exists; <code>find_context</code>, <code>expand_table</code> and{" "}
        <code>list_data_sources</code> to understand the data; <code>check_sql</code> for the shape and{" "}
        <code>explain_query</code> for the cost; then <code>run_query</code>, which returns up to 1000 rows and runs on
        a worker like any other query.
      </p>
    </div>
  );
}

ConnectPanel.propTypes = { origin: PropTypes.string.isRequired };

function ActivePanel({ active, minutes }) {
  if (!active.length) {
    return (
      <div className="mcp-panel">
        <h3>Nobody connected</h3>
        <p className="mcp-muted">No MCP session has been active in the last {minutes} minutes.</p>
      </div>
    );
  }
  return (
    <div className="mcp-panel">
      <h3>
        Active sessions{" "}
        {/* Not a socket: this transport is one POST per call, so "connected"
            can only honestly mean "seen recently". */}
        <Tooltip
          title={`A session seen in the last ${minutes} minutes. The transport holds no connection open, so this means recently active rather than attached.`}
        >
          <span className="mcp-muted" style={{ fontWeight: 400, fontSize: 13 }}>
            — seen in the last {minutes} minutes
          </span>
        </Tooltip>
      </h3>
      <dl className="mcp-facts">
        {active.map((session) => (
          <React.Fragment key={session.session_id}>
            <dt>{session.user || "unknown"}</dt>
            <dd>
              {session.client || "unnamed client"} · {session.calls} call{session.calls === 1 ? "" : "s"} ·{" "}
              <TimeAgo date={session.last_seen} />
            </dd>
          </React.Fragment>
        ))}
      </dl>
    </div>
  );
}

ActivePanel.propTypes = {
  active: PropTypes.arrayOf(PropTypes.object).isRequired, // eslint-disable-line react/forbid-prop-types
  minutes: PropTypes.number.isRequired,
};

const COLUMNS = [
  {
    title: "When",
    dataIndex: "at",
    width: 130,
    render: (at) => <TimeAgo date={at} />,
  },
  { title: "User", dataIndex: "user", width: 150, render: (user) => user || <em>unauthenticated</em> },
  { title: "Method", dataIndex: "method", width: 120 },
  { title: "Tool", dataIndex: "tool", width: 140, render: (tool) => tool || "" },
  {
    title: "Outcome",
    dataIndex: "outcome",
    width: 100,
    render: (outcome) => {
      const it = OUTCOME[outcome] || OUTCOME.ok;
      return it.colour ? <Tag color={it.colour}>{it.label}</Tag> : <span className="mcp-outcome-ok">{it.label}</span>;
    },
  },
  { title: "Took", dataIndex: "duration_ms", width: 80, render: (ms) => (ms === null ? "" : `${ms} ms`) },
  { title: "From", dataIndex: "remote_addr", width: 130 },
  { title: "Detail", dataIndex: "detail", render: (detail) => <span className="mcp-detail">{detail}</span> },
];

export default function McpHome({ onError }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const isAdmin = currentUser.hasPermission("super_admin");

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get("api/mcp/audit")
      .then(setData)
      .catch(onError)
      .finally(() => setLoading(false));
  }, [onError]);

  useEffect(() => {
    if (isAdmin) {
      load();
    } else {
      setLoading(false);
    }
  }, [isAdmin, load]);

  const origin = window.location.origin;

  return (
    <div className="container mcp-page" data-test="McpHome">
      <div className="mcp-header">
        <h2>MCP</h2>
        <p className="mcp-muted">
          SQLDesk answers questions about your warehouse over the Model Context Protocol, using the catalog it builds
          from your schema and your saved queries.
        </p>
      </div>

      {!clientConfig.aiEnabled && (
        <Alert
          className="m-b-15"
          type="warning"
          showIcon
          message="MCP is off"
          description="Set SQLDESK_FEATURE_AI=true on the server. Until then the endpoint answers 404."
        />
      )}

      <ConnectPanel origin={origin} />

      {!isAdmin && (
        <Alert
          type="info"
          showIcon
          message="The audit is for administrators"
          description="It names every user, every question and every address, so it is not shown here."
        />
      )}

      {isAdmin && data && <ActivePanel active={data.active} minutes={data.active_minutes} />}

      {isAdmin && (
        <React.Fragment>
          <h3 className="mcp-section-title">
            Audit{" "}
            <Button size="small" onClick={load} loading={loading} data-test="McpAuditRefresh">
              Refresh
            </Button>
          </h3>
          {data && data.events.length === 0 ? (
            <div className="mcp-empty">Nothing yet. Connect a client and its calls will appear here.</div>
          ) : (
            <Table
              className="mcp-audit-table"
              dataSource={data ? data.events : []}
              columns={COLUMNS}
              rowKey="id"
              size="small"
              loading={loading}
              pagination={{ pageSize: 25, showSizeChanger: false }}
              data-test="McpAuditTable"
            />
          )}
        </React.Fragment>
      )}
    </div>
  );
}

McpHome.propTypes = { onError: PropTypes.func };
McpHome.defaultProps = { onError: () => {} };

routes.register(
  "Admin.MCP",
  routeWithUserSession({
    path: "/admin/mcp",
    title: "MCP",
    render: (pageProps) => <McpHome {...pageProps} />,
  })
);

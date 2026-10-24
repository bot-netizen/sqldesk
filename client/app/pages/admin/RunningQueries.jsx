import React, { useCallback, useEffect } from "react";
import PropTypes from "prop-types";
import Button from "antd/lib/button";
import Modal from "antd/lib/modal";
import Table from "antd/lib/table";

import Layout from "@/components/admin/Layout";
import StaleNotice from "@/components/admin/StaleNotice";
import Link from "@/components/Link";
import LoadingState from "@/components/items-list/components/LoadingState";
import { axios } from "@/services/axios";
import notification from "@/services/notification";
import recordEvent from "@/services/recordEvent";
import usePolledData from "@/lib/hooks/usePolledData";

import { formatElapsed } from "./overview/pressure";

/*
  What the workers have in flight, and the one button that ends it.

  It was a panel at the bottom of the overview, which is the wrong place for
  two reasons. It is read while somebody is waiting -- so it wants to refresh
  far more often than table sizes and an hour of aggregated events do -- and it
  is the only page in this section with an action on it, which should not be
  something you scroll past four panels of figures to reach.

  Fifteen seconds rather than the overview's minute. Short enough that a query
  that has just ended stops being offered a Kill button; long enough that
  leaving the page open is not itself load.
*/
const REFRESH_MS = 15 * 1000;

export default function RunningQueries({ onError }) {
  const load = useCallback(() => axios.get("/api/admin/queries/running").then((data) => data.running), []);
  const {
    data: running,
    loadedAt,
    failedAt,
    refresh,
  } = usePolledData(load, {
    intervalMs: REFRESH_MS,
    onError,
  });

  useEffect(() => {
    recordEvent("view", "page", "admin/queries/running");
  }, []);

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
            return refresh();
          })
          .catch(() => notification.error("Could not stop that query.")),
    });
  };

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
      // An MCP run does have one -- whoever's API key it was -- but they are
      // not sitting in front of it, which is the same distinction again.
      render: (name, row) =>
        name ? (
          <span>
            {name}
            {row.mcp && <span className="admin-muted"> via MCP</span>}
          </span>
        ) : (
          <span className="admin-muted">{row.scheduled ? "Scheduler" : "—"}</span>
        ),
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
        <Button size="small" danger onClick={() => kill(row)} data-test="KillQueryButton">
          Kill
        </Button>
      ),
    },
  ];

  return (
    <Layout activeTab="running_queries">
      {failedAt && <StaleNotice loadedAt={loadedAt} onRetry={refresh} />}
      {running === null ? (
        <LoadingState className="" />
      ) : (
        <Table
          size="small"
          rowKey="job_id"
          dataSource={running}
          columns={columns}
          pagination={false}
          locale={{ emptyText: "Nothing is running." }}
        />
      )}
    </Layout>
  );
}

RunningQueries.propTypes = { onError: PropTypes.func };
RunningQueries.defaultProps = { onError: () => {} };

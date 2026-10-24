import { omit } from "lodash";
import React, { useCallback, useEffect } from "react";
import PropTypes from "prop-types";

import Layout from "@/components/admin/Layout";
import StaleNotice from "@/components/admin/StaleNotice";
import * as StatusBlock from "@/components/admin/StatusBlock";

import { axios } from "@/services/axios";
import recordEvent from "@/services/recordEvent";
import usePolledData from "@/lib/hooks/usePolledData";

import "./system-status.less";

/*
  Fifteen panels of worker and database figures, refreshed on its own.

  Like the overview, it keeps what it has when a refresh fails: the page is
  read while something is wrong, which is when a request is most likely to be
  the thing that breaks.
*/
const REFRESH_MS = 60 * 1000;

export default function SystemStatus({ onError }) {
  const load = useCallback(() => axios.get("/status.json"), []);
  const { data, loadedAt, failedAt, refresh } = usePolledData(load, { intervalMs: REFRESH_MS, onError });

  useEffect(() => {
    recordEvent("view", "page", "admin/status");
  }, []);

  const manager = data
    ? {
        startedAt: data.manager.started_at * 1000,
        lastRefreshAt: data.manager.last_refresh_at * 1000,
        outdatedQueriesCount: data.manager.outdated_queries_count,
      }
    : null;

  return (
    <Layout activeTab="system_status">
      <div className="system-status-page">
        {failedAt && <StaleNotice loadedAt={loadedAt} onRetry={refresh} />}
        <div className="system-status-page-blocks">
          <div className="system-status-page-block">
            <StatusBlock.General info={data ? omit(data, ["workers", "manager", "database_metrics"]) : {}} />
          </div>
          <div className="system-status-page-block">
            <StatusBlock.Manager info={manager} />
          </div>
          <div className="system-status-page-block">
            <StatusBlock.Queues info={data ? data.manager.queues : []} />
          </div>
          <div className="system-status-page-block">
            <StatusBlock.DatabaseMetrics info={data ? data.database_metrics.metrics || [] : []} />
          </div>
        </div>
      </div>
    </Layout>
  );
}

SystemStatus.propTypes = { onError: PropTypes.func };
SystemStatus.defaultProps = { onError: () => {} };

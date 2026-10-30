import React, { useCallback, useEffect, useState } from "react";
import Alert from "antd/lib/alert";
import Select from "antd/lib/select";
import Table from "antd/lib/table";
import { map, max } from "lodash";

import Layout from "@/components/admin/Layout";
import Link from "@/components/Link";
import { axios } from "@/services/axios";
import recordEvent from "@/services/recordEvent";

import "./audit.less";

/*
  Where the month went.

  Overview answers "what is happening now" and is read while something is
  wrong. This is read afterwards, or on the first of the month, and it reads
  the same `events` rows as a *history* -- which nothing did before, though
  every execution has been recorded there since the fork.

  Three breakdowns rather than one, because "expensive" has three different
  answers and only one of them is a person:

  - **by person**, which is the one that gets asked for;
  - **by data source**, which says where the money went: a thousand runs
    against a cached Postgres and a thousand against a warehouse that bills
    per scan are not the same month;
  - **by query**, so a dashboard refreshing something expensive every minute
    is visible as itself rather than buried in its owner's total.

  A scheduled refresh is not in here. `events` records what a person asked
  for, and that is what an audit is about -- Running Queries is where the
  scheduler's work shows.
*/

const WINDOWS = [
  { value: 7, label: "the last 7 days" },
  { value: 30, label: "the last 30 days" },
  { value: 90, label: "the last 90 days" },
  { value: 365, label: "the last year" },
];

/** A count, grouped so four figures do not read as one long number. */
export function count(n) {
  return Number(n || 0).toLocaleString();
}

/**
 * Executions a day, as a strip.
 *
 * Bars rather than a chart library: it is one series of small integers, and
 * the thing somebody is looking for is a step -- the day the refresh interval
 * was changed, or the day somebody pointed a script at it.
 */
export function Sparkline({ series }) {
  if (!series || series.length === 0) {
    return null;
  }
  const highest = max(map(series, ([, n]) => n)) || 1;
  return (
    <div className="audit-sparkline" data-test="AuditSparkline">
      {map(series, ([day, n]) => (
        <span
          key={day}
          className="audit-sparkline-bar"
          style={{ height: `${Math.max(2, Math.round((n / highest) * 100))}%` }}
          title={`${day}: ${count(n)}`}
        />
      ))}
    </div>
  );
}

export default function Audit() {
  const [audit, setAudit] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState(null);

  useEffect(() => {
    recordEvent("view", "page", "admin/audit");
  }, []);

  const load = useCallback(() => {
    setError(null);
    axios
      .get("api/admin/audit", { params: { days } })
      .then(setAudit)
      .catch(() => setError("The audit could not be read."));
  }, [days]);

  useEffect(load, [load]);

  const columns = (what, link) => [
    {
      title: what,
      dataIndex: "name",
      key: "name",
      render: (name, row) => (link && row.id ? <Link href={link(row)}>{name}</Link> : name),
    },
    {
      title: "Executions",
      dataIndex: "executions",
      key: "executions",
      width: 140,
      align: "right",
      render: count,
    },
  ];

  return (
    <Layout activeTab="audit">
      <div className="admin-audit" data-test="AdminAudit">
        {error && <Alert type="warning" showIcon message={error} className="m-b-15" />}

        <div className="audit-controls">
          <Select value={days} onChange={setDays} style={{ width: 200 }} data-test="AuditWindow">
            {map(WINDOWS, (one) => (
              <Select.Option key={one.value} value={one.value}>
                {one.label}
              </Select.Option>
            ))}
          </Select>
        </div>

        {audit && (
          <>
            <div className="audit-totals" data-test="AuditTotals">
              <div className="audit-total">
                <span className="audit-total-number">{count(audit.executions)}</span>
                <span className="audit-total-label">executions</span>
              </div>
              <div className="audit-total">
                <span className="audit-total-number">
                  {/*
                    Nothing rather than 0% when nothing ran: a ratio of no
                    executions is not a cache missing everything.
                  */}
                  {audit.cache_hit_ratio === null ? "—" : `${Math.round(audit.cache_hit_ratio * 100)}%`}
                </span>
                <span className="audit-total-label">served from cache</span>
              </div>
              <Sparkline series={audit.per_day} />
            </div>

            <div className="audit-tables">
              <Table
                size="small"
                rowKey={(row) => `user-${row.id}`}
                dataSource={audit.top_users}
                columns={columns("Person")}
                pagination={false}
                data-test="AuditByUser"
              />
              <Table
                size="small"
                rowKey={(row) => `source-${row.id}`}
                dataSource={audit.top_data_sources}
                columns={columns("Data source", (row) => `data_sources/${row.id}`)}
                pagination={false}
                data-test="AuditByDataSource"
              />
              <Table
                size="small"
                rowKey={(row) => `query-${row.id}`}
                dataSource={audit.top_queries}
                columns={columns("Query", (row) => `queries/${row.id}`)}
                pagination={false}
                data-test="AuditByQuery"
              />
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}

import { isEmpty } from "lodash";
import React from "react";
import PropTypes from "prop-types";
import Table from "antd/lib/table";
import Skeleton from "antd/lib/skeleton";
import Link from "@/components/Link";
import SchedulePhrase from "@/components/queries/SchedulePhrase";
import { durationHumanize, prettySize } from "@/lib/utils";

// Slowest first, which is what the endpoint returns. A scheduled query is one
// nobody watches run, so this is where a query that has quietly grown from two
// seconds to two minutes shows up.
const columns = [
  {
    title: "Query",
    dataIndex: "name",
    key: "name",
    render: (name, row) => <Link href={`queries/${row.id}`}>{name}</Link>,
  },
  {
    title: "Data source",
    dataIndex: "data_source",
    key: "data_source",
    render: (dataSource) => dataSource || <span className="home-muted">—</span>,
  },
  {
    title: "Runtime",
    dataIndex: "runtime",
    key: "runtime",
    align: "right",
    // A scheduled query that has never run has no runtime yet. Saying so beats
    // a zero, which reads as "instant".
    render: (runtime) =>
      runtime === null || runtime === undefined ? (
        <span className="home-muted">not yet run</span>
      ) : (
        durationHumanize(runtime)
      ),
  },
  {
    title: "Result",
    dataIndex: "result_bytes",
    key: "result_bytes",
    align: "right",
    render: (bytes) => (bytes ? prettySize(bytes) : <span className="home-muted">—</span>),
  },
  {
    title: "Schedule",
    dataIndex: "schedule",
    key: "schedule",
    render: (schedule) => <SchedulePhrase isNew={false} schedule={schedule} />,
  },
];

export default function ScheduledQueriesList({ queries, loading }) {
  return (
    <div className="home-panel">
      <div className="home-panel-title">Scheduled queries, slowest first</div>

      {loading && <Skeleton active paragraph={{ rows: 4 }} title={false} />}

      {!loading && isEmpty(queries) && (
        <p className="home-muted">
          Queries you put on a refresh schedule appear here, slowest first. Set one from the Refresh menu on any{" "}
          <Link href="queries">query</Link>.
        </p>
      )}

      {!loading && !isEmpty(queries) && (
        <Table
          className="home-scheduled-table"
          dataSource={queries}
          columns={columns}
          rowKey="id"
          size="small"
          pagination={false}
        />
      )}
    </div>
  );
}

ScheduledQueriesList.propTypes = {
  queries: PropTypes.arrayOf(PropTypes.object), // eslint-disable-line react/forbid-prop-types
  loading: PropTypes.bool,
};

ScheduledQueriesList.defaultProps = { queries: [], loading: false };

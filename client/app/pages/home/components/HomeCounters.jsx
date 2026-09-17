import React from "react";
import PropTypes from "prop-types";
import Skeleton from "antd/lib/skeleton";
import Link from "@/components/Link";
import { prettySizeWithUnit } from "@/lib/utils";

// Each tile is a link, because a count is nearly always the start of a
// question -- "eleven scheduled queries" is followed by "which ones".
function Counter({ label, value, unit, href, loading }) {
  const body = (
    <React.Fragment>
      <div className="home-counter-value">
        {loading ? (
          <Skeleton title={{ width: 48 }} paragraph={false} active />
        ) : (
          <React.Fragment>
            {value}
            {unit && <span className="home-counter-unit">{unit}</span>}
          </React.Fragment>
        )}
      </div>
      <div className="home-counter-label">{label}</div>
    </React.Fragment>
  );

  return href ? (
    <Link className="home-counter" href={href}>
      {body}
    </Link>
  ) : (
    <div className="home-counter">{body}</div>
  );
}

Counter.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.node,
  unit: PropTypes.string,
  href: PropTypes.string,
  loading: PropTypes.bool,
};

Counter.defaultProps = { value: null, unit: null, href: null, loading: false };

export default function HomeCounters({ counters, loading }) {
  const c = counters || {};
  // Split so the unit can be set smaller than the number: "1.2 GB" reads as one
  // value, and a full-size "GB" competes with the figure it qualifies.
  const storage = prettySizeWithUnit(c.result_storage_bytes || 0);

  return (
    <div className="home-counters">
      <Counter label="Queries" value={c.queries} href="queries" loading={loading} />
      <Counter label="Dashboards" value={c.dashboards} href="dashboards" loading={loading} />
      <Counter label="Scheduled" value={c.scheduled_queries} href="queries?tab=all" loading={loading} />
      <Counter label="Alerts" value={c.alerts} href="alerts" loading={loading} />
      <Counter label="Result storage" value={storage.value} unit={storage.unit} loading={loading} />
    </div>
  );
}

HomeCounters.propTypes = {
  // eslint-disable-next-line react/forbid-prop-types
  counters: PropTypes.object,
  loading: PropTypes.bool,
};

HomeCounters.defaultProps = { counters: null, loading: false };

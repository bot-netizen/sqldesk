import React from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";

import TimeAgo from "@/components/TimeAgo";

/*
  Shown on a self-refreshing page whose last refresh failed.

  The page keeps the figures it had rather than throwing them away, so the one
  thing it owes the reader is that they are not current -- a stale connection
  count read as live is worse than no count at all. The age comes from when the
  figures were last good, not from when the failure happened.
*/
export default function StaleNotice({ loadedAt, onRetry }) {
  return (
    <Alert
      className="m-b-15"
      type="warning"
      showIcon
      data-test="StaleNotice"
      message={
        <span>
          Could not refresh. These figures are from {loadedAt ? <TimeAgo date={loadedAt} /> : "an earlier reading"}.
        </span>
      }
      action={
        <Button size="small" onClick={onRetry}>
          Try now
        </Button>
      }
    />
  );
}

StaleNotice.propTypes = {
  loadedAt: PropTypes.number,
  onRetry: PropTypes.func.isRequired,
};

StaleNotice.defaultProps = { loadedAt: null };

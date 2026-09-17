import { includes } from "lodash";
import React from "react";
import PropTypes from "prop-types";
import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import Timer from "@/components/Timer";

// Shared with QueryExecutionMetadata, which shows the same words in the footer
// while a query runs. Two places saying "Executing query..." slightly
// differently would be two places to keep in step.
export function executionStatusMessage(status, isCancelling) {
  if (isCancelling) {
    return "Cancelling\u2026";
  }
  switch (status) {
    case "waiting":
      return "Query in queue\u2026";
    case "processing":
      return "Executing query\u2026";
    case "loading-result":
      return "Loading results\u2026";
    default:
      return null;
  }
}

export default function QueryExecutionStatus({ status, updatedAt, error, isCancelling, onCancel }) {
  const alertType = status === "failed" ? "error" : "info";
  const showTimer = status !== "failed" && updatedAt;
  const isCancelButtonAvailable = includes(["waiting", "processing"], status);
  let message = executionStatusMessage(status, isCancelling);

  if (status === "failed") {
    message = (
      <React.Fragment>
        Error running query: <strong>{error}</strong>
      </React.Fragment>
    );
  }

  return (
    <Alert
      data-test="QueryExecutionStatus"
      type={alertType}
      message={
        <div className="d-flex align-items-center">
          <div className="flex-fill p-t-5 p-b-5">
            {message} {showTimer && <Timer from={updatedAt} />}
          </div>
          <div>
            {isCancelButtonAvailable && (
              <Button className="m-l-10" type="primary" size="small" disabled={isCancelling} onClick={onCancel}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      }
    />
  );
}

QueryExecutionStatus.propTypes = {
  status: PropTypes.string,
  updatedAt: PropTypes.any,
  error: PropTypes.string,
  isCancelling: PropTypes.bool,
  onCancel: PropTypes.func,
};

QueryExecutionStatus.defaultProps = {
  status: "waiting",
  updatedAt: null,
  error: null,
  isCancelling: true,
  onCancel: () => {},
};

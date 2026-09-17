import React from "react";
import PropTypes from "prop-types";
import WarningTwoTone from "@ant-design/icons/WarningTwoTone";
import Button from "antd/lib/button";
import TimeAgo from "@/components/TimeAgo";
import Timer from "@/components/Timer";
import { executionStatusMessage } from "./QueryExecutionStatus";
import Tooltip from "@/components/Tooltip";
import useAddToDashboardDialog from "../hooks/useAddToDashboardDialog";
import useEmbedDialog from "../hooks/useEmbedDialog";
import QueryControlDropdown from "@/components/EditVisualizationButton/QueryControlDropdown";
import EditVisualizationButton from "@/components/EditVisualizationButton";
import useQueryResultData from "@/lib/useQueryResultData";
import { durationHumanize, pluralize, prettySize } from "@/lib/utils";
import { isUndefined } from "lodash";

import "./QueryExecutionMetadata.less";

// Once the result is on its way back there is nothing left to cancel.
const isCancelButtonAvailable = (status) => status === "waiting" || status === "processing";

export default function QueryExecutionMetadata({
  query,
  queryResult,
  isQueryExecuting,
  executionStatus,
  executionStartedAt,
  isCancelling,
  onCancel,
  selectedVisualization,
  showEditVisualizationButton,
  onEditVisualization,
  extraActions,
}) {
  const queryResultData = useQueryResultData(queryResult);
  const openAddToDashboardDialog = useAddToDashboardDialog(query);
  const openEmbedDialog = useEmbedDialog(query);
  return (
    <div className="query-execution-metadata">
      <span className="m-r-5">
        <QueryControlDropdown
          query={query}
          queryResult={queryResult}
          queryExecuting={isQueryExecuting}
          showEmbedDialog={openEmbedDialog}
          embed={false}
          apiKey={query.api_key}
          selectedTab={selectedVisualization}
          openAddToDashboardForm={openAddToDashboardDialog}
        />
      </span>
      {extraActions}
      {showEditVisualizationButton && (
        <EditVisualizationButton openVisualizationEditor={onEditVisualization} selectedTab={selectedVisualization} />
      )}
      <span className="m-l-5 m-r-10">
        <span>
          {queryResultData.truncated === true && (
            <span className="m-r-5">
              <Tooltip
                title={
                  "Result truncated to " +
                  queryResultData.rows.length +
                  " rows. Databricks may truncate query results that are unstably large."
                }
              >
                <WarningTwoTone twoToneColor="#FF9800" />
              </Tooltip>
            </span>
          )}
          <strong>{queryResultData.rows.length}</strong> {pluralize("row", queryResultData.rows.length)}
        </span>
        <span className="m-l-5">
          {!isQueryExecuting && (
            <React.Fragment>
              <strong>{durationHumanize(queryResultData.runtime)}</strong>
              <span className="hidden-xs"> runtime</span>
            </React.Fragment>
          )}
          {isQueryExecuting && <span>Running&hellip;</span>}
        </span>
        {!isUndefined(queryResultData.metadata.data_scanned) && !isQueryExecuting && (
          <span className="m-l-5">
            Data Scanned <strong>{prettySize(queryResultData.metadata.data_scanned)}</strong>
          </span>
        )}
      </span>
      {/* While a query runs, this corner reports what it is doing. It used to
          be an alert above the results, which appeared and disappeared on every
          run and shoved the visualization down the page each time. The corner
          is already where people look for "when was this last refreshed", and
          during a run that is exactly the question being answered. */}
      <div>
        <span className="m-r-10">
          {isQueryExecuting ? (
            <React.Fragment>
              <strong data-test="QueryExecutionStatus">{executionStatusMessage(executionStatus, isCancelling)}</strong>
              {executionStartedAt && (
                <span className="m-l-5">
                  <Timer from={executionStartedAt} />
                </span>
              )}
              {isCancelButtonAvailable(executionStatus) && (
                <Button className="m-l-10" size="small" disabled={isCancelling} onClick={onCancel}>
                  Cancel
                </Button>
              )}
            </React.Fragment>
          ) : (
            <React.Fragment>
              <span className="hidden-xs">Refreshed </span>
              <strong>
                <TimeAgo date={queryResultData.retrievedAt} placeholder="-" />
              </strong>
            </React.Fragment>
          )}
        </span>
      </div>
    </div>
  );
}

QueryExecutionMetadata.propTypes = {
  query: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  queryResult: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  isQueryExecuting: PropTypes.bool,
  executionStatus: PropTypes.string,
  executionStartedAt: PropTypes.any,
  isCancelling: PropTypes.bool,
  onCancel: PropTypes.func,
  selectedVisualization: PropTypes.number,
  showEditVisualizationButton: PropTypes.bool,
  onEditVisualization: PropTypes.func,
  extraActions: PropTypes.node,
};

QueryExecutionMetadata.defaultProps = {
  isQueryExecuting: false,
  executionStatus: null,
  executionStartedAt: null,
  isCancelling: false,
  onCancel: () => {},
  selectedVisualization: null,
  showEditVisualizationButton: false,
  onEditVisualization: () => {},
  extraActions: null,
};

import React, { useState, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import cx from "classnames";
import useMedia from "use-media";
import Button from "antd/lib/button";

import FullscreenOutlinedIcon from "@ant-design/icons/FullscreenOutlined";
import FullscreenExitOutlinedIcon from "@ant-design/icons/FullscreenExitOutlined";

import EditInPlace from "@/components/EditInPlace";
import Parameters from "@/components/Parameters";
import DynamicComponent from "@/components/DynamicComponent";
import PlainButton from "@/components/PlainButton";

import navigateTo from "@/components/ApplicationArea/navigateTo";
import DataSource from "@/services/data-source";
import { ExecutionStatus } from "@/services/query-result";
import { policy } from "@/services/policy";

import useQueryResultData from "@/lib/useQueryResultData";

import QueryPageHeader from "./components/QueryPageHeader";
import QueryVisualizationTabs from "./components/QueryVisualizationTabs";
import ResultTruncatedNotice from "./components/ResultTruncatedNotice";
import QueryExecutionStatus from "./components/QueryExecutionStatus";
import QueryMetadata from "./components/QueryMetadata";
import wrapQueryPage from "./components/wrapQueryPage";
import QueryViewButton from "./components/QueryViewButton";
import QueryExecutionMetadata from "./components/QueryExecutionMetadata";

import useVisualizationTabHandler from "./hooks/useVisualizationTabHandler";
import useQueryExecute from "./hooks/useQueryExecute";
import useUpdateQueryDescription from "./hooks/useUpdateQueryDescription";
import useQueryFlags from "./hooks/useQueryFlags";
import useQueryParameters from "./hooks/useQueryParameters";
import useEditVisualizationDialog from "./hooks/useEditVisualizationDialog";
import useDeleteVisualization from "./hooks/useDeleteVisualization";
import useFullscreenHandler from "../../lib/hooks/useFullscreenHandler";

import "./QueryView.less";

function QueryView(props) {
  const [query, setQuery] = useState(props.query);
  const [dataSource, setDataSource] = useState();
  const queryFlags = useQueryFlags(query, dataSource);
  const [parameters, areParametersDirty, updateParametersDirtyFlag] = useQueryParameters(query);
  const [selectedVisualization, setSelectedVisualization] = useVisualizationTabHandler(query.visualizations);
  const isDesktop = useMedia({ minWidth: 768 });
  const isFixedLayout = useMedia({ minHeight: 500 }) && isDesktop;
  const [fullscreen, toggleFullscreen] = useFullscreenHandler(isDesktop);
  const [addingDescription, setAddingDescription] = useState(false);

  const {
    queryResult,
    loadedInitialResults,
    isExecuting,
    executionStatus,
    executeQuery,
    error: executionError,
    cancelCallback: cancelExecution,
    isCancelling: isExecutionCancelling,
    updatedAt,
  } = useQueryExecute(query);

  const queryResultData = useQueryResultData(queryResult);

  const updateQueryDescription = useUpdateQueryDescription(query, setQuery);
  const addVisualization = useEditVisualizationDialog(query, queryResult, (newQuery, visualization) => {
    setQuery(newQuery);
    setSelectedVisualization(visualization.id);
  });
  const editVisualization = useEditVisualizationDialog(query, queryResult, (newQuery) => setQuery(newQuery));
  const deleteVisualization = useDeleteVisualization(query, setQuery);

  const doExecuteQuery = useCallback(
    (skipParametersDirtyFlag = false) => {
      if (!queryFlags.canExecute || (!skipParametersDirtyFlag && (areParametersDirty || isExecuting))) {
        return;
      }
      executeQuery();
    },
    [areParametersDirty, executeQuery, isExecuting, queryFlags.canExecute]
  );

  useEffect(() => {
    document.title = query.name;
  }, [query.name]);

  useEffect(() => {
    DataSource.get({ id: query.data_source_id }).then(setDataSource);
  }, [query.data_source_id]);

  return (
    <div
      className={cx("query-page-wrapper", {
        "query-view-fullscreen": fullscreen,
        "query-fixed-layout": isFixedLayout,
      })}
    >
      <div className="container w-100">
        <QueryPageHeader
          query={query}
          dataSource={dataSource}
          onChange={setQuery}
          selectedVisualization={selectedVisualization}
          headerExtra={
            <DynamicComponent name="QueryView.HeaderExtra" query={query}>
              {policy.canRun(query) && (
                <QueryViewButton
                  className="m-r-5"
                  type="primary"
                  shortcut="mod+enter, alt+enter, ctrl+enter"
                  disabled={!queryFlags.canExecute || isExecuting || areParametersDirty}
                  onClick={doExecuteQuery}
                >
                  Refresh
                </QueryViewButton>
              )}
            </DynamicComponent>
          }
          tagsExtra={
            !query.description &&
            queryFlags.canEdit &&
            !addingDescription &&
            !fullscreen && (
              <PlainButton className="label label-tag hidden-xs" role="none" onClick={() => setAddingDescription(true)}>
                <i className="zmdi zmdi-plus m-r-5" aria-hidden="true" />
                Add description
              </PlainButton>
            )
          }
        />
        {(query.description || addingDescription) && (
          <div className={cx("m-t-5", { hidden: fullscreen })}>
            <EditInPlace
              className="w-100"
              value={query.description}
              isEditable={queryFlags.canEdit}
              onDone={updateQueryDescription}
              onStopEditing={() => setAddingDescription(false)}
              placeholder="Add description"
              ignoreBlanks={false}
              editorProps={{ autoSize: { minRows: 2, maxRows: 4 } }}
              defaultEditing={addingDescription}
              multiline
            />
          </div>
        )}
      </div>
      <div className="query-view-content">
        {query.hasParameters() && (
          <div className={cx("bg-white tiled p-15 m-t-15 m-l-15 m-r-15", { hidden: fullscreen })}>
            <Parameters
              parameters={parameters}
              onValuesChange={() => {
                updateParametersDirtyFlag(false);
                doExecuteQuery(true);
              }}
              onPendingValuesChange={() => updateParametersDirtyFlag()}
            />
          </div>
        )}
        <div className="query-results m-t-15">
          {loadedInitialResults && queryResultData.truncated === true && (
            <ResultTruncatedNotice rowCount={queryResultData.rows.length} truncation={queryResultData.truncation} />
          )}
          {loadedInitialResults && (
            <QueryVisualizationTabs
              queryResult={queryResult}
              visualizations={query.visualizations}
              showNewVisualizationButton={queryFlags.canEdit && queryResultData.status === ExecutionStatus.DONE}
              canDeleteVisualizations={queryFlags.canEdit}
              selectedTab={selectedVisualization}
              onChangeTab={setSelectedVisualization}
              onAddVisualization={addVisualization}
              onDeleteVisualization={deleteVisualization}
              refreshButton={
                policy.canRun(query) && (
                  <Button
                    type="primary"
                    disabled={!queryFlags.canExecute || areParametersDirty}
                    loading={isExecuting}
                    onClick={doExecuteQuery}
                  >
                    {!isExecuting && <i className="zmdi zmdi-refresh m-r-5" aria-hidden="true" />}
                    Refresh Now
                  </Button>
                )
              }
              canRefresh={policy.canRun(query)}
            />
          )}
          <div className="query-results-footer">
            {queryResult && !queryResult.getError() && (
              <QueryExecutionMetadata
                query={query}
                queryResult={queryResult}
                selectedVisualization={selectedVisualization}
                isQueryExecuting={isExecuting}
                executionStatus={executionStatus}
                executionStartedAt={updatedAt}
                isCancelling={isExecutionCancelling}
                onCancel={cancelExecution}
                showEditVisualizationButton={queryFlags.canEdit}
                onEditVisualization={editVisualization}
                extraActions={
                  <QueryViewButton
                    className="icon-button m-r-5 hidden-xs"
                    title="Toggle Fullscreen"
                    type="default"
                    shortcut="alt+f"
                    onClick={toggleFullscreen}
                  >
                    {fullscreen ? <FullscreenExitOutlinedIcon /> : <FullscreenOutlinedIcon />}
                  </QueryViewButton>
                }
              />
            )}
            {/* See QuerySource: the running status goes in the footer, and only
                an error or a query with no result yet needs a block here. */}
            {(executionError || (isExecuting && !queryResult)) && (
              <div className="query-execution-status">
                <QueryExecutionStatus
                  status={executionStatus}
                  error={executionError}
                  isCancelling={isExecutionCancelling}
                  onCancel={cancelExecution}
                  updatedAt={updatedAt}
                />
              </div>
            )}
          </div>
        </div>
        <div className={cx("p-t-15 p-r-15 p-l-15", { hidden: fullscreen })}>
          <QueryMetadata layout="horizontal" query={query} dataSource={dataSource} />
        </div>
      </div>
    </div>
  );
}

QueryView.propTypes = { query: PropTypes.object.isRequired }; // eslint-disable-line react/forbid-prop-types

/*
  A streaming query has no view page.

  This page shows a stored result and offers to re-run it. A streaming query
  stores nothing -- the window is what a consumer saw while somebody was
  watching -- so there is nothing here to show, and the Execute path it would
  reach for would enqueue a warehouse job against a broker.

  Links go straight to the editor now (`Query#getUrl`). This is for the ones
  already in somebody's history, and it is a wrapper rather than an early
  return inside `QueryView` so that none of that page's hooks -- including the
  one that would execute -- ever run for a stream.
*/
function QueryViewOrEditor({ query, ...props }) {
  const streaming = !!query.is_streaming;

  useEffect(() => {
    if (streaming) {
      navigateTo(query.getUrl(), true);
    }
  }, [streaming, query]);

  if (streaming) {
    return null;
  }
  return <QueryView query={query} {...props} />;
}

QueryViewOrEditor.propTypes = { query: PropTypes.object.isRequired }; // eslint-disable-line react/forbid-prop-types

const QueryViewPage = wrapQueryPage(QueryViewOrEditor);

export default QueryViewPage;

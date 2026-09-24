import React, { useState } from "react";
import PropTypes from "prop-types";
import { compact, isEmpty, invoke, map } from "lodash";
import { markdown } from "markdown";
import cx from "classnames";
import Menu from "antd/lib/menu";
import HtmlContent from "@sqldesk/viz/lib/components/HtmlContent";
import { currentUser } from "@/services/auth";
import recordEvent from "@/services/recordEvent";
import { formatDateTime } from "@/lib/utils";
import Link from "@/components/Link";
import Parameters from "@/components/Parameters";
import TimeAgo from "@/components/TimeAgo";
import Timer from "@/components/Timer";
import { Moment } from "@/components/proptypes";
import QueryLink from "@/components/QueryLink";
import { FiltersType } from "@/components/Filters";
import PlainButton from "@/components/PlainButton";
import ExpandedWidgetDialog from "@/components/dashboards/ExpandedWidgetDialog";
import EditParameterMappingsDialog from "@/components/dashboards/EditParameterMappingsDialog";
import VisualizationRenderer from "@/components/visualizations/VisualizationRenderer";
import VisualizationDescription from "@/components/visualizations/VisualizationDescription";

import Widget from "./Widget";
import LiveCountdown from "./LiveCountdown";

function visualizationWidgetMenuOptions({ widget, canEditDashboard, onParametersEdit }) {
  const canViewQuery = currentUser.hasPermission("view_query");
  const canEditParameters = canEditDashboard && !isEmpty(invoke(widget, "query.getParametersDefs"));
  const widgetQueryResult = widget.getQueryResult();
  const isQueryResultEmpty = !widgetQueryResult || !widgetQueryResult.isEmpty || widgetQueryResult.isEmpty();

  const downloadLink = (fileType) => widgetQueryResult.getLink(widget.getQuery().id, fileType);
  const downloadName = (fileType) => widgetQueryResult.getName(widget.getQuery().name, fileType);
  return compact([
    <Menu.Item key="download_csv" disabled={isQueryResultEmpty}>
      {!isQueryResultEmpty ? (
        <Link href={downloadLink("csv")} download={downloadName("csv")} target="_self">
          Download as CSV File
        </Link>
      ) : (
        "Download as CSV File"
      )}
    </Menu.Item>,
    <Menu.Item key="download_tsv" disabled={isQueryResultEmpty}>
      {!isQueryResultEmpty ? (
        <Link href={downloadLink("tsv")} download={downloadName("tsv")} target="_self">
          Download as TSV File
        </Link>
      ) : (
        "Download as TSV File"
      )}
    </Menu.Item>,
    <Menu.Item key="download_excel" disabled={isQueryResultEmpty}>
      {!isQueryResultEmpty ? (
        <Link href={downloadLink("xlsx")} download={downloadName("xlsx")} target="_self">
          Download as Excel File
        </Link>
      ) : (
        "Download as Excel File"
      )}
    </Menu.Item>,
    (canViewQuery || canEditParameters) && <Menu.Divider key="divider" />,
    canViewQuery && (
      <Menu.Item key="view_query">
        <Link href={widget.getQuery().getUrl(true, widget.visualization.id)}>View Query</Link>
      </Menu.Item>
    ),
    canEditParameters && (
      <Menu.Item key="edit_parameters" onClick={onParametersEdit}>
        Edit Parameters
      </Menu.Item>
    ),
  ]);
}

function RefreshIndicator({ refreshStartedAt }) {
  return (
    <div className="refresh-indicator">
      <div className="refresh-icon">
        <i className="zmdi zmdi-refresh zmdi-hc-spin" aria-hidden="true" />
        <span className="sr-only">Refreshing...</span>
      </div>
      <Timer from={refreshStartedAt} />
    </div>
  );
}

RefreshIndicator.propTypes = { refreshStartedAt: Moment };
RefreshIndicator.defaultProps = { refreshStartedAt: null };

function VisualizationWidgetHeader({
  widget,
  refreshStartedAt,
  parameters,
  isEditing,
  onParametersUpdate,
  onParametersEdit,
}) {
  const canViewQuery = currentUser.hasPermission("view_query");

  return (
    <>
      <RefreshIndicator refreshStartedAt={refreshStartedAt} />
      <div className="t-header widget clearfix">
        <div className="th-title">
          <p>
            <QueryLink query={widget.getQuery()} visualization={widget.visualization} readOnly={!canViewQuery} />
            <VisualizationDescription description={widget.visualization.description} />
          </p>
          {!isEmpty(widget.getQuery().description) && (
            <HtmlContent className="text-muted markdown query--description">
              {markdown.toHTML(widget.getQuery().description || "")}
            </HtmlContent>
          )}
        </div>
      </div>
      {!isEmpty(parameters) && (
        <div className="m-b-10">
          <Parameters
            parameters={parameters}
            sortable={isEditing}
            appendSortableToParent={false}
            onValuesChange={onParametersUpdate}
            onParametersEdit={onParametersEdit}
          />
        </div>
      )}
    </>
  );
}

VisualizationWidgetHeader.propTypes = {
  widget: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  refreshStartedAt: Moment,
  parameters: PropTypes.arrayOf(PropTypes.object),
  isEditing: PropTypes.bool,
  onParametersUpdate: PropTypes.func,
  onParametersEdit: PropTypes.func,
};

VisualizationWidgetHeader.defaultProps = {
  refreshStartedAt: null,
  onParametersUpdate: () => {},
  onParametersEdit: () => {},
  isEditing: false,
  parameters: [],
};

function VisualizationWidgetFooter({ widget, isPublic, isLive, liveInterval, onRefresh, onExpand }) {
  // A live dashboard's results come from the server: no refresh button, but a
  // countdown to the next one (or, paused, how old this one is).
  const canRefresh = !isPublic && !isLive;
  const widgetQueryResult = widget.getQueryResult();
  const updatedAt = invoke(widgetQueryResult, "getUpdatedAt");
  const [refreshClickButtonId, setRefreshClickButtonId] = useState();

  const refreshWidget = (buttonId) => {
    if (!refreshClickButtonId) {
      setRefreshClickButtonId(buttonId);
      onRefresh().finally(() => setRefreshClickButtonId(null));
    }
  };

  return widgetQueryResult ? (
    <>
      <span>
        {canRefresh && !!widgetQueryResult && (
          <PlainButton
            className="refresh-button hidden-print btn btn-sm btn-default btn-transparent"
            onClick={() => refreshWidget(1)}
            data-test="RefreshButton"
          >
            <i className={cx("zmdi zmdi-refresh", { "zmdi-hc-spin": refreshClickButtonId === 1 })} aria-hidden="true" />
            <span className="sr-only">
              {refreshClickButtonId === 1 ? "Refreshing, please wait. " : "Press to refresh. "}
            </span>{" "}
            <TimeAgo date={updatedAt} />
          </PlainButton>
        )}
        <span className="visible-print">
          <i className="zmdi zmdi-time-restore" aria-hidden="true" /> {formatDateTime(updatedAt)}
        </span>
        {isLive && updatedAt && <LiveCountdown updatedAt={updatedAt} interval={liveInterval} />}
        {!canRefresh && !isLive && (
          <span className="small hidden-print">
            <i className="zmdi zmdi-time-restore" aria-hidden="true" /> <TimeAgo date={updatedAt} />
          </span>
        )}
      </span>
      <span>
        {canRefresh && (
          <PlainButton
            className="btn btn-sm btn-default hidden-print btn-transparent btn__refresh"
            onClick={() => refreshWidget(2)}
          >
            <i className={cx("zmdi zmdi-refresh", { "zmdi-hc-spin": refreshClickButtonId === 2 })} aria-hidden="true" />
            <span className="sr-only">
              {refreshClickButtonId === 2 ? "Refreshing, please wait." : "Press to refresh."}
            </span>
          </PlainButton>
        )}
        <PlainButton className="btn btn-sm btn-default hidden-print btn-transparent btn__refresh" onClick={onExpand}>
          <i className="zmdi zmdi-fullscreen" aria-hidden="true" />
        </PlainButton>
      </span>
    </>
  ) : null;
}

VisualizationWidgetFooter.propTypes = {
  widget: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  isPublic: PropTypes.bool,
  isLive: PropTypes.bool,
  liveInterval: PropTypes.number,
  onRefresh: PropTypes.func.isRequired,
  onExpand: PropTypes.func.isRequired,
};

VisualizationWidgetFooter.defaultProps = { isPublic: false, isLive: false, liveInterval: null };

class VisualizationWidget extends React.Component {
  static propTypes = {
    widget: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
    getDashboard: PropTypes.func.isRequired,
    filters: FiltersType,
    isPublic: PropTypes.bool,
    isLive: PropTypes.bool,
    // Seconds between the server's refreshes; null while paused or not live.
    liveInterval: PropTypes.number,
    isLoading: PropTypes.bool,
    canEdit: PropTypes.bool,
    isEditing: PropTypes.bool,
    onLoad: PropTypes.func,
    onRefresh: PropTypes.func,
    onParametersChange: PropTypes.func,
    onDelete: PropTypes.func,
    onParameterMappingsChange: PropTypes.func,
  };

  static defaultProps = {
    filters: [],
    isPublic: false,
    isLive: false,
    liveInterval: null,
    isLoading: false,
    canEdit: false,
    isEditing: false,
    onLoad: () => {},
    onRefresh: () => {},
    onParametersChange: () => {},
    onDelete: () => {},
    onParameterMappingsChange: () => {},
  };

  constructor(props) {
    super(props);
    this.state = {
      localParameters: props.widget.getLocalParameters(),
      localFilters: props.filters,
    };
  }

  componentDidMount() {
    const { widget, onLoad } = this.props;
    recordEvent("view", "query", widget.visualization.query.id, { dashboard: true });
    recordEvent("view", "visualization", widget.visualization.id, { dashboard: true });
    onLoad();
  }

  onLocalFiltersChange = (localFilters) => {
    this.setState({ localFilters });
  };

  expandWidget = () => {
    ExpandedWidgetDialog.showModal({ widget: this.props.widget, filters: this.state.localFilters });
  };

  editParameterMappings = () => {
    const { widget, getDashboard, onParametersChange, onParameterMappingsChange } = this.props;
    EditParameterMappingsDialog.showModal({
      // Read now, not when this widget last rendered. The widget is memoized
      // and `dashboard` changes identity on every widget load, so holding the
      // object meant the dialog could be handed a dashboard several loads old.
      dashboard: getDashboard(),
      widget,
    }).onClose((valuesChanged) => {
      // refresh widget if any parameter value has been updated
      if (valuesChanged) {
        onParametersChange();
      }
      onParameterMappingsChange();
      this.setState({ localParameters: widget.getLocalParameters() });
    });
  };

  renderVisualization() {
    const { widget, filters } = this.props;
    const widgetQueryResult = widget.getQueryResult();
    const widgetStatus = widgetQueryResult && widgetQueryResult.getStatus();
    switch (widgetStatus) {
      case "failed":
        return (
          <div className="body-row-auto scrollbox">
            {widgetQueryResult.getError() && (
              <div className="alert alert-danger m-5">
                Error running query: <strong>{widgetQueryResult.getError()}</strong>
              </div>
            )}
          </div>
        );
      case "done":
        return (
          <div className="body-row-auto scrollbox">
            <VisualizationRenderer
              visualization={widget.visualization}
              queryResult={widgetQueryResult}
              filters={filters}
              onFiltersChange={this.onLocalFiltersChange}
              context="widget"
            />
          </div>
        );
      default:
        return (
          <div
            className="body-row-auto spinner-container"
            role="status"
            aria-live="polite"
            aria-relevant="additions removals"
          >
            <div className="spinner">
              <i className="zmdi zmdi-refresh zmdi-hc-spin zmdi-hc-5x" aria-hidden="true" />
              <span className="sr-only">Loading...</span>
            </div>
          </div>
        );
    }
  }

  render() {
    const { widget, isLoading, isPublic, isLive, liveInterval, canEdit, isEditing, onRefresh, onParametersChange } =
      this.props;
    const { localParameters } = this.state;
    const widgetQueryResult = widget.getQueryResult();
    const isRefreshing = isLoading && !!(widgetQueryResult && widgetQueryResult.getStatus());
    const onParametersEdit = (parameters) => {
      const paramOrder = map(parameters, "name");
      widget.options.paramOrder = paramOrder;
      widget.save("options", { paramOrder });
    };

    return (
      <Widget
        {...this.props}
        className="widget-visualization"
        menuOptions={visualizationWidgetMenuOptions({
          widget,
          canEditDashboard: canEdit,
          onParametersEdit: this.editParameterMappings,
        })}
        header={
          <VisualizationWidgetHeader
            widget={widget}
            refreshStartedAt={isRefreshing ? widget.refreshStartedAt : null}
            // A live dashboard's parameters are fixed to what the server runs.
            parameters={isLive ? [] : localParameters}
            isEditing={isEditing}
            onParametersUpdate={onParametersChange}
            onParametersEdit={onParametersEdit}
          />
        }
        footer={
          <VisualizationWidgetFooter
            widget={widget}
            isPublic={isPublic}
            isLive={isLive}
            liveInterval={liveInterval}
            onRefresh={onRefresh}
            onExpand={this.expandWidget}
          />
        }
        tileProps={{ "data-refreshing": isRefreshing }}
      >
        {this.renderVisualization()}
      </Widget>
    );
  }
}

export default VisualizationWidget;

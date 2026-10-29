import React, { useState } from "react";
import PropTypes from "prop-types";
import { compact, find, isEmpty, invoke, map } from "lodash";
import cx from "classnames";
import Menu from "antd/lib/menu";
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
import ChooseWidgetTabsDialog from "@/components/dashboards/ChooseWidgetTabsDialog";
import VisualizationRenderer from "@/components/visualizations/VisualizationRenderer";
import VisualizationDescription from "@/components/visualizations/VisualizationDescription";

import Widget from "./Widget";
import LiveCountdown from "./LiveCountdown";
import Spinner from "@/components/Spinner";

function visualizationWidgetMenuOptions({ widget, canEditDashboard, onParametersEdit, onTabsEdit }) {
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
    (canViewQuery || canEditParameters || canEditDashboard) && <Menu.Divider key="divider" />,
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
    // Only for somebody who can change the dashboard: which views this widget
    // offers is a property of the widget, not of the person reading it.
    canEditDashboard && (
      <Menu.Item key="choose_tabs" onClick={onTabsEdit}>
        Choose Tabs
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

// Exported for its own test: where a widget's filters go is a rule of its own.
export function VisualizationWidgetHeader({
  widget,
  refreshStartedAt,
  parameters,
  isEditing,
  onParametersUpdate,
  onParametersEdit,
}) {
  const canViewQuery = currentUser.hasPermission("view_query");

  /*
    A widget's own filter goes on the title's row. Under it, `Parameters`
    stacks a label above its control inside a white block -- measured, 63px,
    most of it air, taken out of a widget that is mostly chart.

    Not while the layout is being edited: there the parameters are dragged
    into order, and drag handles want a block of their own. Same reasoning as
    the dashboard's own filters -- see DashboardFilters.
  */
  const filtersInline = !isEditing && !isEmpty(parameters);
  const parameterControls = (
    <Parameters
      parameters={parameters}
      sortable={isEditing}
      appendSortableToParent={false}
      onValuesChange={onParametersUpdate}
      onParametersEdit={onParametersEdit}
    />
  );

  return (
    <>
      <RefreshIndicator refreshStartedAt={refreshStartedAt} />
      <div className={cx("t-header widget clearfix", { "t-header-filtered": filtersInline })}>
        <div className="th-title">
          <p>
            <QueryLink query={widget.getQuery()} visualization={widget.visualization} readOnly={!canViewQuery} />
          </p>
          {/*
            The chart's own description, written for the chart. Not the
            query's: queries are described mostly for MCP, and on a panel
            that put a paragraph between the title and the chart.
          */}
          <VisualizationDescription description={widget.visualization.description} />
        </div>
        {filtersInline && (
          <div className="widget-filters hidden-print" data-test="WidgetFilters">
            {parameterControls}
          </div>
        )}
      </div>
      {!filtersInline && !isEmpty(parameters) && <div className="m-b-10">{parameterControls}</div>}
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
      // Which tab is in front. Per viewer and not saved: a tab is a way of
      // looking at a result, not a property of the dashboard, so one person
      // reading the channel split should not move it for everybody else.
      activeTabId: props.widget.visualization.id,
    };
  }

  componentDidMount() {
    const { widget, onLoad } = this.props;
    // One event per widget, naming the query behind it. The widget's own id
    // and the visualization's used to be recorded here as well: three rows
    // per tile, two of which nothing on any page or in any report reads, on
    // a dashboard that may hold thirty of them.
    recordEvent("view", "query", widget.visualization.query.id, { dashboard: true });
    onLoad();
  }

  onLocalFiltersChange = (localFilters) => {
    this.setState({ localFilters });
  };

  expandWidget = () => {
    ExpandedWidgetDialog.showModal({ widget: this.props.widget, filters: this.state.localFilters });
  };

  editTabs = () => {
    ChooseWidgetTabsDialog.showModal({ widget: this.props.widget }).onClose(() => {
      // The saved widget may no longer have the tab that was in front.
      this.setState({ activeTabId: this.activeVisualization().id });
    });
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

  /**
   * The strip that chooses which of this widget's visualizations is shown.
   *
   * Drawn only when there is a choice. Every tab draws the result already
   * fetched for this widget -- the server sends a tab only if it belongs to
   * the same query -- so switching costs nothing but a redraw, which is the
   * whole reason to prefer this to one widget per chart.
   */
  renderTabs() {
    const { widget } = this.props;
    const tabs = widget.getTabs();
    if (tabs.length < 2) {
      return null;
    }

    const { activeTabId } = this.state;
    return (
      <div className="widget-tabs" role="tablist" aria-label="Views of this query">
        {map(tabs, (one) => (
          <PlainButton
            key={one.id}
            role="tab"
            type="button"
            aria-selected={one.id === activeTabId}
            className={cx("widget-tab", { active: one.id === activeTabId })}
            onClick={() => this.setState({ activeTabId: one.id })}
          >
            {one.name}
          </PlainButton>
        ))}
      </div>
    );
  }

  /** The visualization in front, falling back to the widget's own. */
  activeVisualization() {
    const { widget } = this.props;
    const { activeTabId } = this.state;
    // A tab can disappear under a viewer who has it open, if somebody deletes
    // that visualization while the dashboard is up. The widget's own is the
    // one that cannot.
    return find(widget.getTabs(), { id: activeTabId }) || widget.visualization;
  }

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
      case "done": {
        const renderer = (
          <VisualizationRenderer
            visualization={this.activeVisualization()}
            queryResult={widgetQueryResult}
            filters={filters}
            onFiltersChange={this.onLocalFiltersChange}
            context="widget"
          />
        );
        const tabs = this.renderTabs();
        // Without tabs, exactly the markup this has always emitted. Inside a
        // widget the renderer is absolutely positioned to fill its nearest
        // positioned ancestor, so a strip added as a plain sibling would be
        // painted under the chart; the tabbed case gives the renderer a
        // positioned box of its own that stops below the strip. Only the
        // tabbed case gets the extra wrapper, so no existing widget's layout
        // moves because this feature exists.
        return tabs ? (
          <div className="body-row-auto scrollbox widget-has-tabs">
            {tabs}
            <div className="widget-visualization-area">{renderer}</div>
          </div>
        ) : (
          <div className="body-row-auto scrollbox">{renderer}</div>
        );
      }
      default:
        return (
          <div
            className="body-row-auto spinner-container"
            role="status"
            aria-live="polite"
            aria-relevant="additions removals"
          >
            <div className="spinner">
              <Spinner size="large" />
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
          onTabsEdit: this.editTabs,
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

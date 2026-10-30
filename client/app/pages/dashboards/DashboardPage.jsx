import { isEmpty, map } from "lodash";
import React, { useState, useEffect } from "react";
import PropTypes from "prop-types";
import cx from "classnames";

import Alert from "antd/lib/alert";
import Button from "antd/lib/button";
import DynamicComponent from "@/components/DynamicComponent";
import DashboardGrid from "@/components/dashboards/DashboardGrid";
import useRunningStreams, { StreamsContext } from "./hooks/useRunningStreams";
import { StreamRollup } from "./components/StreamMarker";
import Parameters from "@/components/Parameters";
import Filters from "@/components/Filters";

import { Dashboard } from "@/services/dashboard";
import recordEvent from "@/services/recordEvent";
import resizeObserver from "@/services/resizeObserver";
import location from "@/services/location";
import url from "@/services/url";
import useImmutableCallback from "@/lib/hooks/useImmutableCallback";
import useUnsavedChangesAlert from "@/lib/hooks/useUnsavedChangesAlert";

import useDashboard from "./hooks/useDashboard";
import DashboardHeader from "./components/DashboardHeader";

import "./DashboardPage.less";

function AddWidgetContainer({ dashboardConfiguration, className, ...props }) {
  const { showAddTextboxDialog, showAddWidgetDialog } = dashboardConfiguration;
  return (
    <div className={cx("add-widget-container", className)} {...props}>
      <h2>
        <i className="zmdi zmdi-widgets" aria-hidden="true" />
        <span className="hidden-xs hidden-sm">
          Widgets are individual query visualizations or text boxes you can place on your dashboard in various
          arrangements.
        </span>
      </h2>
      <div>
        <Button className="m-r-15" onClick={showAddTextboxDialog} data-test="AddTextboxButton">
          Add Textbox
        </Button>
        <Button type="primary" onClick={showAddWidgetDialog} data-test="AddWidgetButton">
          Add Widget
        </Button>
      </div>
    </div>
  );
}

AddWidgetContainer.propTypes = {
  dashboardConfiguration: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  className: PropTypes.string,
};

function DashboardComponent(props) {
  const dashboardConfiguration = useDashboard(props.dashboard);
  const {
    dashboard,
    filters,
    setFilters,
    loadDashboard,
    loadWidget,
    removeWidget,
    updateDashboardLayout,
    layoutGeneration,
    hasUnsavedChanges,
    globalParameters,
    updateDashboard,
    refreshDashboard,
    refreshWidget,
    editingLayout,
    setGridDisabled,
    live,
    canManageLive,
  } = dashboardConfiguration;

  // Layout changes live only in the browser until they are saved, so leaving
  // the page with some pending would throw them away silently.
  useUnsavedChangesAlert(hasUnsavedChanges);

  // Asked once for the board, and only while it is live: a streaming
  // dashboard that is not running has nothing to report.
  const streams = useRunningStreams(dashboard, !!live && !live.paused);

  const [pageContainer, setPageContainer] = useState(null);
  const [bottomPanelStyles, setBottomPanelStyles] = useState({});
  const onParametersEdit = (parameters) => {
    const paramOrder = map(parameters, "name");
    updateDashboard({ options: { ...dashboard.options, globalParamOrder: paramOrder } });
  };

  useEffect(() => {
    if (pageContainer) {
      const unobserve = resizeObserver(pageContainer, () => {
        if (editingLayout) {
          const style = window.getComputedStyle(pageContainer, null);
          const bounds = pageContainer.getBoundingClientRect();
          const paddingLeft = parseFloat(style.paddingLeft) || 0;
          const paddingRight = parseFloat(style.paddingRight) || 0;
          setBottomPanelStyles({
            left: Math.round(bounds.left) + paddingRight,
            width: pageContainer.clientWidth - paddingLeft - paddingRight,
          });
        }

        // reflow grid when container changes its size
        window.dispatchEvent(new Event("resize"));
      });
      return unobserve;
    }
  }, [pageContainer, editingLayout]);

  return (
    /*
      The band down the left says what this dashboard is on every screenful,
      including the ones a chip in the header has scrolled off. It goes green
      while the topics are actually being consumed, which is the same language
      the stream editor uses -- the difference between "this is a streaming
      dashboard" and "this streaming dashboard is running" is the one people
      actually need at a glance.
    */
    <div
      className={cx("container", {
        "dashboard-streaming": dashboard.is_streaming,
        "dashboard-streaming-running": dashboard.is_streaming && live && !live.paused,
      })}
      ref={setPageContainer}
      data-test={`DashboardId${dashboard.id}Container`}
    >
      <DashboardHeader
        dashboardConfiguration={dashboardConfiguration}
        onParametersEdit={onParametersEdit}
        headerExtra={
          <>
            {/*
              Beside the Live badge, because the badge describes the *redraw*
              and this describes the *data* -- and when the panels disagree,
              one of them has to say so.
            */}
            <StreamRollup summary={streams.rollUp} />
            <DynamicComponent
              name="Dashboard.HeaderExtra"
              dashboard={dashboard}
              dashboardConfiguration={dashboardConfiguration}
            />
          </>
        }
      />
      {/*
        Filters live in the header now -- see DashboardFilters -- except while
        the layout is being edited, when parameters are dragged into order and
        the drag handles want a band of their own.

        A live dashboard shows what the server refreshes, from its saved
        parameter values, so it offers no controls at all.
      */}
      {editingLayout && !live && !isEmpty(globalParameters) && (
        <div className="dashboard-parameters m-b-10 p-15 bg-white tiled" data-test="DashboardParameters">
          <Parameters
            parameters={globalParameters}
            onValuesChange={refreshDashboard}
            sortable
            onParametersEdit={onParametersEdit}
          />
        </div>
      )}
      {/*
        Column filters get the row while editing too. Turning "Dashboard level
        filters" on and being shown nothing until you leave edit mode is not a
        setting taking effect, it is a setting that looks broken.
      */}
      {editingLayout && !isEmpty(filters) && (
        <div className="m-b-10 p-15 bg-white tiled" data-test="DashboardFilters">
          <Filters filters={filters} onChange={setFilters} />
        </div>
      )}
      {/*
        A streaming dashboard that is not live is showing nothing, and an
        empty chart reads as a broken dashboard rather than as one waiting to
        be started. Said once at the top instead of on every panel: the answer
        is the same for all of them, and repeating it eight times is noise.
      */}
      {dashboard.is_streaming && !live && (
        <Alert
          className="m-b-10"
          type="info"
          showIcon
          data-test="StreamsResting"
          message="These panels are still."
          description={
            canManageLive
              ? "A stream is consumed only while somebody is watching it. Make this dashboard live, from the \u22ee menu, and the topics start — they stop again a minute after the last person closes it."
              : "A stream is consumed only while somebody is watching it. Somebody who may make this dashboard live has to start it; the topics stop again a minute after the last person closes it."
          }
        />
      )}
      {/*
        One request for the whole board, shared with every panel. The refresh
        is per dashboard and the events are per widget, so each panel says what
        its own topic is doing -- see useRunningStreams.
      */}
      <div id="dashboard-container">
        <StreamsContext.Provider value={streams}>
          <DashboardGrid
            dashboard={dashboard}
            widgets={dashboard.widgets}
            filters={filters}
            isEditing={editingLayout}
            isLive={!!live}
            liveInterval={live && !live.paused ? live.interval : null}
            layoutGeneration={layoutGeneration}
            onLayoutChange={editingLayout ? updateDashboardLayout : () => {}}
            onBreakpointChange={setGridDisabled}
            onLoadWidget={loadWidget}
            onRefreshWidget={refreshWidget}
            onRemoveWidget={removeWidget}
            onParameterMappingsChange={loadDashboard}
          />
        </StreamsContext.Provider>
      </div>
      {editingLayout && (
        <AddWidgetContainer dashboardConfiguration={dashboardConfiguration} style={bottomPanelStyles} />
      )}
    </div>
  );
}

DashboardComponent.propTypes = {
  dashboard: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
};

function DashboardPage({ dashboardSlug, dashboardId, onError }) {
  const [dashboard, setDashboard] = useState(null);
  const handleError = useImmutableCallback(onError);

  useEffect(() => {
    Dashboard.get({ id: dashboardId, slug: dashboardSlug })
      .then((dashboardData) => {
        recordEvent("view", "dashboard", dashboardData.id);
        setDashboard(dashboardData);

        // if loaded by slug, update location url to use the id
        if (!dashboardId) {
          location.setPath(url.parse(dashboardData.url).pathname, true);
        }
      })
      .catch(handleError);
  }, [dashboardId, dashboardSlug, handleError]);

  return <div className="dashboard-page">{dashboard && <DashboardComponent dashboard={dashboard} />}</div>;
}

DashboardPage.propTypes = {
  dashboardSlug: PropTypes.string,
  dashboardId: PropTypes.string,
  onError: PropTypes.func,
};

DashboardPage.defaultProps = {
  dashboardSlug: null,
  dashboardId: null,
  onError: PropTypes.func,
};

export default DashboardPage;

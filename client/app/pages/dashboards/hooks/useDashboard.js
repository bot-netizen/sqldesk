import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { isEmpty, includes, compact, map, has, pick, keys, extend, every, get } from "lodash";
import notification from "@/services/notification";
import location from "@/services/location";
import url from "@/services/url";
import { Dashboard, collectDashboardFilters } from "@/services/dashboard";
import { currentUser } from "@/services/auth";
import recordEvent from "@/services/recordEvent";
import { QueryResultError } from "@/services/query";
import AddWidgetDialog from "@/components/dashboards/AddWidgetDialog";
import TextboxDialog from "@/components/dashboards/TextboxDialog";
import PermissionsEditorDialog from "@/components/PermissionsEditorDialog";
import { editableMappingsToParameterMappings, synchronizeWidgetTitles } from "@/components/ParameterMappingInput";
import ShareDashboardDialog from "../components/ShareDashboardDialog";
import useFullscreenHandler from "../../../lib/hooks/useFullscreenHandler";
import useRefreshRateHandler from "./useRefreshRateHandler";
import useLiveDashboard from "./useLiveDashboard";
import { autoRefreshMaxAge, nothingWasRun, shownResultIds } from "./refreshResults";
import useEditModeHandler from "./useEditModeHandler";
import useDuplicateDashboard from "./useDuplicateDashboard";
import { policy } from "@/services/policy";

export { DashboardStatusEnum } from "./useEditModeHandler";

// The Refresh buttons re-run only results older than this, so a room of people
// pressing Refresh at once runs each query once.
export const MANUAL_REFRESH_MAX_AGE = 60;

export const MANAGE_LIVE_PERMISSION = "manage_live_dashboards";

/**
 * A live dashboard shows the result the server makes, which uses the saved
 * parameter values. Values a viewer brought in the URL would ask for a
 * different result nobody is refreshing, so they are dropped.
 */
function dropUrlParameters() {
  const drop = {};
  Object.keys(location.search || {}).forEach((key) => {
    if (key.startsWith("p_")) {
      drop[key] = null;
    }
  });
  if (Object.keys(drop).length > 0) {
    location.setSearch(drop, true);
  }
}

function sayUpToDate(description) {
  notification.info("Already up to date", description);
}

function getAffectedWidgets(widgets, updatedParameters = []) {
  return !isEmpty(updatedParameters)
    ? widgets.filter((widget) =>
        Object.values(widget.getParameterMappings())
          .filter(({ type }) => type === "dashboard-level")
          .some(({ mapTo }) =>
            includes(
              updatedParameters.map((p) => p.name),
              mapTo
            )
          )
      )
    : widgets;
}

function useDashboard(dashboardData, { publicToken = null } = {}) {
  const [dashboard, setDashboard] = useState(dashboardData);
  const [filters, setFilters] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [gridDisabled, setGridDisabled] = useState(false);
  const globalParameters = useMemo(() => dashboard.getParametersDefs(), [dashboard]);
  const canEditDashboard = !dashboard.is_archived && policy.canEdit(dashboard);
  const isDashboardOwnerOrAdmin = useMemo(
    () =>
      !dashboard.is_archived &&
      has(dashboard, "user.id") &&
      (currentUser.id === dashboard.user.id || currentUser.isAdmin),
    [dashboard]
  );
  const hasOnlySafeQueries = useMemo(
    () => every(dashboard.widgets, (w) => (w.getQuery() ? w.getQuery().is_safe : true)),
    [dashboard]
  );

  const [isDuplicating, duplicateDashboard] = useDuplicateDashboard(dashboard);

  const managePermissions = useCallback(() => {
    const aclUrl = `api/dashboards/${dashboard.id}/acl`;
    PermissionsEditorDialog.showModal({
      aclUrl,
      context: "dashboard",
      author: dashboard.user,
    });
  }, [dashboard]);

  const updateDashboard = useCallback(
    (data, includeVersion = true) => {
      setDashboard((currentDashboard) => extend({}, currentDashboard, data));
      data = { ...data, id: dashboard.id };
      if (includeVersion) {
        data = { ...data, version: dashboard.version };
      }
      return Dashboard.save(data)
        .then((updatedDashboard) => {
          setDashboard((currentDashboard) => extend({}, currentDashboard, pick(updatedDashboard, keys(data))));
          if (has(data, "name")) {
            location.setPath(url.parse(updatedDashboard.url).pathname, true);
          }
        })
        .catch((error) => {
          const status = get(error, "response.status");
          if (status === 403) {
            notification.error("Dashboard update failed", "Permission Denied.");
          } else if (status === 409) {
            notification.error(
              "It seems like the dashboard has been modified by another user. ",
              "Please copy/backup your changes and reload this page.",
              { duration: null }
            );
          }
        });
    },
    [dashboard]
  );

  const togglePublished = useCallback(() => {
    recordEvent("toggle_published", "dashboard", dashboard.id);
    updateDashboard({ is_draft: !dashboard.is_draft }, false);
  }, [dashboard, updateDashboard]);

  const loadWidget = useCallback((widget, forceRefresh = false, maxAge = undefined) => {
    widget.getParametersDefs(); // Force widget to read parameters values from URL
    setDashboard((currentDashboard) => extend({}, currentDashboard));
    return widget
      .load(forceRefresh, maxAge)
      .catch((error) => {
        // QueryResultErrors are expected
        if (error instanceof QueryResultError) {
          return;
        }
        return Promise.reject(error);
      })
      .finally(() => setDashboard((currentDashboard) => extend({}, currentDashboard)));
  }, []);

  // The Refresh button accepts a result from the last minute. New parameter
  // values are a request to run the query with them, so they always run --
  // the cache is keyed by query text, and a result somebody else made with the
  // same values a moment ago would otherwise come back instead.
  const refreshWidget = useCallback(
    (widget, { parametersChanged = false } = {}) => {
      if (parametersChanged) {
        return loadWidget(widget, true);
      }
      // A Refresh that brings back the same result would otherwise look like
      // a button that does nothing.
      const before = shownResultIds([widget]);
      return loadWidget(widget, true, MANUAL_REFRESH_MAX_AGE).then((result) => {
        if (nothingWasRun(before, [widget])) {
          sayUpToDate(
            "This result is under a minute old, so the query was not run again. Refresh runs it once the result is older."
          );
        }
        return result;
      });
    },
    [loadWidget]
  );

  const removeWidget = useCallback((widgetId) => {
    setDashboard((currentDashboard) =>
      extend({}, currentDashboard, {
        widgets: currentDashboard.widgets.filter((widget) => widget.id !== undefined && widget.id !== widgetId),
      })
    );
  }, []);

  const dashboardRef = useRef();
  dashboardRef.current = dashboard;

  const loadDashboard = useCallback(
    (forceRefresh = false, updatedParameters = [], maxAge = undefined) => {
      const affectedWidgets = getAffectedWidgets(dashboardRef.current.widgets, updatedParameters);
      const loadWidgetPromises = compact(
        affectedWidgets.map((widget) => loadWidget(widget, forceRefresh, maxAge).catch((error) => error))
      );

      return Promise.all(loadWidgetPromises).then(() => {
        const queryResults = compact(map(dashboardRef.current.widgets, (widget) => widget.getQueryResult()));
        const updatedFilters = collectDashboardFilters(dashboardRef.current, queryResults, location.search);
        setFilters(updatedFilters);
      });
    },
    [loadWidget]
  );

  const refreshDashboard = useCallback(
    (updatedParameters) => {
      if (!refreshing) {
        setRefreshing(true);
        // New parameter values are a request to run the query with them, so
        // they always run. The Refresh button accepts anything from the last
        // minute.
        const fromButton = isEmpty(updatedParameters);
        const widgets = dashboardRef.current.widgets;
        const before = shownResultIds(widgets);
        loadDashboard(true, updatedParameters, fromButton ? MANUAL_REFRESH_MAX_AGE : undefined)
          .then(() => {
            if (fromButton && nothingWasRun(before, widgets)) {
              sayUpToDate(
                "Every result here is under a minute old, so nothing was run again. Refresh runs the queries once their results are older."
              );
            }
          })
          .finally(() => setRefreshing(false));
      }
    },
    [refreshing, loadDashboard]
  );

  // Auto-refresh reuses a recent result -- whichever open tab gets there first
  // runs the query, and the rest read its result -- but not one as old as its
  // own last refresh (see autoRefreshMaxAge).
  const autoRefreshDashboard = useCallback(
    (refreshRate) => {
      if (!refreshing) {
        setRefreshing(true);
        loadDashboard(true, [], autoRefreshMaxAge(refreshRate)).finally(() => setRefreshing(false));
      }
    },
    [refreshing, loadDashboard]
  );

  const saveDashboardParameters = useCallback(() => {
    const currentDashboard = dashboardRef.current;

    return updateDashboard({
      options: {
        ...currentDashboard.options,
        parameters: map(globalParameters, (p) => p.toSaveableObject()),
      },
    }).catch((error) => {
      console.error("Failed to persist parameter values:", error);
      notification.error("Parameter values could not be saved. Your changes may not be persisted.");
      throw error;
    });
  }, [globalParameters, updateDashboard]);

  const archiveDashboard = useCallback(() => {
    recordEvent("archive", "dashboard", dashboard.id);
    Dashboard.delete(dashboard).then((updatedDashboard) =>
      setDashboard((currentDashboard) => extend({}, currentDashboard, pick(updatedDashboard, ["is_archived"])))
    );
  }, [dashboard]); // eslint-disable-line react-hooks/exhaustive-deps

  const showShareDashboardDialog = useCallback(() => {
    const handleDialogClose = () => setDashboard((currentDashboard) => extend({}, currentDashboard));

    ShareDashboardDialog.showModal({
      dashboard,
      hasOnlySafeQueries,
    })
      .onClose(handleDialogClose)
      .onDismiss(handleDialogClose);
  }, [dashboard, hasOnlySafeQueries]);

  const showAddTextboxDialog = useCallback(() => {
    TextboxDialog.showModal({
      isNew: true,
    }).onClose((text) =>
      dashboard.addWidget(text).then(() => setDashboard((currentDashboard) => extend({}, currentDashboard)))
    );
  }, [dashboard]);

  const showAddWidgetDialog = useCallback(() => {
    AddWidgetDialog.showModal({
      dashboard,
    }).onClose(({ visualization, parameterMappings }) =>
      dashboard
        .addWidget(visualization, {
          parameterMappings: editableMappingsToParameterMappings(parameterMappings),
        })
        .then((widget) => {
          const widgetsToSave = [
            widget,
            ...synchronizeWidgetTitles(widget.options.parameterMappings, dashboard.widgets),
          ];
          return Promise.all(widgetsToSave.map((w) => w.save())).then(() =>
            setDashboard((currentDashboard) => extend({}, currentDashboard))
          );
        })
    );
  }, [dashboard]);

  const [refreshRate, setRefreshRate, disableRefreshRate] = useRefreshRateHandler(autoRefreshDashboard);

  // Live: the server keeps the results fresh; this tab only watches.
  const { live, setLive, lastUpdate: liveUpdatedAt } = useLiveDashboard({ dashboard, loadWidget, publicToken });
  const canManageLive = canEditDashboard && (currentUser.isAdmin || currentUser.hasPermission(MANAGE_LIVE_PERMISSION));

  // A tab timer on a live dashboard would only duplicate what the server does.
  useEffect(() => {
    if (live && refreshRate) {
      disableRefreshRate();
    }
  }, [live, refreshRate, disableRefreshRate]);

  const changeLive = useCallback(
    (changes) =>
      Dashboard.setLive(dashboard, changes)
        .then((response) => {
          setLive(response.live || null);
          setDashboard((currentDashboard) => extend({}, currentDashboard, { live: response.live || null }));
          if (response.live) {
            dropUrlParameters();
          }
        })
        .catch((error) => {
          notification.error("Could not change live settings", get(error, "response.data.message") || error.message);
        }),
    [dashboard, setLive]
  );
  const [fullscreen, toggleFullscreen] = useFullscreenHandler();
  const editModeHandler = useEditModeHandler(!gridDisabled && canEditDashboard, dashboard.widgets);

  useEffect(() => {
    if (dashboardData.live) {
      dropUrlParameters();
    }
    setDashboard(dashboardData);
    loadDashboard();
  }, [dashboardData]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    document.title = dashboard.name;
  }, [dashboard.name]);

  // reload dashboard when filter option changes
  useEffect(() => {
    loadDashboard();
  }, [dashboard.dashboard_filters_enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    dashboard,
    globalParameters,
    refreshing,
    filters,
    setFilters,
    loadDashboard,
    refreshDashboard,
    updateDashboard,
    togglePublished,
    archiveDashboard,
    loadWidget,
    refreshWidget,
    removeWidget,
    canEditDashboard,
    isDashboardOwnerOrAdmin,
    refreshRate,
    setRefreshRate,
    disableRefreshRate,
    live,
    liveUpdatedAt,
    canManageLive,
    changeLive,
    ...editModeHandler,
    saveDashboardParameters,
    gridDisabled,
    setGridDisabled,
    fullscreen,
    toggleFullscreen,
    showShareDashboardDialog,
    showAddTextboxDialog,
    showAddWidgetDialog,
    managePermissions,
    isDuplicating,
    duplicateDashboard,
  };
}

export default useDashboard;

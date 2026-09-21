import { isEmpty } from "lodash";
import React, { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";

import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import BigMessage from "@/components/BigMessage";
import DashboardGrid from "@/components/dashboards/DashboardGrid";
import Filters from "@/components/Filters";

import { Auth } from "@/services/auth";
import { Dashboard } from "@/services/dashboard";
import location from "@/services/location";
import routes from "@/services/routes";

import useDashboard from "./hooks/useDashboard";
import useWallTheme from "./hooks/useWallTheme";
import useDashboardCycle from "./hooks/useDashboardCycle";
import useWallScroll from "./hooks/useWallScroll";

import "./WallDashboardPage.less";

function WallDashboard({ dashboard, token }) {
  const { filters, setFilters, loadWidget, refreshWidget, live } = useDashboard(dashboard, { publicToken: token });

  return (
    <React.Fragment>
      <div className="wall-heading">
        <h1>{dashboard.name}</h1>
        {live && !live.paused && <span className="wall-live">live</span>}
      </div>
      {/* Filters stay: a wall dashboard is sometimes set up once with a region
          chosen, and hiding them would make that impossible to change. */}
      {!isEmpty(filters) && (
        <div className="wall-filters">
          <Filters filters={filters} onChange={setFilters} />
        </div>
      )}
      <DashboardGrid
        dashboard={dashboard}
        widgets={dashboard.widgets}
        filters={filters}
        isEditing={false}
        isPublic
        isLive={!!live}
        liveInterval={live && !live.paused ? live.interval : null}
        onLoadWidget={loadWidget}
        onRefreshWidget={refreshWidget}
      />
    </React.Fragment>
  );
}

WallDashboard.propTypes = {
  dashboard: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  token: PropTypes.string.isRequired,
};

/**
 * A dashboard for a screen on the wall: dark, no chrome, big type, and able to
 * move from one dashboard to the next on its own.
 *
 * It runs off a public token, deliberately. A wall display is unattended for
 * weeks; a login session is not, and the screen would eventually be showing a
 * sign-in form nobody is there to fill in.
 *
 *   /wall/dashboards/<token>
 *   /wall/dashboards/<token>?also=<token>,<token>&every=45
 */
function WallDashboardPage({ token }) {
  const tokens = useMemo(() => {
    const also = (location.search.also || "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    return [token, ...also];
  }, [token]);

  const dwell = useMemo(() => {
    const asked = parseInt(location.search.every, 10);
    // Under fifteen seconds nobody finishes reading a dashboard before it
    // goes; an hour is long enough for "do not cycle, really".
    return Number.isFinite(asked) ? Math.min(Math.max(asked, 15), 3600) : 60;
  }, []);

  const { current, progress } = useDashboardCycle(tokens, dwell);
  const activeToken = tokens[current];

  useWallTheme();

  // `token` is the one whose dashboard is *on screen*, which is not the one
  // being fetched while a new dashboard loads. Keeping them apart is what lets
  // the old dashboard stay put, and untouched, until the next one is ready.
  const [state, setState] = useState({ loading: true, dashboard: null, token: null, error: null });

  useEffect(() => {
    let cancelled = false;
    // Keep the dashboard on screen while the next one loads: a wall that
    // blinks to a spinner every minute is worse than one that pauses.
    setState((s) => (s.dashboard ? s : { ...s, loading: true }));
    Dashboard.getByToken({ token: activeToken })
      .then((dashboard) => {
        if (cancelled) {
          return;
        }
        // Each public dashboard is its own credentials, and the widgets are
        // about to ask for query results with them. The session key moves at
        // the same moment the dashboard does -- earlier and the dashboard
        // still on screen would be refreshing against the wrong key.
        Auth.setApiKey(activeToken);
        setState({ loading: false, dashboard, token: activeToken, error: null });
      })
      .catch((error) => {
        if (!cancelled) {
          setState((s) => ({ ...s, loading: false, error }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeToken]);

  const { loading, dashboard, token: shownToken, error } = state;

  // Keyed on the dashboard being shown, not the one being fetched, so the
  // walk down the page restarts when the dashboard actually changes.
  useWallScroll(dwell, shownToken);

  return (
    <div className="wall-dashboard-page">
      {tokens.length > 1 && (
        <div className="wall-progress" role="presentation">
          <div className="wall-progress-bar" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}
      {error && !dashboard ? (
        <BigMessage
          className="wall-message"
          icon="fa-exclamation-triangle"
          message="This dashboard is not available."
        />
      ) : loading && !dashboard ? (
        <BigMessage className="wall-message" icon="fa-spinner fa-2x fa-pulse" message="" />
      ) : (
        // Keyed by the token of the dashboard being shown, so moving to the
        // next one starts a clean dashboard rather than reconciling two
        // different sets of widgets -- and so the one already on screen is not
        // torn down and refetched the instant the cycle advances.
        <WallDashboard key={shownToken} dashboard={dashboard} token={shownToken} />
      )}
    </div>
  );
}

WallDashboardPage.propTypes = {
  token: PropTypes.string.isRequired,
};

routes.register(
  "Dashboards.Wall",
  routeWithApiKeySession({
    path: "/wall/dashboards/:token",
    render: (pageProps) => <WallDashboardPage {...pageProps} />,
    getApiKey: (currentRoute) => currentRoute.routeParams.token,
  })
);

export default WallDashboardPage;

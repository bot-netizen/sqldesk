import React from "react";
import PropTypes from "prop-types";

import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import Link from "@/components/Link";
import BigMessage from "@/components/BigMessage";
import PageHeader from "@/components/PageHeader";
import DashboardGrid from "@/components/dashboards/DashboardGrid";

import { Dashboard } from "@/services/dashboard";
import routes from "@/services/routes";

import logoUrl from "@/assets/images/sqldesk_icon.svg";

import useDashboard from "./hooks/useDashboard";
import LiveBadge from "./components/LiveBadge";
import DashboardFilters from "./components/DashboardFilters";

import useScreenshotMode from "@/lib/hooks/useScreenshotMode";

import "./PublicDashboardPage.less";

function PublicDashboard({ dashboard, token }) {
  const dashboardConfiguration = useDashboard(dashboard, { publicToken: token });
  const { filters, loadWidget, refreshWidget, live } = dashboardConfiguration;

  // Being photographed for an alert: say so once every widget has stopped
  // loading, or the renderer captures a page of spinners.
  const everyWidgetLoaded = dashboard.widgets.every((widget) => !widget.loading);
  useScreenshotMode(everyWidgetLoaded);

  return (
    <div className="container p-t-10 p-b-20">
      {/*
        Beside the title rather than in a band of its own above the grid --
        the same control the signed-in page puts beside Refresh. A shared
        dashboard is the one most likely to be read on a laptop in a meeting,
        so the row it used to spend on one dropdown is the row worth having.
      */}
      <PageHeader
        title={dashboard.name}
        actions={
          <span className="public-dashboard-actions">
            {live ? <LiveBadge live={live} /> : null}
            <DashboardFilters dashboardConfiguration={dashboardConfiguration} />
          </span>
        }
      />
      <div id="dashboard-container">
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
      </div>
    </div>
  );
}

PublicDashboard.propTypes = {
  dashboard: PropTypes.object.isRequired, // eslint-disable-line react/forbid-prop-types
  token: PropTypes.string.isRequired,
};

class PublicDashboardPage extends React.Component {
  static propTypes = {
    token: PropTypes.string.isRequired,
    onError: PropTypes.func,
  };

  static defaultProps = {
    onError: () => {},
  };

  state = {
    loading: true,
    dashboard: null,
  };

  componentDidMount() {
    Dashboard.getByToken({ token: this.props.token })
      .then((dashboard) => this.setState({ dashboard, loading: false }))
      .catch((error) => this.props.onError(error));
  }

  render() {
    const { loading, dashboard } = this.state;
    return (
      <div className="public-dashboard-page">
        {loading ? (
          <div className="container loading-message">
            <BigMessage className="" icon="fa-spinner fa-2x fa-pulse" message="Loading..." />
          </div>
        ) : (
          <PublicDashboard dashboard={dashboard} token={this.props.token} />
        )}
        <div id="footer">
          <div className="text-center">
            <Link href="https://sqldesk.github.io/sqldesk">
              <img alt="SQLDesk" src={logoUrl} width="38" />
            </Link>
          </div>
          Powered by <Link href="https://sqldesk.github.io/sqldesk">SQLDesk</Link>
        </div>
      </div>
    );
  }
}

routes.register(
  "Dashboards.ViewShared",
  routeWithApiKeySession({
    path: "/public/dashboards/:token",
    render: (pageProps) => <PublicDashboardPage {...pageProps} />,
    getApiKey: (currentRoute) => currentRoute.routeParams.token,
  })
);

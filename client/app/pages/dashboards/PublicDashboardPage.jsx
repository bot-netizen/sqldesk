import { isEmpty } from "lodash";
import React from "react";
import PropTypes from "prop-types";

import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import Link from "@/components/Link";
import BigMessage from "@/components/BigMessage";
import PageHeader from "@/components/PageHeader";
import Parameters from "@/components/Parameters";
import DashboardGrid from "@/components/dashboards/DashboardGrid";
import Filters from "@/components/Filters";

import { Dashboard } from "@/services/dashboard";
import routes from "@/services/routes";

import logoUrl from "@/assets/images/sqldesk_icon.svg";

import useDashboard from "./hooks/useDashboard";
import LiveBadge from "./components/LiveBadge";

import useScreenshotMode from "@/lib/hooks/useScreenshotMode";

import "./PublicDashboardPage.less";

function PublicDashboard({ dashboard, token }) {
  const { globalParameters, filters, setFilters, refreshDashboard, loadWidget, refreshWidget, live } = useDashboard(
    dashboard,
    { publicToken: token }
  );

  // Being photographed for an alert: say so once every widget has stopped
  // loading, or the renderer captures a page of spinners.
  const everyWidgetLoaded = dashboard.widgets.every((widget) => !widget.loading);
  useScreenshotMode(everyWidgetLoaded);

  return (
    <div className="container p-t-10 p-b-20">
      <PageHeader title={dashboard.name} actions={live ? <LiveBadge live={live} /> : null} />
      {/* A live dashboard's parameters are fixed: it shows what the server refreshes. */}
      {!live && !isEmpty(globalParameters) && (
        <div className="m-b-10 p-15 bg-white tiled">
          <Parameters parameters={globalParameters} onValuesChange={refreshDashboard} />
        </div>
      )}
      {!isEmpty(filters) && (
        <div className="m-b-10 p-15 bg-white tiled">
          <Filters filters={filters} onChange={setFilters} />
        </div>
      )}
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

import React from "react";
import cx from "classnames";
import PropTypes from "prop-types";
import { first, includes } from "lodash";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import HelpTrigger from "@/components/HelpTrigger";
import CreateDashboardDialog from "@/components/dashboards/CreateDashboardDialog";
import { useCurrentRoute } from "@/components/ApplicationArea/Router";
import { Auth, currentUser } from "@/services/auth";
import settingsMenu from "@/services/settingsMenu";
import logoUrl from "@/assets/images/sqldesk_icon.svg";

import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import QuestionCircleOutlinedIcon from "@ant-design/icons/QuestionCircleOutlined";
import SettingOutlinedIcon from "@ant-design/icons/SettingOutlined";

import VersionInfo from "./VersionInfo";

import "./DesktopNavbar.less";

function NavLink({ href, active, children, ...rest }) {
  return (
    <Link href={href} className={cx("desktop-navbar-link", { "desktop-navbar-link-active": active })} {...rest}>
      {children}
    </Link>
  );
}

NavLink.propTypes = {
  href: PropTypes.string.isRequired,
  active: PropTypes.bool,
  children: PropTypes.node,
};

NavLink.defaultProps = { active: false, children: null };

function useNavbarActiveState() {
  const currentRoute = useCurrentRoute();

  return React.useMemo(
    () => ({
      dashboards: includes(
        [
          "Dashboards.List",
          "Dashboards.Favorites",
          "Dashboards.My",
          "Dashboards.ViewOrEdit",
          "Dashboards.LegacyViewOrEdit",
        ],
        currentRoute.id
      ),
      queries: includes(
        [
          "Queries.List",
          "Queries.Favorites",
          "Queries.Archived",
          "Queries.My",
          "Queries.View",
          "Queries.New",
          "Queries.Edit",
        ],
        currentRoute.id
      ),
      dataSources: includes(["DataSources.List"], currentRoute.id),
      alerts: includes(["Alerts.List", "Alerts.New", "Alerts.View", "Alerts.Edit"], currentRoute.id),
    }),
    [currentRoute.id]
  );
}

export default function DesktopNavbar() {
  const firstSettingsTab = first(settingsMenu.getAvailableItems());
  const activeState = useNavbarActiveState();

  const canCreateQuery = currentUser.hasPermission("create_query");
  const canCreateDashboard = currentUser.hasPermission("create_dashboard");
  const canCreateAlert = currentUser.hasPermission("list_alerts");
  const canCreate = canCreateQuery || canCreateDashboard || canCreateAlert;

  const createMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      {canCreateQuery && (
        <Menu.Item key="new-query">
          <Link href="queries/new" data-test="CreateQueryMenuItem">
            New Query
          </Link>
        </Menu.Item>
      )}
      {canCreateDashboard && (
        <Menu.Item key="new-dashboard">
          <PlainButton data-test="CreateDashboardMenuItem" onClick={() => CreateDashboardDialog.showModal()}>
            New Dashboard
          </PlainButton>
        </Menu.Item>
      )}
      {canCreateAlert && (
        <Menu.Item key="new-alert">
          <Link data-test="CreateAlertMenuItem" href="alerts/new">
            New Alert
          </Link>
        </Menu.Item>
      )}
    </Menu>
  );

  const profileMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="profile">
        <Link href="users/me">Profile</Link>
      </Menu.Item>
      {currentUser.hasPermission("super_admin") && (
        <Menu.Item key="status">
          <Link href="admin/status">System Status</Link>
        </Menu.Item>
      )}
      <Menu.Divider />
      <Menu.Item key="logout">
        <PlainButton data-test="LogOutButton" onClick={() => Auth.logout()}>
          Log out
        </PlainButton>
      </Menu.Item>
      <Menu.Divider />
      <Menu.Item key="version" role="presentation" disabled className="version-info">
        <VersionInfo />
      </Menu.Item>
    </Menu>
  );

  return (
    <nav className="desktop-navbar" aria-label="Main">
      <Link href="./" className="desktop-navbar-brand" aria-label="SQLDesk home">
        <img src={logoUrl} alt="" />
        <span className="desktop-navbar-wordmark">SQLDesk</span>
      </Link>

      <div className="desktop-navbar-links">
        {currentUser.hasPermission("list_dashboards") && (
          <NavLink href="dashboards" active={activeState.dashboards}>
            Dashboards
          </NavLink>
        )}
        {currentUser.hasPermission("view_query") && (
          <NavLink href="queries" active={activeState.queries}>
            Queries
          </NavLink>
        )}
        {currentUser.hasPermission("list_alerts") && (
          <NavLink href="alerts" active={activeState.alerts}>
            Alerts
          </NavLink>
        )}
      </div>

      <div className="desktop-navbar-spacer" />

      {canCreate && (
        <Dropdown overlay={createMenu} trigger={["click"]} placement="bottomRight">
          <PlainButton className="desktop-navbar-create-button" data-test="CreateButton">
            <PlusOutlinedIcon aria-hidden="true" />
            <span>Create</span>
          </PlainButton>
        </Dropdown>
      )}

      <HelpTrigger showTooltip={false} type="HOME" tabIndex={0} className="desktop-navbar-icon-link">
        <QuestionCircleOutlinedIcon aria-hidden="true" />
        <span className="sr-only">Help</span>
      </HelpTrigger>

      {firstSettingsTab && (
        <Link
          href={firstSettingsTab.path}
          data-test="SettingsLink"
          className={cx("desktop-navbar-icon-link", { "desktop-navbar-link-active": activeState.dataSources })}
        >
          <SettingOutlinedIcon aria-hidden="true" />
          <span className="sr-only">Settings</span>
        </Link>
      )}

      <Dropdown overlay={profileMenu} trigger={["click"]} placement="bottomRight">
        <PlainButton className="desktop-navbar-profile-button" data-test="ProfileDropdown" aria-label="Account menu">
          <img className="profile__image_thumb" src={currentUser.profile_image_url} alt="" />
        </PlainButton>
      </Dropdown>
    </nav>
  );
}

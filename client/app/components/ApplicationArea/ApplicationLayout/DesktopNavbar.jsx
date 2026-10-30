import React from "react";
import cx from "classnames";
import PropTypes from "prop-types";
import { includes } from "lodash";
import Dropdown from "antd/lib/dropdown";
import Menu from "antd/lib/menu";
import Link from "@/components/Link";
import PlainButton from "@/components/PlainButton";
import UserAvatar from "@/components/UserAvatar";
import HelpTrigger from "@/components/HelpTrigger";
import CreateDashboardDialog from "@/components/dashboards/CreateDashboardDialog";
import { useCurrentRoute } from "@/components/ApplicationArea/Router";
import { Auth, currentUser } from "@/services/auth";
import { axios } from "@/services/axios";
import settingsMenu from "@/services/settingsMenu";
import { adminTabs } from "@/pages/admin/adminTabs";
import logoUrl from "@/assets/images/sqldesk_icon.svg";

import PlusOutlinedIcon from "@ant-design/icons/PlusOutlined";
import QuestionCircleOutlinedIcon from "@ant-design/icons/QuestionCircleOutlined";

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

/*
  A button that opens a menu, told apart from one that goes somewhere.

  Every dropdown in this bar wears the same chevron. Dashboards had one and
  Admin did not, so two controls that behave identically looked like two
  different kinds of thing -- and the one without it read as a link that had
  stopped working when a click produced a menu instead of a page.
*/
function NavMenuButton({ overlay, active, children, ...rest }) {
  return (
    <Dropdown overlay={overlay} trigger={["click"]} placement="bottomLeft">
      <PlainButton className={cx("desktop-navbar-link", { "desktop-navbar-link-active": active })} {...rest}>
        {children}
        <i className="fa fa-angle-down desktop-navbar-caret" aria-hidden="true" />
      </PlainButton>
    </Dropdown>
  );
}

NavMenuButton.propTypes = {
  overlay: PropTypes.node.isRequired,
  active: PropTypes.bool,
  children: PropTypes.node,
};

NavMenuButton.defaultProps = { active: false, children: null };

const SETTINGS_ROUTES = [
  "AlertDestinations.Edit",
  "AlertDestinations.List",
  "AlertDestinations.New",
  "DataSources.Edit",
  "DataSources.List",
  "DataSources.New",
  "Groups.DataSources",
  "Groups.List",
  "Groups.Members",
  "QuerySnippets.List",
  "QuerySnippets.NewOrEdit",
  "Settings.Organization",
  // The topics page: a tab beside Data Sources, because it configures a
  // connection.
  "Streams.Topics",
  "Users.Account",
  "Users.Disabled",
  "Users.List",
  "Users.New",
  "Users.Pending",
  "Users.ViewOrEdit",
];

function useNavbarActiveState() {
  const currentRoute = useCurrentRoute();

  return React.useMemo(
    () => ({
      // Both halves light the same tab. A streaming dashboard is a dashboard,
      // so being on one is being under Dashboards; the same for a streaming
      // query, including in the editor, which has its own path only because a
      // streaming query has no second page to distinguish.
      dashboards: includes(
        [
          "Dashboards.List",
          "Dashboards.Favorites",
          "Dashboards.My",
          "Dashboards.Streaming",
          "Dashboards.StreamingFavorites",
          "Dashboards.StreamingMy",
          "Dashboards.Folder",
          "Dashboards.Folders",
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
          "Queries.Streaming",
          "Queries.StreamingFavorites",
          "Queries.StreamingMy",
          "Queries.StreamingArchived",
          "Queries.View",
          "Queries.New",
          "Queries.Edit",
          "Streams.Query",
          "Streams.QueryEdit",
        ],
        currentRoute.id
      ),
      notebooks: includes(["Notebooks.List", "Notebooks.View"], currentRoute.id),
      alerts: includes(["Alerts.List", "Alerts.New", "Alerts.View", "Alerts.Edit"], currentRoute.id),
      catalog: currentRoute.id === "Catalog",
      settings: includes(SETTINGS_ROUTES, currentRoute.id),
      // Every Admin page, from the one list that draws the menu -- so a page
      // added there lights the right tab here without this being touched.
      admin: (currentRoute.id || "").startsWith("Admin."),
    }),
    [currentRoute.id]
  );
}

/*
  The folders chosen for the Dashboards menu.

  Only the ones somebody picked. An install ends up with more folders than fit
  in a dropdown and a menu of thirty is a menu nobody reads, so the few people
  use daily are here and the rest are a click away under Browse folders.

  Fetched once when the navbar mounts rather than on every open: the list is
  short, it changes rarely, and a dropdown that waits for a request before it
  can draw is a dropdown that feels broken. A failure leaves it empty, which
  degrades to exactly the menu there was before folders existed.
*/
function useDashboardFolders() {
  const [folders, setFolders] = React.useState([]);

  React.useEffect(() => {
    let live = true;
    axios
      .get("api/dashboard_folders?in_menu=true")
      .then((found) => live && setFolders(found || []))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  return folders;
}

export default function DesktopNavbar() {
  const settingsTabs = settingsMenu.getAvailableItems();
  const activeState = useNavbarActiveState();
  const folders = useDashboardFolders();

  const canCreateQuery = currentUser.hasPermission("create_query");
  const canCreateDashboard = currentUser.hasPermission("create_dashboard");
  const canCreateAlert = currentUser.hasPermission("list_alerts");
  const canCreate = canCreateQuery || canCreateDashboard || canCreateAlert || currentUser.can("use_notebooks");
  const canUseStreams = currentUser.can("use_streams") || currentUser.can("manage_streams");
  const canUseNotebooks = currentUser.can("use_notebooks");

  const createMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      {canCreateQuery && (
        <Menu.Item key="new-query">
          <Link href="queries/new" data-test="CreateQueryMenuItem">
            New Query
          </Link>
        </Menu.Item>
      )}
      {/*
        Where starting a stream lives now. It was the first item of a menu of
        its own, which made a create action look like a place -- the only
        entry in this bar that opened an empty editor rather than a list.
      */}
      {canCreateQuery && canUseStreams && (
        <Menu.Item key="new-streaming-query">
          <Link href="streams/query" data-test="CreateStreamingQueryMenuItem">
            New Streaming Query
          </Link>
        </Menu.Item>
      )}
      {canUseNotebooks && (
        <Menu.Item key="new-notebook">
          <Link href="notebooks" data-test="CreateNotebookMenuItem">
            New Notebook
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

  // Everything an admin does, from the same list that draws the tab strip on
  // the pages themselves -- Storage and Streams were pages with routes and no
  // way to reach either, because two hand-written menus had drifted apart.
  //
  // Titles only. Each tab describes itself in two or three lines, and eight of
  // those make a menu taller than the window; the description belongs on the
  // page, which is where somebody reads it anyway.
  const adminMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      {adminTabs().map((tab) => (
        <Menu.Item key={`admin-${tab.key}`}>
          <Link href={tab.path}>{tab.title}</Link>
        </Menu.Item>
      ))}
    </Menu>
  );

  // The same two halves, for queries. Only a menu when there is a second half
  // to offer: an install with streams switched off -- which is the default --
  // gets the plain link it has always had, rather than a dropdown with one
  // thing in it.
  const queriesMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="queries-all">
        <Link href="queries">Queries</Link>
      </Menu.Item>
      <Menu.Item key="queries-streaming">
        <Link href="queries/streaming">Streaming Queries</Link>
      </Menu.Item>
    </Menu>
  );

  /*
    Dashboards opens on all of them, as it always has. The folders are under
    it, each a set with a stated meaning -- which is only useful if people can
    get to them without knowing they exist, hence here rather than only on a
    page of their own.
  */
  const dashboardsMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="dashboards-all">
        <Link href="dashboards">Dashboards</Link>
      </Menu.Item>
      {/*
        The other half of the same set. A dashboard shows streams or saved
        queries and never both, so it is in exactly one of these two lists --
        which is why the menu offers the halves and the page offers All,
        Favorites and Mine within whichever you picked. Repeating those three
        here would be the same control twice, and eight entries deep.
      */}
      {canUseStreams && (
        <Menu.Item key="dashboards-streaming">
          <Link href="dashboards/streaming">Streaming Dashboards</Link>
        </Menu.Item>
      )}
      {folders.length > 0 && <Menu.Divider />}
      {folders.map((folder) => (
        <Menu.Item key={`folder-${folder.id}`}>
          <Link href={`dashboards/folder/${folder.id}`}>{folder.name}</Link>
        </Menu.Item>
      ))}
      <Menu.Divider />
      <Menu.Item key="dashboards-folders">
        <Link href="dashboards/folders">Browse folders…</Link>
      </Menu.Item>
    </Menu>
  );

  // Out of the gear on the right and into the row, because what it holds
  // depends entirely on who you are: an administrator sees data sources,
  // groups and the organisation's settings; everybody else sees their own
  // account and their snippets. An icon cannot say that; a named menu can.
  const settingsNavMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      {settingsTabs.map((tab) => (
        <Menu.Item key={`settings-${tab.id || tab.path}`}>
          <Link href={tab.path}>{tab.title}</Link>
        </Menu.Item>
      ))}
    </Menu>
  );

  const profileMenu = (
    <Menu className="desktop-navbar-dropdown-menu">
      <Menu.Item key="profile">
        <Link href="users/me">Profile</Link>
      </Menu.Item>
      {/*
        Everybody who may connect a client, not administrators: the page says
        how to point one at SQLDesk and what yours has been doing. Reachable
        only from the Admin menu, nobody without super_admin could find it at
        all -- which was the state before this.
      */}
      {currentUser.can("use_mcp") && (
        <Menu.Item key="mcp">
          <Link href="mcp/mine">My MCP</Link>
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
          <NavMenuButton overlay={dashboardsMenu} active={activeState.dashboards} data-test="DashboardsMenuButton">
            Dashboards
          </NavMenuButton>
        )}
        {currentUser.hasPermission("view_query") &&
          (canUseStreams ? (
            <NavMenuButton overlay={queriesMenu} active={activeState.queries} data-test="QueriesMenuButton">
              Queries
            </NavMenuButton>
          ) : (
            <NavLink href="queries" active={activeState.queries}>
              Queries
            </NavLink>
          ))}
        {/*
          After Queries, because that is what it is the long form of: the work
          a saved query cannot hold, where everything else here ends in one
          SELECT. Shown only to a group an administrator gave it to.
        */}
        {canUseNotebooks && (
          <NavLink href="notebooks" active={activeState.notebooks}>
            Notebooks
          </NavLink>
        )}
        {/*
          Beside the others rather than under Admin: describing a table is
          the work of whoever knows what it is for, and an administrator
          hands that out per group.
        */}
        {currentUser.can("manage_catalog") && (
          <NavLink href="catalog" active={activeState.catalog}>
            Catalog
          </NavLink>
        )}
        {currentUser.hasPermission("list_alerts") && (
          <NavLink href="alerts" active={activeState.alerts}>
            Alerts
          </NavLink>
        )}
        {settingsTabs.length > 0 && (
          <NavMenuButton overlay={settingsNavMenu} active={activeState.settings} data-test="SettingsMenuButton">
            Settings
          </NavMenuButton>
        )}
        {currentUser.hasPermission("super_admin") && (
          <NavMenuButton overlay={adminMenu} active={activeState.admin} data-test="AdminMenuButton">
            Admin
          </NavMenuButton>
        )}
      </div>

      <div className="desktop-navbar-spacer" />

      {canCreate && (
        <Dropdown overlay={createMenu} trigger={["click"]} placement="bottomRight">
          <PlainButton className="desktop-navbar-create-button" data-test="CreateButton">
            <PlusOutlinedIcon aria-hidden="true" />
            <span>Create</span>
            <i className="fa fa-angle-down desktop-navbar-caret" aria-hidden="true" />
          </PlainButton>
        </Dropdown>
      )}

      <HelpTrigger showTooltip={false} type="HOME" tabIndex={0} className="desktop-navbar-icon-link">
        <QuestionCircleOutlinedIcon aria-hidden="true" />
        <span className="sr-only">Help</span>
      </HelpTrigger>

      <Dropdown overlay={profileMenu} trigger={["click"]} placement="bottomRight">
        <PlainButton className="desktop-navbar-profile-button" data-test="ProfileDropdown" aria-label="Account menu">
          <UserAvatar user={currentUser} size={28} />
          <i className="fa fa-angle-down desktop-navbar-caret" aria-hidden="true" />
        </PlainButton>
      </Dropdown>
    </nav>
  );
}

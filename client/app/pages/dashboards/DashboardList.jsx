import React, { useMemo, useRef } from "react";
import cx from "classnames";

import Button from "antd/lib/button";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import Link from "@/components/Link";
import Paginator from "@/components/Paginator";
import DynamicComponent from "@/components/DynamicComponent";
import { DashboardTagsControl } from "@/components/tags-control/TagsControl";
import { wrap as itemsList, ControllerType } from "@/components/items-list/ItemsList";
import { ResourceItemsSource } from "@/components/items-list/classes/ItemsSource";
import { UrlStateStorage } from "@/components/items-list/classes/StateStorage";
import * as Sidebar from "@/components/items-list/components/Sidebar";
import { Shell, Header, ViewTabs, TagChips } from "@/components/items-list/components/ListPage";
import {
  FilterControl,
  ColumnsControl,
  useHiddenColumns,
  visibleColumns,
} from "@/components/items-list/components/ListPageControls";
import ItemsTable, { Columns } from "@/components/items-list/components/ItemsTable";
import ListItemActions from "@/components/items-list/components/ListItemActions";
import useItemsListExtraActions from "@/components/items-list/hooks/useItemsListExtraActions";
import CreateDashboardDialog from "@/components/dashboards/CreateDashboardDialog";

import { Dashboard } from "@/services/dashboard";
import { currentUser } from "@/services/auth";
import routes from "@/services/routes";

import DashboardListEmptyState from "./components/DashboardListEmptyState";

import "./dashboard-list.css";

const sidebarMenu = [
  {
    key: "all",
    href: "dashboards",
    title: "All",
    icon: () => <Sidebar.MenuIcon icon="zmdi zmdi-view-quilt" />,
  },
  {
    key: "favorites",
    href: "dashboards/favorites",
    title: "Favorites",
    icon: () => <Sidebar.MenuIcon icon="fa fa-star" />,
  },
  {
    key: "my",
    href: "dashboards/my",
    title: "Mine",
    icon: () => <Sidebar.ProfileImage user={currentUser} />,
  },
];

// Factory, not a constant: the actions column needs the controller to
// refresh the list after an archive.
// Appended last by the component, after any page-specific columns, so a
// row's menu sits where actions are expected: at the end of the row.
function getActionsColumn(controllerRef) {
  return Columns.custom(
    (text, item) => (
      <ListItemActions
        item={item}
        editUrl={item.url}
        aclUrl={`api/dashboards/${item.id}/acl`}
        aclContext="dashboard"
        deleteLabel="Archive"
        deleteConfirm={{
          title: "Archive Dashboard",
          content: `Are you sure you want to archive the "${item.name}" dashboard?`,
          okText: "Archive",
        }}
        onDelete={(dashboard) => Dashboard.delete({ id: dashboard.id }).then(() => controllerRef.current.update())}
      />
    ),
    { title: "", width: "1%", className: "p-l-0" }
  );
}

function getListColumns(controllerRef) {
  return [
    Columns.favorites({ className: "p-r-0" }),
    Columns.custom.sortable(
      (text, item) => (
        <span className="list-page-name">
          <Link className="table-main-title" href={item.url} data-test={`DashboardId${item.id}`}>
            {item.name}
          </Link>
          <DashboardTagsControl tags={item.tags} isDraft={item.is_draft} isArchived={item.is_archived} />
        </span>
      ),
      {
        title: "Name",
        field: "name",
        width: null,
      }
    ),
    // Panels and the distinct queries behind them. Two panels charting the same
    // query count once, so this says what the dashboard costs to refresh rather
    // than how many tiles it has.
    Columns.custom(
      (text, item) => (
        <span className="dashboard-list-content">
          <span>
            {item.widget_count} {item.widget_count === 1 ? "panel" : "panels"}
          </span>
          <span className="dashboard-list-content-sep">·</span>
          <span>
            {item.query_count} {item.query_count === 1 ? "query" : "queries"}
          </span>
        </span>
      ),
      { title: "Content", width: 190 }
    ),
    Columns.custom(
      (text, item) => (
        <span className="list-page-owner">
          <img src={item.user.profile_image_url} alt="" />
          {item.user.name}
        </span>
      ),
      { title: "Owner", width: 190 }
    ),
    Columns.timeAgo.sortable({
      title: "Created",
      field: "created_at",
      width: 150,
    }),
  ];
}

function DashboardListExtraActions(props) {
  return <DynamicComponent name="DashboardList.Actions" {...props} />;
}

function DashboardList({ controller }) {
  const controllerRef = useRef();
  controllerRef.current = controller;

  let usedListColumns = useMemo(() => getListColumns(controllerRef), []);
  if (controller.params.currentPage === "favorites") {
    usedListColumns = [
      ...usedListColumns,
      Columns.dateTime.sortable({ title: "Starred At", field: "starred_at", width: "1%" }),
    ];
  }
  usedListColumns = [...usedListColumns, getActionsColumn(controllerRef)];
  const [hiddenColumns, toggleColumn] = useHiddenColumns("dashboards");
  // allListColumns is what the Columns menu lists; usedListColumns is what the
  // table renders. They have to stay distinct, or hiding a column removes it
  // from the menu that would bring it back.
  const allListColumns = usedListColumns;
  usedListColumns = visibleColumns(allListColumns, hiddenColumns);

  const sortLabel = useMemo(() => {
    const labels = { name: "name", created_at: "created", starred_at: "starred" };
    return labels[controller.orderByField] || controller.orderByField || "name";
  }, [controller.orderByField]);
  const {
    areExtraActionsAvailable,
    listColumns: tableColumns,
    Component: ExtraActionsComponent,
    selectedItems,
  } = useItemsListExtraActions(controller, usedListColumns, DashboardListExtraActions);

  const sourceSubtitle = controller.isLoaded
    ? `${controller.totalItemsCount} ${controller.totalItemsCount === 1 ? "dashboard" : "dashboards"}`
    : "Loading…";

  return (
    <div className="page-dashboard-list">
      <Shell>
        <Header title={controller.params.pageTitle} subtitle={sourceSubtitle}>
          <FilterControl
            value={controller.searchTerm}
            onChange={controller.updateSearch}
            placeholder="Search dashboards…"
            label="Search dashboards"
          />
          <ColumnsControl columns={allListColumns} hidden={hiddenColumns} onToggle={toggleColumn} />
          {currentUser.hasPermission("create_dashboard") && (
            <Button type="primary" onClick={() => CreateDashboardDialog.showModal()}>
              <i className="fa fa-plus m-r-5" aria-hidden="true" />
              New dashboard
            </Button>
          )}
        </Header>

        <ViewTabs items={sidebarMenu} selected={controller.params.currentPage} ariaLabel="Dashboard views" />

        <TagChips
          tagsUrl="api/dashboards/tags"
          onChange={controller.updateSelectedTags}
          aside={
            <React.Fragment>
              Sorted by <strong>{sortLabel}</strong>
            </React.Fragment>
          }
        />

        <div data-test="DashboardLayoutContent">
          {controller.isLoaded && controller.isEmpty ? (
            <DashboardListEmptyState
              page={controller.params.currentPage}
              searchTerm={controller.searchTerm}
              selectedTags={controller.selectedTags}
            />
          ) : (
            <React.Fragment>
              <div className={cx({ "m-b-10": areExtraActionsAvailable })}>
                <ExtraActionsComponent selectedItems={selectedItems} />
              </div>
              <div className="bg-white tiled table-responsive">
                <ItemsTable
                  items={controller.pageItems}
                  loading={!controller.isLoaded}
                  columns={tableColumns}
                  orderByField={controller.orderByField}
                  orderByReverse={controller.orderByReverse}
                  toggleSorting={controller.toggleSorting}
                />
                <Paginator
                  showPageSizeSelect
                  totalCount={controller.totalItemsCount}
                  pageSize={controller.itemsPerPage}
                  onPageSizeChange={(itemsPerPage) => controller.updatePagination({ itemsPerPage })}
                  page={controller.page}
                  onChange={(page) => controller.updatePagination({ page })}
                />
              </div>
            </React.Fragment>
          )}
        </div>
      </Shell>
    </div>
  );
}

DashboardList.propTypes = {
  controller: ControllerType.isRequired,
};

const DashboardListPage = itemsList(
  DashboardList,
  () =>
    new ResourceItemsSource({
      getResource({ params: { currentPage } }) {
        return {
          all: Dashboard.query.bind(Dashboard),
          my: Dashboard.myDashboards.bind(Dashboard),
          favorites: Dashboard.favorites.bind(Dashboard),
        }[currentPage];
      },
      getItemProcessor() {
        return (item) => new Dashboard(item);
      },
    }),
  ({ ...props }) => new UrlStateStorage({ orderByField: props.orderByField ?? "created_at", orderByReverse: true })
);

routes.register(
  "Dashboards.List",
  routeWithUserSession({
    path: "/dashboards",
    title: "Dashboards",
    render: (pageProps) => <DashboardListPage {...pageProps} currentPage="all" />,
  })
);
routes.register(
  "Dashboards.Favorites",
  routeWithUserSession({
    path: "/dashboards/favorites",
    title: "Favorite Dashboards",
    render: (pageProps) => <DashboardListPage {...pageProps} currentPage="favorites" orderByField="starred_at" />,
  })
);
routes.register(
  "Dashboards.My",
  routeWithUserSession({
    path: "/dashboards/my",
    title: "My Dashboards",
    render: (pageProps) => <DashboardListPage {...pageProps} currentPage="my" />,
  })
);

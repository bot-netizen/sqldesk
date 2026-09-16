import React, { useCallback, useEffect, useMemo, useRef } from "react";
import cx from "classnames";
import { get } from "lodash";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import Link from "@/components/Link";
import Paginator from "@/components/Paginator";
import DynamicComponent from "@/components/DynamicComponent";
import { QueryTagsControl } from "@/components/tags-control/TagsControl";
import SchedulePhrase from "@/components/queries/SchedulePhrase";
import QueryHealth from "@/components/queries/QueryHealth";
import useDataSourceNames from "@/components/queries/useDataSourceNames";
import { formatRuntime, formatRowCount } from "@/lib/utils";

import { wrap as itemsList, ControllerType } from "@/components/items-list/ItemsList";
import useItemsListExtraActions from "@/components/items-list/hooks/useItemsListExtraActions";
import { ResourceItemsSource } from "@/components/items-list/classes/ItemsSource";
import { UrlStateStorage } from "@/components/items-list/classes/StateStorage";

import * as Sidebar from "@/components/items-list/components/Sidebar";
import { Shell, Header, ViewTabs, TagChips } from "@/components/items-list/components/ListPage";
import { FilterControl, ColumnsControl, useHiddenColumns } from "@/components/items-list/components/ListPageControls";
import ItemsTable, { Columns } from "@/components/items-list/components/ItemsTable";
import ListItemActions from "@/components/items-list/components/ListItemActions";

import { Query } from "@/services/query";
import { clientConfig, currentUser } from "@/services/auth";
import location from "@/services/location";
import routes from "@/services/routes";

import QueriesListEmptyState from "./QueriesListEmptyState";

import "./queries-list.css";

const sidebarMenu = [
  {
    key: "all",
    href: "queries",
    title: "All",
    icon: () => <Sidebar.MenuIcon icon="fa fa-code" />,
  },
  {
    key: "favorites",
    href: "queries/favorites",
    title: "Favorites",
    icon: () => <Sidebar.MenuIcon icon="fa fa-star" />,
  },
  {
    key: "my",
    href: "queries/my",
    title: "Mine",
    icon: () => <Sidebar.ProfileImage user={currentUser} />,
  },
  {
    key: "archive",
    href: "queries/archive",
    title: "Archived",
    icon: () => <Sidebar.MenuIcon icon="fa fa-archive" />,
  },
];

/*
  Built as a factory rather than a constant so the Source column can close
  over the id -> name map, which arrives asynchronously.
*/
// Appended last by the component, after any page-specific columns, so a
// row's menu sits where actions are expected: at the end of the row.
function getActionsColumn(controllerRef) {
  return Columns.custom(
    (text, item) => (
      <ListItemActions
        item={item}
        editUrl={`queries/${item.id}/source`}
        aclUrl={`api/queries/${item.id}/acl`}
        aclContext="query"
        deleteLabel="Archive"
        deleteConfirm={{
          title: "Archive Query",
          content: (
            <React.Fragment>
              <div className="m-b-5">Are you sure you want to archive this query?</div>
              <div>All alerts and dashboard widgets created with its visualizations will be deleted.</div>
            </React.Fragment>
          ),
          okText: "Archive",
        }}
        onDelete={(query) => Query.delete({ id: query.id }).then(() => controllerRef.current.update())}
      />
    ),
    { title: "", width: "1%", className: "p-l-0" }
  );
}

function getListColumns(dataSourceNames, controllerRef) {
  return [
    Columns.favorites({ className: "p-r-0" }),
    Columns.custom.sortable(
      (text, item) => (
        <span className="list-page-name">
          <Link className="table-main-title" href={"queries/" + item.id}>
            {item.name}
          </Link>
          <QueryTagsControl tags={item.tags} isDraft={item.is_draft} isArchived={item.is_archived} />
        </span>
      ),
      {
        title: "Name",
        field: "name",
        width: null,
      }
    ),
    Columns.custom(
      (text, item) => <span className="queries-list-source">{dataSourceNames[item.data_source_id] || "\u2014"}</span>,
      { title: "Source", width: 150 }
    ),
    // Not sortable: health is derived on the client from three fields, so
    // there is no single column the backend could order by.
    Columns.custom((text, item) => <QueryHealth query={item} />, { title: "Status", width: 130 }),
    Columns.custom((text, item) => <span className="queries-list-rows">{formatRowCount(item.row_count)}</span>, {
      title: "Rows",
      width: 110,
      className: "text-right",
    }),
    Columns.custom((text, item) => <span className="queries-list-runtime">{formatRuntime(item.runtime)}</span>, {
      title: "Runtime",
      width: 120,
      className: "text-right",
    }),
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
      title: "Last run",
      field: "retrieved_at",
      orderByField: "executed_at",
      width: 150,
    }),
    Columns.custom.sortable(
      (text, item) => (
        <span className="queries-list-schedule">
          <SchedulePhrase schedule={item.schedule} isNew={item.isNew()} />
        </span>
      ),
      {
        title: "Schedule",
        field: "schedule",
        width: 140,
      }
    ),
  ];
}

function QueriesListExtraActions(props) {
  return <DynamicComponent name="QueriesList.Actions" {...props} />;
}

function QueriesList({ controller }) {
  const controllerRef = useRef();
  controllerRef.current = controller;

  const updateSearch = useCallback(
    (searchTemm) => {
      controller.updateSearch(searchTemm, { isServerSideFTS: !clientConfig.multiByteSearchEnabled });
    },
    [controller]
  );

  useEffect(() => {
    const unlistenLocationChanges = location.listen((unused, action) => {
      const searchTerm = location.search.q || "";
      if (action === "PUSH" && searchTerm !== controllerRef.current.searchTerm) {
        updateSearch(searchTerm);
      }
    });

    return () => {
      unlistenLocationChanges();
    };
  }, [updateSearch]);

  const dataSourceNames = useDataSourceNames();
  let usedListColumns = useMemo(() => getListColumns(dataSourceNames, controllerRef), [dataSourceNames]);
  if (controller.params.currentPage === "favorites") {
    usedListColumns = [
      ...usedListColumns,
      Columns.dateTime.sortable({ title: "Starred At", field: "starred_at", width: "1%" }),
    ];
  }
  usedListColumns = [...usedListColumns, getActionsColumn(controllerRef)];
  const [hiddenColumns, toggleColumn] = useHiddenColumns("queries");
  usedListColumns = usedListColumns.filter(
    (column) => typeof column.title !== "string" || !hiddenColumns.includes(column.title)
  );
  const {
    areExtraActionsAvailable,
    listColumns: tableColumns,
    Component: ExtraActionsComponent,
    selectedItems,
  } = useItemsListExtraActions(controller, usedListColumns, QueriesListExtraActions);

  const sourceCount = Object.keys(dataSourceNames).length;
  // failing_count comes from the list endpoint and covers the whole filtered
  // set. Counting the current page instead would under-report, and a
  // page-local number under a global-looking label would mislead.
  const failingCount = get(controller, "params.meta.failing_count", 0);
  const sortLabel = useMemo(() => {
    const labels = {
      name: "name",
      created_at: "created",
      retrieved_at: "last run",
      executed_at: "last run",
      schedule: "schedule",
      starred_at: "starred",
    };
    return labels[controller.orderByField] || controller.orderByField || "name";
  }, [controller.orderByField]);

  const subtitle = useMemo(() => {
    if (!controller.isLoaded) {
      return "Loading…";
    }
    const total = controller.totalItemsCount;
    const parts = [`${total} ${total === 1 ? "query" : "queries"}`];
    if (sourceCount > 0) {
      parts.push(`across ${sourceCount} data ${sourceCount === 1 ? "source" : "sources"}`);
    }
    return parts.join(" ");
  }, [controller.isLoaded, controller.totalItemsCount, sourceCount]);

  return (
    <div className="page-queries-list">
      <Shell>
        <Header
          title={controller.params.pageTitle}
          subtitle={
            <React.Fragment>
              {subtitle}
              {failingCount > 0 && <span className="list-page-subtitle-alert">{failingCount} failing</span>}
            </React.Fragment>
          }
        >
          <FilterControl
            value={controller.searchTerm}
            onChange={updateSearch}
            placeholder="Search queries…"
            label="Search queries"
          />
          <ColumnsControl columns={usedListColumns} hidden={hiddenColumns} onToggle={toggleColumn} />
          {currentUser.hasPermission("create_query") && (
            <Link.Button type="primary" href="queries/new">
              <i className="fa fa-plus m-r-5" aria-hidden="true" />
              New query
            </Link.Button>
          )}
        </Header>

        <ViewTabs items={sidebarMenu} selected={controller.params.currentPage} ariaLabel="Query views" />

        <TagChips
          tagsUrl="api/queries/tags"
          onChange={controller.updateSelectedTags}
          aside={
            <React.Fragment>
              Sorted by <strong>{sortLabel}</strong>
            </React.Fragment>
          }
        />

        {controller.isLoaded && controller.isEmpty ? (
          <QueriesListEmptyState
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
                setSorting={controller.setSorting}
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
      </Shell>
    </div>
  );
}

QueriesList.propTypes = {
  controller: ControllerType.isRequired,
};

const QueriesListPage = itemsList(
  QueriesList,
  () =>
    new ResourceItemsSource({
      getResource({ params: { currentPage } }) {
        return {
          all: Query.query.bind(Query),
          my: Query.myQueries.bind(Query),
          favorites: Query.favorites.bind(Query),
          archive: Query.archive.bind(Query),
        }[currentPage];
      },
      getItemProcessor() {
        return (item) => new Query(item);
      },
    }),
  ({ ...props }) => new UrlStateStorage({ orderByField: props.orderByField ?? "created_at", orderByReverse: true })
);

routes.register(
  "Queries.List",
  routeWithUserSession({
    path: "/queries",
    title: "Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="all" />,
  })
);
routes.register(
  "Queries.Favorites",
  routeWithUserSession({
    path: "/queries/favorites",
    title: "Favorite Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="favorites" orderByField="starred_at" />,
  })
);
routes.register(
  "Queries.Archived",
  routeWithUserSession({
    path: "/queries/archive",
    title: "Archived Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="archive" />,
  })
);
routes.register(
  "Queries.My",
  routeWithUserSession({
    path: "/queries/my",
    title: "My Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="my" />,
  })
);

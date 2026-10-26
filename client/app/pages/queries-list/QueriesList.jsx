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
import {
  SearchControl,
  ColumnsControl,
  useHiddenColumns,
  visibleColumns,
} from "@/components/items-list/components/ListPageControls";
import ItemsTable, { Columns } from "@/components/items-list/components/ItemsTable";
import ListItemActions from "@/components/items-list/components/ListItemActions";

import { Query } from "@/services/query";
import { clientConfig, currentUser } from "@/services/auth";
import location from "@/services/location";
import routes from "@/services/routes";

import QueriesListEmptyState from "./QueriesListEmptyState";

import "./queries-list.css";

/*
  The four views, in whichever half of the list you are in.

  Saved queries and streaming ones are two halves of one set: a query is in
  exactly one of them, never both. So the views repeat inside each half rather
  than the halves repeating inside each view -- "my streaming queries" is
  Mine, reached from the streaming half, and there is one place it lives.

  The navbar carries the two halves and this carries the four views, which is
  why neither needs to carry the other's eight combinations.
*/
const VIEWS = [
  { key: "all", title: "All", icon: () => <Sidebar.MenuIcon icon="fa fa-code" /> },
  { key: "favorites", title: "Favorites", icon: () => <Sidebar.MenuIcon icon="fa fa-star" /> },
  { key: "my", title: "Mine", icon: () => <Sidebar.ProfileImage user={currentUser} /> },
  { key: "archive", title: "Archived", icon: () => <Sidebar.MenuIcon icon="fa fa-archive" /> },
];

export const STREAMING_BASE = "queries/streaming";

export function viewsFor(kind) {
  const base = kind === "streaming" ? STREAMING_BASE : "queries";
  return VIEWS.map((view) => ({
    ...view,
    href: view.key === "all" ? base : `${base}/${view.key}`,
  }));
}

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
        editUrl={item.getUrl(true)}
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
          <Link className="table-main-title" href={item.getUrl()}>
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
    // Both order on the latest result's own columns, which all_queries()
    // already joins and loads -- see the order map in handlers/queries.py.
    Columns.custom.sortable(
      (text, item) => <span className="queries-list-rows">{formatRowCount(item.row_count)}</span>,
      {
        title: "Rows",
        field: "row_count",
        width: 110,
        className: "text-right",
      }
    ),
    Columns.custom.sortable(
      (text, item) => <span className="queries-list-runtime">{formatRuntime(item.runtime)}</span>,
      {
        title: "Runtime",
        field: "runtime",
        width: 120,
        className: "text-right",
      }
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
  const streaming = controller.params.kind === "streaming";

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
  // allListColumns is what the Columns menu lists; usedListColumns is what the
  // table renders. They have to stay distinct, or hiding a column removes it
  // from the menu that would bring it back.
  const allListColumns = usedListColumns;
  usedListColumns = visibleColumns(allListColumns, hiddenColumns);
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
      row_count: "rows",
      runtime: "runtime",
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
    const noun = total === 1 ? "query" : "queries";
    if (streaming) {
      // Not "across N data sources" here: `useDataSourceNames` counts every
      // source this person can reach, and quoting that beside a count of
      // streaming queries would claim a breadth this half does not have.
      return `${total} streaming ${noun}`;
    }
    const parts = [`${total} ${noun}`];
    if (sourceCount > 0) {
      parts.push(`across ${sourceCount} data ${sourceCount === 1 ? "source" : "sources"}`);
    }
    return parts.join(" ");
  }, [controller.isLoaded, controller.totalItemsCount, sourceCount, streaming]);

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
          <SearchControl
            value={controller.searchTerm}
            onChange={updateSearch}
            placeholder="Search queries…"
            label="Search queries"
          />
          <ColumnsControl columns={allListColumns} hidden={hiddenColumns} onToggle={toggleColumn} />
          {currentUser.hasPermission("create_query") && (
            <Link.Button type="primary" href={streaming ? "streams/query" : "queries/new"}>
              <i className="fa fa-plus m-r-5" aria-hidden="true" />
              {streaming ? "New streaming query" : "New query"}
            </Link.Button>
          )}
        </Header>

        <ViewTabs
          items={viewsFor(controller.params.kind)}
          selected={controller.params.currentPage}
          ariaLabel="Query views"
        />

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
      getResource({ params: { currentPage, kind } }) {
        const resource = {
          all: Query.query.bind(Query),
          my: Query.myQueries.bind(Query),
          favorites: Query.favorites.bind(Query),
          archive: Query.archive.bind(Query),
        }[currentPage];
        // `kind` goes on every one of them, not only the unfiltered list. The
        // first version of this filtered All and left Mine and Favorites
        // showing both kinds, so the half somebody was looking at depended on
        // which tab they had clicked.
        return (request) => resource({ ...request, kind });
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
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="all" kind="saved" />,
  })
);
routes.register(
  "Queries.Favorites",
  routeWithUserSession({
    path: "/queries/favorites",
    title: "Favorite Queries",
    render: (pageProps) => (
      <QueriesListPage {...pageProps} currentPage="favorites" kind="saved" orderByField="starred_at" />
    ),
  })
);
routes.register(
  "Queries.Archived",
  routeWithUserSession({
    path: "/queries/archive",
    title: "Archived Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="archive" kind="saved" />,
  })
);
routes.register(
  "Queries.My",
  routeWithUserSession({
    path: "/queries/my",
    title: "My Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="my" kind="saved" />,
  })
);

/*
  The streaming half. The same page and the same four views, against the other
  half of the set.

  Under `/queries` rather than somewhere of its own, because a streaming query
  is a query: it is the same object, written in the same editor, and it earns
  no second URL space. These sort ahead of `/queries/:queryId` without being
  told to -- `routes.ts` puts paths with no parameters first.
*/
routes.register(
  "Queries.Streaming",
  routeWithUserSession({
    path: "/queries/streaming",
    title: "Streaming Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="all" kind="streaming" />,
  })
);
routes.register(
  "Queries.StreamingFavorites",
  routeWithUserSession({
    path: "/queries/streaming/favorites",
    title: "Favorite Streaming Queries",
    render: (pageProps) => (
      <QueriesListPage {...pageProps} currentPage="favorites" kind="streaming" orderByField="starred_at" />
    ),
  })
);
routes.register(
  "Queries.StreamingMy",
  routeWithUserSession({
    path: "/queries/streaming/my",
    title: "My Streaming Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="my" kind="streaming" />,
  })
);
routes.register(
  "Queries.StreamingArchived",
  routeWithUserSession({
    path: "/queries/streaming/archive",
    title: "Archived Streaming Queries",
    render: (pageProps) => <QueriesListPage {...pageProps} currentPage="archive" kind="streaming" />,
  })
);

import React from "react";
import lazyPage from "@/lib/lazyPage";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

// The tabs and the navbar link, which have to exist before any of these
// pages is fetched.
import "./settings.menu";

/*
  Everything reached from the settings menu, without the pages themselves.

  Imported at startup so the paths are known; the pages arrive when somebody
  opens one. These are the pages somebody visits when they are setting the
  install up or adding a colleague -- not what anybody does on the way to
  reading a dashboard, which is what the first download is for.

  One chunk, because they are one visit: whoever is adding a data source is
  usually about to put a group in front of it. They also share the dynamic
  form that draws a data source's and a destination's settings, so splitting
  them apart would duplicate it or strand it in the common chunk anyway.

  The Suspense boundary that covers the wait is in Router.
*/
const DataSourcesList = lazyPage(() => import(/* webpackChunkName: "settings" */ "./data-sources/DataSourcesList"));
const EditDataSource = lazyPage(() => import(/* webpackChunkName: "settings" */ "./data-sources/EditDataSource"));
const DestinationsList = lazyPage(() => import(/* webpackChunkName: "settings" */ "./destinations/DestinationsList"));
const EditDestination = lazyPage(() => import(/* webpackChunkName: "settings" */ "./destinations/EditDestination"));
const GroupsList = lazyPage(() => import(/* webpackChunkName: "settings" */ "./groups/GroupsList"));
const GroupMembers = lazyPage(() => import(/* webpackChunkName: "settings" */ "./groups/GroupMembers"));
const GroupDataSources = lazyPage(() => import(/* webpackChunkName: "settings" */ "./groups/GroupDataSources"));
const UsersList = lazyPage(() => import(/* webpackChunkName: "settings" */ "./users/UsersList"));
const UserProfile = lazyPage(() => import(/* webpackChunkName: "settings" */ "./users/UserProfile"));
const QuerySnippetsList = lazyPage(
  () => import(/* webpackChunkName: "settings" */ "./query-snippets/QuerySnippetsList")
);
const OrganizationSettings = lazyPage(
  () => import(/* webpackChunkName: "settings" */ "./settings/OrganizationSettings")
);

routes.register(
  "DataSources.List",
  routeWithUserSession({
    path: "/data_sources",
    title: "Data Sources",
    render: (pageProps) => <DataSourcesList {...pageProps} />,
  })
);
routes.register(
  "DataSources.New",
  routeWithUserSession({
    path: "/data_sources/new",
    title: "Data Sources",
    render: (pageProps) => <DataSourcesList {...pageProps} isNewDataSourcePage />,
  })
);
routes.register(
  "DataSources.Edit",
  routeWithUserSession({
    path: "/data_sources/:dataSourceId",
    title: "Data Sources",
    render: (pageProps) => <EditDataSource {...pageProps} />,
  })
);

routes.register(
  "AlertDestinations.List",
  routeWithUserSession({
    path: "/destinations",
    title: "Alert Destinations",
    render: (pageProps) => <DestinationsList {...pageProps} />,
  })
);
routes.register(
  "AlertDestinations.New",
  routeWithUserSession({
    path: "/destinations/new",
    title: "Alert Destinations",
    render: (pageProps) => <DestinationsList {...pageProps} isNewDestinationPage />,
  })
);
routes.register(
  "AlertDestinations.Edit",
  routeWithUserSession({
    path: "/destinations/:destinationId",
    title: "Alert Destinations",
    render: (pageProps) => <EditDestination {...pageProps} />,
  })
);

routes.register(
  "Groups.List",
  routeWithUserSession({
    path: "/groups",
    title: "Groups",
    render: (pageProps) => <GroupsList {...pageProps} currentPage="groups" />,
  })
);
routes.register(
  "Groups.Members",
  routeWithUserSession({
    path: "/groups/:groupId",
    title: "Group Members",
    render: (pageProps) => <GroupMembers {...pageProps} currentPage="users" />,
  })
);
routes.register(
  "Groups.DataSources",
  routeWithUserSession({
    path: "/groups/:groupId/data_sources",
    title: "Group Data Sources",
    render: (pageProps) => <GroupDataSources {...pageProps} currentPage="datasources" />,
  })
);

routes.register(
  "Users.New",
  routeWithUserSession({
    path: "/users/new",
    title: "Users",
    render: (pageProps) => <UsersList {...pageProps} currentPage="active" isNewUserPage />,
  })
);
routes.register(
  "Users.List",
  routeWithUserSession({
    path: "/users",
    title: "Users",
    render: (pageProps) => <UsersList {...pageProps} currentPage="active" />,
  })
);
routes.register(
  "Users.Pending",
  routeWithUserSession({
    path: "/users/pending",
    title: "Pending Invitations",
    render: (pageProps) => <UsersList {...pageProps} currentPage="pending" />,
  })
);
routes.register(
  "Users.Disabled",
  routeWithUserSession({
    path: "/users/disabled",
    title: "Disabled Users",
    render: (pageProps) => <UsersList {...pageProps} currentPage="disabled" />,
  })
);
routes.register(
  "Users.Account",
  routeWithUserSession({
    path: "/users/me",
    title: "Account",
    render: (pageProps) => <UserProfile {...pageProps} />,
  })
);
routes.register(
  "Users.ViewOrEdit",
  routeWithUserSession({
    path: "/users/:userId",
    title: "Users",
    render: (pageProps) => <UserProfile {...pageProps} />,
  })
);

routes.register(
  "QuerySnippets.List",
  routeWithUserSession({
    path: "/query_snippets",
    title: "Query Snippets",
    render: (pageProps) => <QuerySnippetsList {...pageProps} currentPage="query_snippets" />,
  })
);
routes.register(
  "QuerySnippets.NewOrEdit",
  routeWithUserSession({
    path: "/query_snippets/:querySnippetId",
    title: "Query Snippets",
    render: (pageProps) => <QuerySnippetsList {...pageProps} currentPage="query_snippets" isNewOrEditPage />,
  })
);

routes.register(
  "Settings.Organization",
  routeWithUserSession({
    path: "/settings/general",
    title: "General Settings",
    render: (pageProps) => <OrganizationSettings {...pageProps} />,
  })
);

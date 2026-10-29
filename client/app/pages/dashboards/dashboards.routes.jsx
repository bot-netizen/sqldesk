import React from "react";
import lazyPage from "@/lib/lazyPage";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import routes from "@/services/routes";

/*
  The dashboard routes, without the dashboard pages.

  Imported at startup so the paths are known; the pages arrive when somebody
  opens one. All four share a chunk because they share the grid --
  react-grid-layout and react-draggable, which are of no use anywhere else in
  the application and were in everybody's first download.

  The public and wall pages are in the same chunk on purpose. They are what an
  anonymous viewer loads, and giving them their own would mean a third
  variation of the same code to fetch and cache; sharing it means the one
  chunk is already in the cache for anyone who has opened a dashboard before.

  The Suspense boundary that covers the wait is in Router.
*/
const DashboardFolders = lazyPage(() => import(/* webpackChunkName: "dashboard" */ "./DashboardFolders"));
const DashboardPage = lazyPage(() => import(/* webpackChunkName: "dashboard" */ "./DashboardPage"));
const PublicDashboardPage = lazyPage(() => import(/* webpackChunkName: "dashboard" */ "./PublicDashboardPage"));
const WallDashboardPage = lazyPage(() => import(/* webpackChunkName: "dashboard" */ "./WallDashboardPage"));

// Kept for the links people have already sent each other.
routes.register(
  "Dashboards.LegacyViewOrEdit",
  routeWithUserSession({
    path: "/dashboard/:dashboardSlug",
    render: (pageProps) => <DashboardPage {...pageProps} />,
  })
);

routes.register(
  "Dashboards.ViewOrEdit",
  routeWithUserSession({
    path: "/dashboards/:dashboardId([^-]+)(-.*)?",
    render: (pageProps) => <DashboardPage {...pageProps} />,
  })
);

routes.register(
  "Dashboards.ViewShared",
  routeWithApiKeySession({
    path: "/public/dashboards/:token",
    render: (pageProps) => <PublicDashboardPage {...pageProps} />,
    getApiKey: (currentRoute) => currentRoute.routeParams.token,
  })
);

routes.register(
  "Dashboards.Wall",
  routeWithApiKeySession({
    path: "/wall/dashboards/:token",
    render: (pageProps) => <WallDashboardPage {...pageProps} />,
    getApiKey: (currentRoute) => currentRoute.routeParams.token,
  })
);

routes.register(
  "Dashboards.Folders",
  routeWithUserSession({
    path: "/dashboards/folders",
    title: "Dashboard folders",
    render: (pageProps) => <DashboardFolders {...pageProps} />,
  })
);

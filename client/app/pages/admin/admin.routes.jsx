import React from "react";
import lazyPage from "@/lib/lazyPage";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

/*
  The admin routes, without the admin pages.

  Imported at startup so the paths are known; the pages arrive when somebody
  opens one. Eight pages nobody visits in an ordinary day, and everybody was
  downloading all of them before drawing anything.

  One chunk, because somebody looking at system status is usually about to
  look at the queue as well.

  The Suspense boundary that covers the wait is in Router.
*/
const Overview = lazyPage(() => import(/* webpackChunkName: "admin" */ "./overview/Overview"));
const Jobs = lazyPage(() => import(/* webpackChunkName: "admin" */ "./Jobs"));
const RunningQueries = lazyPage(() => import(/* webpackChunkName: "admin" */ "./RunningQueries"));
const OutdatedQueries = lazyPage(() => import(/* webpackChunkName: "admin" */ "./OutdatedQueries"));
const SystemStatus = lazyPage(() => import(/* webpackChunkName: "admin" */ "./SystemStatus"));
const Catalog = lazyPage(() => import(/* webpackChunkName: "admin" */ "./Catalog"));
const McpHome = lazyPage(() => import(/* webpackChunkName: "admin" */ "../mcp/McpHome"));
const Storage = lazyPage(() => import(/* webpackChunkName: "admin" */ "./Storage"));
const Streams = lazyPage(() => import(/* webpackChunkName: "admin" */ "./Streams"));
const Audit = lazyPage(() => import(/* webpackChunkName: "admin" */ "./Audit"));

routes.register(
  "Admin.Streams",
  routeWithUserSession({
    path: "/admin/streams",
    title: "Streams",
    render: (pageProps) => <Streams {...pageProps} />,
  })
);

routes.register(
  "Admin.Audit",
  routeWithUserSession({
    path: "/admin/audit",
    title: "Audit",
    render: (pageProps) => <Audit {...pageProps} />,
  })
);

routes.register(
  "Admin.Storage",
  routeWithUserSession({
    path: "/admin/storage",
    title: "Storage",
    render: (pageProps) => <Storage {...pageProps} />,
  })
);

routes.register(
  "Admin.Overview",
  routeWithUserSession({
    path: "/admin/overview",
    title: "Admin Overview",
    render: (pageProps) => <Overview {...pageProps} />,
  })
);
routes.register(
  "Admin.RunningQueries",
  routeWithUserSession({
    path: "/admin/queries/running",
    title: "Running Queries",
    render: (pageProps) => <RunningQueries {...pageProps} />,
  })
);
routes.register(
  "Admin.Jobs",
  routeWithUserSession({
    path: "/admin/queries/jobs",
    title: "RQ Status",
    render: (pageProps) => <Jobs {...pageProps} />,
  })
);
routes.register(
  "Admin.OutdatedQueries",
  routeWithUserSession({
    path: "/admin/queries/outdated",
    title: "Outdated Queries",
    render: (pageProps) => <OutdatedQueries {...pageProps} currentPage="outdated_queries" />,
  })
);
routes.register(
  "Admin.SystemStatus",
  routeWithUserSession({
    path: "/admin/status",
    title: "System Status",
    render: (pageProps) => <SystemStatus {...pageProps} />,
  })
);
routes.register(
  "Admin.MCP",
  routeWithUserSession({
    path: "/admin/mcp",
    title: "MCP",
    render: (pageProps) => <McpHome {...pageProps} />,
  })
);
routes.register(
  "Catalog",
  routeWithUserSession({
    path: "/catalog",
    title: "Catalog",
    render: (pageProps) => <Catalog {...pageProps} />,
  })
);

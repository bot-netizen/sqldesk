import React from "react";
import lazyPage from "@/lib/lazyPage";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import location from "@/services/location";
import routes from "@/services/routes";

/*
  The query routes, without the query pages.

  This module is imported at startup so the paths are known; the pages arrive
  when somebody opens one. What that keeps out of everybody's first download:
  Ace, the largest single thing the application bundles, and `marked`, which
  only ever renders a description or a textbox.

  Three chunks rather than one, because these are three different visits. The
  editor is for the person writing SQL, the view is for the person reading the
  answer, and the embed is a single chart on somebody else's page -- usually
  for a reader who will never open either of the others.

  The Suspense boundary that covers the wait is in Router.
*/
const QuerySourcePage = lazyPage(() => import(/* webpackChunkName: "query-editor" */ "./QuerySource"));
const QueryViewPage = lazyPage(() => import(/* webpackChunkName: "query-view" */ "./QueryView"));
const VisualizationEmbed = lazyPage(() => import(/* webpackChunkName: "visualization-embed" */ "./VisualizationEmbed"));

routes.register(
  "Queries.New",
  routeWithUserSession({
    path: "/queries/new",
    render: (pageProps) => <QuerySourcePage {...pageProps} />,
    bodyClass: "fixed-layout",
  })
);
routes.register(
  "Queries.Edit",
  routeWithUserSession({
    path: "/queries/:queryId/source",
    render: (pageProps) => <QuerySourcePage {...pageProps} />,
    bodyClass: "fixed-layout",
  })
);
routes.register(
  "Queries.View",
  routeWithUserSession({
    path: "/queries/:queryId",
    render: (pageProps) => <QueryViewPage {...pageProps} />,
  })
);
routes.register(
  "Visualizations.ViewShared",
  routeWithApiKeySession({
    path: "/embed/query/:queryId/visualization/:visualizationId",
    render: (pageProps) => <VisualizationEmbed {...pageProps} />,
    getApiKey: () => location.search.api_key,
  })
);

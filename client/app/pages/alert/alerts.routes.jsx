import React from "react";
import lazyPage from "@/lib/lazyPage";
import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";
import MODES from "./modes";

/*
  The alert routes, without the alert pages.

  Imported at startup so the paths are known; the pages arrive when somebody
  opens one. The list and the alert itself share a chunk, because reaching one
  almost always means reaching the other.

  The Suspense boundary that covers the wait is in Router.
*/
const AlertsList = lazyPage(() => import(/* webpackChunkName: "alerts" */ "../alerts/AlertsList"));
const Alert = lazyPage(() => import(/* webpackChunkName: "alerts" */ "./Alert"));

routes.register(
  "Alerts.List",
  routeWithUserSession({
    path: "/alerts",
    title: "Alerts",
    render: (pageProps) => <AlertsList {...pageProps} currentPage="alerts" />,
  })
);
routes.register(
  "Alerts.New",
  routeWithUserSession({
    path: "/alerts/new",
    title: "New Alert",
    render: (pageProps) => <Alert {...pageProps} mode={MODES.NEW} />,
  })
);
routes.register(
  "Alerts.View",
  routeWithUserSession({
    path: "/alerts/:alertId",
    title: "Alert",
    render: (pageProps) => <Alert {...pageProps} mode={MODES.VIEW} />,
  })
);
routes.register(
  "Alerts.Edit",
  routeWithUserSession({
    path: "/alerts/:alertId/edit",
    title: "Alert",
    render: (pageProps) => <Alert {...pageProps} mode={MODES.EDIT} />,
  })
);

/*
  The notebook page, fetched when somebody opens one.

  The list is imported directly in `pages/index.js`, as the other landing
  pages are -- it is a place people go. The notebook itself carries the Ace
  editor, so it stays behind this and is downloaded on the way in. See
  `client/bundle-budget.js` for what that is worth.
*/
import React from "react";
import lazyPage from "@/lib/lazyPage";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routeWithApiKeySession from "@/components/ApplicationArea/routeWithApiKeySession";
import routes from "@/services/routes";

const NotebookPage = lazyPage(() => import(/* webpackChunkName: "notebook" */ "./Notebook"));
const PublicNotebookPage = lazyPage(() => import(/* webpackChunkName: "notebook" */ "./PublicNotebook"));

routes.register(
  "Notebooks.View",
  routeWithUserSession({
    path: "/notebooks/:notebookId",
    title: "Notebook",
    render: (pageProps) => <NotebookPage {...pageProps} />,
  })
);

/*
  A shared notebook. The token is the whole of a reader's credentials, the
  same way a public dashboard's is -- and it buys less here, because nothing
  is re-run for them.
*/
routes.register(
  "Notebooks.ViewShared",
  routeWithApiKeySession({
    path: "/public/notebooks/:token",
    title: "Notebook",
    render: (pageProps) => <PublicNotebookPage {...pageProps} />,
    getApiKey: (currentRoute) => currentRoute.routeParams.token,
  })
);

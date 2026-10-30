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
import routes from "@/services/routes";

const NotebookPage = lazyPage(() => import(/* webpackChunkName: "notebook" */ "./Notebook"));

routes.register(
  "Notebooks.View",
  routeWithUserSession({
    path: "/notebooks/:notebookId",
    title: "Notebook",
    render: (pageProps) => <NotebookPage {...pageProps} />,
  })
);

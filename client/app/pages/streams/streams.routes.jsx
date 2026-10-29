import React from "react";
import lazyPage from "@/lib/lazyPage";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import navigateTo from "@/components/ApplicationArea/navigateTo";
import routes from "@/services/routes";
import { currentUser } from "@/services/auth";

/*
  Streaming is a property of a query, not a place in the application.

  There is no Streams section any more. A streaming query is a query, listed
  with the others under `/queries/streaming`; a streaming dashboard is a
  dashboard, under `/dashboards/streaming`; which of a cluster's topics may be
  queried is a setting on the connection, under Settings. What is left here is
  the editor itself and the redirects for the URLs people have already sent
  each other.
*/
const QuerySourcePage = lazyPage(() => import(/* webpackChunkName: "query-editor" */ "../queries/QuerySource"));
const ManageTopics = lazyPage(() => import(/* webpackChunkName: "streams" */ "./ManageTopics"));

/*
  The stream editor *is* the query editor.

  A stream query written on a page of its own would get no visualizations, no
  parameters and no way onto a dashboard -- all of which hang off a query. So
  it is one, and this is the same page with `streamsOnly`: a picker offering
  only clusters, a button that says Start streaming, and no result ever stored.

  It keeps its own path because a streaming query has only this one page.
  Nothing it produces is stored, so there is no saved result for a view page to
  show -- `Query#getUrl` sends every link to one here.
*/
routes.register(
  "Streams.Query",
  routeWithUserSession({
    path: "/streams/query",
    title: "Query a stream",
    render: (pageProps) => <QuerySourcePage {...pageProps} streamsOnly />,
    bodyClass: "fixed-layout",
  })
);
routes.register(
  "Streams.QueryEdit",
  routeWithUserSession({
    path: "/streams/query/:queryId",
    title: "Query a stream",
    render: (pageProps) => <QuerySourcePage {...pageProps} streamsOnly />,
    bodyClass: "fixed-layout",
  })
);

/*
  Which topics are queryable, now a tab beside Data Sources -- it configures a
  connection, and it was the one thing in the old Streams menu that was not
  already somewhere else.
*/
routes.register(
  "Streams.Topics",
  routeWithUserSession({
    path: "/data_sources/streaming",
    title: "Streaming Data Sources",
    render: (pageProps) => <ManageTopics {...pageProps} />,
  })
);

/*
  Where the old paths went.

  Both were in a menu, so both are in somebody's history and in whatever
  anyone pasted into a chat. A redirect costs one route each; a 404 costs
  somebody the assumption that the page was removed.

  `/streams/running` has no destination of its own any more. What was consuming
  and how many slots were left is now part of Admin -> Streaming Queries, which
  also holds the budgets, and the count that mattered to everybody else -- "all
  the slots are in use" -- is on the editor's status strip, where it is read at
  the moment it bites.
*/
function Redirect({ to }) {
  React.useEffect(() => {
    navigateTo(to, true);
  }, [to]);
  return null;
}

routes.register(
  "Streams.TopicsMoved",
  routeWithUserSession({
    path: "/streams/topics",
    title: "Streaming Data Sources",
    render: () => <Redirect to="data_sources/streaming" />,
  })
);
routes.register(
  "Streams.RunningMoved",
  routeWithUserSession({
    path: "/streams/running",
    title: "Streaming Queries",
    // Two destinations, because the page had two audiences. An administrator
    // wants the one with the budgets on it; anybody else following an old
    // bookmark there would meet a permission error, and what they were
    // looking for is the list of streaming queries.
    render: () =>
      currentUser.hasPermission("super_admin") ? <Redirect to="admin/streams" /> : <Redirect to="queries/streaming" />,
  })
);

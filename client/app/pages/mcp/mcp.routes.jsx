import React from "react";
import lazyPage from "@/lib/lazyPage";

import routeWithUserSession from "@/components/ApplicationArea/routeWithUserSession";
import routes from "@/services/routes";

/*
  My MCP: how to connect a client, and what mine has been doing.

  Its own route rather than a tab under Admin, because it is for everybody who
  may connect a client -- and reachable only from the Admin menu, nobody
  without super_admin could find it at all.
*/
const MyMcp = lazyPage(() => import(/* webpackChunkName: "mcp" */ "./MyMcp"));

routes.register(
  "Mcp.Mine",
  routeWithUserSession({
    path: "/mcp/mine",
    title: "My MCP",
    render: (pageProps) => <MyMcp {...pageProps} />,
  })
);

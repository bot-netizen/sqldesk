import routes from "@/services/routes";

/*
  Every path the application answers, in one list.

  Splitting a page into a lazily loaded chunk means moving its
  `routes.register` call out of the page module and into a `*.routes.jsx` that
  is still imported at startup. Forget one and the page is simply gone: the
  router has no path for it, the SPA falls through to its not-found page, and
  nothing fails at build time or in any other test. This is the test that
  fails.

  Add a line when you add a page. Change one only when you mean to change a
  URL somebody may have bookmarked.
*/
const EXPECTED = [
  ["Home", "/"],
  ["Dashboards.List", "/dashboards"],
  ["Dashboards.Favorites", "/dashboards/favorites"],
  ["Dashboards.My", "/dashboards/my"],
  ["Dashboards.Archive", "/dashboards/archive"],
  ["Dashboards.LegacyViewOrEdit", "/dashboard/:dashboardSlug"],
  ["Dashboards.ViewOrEdit", "/dashboards/:dashboardId([^-]+)(-.*)?"],
  ["Dashboards.ViewShared", "/public/dashboards/:token"],
  ["Dashboards.Wall", "/wall/dashboards/:token"],
  ["Queries.List", "/queries"],
  ["Queries.Favorites", "/queries/favorites"],
  ["Queries.Archived", "/queries/archive"],
  ["Queries.My", "/queries/my"],
  // The streaming half of the same list. Under /queries because a streaming
  // query is a query -- see plan/0.7-nav.md.
  ["Queries.Streaming", "/queries/streaming"],
  ["Queries.StreamingFavorites", "/queries/streaming/favorites"],
  ["Queries.StreamingMy", "/queries/streaming/my"],
  ["Queries.StreamingArchived", "/queries/streaming/archive"],
  ["Queries.New", "/queries/new"],
  ["Queries.Edit", "/queries/:queryId/source"],
  ["Queries.View", "/queries/:queryId"],
  ["Visualizations.ViewShared", "/embed/query/:queryId/visualization/:visualizationId"],
  ["Alerts.List", "/alerts"],
  ["Alerts.New", "/alerts/new"],
  ["Alerts.Edit", "/alerts/:alertId/edit"],
  ["Alerts.View", "/alerts/:alertId"],
  ["AlertDestinations.List", "/destinations"],
  ["AlertDestinations.New", "/destinations/new"],
  ["AlertDestinations.Edit", "/destinations/:destinationId"],
  ["DataSources.List", "/data_sources"],
  ["DataSources.New", "/data_sources/new"],
  ["DataSources.Edit", "/data_sources/:dataSourceId"],
  ["QuerySnippets.List", "/query_snippets"],
  ["QuerySnippets.NewOrEdit", "/query_snippets/:querySnippetId"],
  ["Groups.List", "/groups"],
  ["Groups.Members", "/groups/:groupId"],
  ["Groups.DataSources", "/groups/:groupId/data_sources"],
  ["Users.List", "/users"],
  ["Users.New", "/users/new"],
  ["Users.Disabled", "/users/disabled"],
  ["Users.Pending", "/users/pending"],
  ["Users.Account", "/users/me"],
  ["Users.ViewOrEdit", "/users/:userId"],
  ["Settings.Organization", "/settings/general"],
  ["Catalog", "/catalog"],
  ["Admin.Overview", "/admin/overview"],
  ["Admin.RunningQueries", "/admin/queries/running"],
  ["Admin.Jobs", "/admin/queries/jobs"],
  ["Admin.OutdatedQueries", "/admin/queries/outdated"],
  ["Admin.SystemStatus", "/admin/status"],
  ["Admin.MCP", "/admin/mcp"],
  ["Admin.Storage", "/admin/storage"],
  ["Admin.Streams", "/admin/streams"],
  ["Mcp.Mine", "/mcp/mine"],
  ["Dashboards.Streaming", "/dashboards/streaming"],
  ["Dashboards.StreamingFavorites", "/dashboards/streaming/favorites"],
  ["Dashboards.StreamingArchive", "/dashboards/streaming/archive"],
  ["Dashboards.StreamingMy", "/dashboards/streaming/my"],
  ["Dashboards.Folders", "/dashboards/folders"],
  ["Dashboards.Folder", "/dashboards/folder/:folderId"],
  // Which topics may be queried: a tab beside Data Sources, because it
  // configures a connection.
  ["Streams.Topics", "/data_sources/streaming"],
  ["Streams.Query", "/streams/query"],
  ["Streams.QueryEdit", "/streams/query/:queryId"],
  // The two paths the old Streams menu had. Both were in somebody's history,
  // so both still answer -- see streams.routes.jsx.
  ["Streams.TopicsMoved", "/streams/topics"],
  ["Streams.RunningMoved", "/streams/running"],
];

describe("the routes the pages register", () => {
  beforeAll(() => {
    // The one place that imports every page, which is what registers them.
    require("@/pages/index");
  });

  test("are all there, and there are no others", () => {
    const registered = routes.items.map((item) => `${item.id} ${item.path}`);
    const expected = EXPECTED.map(([id, path]) => `${id} ${path}`);

    // Compared as sets: the order is the router's own (fewest parameters
    // first, then longest path), not something a page decides.
    expect(new Set(registered)).toEqual(new Set(expected));
  });

  test("and every one of them can render", () => {
    // A lazily loaded page whose import was mistyped registers fine and
    // renders nothing.
    for (const item of routes.items) {
      expect(typeof item.render).toBe("function");
    }
  });
});

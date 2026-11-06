/*
  Where the router learns what paths exist.

  The pages somebody lands on are imported here directly, so they are in the
  first download. Everything else is behind a `*.routes.jsx`, which registers
  the paths and fetches the page when somebody goes to it -- see
  `client/bundle-budget.js` for what that is worth, and
  `services/routes.registration.test.js` for the list of paths this has to
  produce either way.
*/
import "./home/Home";
import "./dashboards/DashboardList";
import "./queries-list/QueriesList";
import "./notebooks/NotebookList";

import "./dashboards/dashboards.routes";
import "./queries/queries.routes";
import "./alert/alerts.routes";
import "./admin/admin.routes";
import "./mcp/mcp.routes";
import "./notebooks/notebooks.routes";
import "./streams/streams.routes";
import "./settings.routes";

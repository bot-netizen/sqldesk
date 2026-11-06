import { clientConfig } from "@/services/auth";

/*
  The Admin section, in one list.

  Two things draw it -- the dropdown in the navbar and the tab strip on the
  pages themselves -- and they had drifted: Storage and Streams existed as
  pages and routes for days with no way to reach either, because the two menus
  were written out by hand in different files and nobody updated both.

  Each tab carries a `description` as well as a title. An administrator opening
  this section for the first time is usually there because something is wrong,
  which is the worst moment to be guessing which of seven pages holds the
  number they want. The dropdown shows the first line of it; the page shows all
  of it under the tabs.
*/
const TABS = [
  {
    key: "overview",
    title: "Overview",
    path: "admin/overview",
    description:
      "Where the headroom is going: Postgres connections, Redis memory, how many workers are busy and how deep the queues are. " +
      "Also who has been running the most queries in the last hour, and how much of that was served from cache. " +
      "Start here when the instance feels slow and you do not yet know why.",
  },
  {
    key: "system_status",
    title: "System Status",
    path: "admin/status",
    description:
      "The server's report on itself: version and uptime, when the query manager last made a pass, the depth of each queue and the size of each table. " +
      "These are the figures to quote when something has to be escalated.",
  },
  {
    key: "jobs",
    title: "RQ Status",
    path: "admin/queries/jobs",
    description:
      "The job queues behind every execution, scheduled refresh, alert and email, worker by worker. " +
      "Shows what each worker has in hand and what is waiting for one to come free. " +
      "A queue that is growing while workers sit idle means the jobs are going somewhere nobody is listening.",
  },
  {
    key: "storage",
    title: "Storage Status",
    path: "admin/storage",
    description:
      "What SQLDesk is holding and what happens to it when: cached query results, uploaded files, and how much of its quota each organisation has left. " +
      "A cached result costs a re-query to lose; an uploaded file is the only copy there is. " +
      "Both clean-ups can be started from here rather than waiting for their slot.",
  },
  {
    key: "running_queries",
    title: "Running Queries",
    path: "admin/queries/running",
    description:
      "Every query the workers have in flight right now, who asked for it, against which data source, and how long it has been going. " +
      "A scheduled refresh shows as the scheduler rather than a person, because nobody is waiting for it. " +
      "Any of them can be stopped from here, and stopping one is recorded.",
  },
  {
    key: "streams",
    title: "Streaming Queries",
    path: "admin/streams",
    description:
      "Every Kafka topic being consumed, how fast events are arriving and -- the column this page exists for -- why a quiet one is quiet. " +
      "Paused, broken and genuinely empty look identical on a chart and are three different problems. " +
      "The row budget and the events-per-second ceiling for each topic are set here.",
  },
  {
    key: "audit",
    title: "Audit",
    path: "admin/audit",
    description:
      "Where the month went, rather than what is happening now: executions by person, by data source and by query, over any window up to a year. " +
      "Overview answers the same question about the last hour and is read while something is wrong; this is read afterwards. " +
      "A scheduled refresh is not counted — these are the things people asked for.",
  },
  {
    key: "outdated_queries",
    title: "Outdated Queries",
    path: "admin/queries/outdated",
    description:
      "Scheduled queries whose next run is already overdue, with the schedule they were meant to keep. " +
      "A handful is ordinary. A long list means the workers are not keeping up with the schedules people have set.",
  },
  {
    key: "mcp",
    title: "MCP",
    path: "admin/mcp",
    description:
      "Which agents and clients have connected, what they asked for and which tokens they still hold. " +
      "Never the questions people put to them or the SQL that came back -- only the calls themselves.",
    isAvailable: () => !!clientConfig.mcpEnabled,
  },
];

/** The tabs this install shows, in order. */
export function adminTabs() {
  return TABS.filter((tab) => !tab.isAvailable || tab.isAvailable());
}

export function adminTab(key) {
  return TABS.find((tab) => tab.key === key) || null;
}

export default TABS;

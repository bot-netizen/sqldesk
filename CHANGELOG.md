# Changelog

## 0.6.0-rc.2

The second release candidate: an audit of rc.1 before anyone depends on it.
Most of what changed is things rc.1 got wrong.

**MCP gives no more than the editor gives.** In rc.1 a user in a view-only
group could run any SQL through `/mcp` that the editor refuses them, and a
user without the `execute_query` permission could run SQL at all; `run_query`
and `explain_query` now check what the editor checks, paused sources
included. With no data source named, `find_context` and `expand_table`
searched the whole organization's catalog, and `find_dashboards` listed every
dashboard in it; both are now limited to what the user can see. And
`explain_query` put `EXPLAIN` in front of whatever it was given, so
`ANALYZE DELETE FROM t` deleted.

**MCP only reads.** `run_query` and `explain_query` accept one statement that
reads -- `SELECT`, `WITH`, `SHOW`, `DESCRIBE` -- and refuse a write anywhere in
it, a `DELETE` inside a `WITH` and `SELECT ... INTO` included. This stops a
model doing damage by accident; the database account's grants are still what
stop it on purpose, so give each data source a read-only user.

**MCP keeps within the web server's time.** One request waits at most ten
seconds less than gunicorn's timeout, across all its calls, rather than 120
seconds a call against a 60-second timeout. Batches hold at most ten
messages, SQL at most 100,000 characters. `/mcp` also worked only with CSRF
checks off -- the development compose file turns them on -- and is now exempt,
since an API key is not a session.

**File uploads are confined to their own folder.** The DuckDB behind file
uploads let SQL read any file the worker could -- another organization's
uploads, `/etc/passwd` -- write over the application, and install extensions.
Each upload source's SQL now reads its own uploads and nothing else, with the
setting locked so SQL cannot switch it back.

**Dashboard export is a one-page report.** Past twelve widgets or one page
tall, Export says "Too big to export" straight away. What fits exports in
under a second: the capture copies the styles that decide how a widget looks
rather than all 560, and draws the widgets at once. Export of rc.1 failed
outright on any dashboard with a map, on any dashboard of real size, and on
the sankey.

**Core and add-ons.** The core is the server, worker, scheduler, Postgres and
Redis. MCP & Catalog and Rendering (pictures in alert emails) are add-ons:
compose profiles `mcp` and `rendering`, and `mcp.enabled` and
`rendering.enabled` in the chart. The renderer is published as
`ghcr.io/bot-netizen/sqldesk-screenshots`, sends the API key only to SQLDesk,
and no longer runs as root.

**Removed: the model-provider layer.** SQLDesk calls no model; MCP serves
tools to the client's. `manage ai configure/status/test/disable/forget`,
`/api/ai/status`, `/api/ai/test`, `/api/queries/optimize`, the
`SQLDESK_AI_PROVIDER` family and the chart's `ai.*` values are gone, and a
migration drops the `ai_providers` table. `SQLDESK_FEATURE_AI` stays: it is
the MCP switch.

**Also fixed.**
- The Helm chart had no volume for uploads, so an upload succeeded and every
  query on it failed. It has one now, shared by the server and every worker.
- A worker being stopped was killed ten seconds in, mid-query, whatever the
  grace period said. It now finishes the query, for up to five minutes.
- The chart's first-run note ran `users create_root` without a password, which
  makes an account nobody can sign in to. It points at the setup page.
- A harvest that got an empty schema -- a failed read, usually -- deleted the
  catalog and the descriptions people had written. It now keeps them.
- `manage ai import` matched tables by name across every data source, so
  staging's description could land on production's table. The folder a file
  is in now says which source it is about. Export no longer reads the join
  list once per table.
- The MCP audit is pruned after 90 days (`SQLDESK_MCP_AUDIT_RETENTION_DAYS`),
  and a script trying keys can no longer fill it: refusals past 60 a minute
  from one address are still refused, just not each written down.
- Every in-app help drawer was blank: the content security policy lost its
  `frame-src` for the docs site in the rename.
- The compose file's default image was still 0.5.0.

**Upgrading from rc.1.** Run `manage db upgrade`: it adds nothing and drops
`ai_providers`. If you set `ai.enabled` on the chart, set `mcp.enabled`
instead; the chart now refuses to render with `ai.*` set rather than silently
ignoring it. With Compose, move `SQLDESK_FEATURE_AI` into `.env` if it is not
there, and add `COMPOSE_PROFILES=mcp` for MCP's own worker.

**Upgrading from 0.5.** Set `SQLDESK_IMAGE`, `pull`, `run --rm server manage db
upgrade`, then `up -d`. MCP stays off until `SQLDESK_FEATURE_AI=true`.

## 0.6.0-rc.1

SQLDesk answers questions about your warehouse over the Model Context
Protocol, and learns what to say from the queries people have already written.

**MCP.** One endpoint, JSON-RPC over streamable HTTP, authenticated with a
SQLDesk API key -- the one on your profile page. Every call runs as that user
and sees only the data sources that user can read; there is no service account
and no way to configure one, because a tool server with more access than its
user is a way to launder permissions. Eight tools, in the order they are meant
to be used: `find_queries` and `find_dashboards` to look for work that already
exists, `find_context`, `expand_table` and `list_data_sources` to understand
the data, `check_sql` for the shape and `explain_query` for the cost, then
`run_query`, which returns at most 1000 rows -- the editor's own ceiling,
reused rather than invented -- and runs on a worker like any other query, so
it appears in Admin under the name of whoever's key it was and can be
cancelled there. Every request leaves an audit row, including the refused
ones. The handshake negotiates the protocol version rather than announcing
its own regardless.

**A catalog, built from what you already have.** You have no data hub, and
most installs never will. But the warehouse states its own structure, several
engines carry `COMMENT ON` text nobody was reading, and every dashboard is
built on SQL somebody wrote and saved. Harvesting reads all three: what exists,
what it is called, which tables anyone actually uses, which columns anyone
selects, which joins anyone writes. It runs on a schedule now rather than
waiting for somebody to remember a command, and learns only from queries that
have *run* in the last week -- measured by when a query last ran rather than
when it was last edited, because a dashboard refreshed every morning and
untouched for a year is the most important thing in the warehouse.

**Measures are proposed, never assumed.** `SUM(amount) AS gross_revenue` in a
saved query is a person naming a metric, and the alias they chose becomes its
name. Admin -> Catalog shows each proposal with how many distinct queries
define it that way, and it reaches a model only once somebody agrees it --
with a Deny beside Agree, because a proposal nobody can reject comes back
every night until the list stops being read. Aggregates across a join and
arithmetic around an aggregate are refused rather than guessed: a metric
definition that is merely plausible is worse than none.

**The semantic layer lives in git.** `manage ai export` writes it as
cube-shaped YAML, one file per table, into a directory you can commit from;
`manage ai import` reads it back on deploy. There is also a Download button,
because the person writing the descriptions is often not the person with
access to a container. SQLDesk never speaks to git itself -- no deploy key, no
conflict handling -- and importing never creates anything the warehouse has
not stated, nor lets a file redefine what a measure computes.

**Documentation.** Twelve guide pages covering concepts, architecture,
connectors, queries, visualizations, dashboards, alerts, MCP, administration
and deploying, with the in-app help links pointing into them. A Helm chart for
Kubernetes, with NodePort for minikube.

## 0.5.0

A dashboard that costs less to look at, and more room on it to say things.

**Dashboards stopped doing the same work several times.** A query behind five
widgets was fetched and parsed five times; now one request serves all of them,
keyed on the query, its parameter values and the auto limit, so widgets share
a result only when they are genuinely asking for the same thing. The server
side closed the matching gap: the query lock now covers *writing* the result,
not just running it. A dashboard loads its widgets in one call instead of
walking them one at a time, an index was added for the lookup `get_latest`
actually does, and a widget that is off screen waits its turn before drawing.
Live dashboards stopped retrying a failing query every ten seconds.

**The chrome gave the charts their space back.** A widget's header carries one
name -- the visualization's, not the query's repeated after it -- in 44px
instead of 47, and the row under it 36. The top of a chart no longer reserves
room for a title it does not draw, Y labels thin out only when they would
crowd, and the grid moved to twenty-four columns and 25px rows so a widget can
take a third of the width. Filters left their full-width band: on a dashboard
they are one button in the header with a count, and a widget's own filter sits
on its title's row. Editing the layout puts both back in a row, because that
is where they are dragged into order.

**Textboxes became somewhere to write.** The markdown library was from 2013
and refused tables, fenced code, task lists, strikethrough, bare URLs and raw
HTML; all of those work now, sanitised by DOMPurify, with a type scale that
does not render a heading at 36px. A textbox can turn its tile off, so a
section heading divides a page instead of sitting on it in a white card, and
it can be aligned left, centre or right. The editor has Write and Preview
tabs, and the preview carries the style and alignment chosen underneath it.

**Eight more chart types** -- the whole of the roadmap's second tier -- drawn
by ECharts, with a matrix test that puts every visualization through every
option it offers. A reading tile for the gauge, a visualization can say what
it is of, and `numeral` was retired for one formatter that respects the
organization's own separators.

**An Admin section**: what is running, who is running it, and what is about to
run out -- with the ability to cancel a query and to run the cleanup job now.
A running query is no longer everyone's to cancel, which it was.

**Alerts can carry a picture.** Up to five dashboards or queries render into
the email, from a headless browser in its own optional container -- the
published image does not grow by a byte, and the feature is off unless
`SQLDESK_SCREENSHOT_URL` is set.

**A dashboard for a wall**: `/wall/dashboards/<token>`, refreshed by the
server once for everyone looking.

Dashboards are saved when you say so -- dragging a widget changes nothing
until Done Editing. Sorting and searching arrived on the list pages. 1,144
lines nothing reached were deleted, and 336 type suppressions went with two
declaration fixes.

## 0.5.0-rc.1

The release candidate for 0.5, and what 0.5.0 is apart from one thing.

**Dashboards built before 0.5 were going to come out shrunken.** The grid went
from twelve columns and 50px rows to twenty-four and 25px, and every number
the *frontend* refers to doubled with it -- but the numbers already in the
database did not. A widget saved six columns wide was half a screen and would
have become a quarter of one. 0.5.0 adds the migration that doubles them,
which upstream shipped when they went from six columns to twelve and which
this change had been missing.

If you ran rc.1, its data is already on the new grid: stamp past
`c9f1a67b3d84` rather than letting it run.

## 0.4.0

Dashboards you watch rather than read.

A dashboard can be made **live**: the server refreshes it every 30 seconds to
5 minutes, once for everyone looking, and only while somebody has it open. The
visualizations that go on a wall came with it -- a gauge, a stat with a
sparkline and a target, progress and bullet bars, a status grid, table cells
that colour and carry data bars, reference lines and bands, and a rolling
window so a live chart slides instead of rescaling. Charts are drawn by Apache
ECharts now rather than Plotly, which is what made the animation between one
result and the next possible, and cut the production JavaScript from 9.6 MB to
4.3 MB.

`latest` and `0.4` point here. Published as
`ghcr.io/bot-netizen/sqldesk:0.4.0`.

The three release candidates below carry the detail of what changed and why;
this release is rc.3 as rebuilt on 19 September, with no further changes.

### Upgrading

**From 0.3.2:**

- **Run `manage db upgrade`.** 0.4 adds a `live` column to `dashboards`:

  ```bash
  docker compose -f compose.prod.yaml run --rm server manage db upgrade
  ```

- Restart the scheduler as well as the server and worker (`up -d` does all
  three). Live dashboards are refreshed by a periodic job that a scheduler
  running the old image never starts.
- **Dashboard auto-refresh now starts at ten minutes.** The 1 and 5 minute
  choices are gone, and a link carrying `?refresh=60` refreshes every ten
  instead. Anything that needs to move faster is what live mode is for.
  `SQLDESK_DASHBOARD_REFRESH_INTERVALS` still sets the menu; values under ten
  minutes are ignored.
- **Nobody can turn live mode on until an admin grants it.** Open a group and
  tick *Members can make dashboards live*. Admins always can.
- Saved charts keep their appearance. A chart saved as `custom` -- which held
  JavaScript written against the Plotly API -- is drawn as a column chart,
  because there is no longer anything to run that code.

**From any 0.4 release candidate:** pull and `up -d`. No migration.

**Going back to 0.3.2:** `manage db downgrade a8e1d0c4b726` while still on the
0.4 image, then switch the image back.

## 0.4.0-rc.3

The third release candidate for 0.4, and the one to try: rc.1 and rc.2
looked right but did not refresh. Published as
`ghcr.io/bot-netizen/sqldesk:0.4.0-rc.3` and marked as a pre-release;
`latest` stays on 0.3.2.

### Rebuilt, 19 September 2026

The rc.3 tag and image were moved rather than a fourth candidate cut, so an
instance that pulls `0.4.0-rc.3` now gets everything below as well. Pull
again and `up -d`; still no migration.

- **A table's data bar collapsed after the first refresh.** The bar is sized
  against its cell, and it was being wrapped in the highlight that marks a
  changed value -- which shrinks to fit the number. From the first change
  onwards the bar measured the digits rather than the column, leaving a
  sliver behind the number. It looked right until then, because the highlight
  only appears once something has changed.
- **A live dashboard retried a failing query every ten seconds.** A refresh
  that works leaves a result behind and the next one waits out the interval;
  a refresh that fails leaves nothing, so the check found nothing on every
  tick of the ten-second scheduler -- about thirty times the intended rate on
  a five-minute dashboard, against a data source already in trouble. Live now
  remembers that it asked, for as long as a result would have stayed fresh.
  That also closed the one way a viewer could make the server run something
  repeatedly: leaving a tab and coming back. Live refreshes moved to the
  scheduled queue, so a wall screen no longer competes with queries somebody
  is waiting on.
- **A counter counting rows against a target took the widget down** when the
  result was empty. It shows no target now, the same as a counter with no
  target column.
- **Dashboards are read in one go.** Showing one walked every widget
  separately -- its visualization, query, author, data source and groups --
  and re-read the viewer's permissions per widget. On a real dashboard that
  was 30 statements to serialize and 34 for every live viewer's check-in,
  four times a minute each; it is now 4 and 8, and serializing no longer
  grows with the number of widgets.
- **Large results are taken in faster.** The test for "is this string a
  date?" ran a full date parse on every string in every cell before the
  cheap check that rules most of them out.
- Internal tidying that changes nothing you can see: two type declarations
  fixed, which removed 336 suppressions across the visualization editors;
  1,144 lines nothing reached deleted; `moment` and `lodash` declared as the
  dependencies they always were.

### Upgrading

- From rc.1 or rc.2: pull and `up -d`. No migration.
- From 0.3.2: as before -- run `manage db upgrade`.

### Fixed

- **No dashboard refresh showed anything new.** Since rc.1, Refresh, the
  auto-refresh timer and live dashboards all quietly reused the result the
  page already had. The browser's query code reuses a known result whenever
  the caller says how old a result it will accept, and rc.1 started saying
  so everywhere: a minute for Refresh, half an interval for auto-refresh,
  "any" for live. Refresh then announced "Already up to date" about a result
  an hour old, and a live dashboard sat on "refreshing…" while the server
  made a new result every 30 seconds. A known result is now reused only when
  no age is given -- a page loading; every other refresh asks the server.
- **A live dashboard never drew the results it fetched.** The grid re-renders
  a widget only when certain things about it change, and a live reload
  changed none of them, so new data arrived and stayed off screen until the
  page was reloaded.
- **Line, area and scatter charts over time were drawn on a number line.**
  An x axis left on automatic asked "are these numbers?" before "are these
  dates?", and a timestamp is also a number -- its epoch milliseconds -- so
  every time series was squeezed against the right-hand edge of an axis
  running from zero. Bars escaped it, being categorical. Dates are now
  checked first, including dates that arrive as text.
- **Time axes were labelled "1789852380000".** They are labelled with times.
- **Legend placement did nothing.** The editor has always offered Right, and
  always drew the legend below. Right now runs it down the side, with the
  plot giving up the width the names need and pies moving over. Charts saved
  with the default get their legend on the right.
- **The home page checklist never ticked off.** It read counts fetched once,
  when the app opened, so a data source or dashboard made since still showed
  as a step to do until the page was reloaded.
- **Widget headers said everything twice** when a visualization was named
  after its query ("Requests per second - Requests per second").
- **Gauge ticks carried the reading's decimals**: "20.0 40.0 60.0" round a
  0-100 dial.

### Changed

- **Refresh always runs the queries**, on the dashboard and on each widget.
  The one-minute reuse rc.1 added, and its "Already up to date" notice, are
  gone: pressing Refresh means run it now.
- **Live widgets say what is coming**: "next in 18s", "refreshing…" while the
  new result is on its way, or "updated 2m ago" while paused -- one of them,
  never two. The countdown runs on the server's clock.
- **Coming back to a live dashboard catches up at once.** The first viewer to
  arrive at a dashboard nobody was watching has the server refresh what is
  stale there and then, and the tab checks in every few seconds until the new
  results are on screen, instead of showing old numbers for up to 25 seconds.
- **Visualizations move at a pace you can see.** A dashboard opening grows
  from nothing over a second -- bars rising, gauges sweeping up, Stat numbers
  counting from zero -- and new data moves from the old values to the new
  over a second. They were 300 and 450 milliseconds, over before anyone
  looked up.
- **Hovering a chart says which x you are on**: labelled on the axis under
  the pointer, and as a heading on the tooltip.

### Development

- The image builds in about four minutes instead of 35. The arm64 image was
  being built under emulation on an amd64 runner; each platform now builds
  on a machine of its own architecture, and the frontend -- the same
  JavaScript for both -- is built once.

## 0.4.0-rc.2

The second release candidate for 0.4: what testing rc.1 found
([milestone](https://github.com/bot-netizen/sqldesk/milestone/1)). Like
rc.1, it is published as `ghcr.io/bot-netizen/sqldesk:0.4.0-rc.2` and marked
as a pre-release; `latest` stays on 0.3.2.

### Upgrading

- From rc.1: pull and `up -d`. No migration.
- From 0.3.2: as for rc.1 -- run `manage db upgrade`.
- The scheduler logs "Removing … from schedule" and "Scheduling …" for each
  periodic job the first time it starts. That is the jobs being re-registered
  with records that no longer expire, and happens once.

### Fixed

- **Live dashboards stopped refreshing after the computer slept**
  ([#1](https://github.com/bot-netizen/sqldesk/issues/1)), and so did
  scheduled query refreshes, result cleanup and lock cleanup. Each periodic
  job keeps a record in Redis, and after every run that record expired after
  a set time -- 60 seconds for live dashboards, 10 minutes for scheduled
  queries. A laptop asleep or a Docker VM paused for longer came back to find
  the record gone, and the scheduler then dropped the job for good; nothing
  put it back until the scheduler was restarted. Periodic jobs now keep their
  record, and the scheduler checks every 30 seconds that each one is still
  scheduled, puts back any that are not and logs a warning when it has to --
  which also brings them back after a Redis restart. The weakness came from
  Redash, whose scheduled-query job has the same 10-minute record.

### Changed

- **A live widget says when it refreshes next** -- "next in 18s", then
  "refreshing…" while the new result is on its way. Paused, it says how old
  the result is instead ("updated 2m ago"). One or the other, never both. The
  countdown runs on the server's clock, so a browser that is a few minutes out
  still counts right.
- **Coming back to a live dashboard catches up at once.** The first viewer to
  arrive at a dashboard nobody was watching -- usually someone returning to a
  hidden tab -- has the server refresh whatever is stale on the spot, and the
  tab checks in every 3 seconds until the new results are on screen, instead
  of showing old numbers for up to 25 seconds. Going live, choosing a new
  interval and Resume do the same.
- **Refresh says when there was nothing to do.** On an ordinary dashboard,
  Refresh reuses anything under a minute old; when that brings back exactly
  the results already shown, it now says "Already up to date" instead of
  looking like a button that did nothing.

## 0.4.0-rc.1

**A release candidate, for testing.** It is tagged and published as
`ghcr.io/bot-netizen/sqldesk:0.4.0-rc.1`, but `latest` and `0.4` still point
at 0.3.2, and it is marked as a pre-release on GitHub. Try it on a copy of your
data before trusting it with the real thing.

This is the first part of the visualization roadmap
([sqldesk site → Roadmap](https://bot-netizen.github.io/sqldesk/roadmap.html)):
charts for dashboards that are watched rather than read, and a live mode for
the dashboards on the wall.

### Upgrading

- **Run `manage db upgrade`.** This release adds a `live` column to
  `dashboards`:

  ```bash
  docker compose -f compose.prod.yaml run --rm server manage db upgrade
  ```

- Restart the scheduler along with the server and worker (`up -d` does all
  three). Live dashboards are refreshed by a new periodic job, and a scheduler
  still running the old image never starts it.
- **Dashboard auto-refresh now starts at ten minutes.** The 1 and 5 minute
  choices are gone, and a link carrying `?refresh=60` or `?refresh=300`
  refreshes every ten. Anything that genuinely needs to move faster than that
  is what live mode is for. `SQLDESK_DASHBOARD_REFRESH_INTERVALS` still sets
  the menu, and values under ten minutes are ignored.
- Nobody can turn live mode on until an admin grants it: open a group, and tick
  **Members can make dashboards live**. Admins can always do it.

### Added

- **Live dashboards.** Pick 30 seconds, 1, 2 or 5 minutes from a dashboard's
  menu and the server refreshes it from then on. A live dashboard shows a
  **Live** badge, hides its Refresh buttons and parameter inputs, and only
  shows what the server made -- a room full of screens runs each query once
  per interval, not once per screen. It runs only while somebody is looking:
  every open tab checks in, a hidden or closed tab says it is leaving, and a
  dashboard nobody has watched for 45 seconds stops refreshing until someone
  opens it again. Pause and Resume sit next to the badge, say who paused it,
  and every viewer sees the change within a check-in. Public links to a live
  dashboard stay live. Parameters use their saved values: a live dashboard is
  one result, shared.
- **Gauge.** One value against a range, as a needle, a ring or a half ring,
  with coloured threshold bands and an optional target marker. The value
  eases to its new reading instead of jumping.
- **Progress Bars.** One bar per row against that row's own target, drawn as
  a bullet (a thin bar over threshold bands, with a tick at the target) or a
  filled bar.
- **Status Grid.** One tile per row, coloured by its state -- `ok`, `warn`,
  `down` and the usual spellings are understood without setup, and the list is
  yours to edit. Sort by severity or name. A tile whose state changed since
  the last refresh is outlined, so a wall screen shows what just moved.
- **Stat** (the Counter, grown up). A sparkline under the number, a change
  against a target, the previous row, _n_ rows back or the previous refresh,
  and a colour from thresholds. Numbers format as plain, compact (`27.2K`),
  percent, currency, bytes or duration, with prefix and suffix. Existing
  counters keep their old formatting until you switch them.
- **Tables** gain conditional formatting (rules or a colour scale, on the text
  or the cell), data bars, value mappings, a **Sparkline** column type for a
  column holding a list of numbers, and ▲▼ marks on cells that changed since the
  last refresh.
- **Charts** gain reference lines (a constant, a vertical line at an x value,
  or a series' average, min or max), shaded bands, a rolling window (the last
  _n_ points or the last _n_ minutes) and zoom (a slider, or scroll to zoom).
- One set of value options behind all of the above: number format, thresholds
  and value mappings work the same in Gauge, Progress Bars, Status Grid, Stat
  and Tables, and colours are named -- good, warning, serious, critical --
  rather than picked, so they follow the theme.
- Charts are exposed to screen readers with a generated description.

### Changed

- **The Refresh buttons reuse anything from the last minute.** Several people
  pressing Refresh on the same dashboard run each query once. Changing a
  parameter still always runs the query.
- Dashboard auto-refresh reuses a result younger than its interval, so two
  tabs on the same dashboard no longer run everything twice.

## 0.3.2

Fixes from using it.

### Fixed

- **The Filter field on the Queries and Dashboards lists closed as you clicked
  into it**, so there was no way to type a search. antd closes a dropdown when
  its overlay is clicked, which is right for a menu and wrong for a panel built
  around a text field.
- **Hiding a column on those lists lost it for good.** The column disappeared
  from the Columns menu as well as the table, leaving nothing to tick to bring
  it back. The page was filtering its column list and then handing the filtered
  list to the menu.
- **The results table header stood roughly twice the height of its rows** --
  63px against 34px. antd moves a sortable column's padding off the header cell
  and onto a wrapper inside it, so setting the cell's padding added to that
  rather than replacing it and the header carried it twice.

### Changed

- **One table density everywhere.** The compact rows added in 0.2.0 applied to
  the query editor only, so the same table looked one way there and another in
  a dashboard widget or an alert. It is now a property of the table itself.
- **The Queries and Dashboards lists match.** They were still on the roomier
  58px row from before the result tables were tightened; they are 42px now,
  with the same cell padding and the same 13px body text. A list row stays a
  little taller because it carries a star, a name and its tags where a data row
  carries text.
- **The home page is titled "My Desk"**, and each counter opens that user's own
  list rather than everybody's.
- **Dashboards lost the schedule control** added in 0.2.0. The refresh-rate
  button beside it already did what people wanted, and two adjacent controls
  both answering "how often" was the problem. Existing dashboard schedules stop
  running; nothing else changes.
- **One Share button on dashboards** instead of two side by side. Public link,
  export as PDF and export as image are one menu.
- **Refresh intervals gain 3 hours, 6 hours and daily**, and lose the crontab
  entry. A query already set to an expression keeps running on it and still
  shows it -- the server never stopped understanding them -- but the menu no
  longer offers new ones.
- The query editor has the same rounded corners as everything else on the page.

## 0.3.1

Fixes uploading a file, which 0.3.0 made worse rather than better.

0.3.0 added a shared volume at `/app/uploads` so the worker could read what
the server wrote. It also stopped shipping `uploads/` inside the image -- and
Docker takes a volume's ownership from the directory already in the image.
With no such directory it created the mount point owned by root, and the
container does not run as root, so saving an upload failed outright. Before
0.3.0 the upload at least succeeded and only the query failed.

The image now creates `/app/uploads` owned by the user the container runs as.

**Anyone on 0.3.0 should move to this.** No migration, no configuration
change: pull and restart.

## 0.3.0

**Tealdash is now SQLDesk.** The project moved to
[bot-netizen/sqldesk](https://github.com/bot-netizen/sqldesk) and the image to
`ghcr.io/bot-netizen/sqldesk`. Nothing else about it changed.

### Upgrading

- The image is `ghcr.io/bot-netizen/sqldesk` now. Pull from there.
- Environment variables are `SQLDESK_*`. **Your existing `.env` keeps working
  without edits** -- `TEALDASH_*` and `REDASH_*` are both still read, with the
  most recent name winning.
- Run `manage db upgrade`. 0.2.0 added a column to `dashboards` and this
  release moves saved chart palettes to the new name; charts work either way,
  because both former names resolve to the default palette.
- SAML group attributes: `SQLDeskGroups` is read first, then
  `TealdashGroups`, then `RedashGroups`. No identity-provider change needed.

### Fixed

- **Uploading a file and then querying it failed in Docker.** The server saves
  an upload to its own container, and the worker -- a different container --
  is what runs the query, so DuckDB looked for the file where it did not
  exist. `compose.prod.yaml` gave those services no volumes at all. They now
  share one, which also keeps uploads across a `compose up` that recreates a
  container; before, they lived in the container's writable layer and went
  with it. Development was unaffected, because `compose.yaml` bind-mounts the
  working tree into every service.
- An image built from a working copy no longer carries that copy's `.env` or
  its uploaded files. `.dockerignore` listed only build noise, so `COPY . /app`
  took both. Images published from CI were never affected -- it builds from a
  clean checkout, where neither file is tracked.

## 0.2.0

Scheduling, a home page that says something, and an editor that gives the
results room.

### Scheduling

- **A refresh schedule can be a crontab expression.** The menu offers five
  intervals, 5 to 60 minutes; anything else is written as `0 9 * * 1-5`, which
  says "09:00 on weekdays" in one field where the old dialog needed four. That
  dialog is gone, and with it the end-date option -- schedules that already
  carry one are still honoured, but nothing sets a new one.
- **Dashboards can carry a schedule too.** A dashboard has no data of its own,
  so its schedule refreshes the queries behind its widgets, and it runs with
  nobody watching. The refresh-rate button beside it is unchanged: that is a
  timer in your browser, for a display somebody is looking at.
- Nothing records when a dashboard last refreshed. Each query is measured
  against when it last ran, so there is no second clock to drift, and a query
  on two scheduled dashboards refreshes on whichever slot comes first.
- An expression the server cannot read is refused when it is saved. Stored, it
  would have failed later in the scheduler, which responds by disabling the
  schedule -- the query would have stopped refreshing with nobody told.

### Home

- Once the setup steps are done, the home page shows your own numbers: queries,
  dashboards, scheduled queries, alerts, and what your cached results occupy on
  disk. Below that, favourites on one side and your scheduled queries on the
  other, slowest first, with data source, runtime, result size and schedule.
- Inviting people is no longer a setup step. It is not something you do before
  the tool is useful, and being a step kept the welcome panel on screen
  permanently for anyone working alone.

### Query editor

- **Roughly six more rows of results before you scroll.** The editor sizes
  itself to the query instead of being a fixed 300px; result tables were inset
  31px on every side by two stacked paddings and are now inset once; the
  description moved to the left rail; rows, controls and tabs are scaled to
  each other rather than to three different defaults.
- **A running query reports itself in the footer corner**, where "Refreshed 20
  minutes ago" already sits, instead of an alert that appeared above the
  results and pushed the visualization down the page on every single run.
- The SQL editor uses the same monospace font as the rest of the application.
  It had been falling back to whatever the browser calls `monospace`.

## 0.1.1

A fix release. **The install documented in 0.1.0 could not work.**

### Fixed

- `compose.prod.yaml` mounted the Postgres volume at `/var/lib/postgresql/data`,
  the layout Postgres used before version 18. Postgres 18 keeps its data in a
  major-version subdirectory, refuses to start when it finds a mount that is not
  `PGDATA`, and restart-loops — so the healthcheck never passed and
  `run --rm server create_db`, the first documented command, could never
  succeed. Nothing caught it because the development compose file gives Postgres
  no volume at all.
- The daily version check crashed on every fresh install: it read the
  organization before one existed, which is the whole window between
  `create_db` and the setup form. It also gathered usage counts — six aggregates
  across every table — before checking whether there was anywhere to send them,
  which on a default install there is not.
- The footer reported `Version: 0.1.0 (dev)`. The frontend version was never
  stamped at build time, so it always differed from the real one. The backend
  version is the only one that can differ between deployments, and it is now the
  only one shown.

### Changed

- The usage-data prompt said data would be shared with "the SQLDesk team".
  There is no such collection: the counts only ever go to an endpoint the
  operator sets in `SQLDESK_VERSION_CHECK_URL`, which is empty by default. The
  wording now says what the setting does, and the prompt appears only when an
  endpoint is configured — otherwise it was asking about something that could
  not happen.

### Documentation

- macOS reserves port 5000 for AirPlay Receiver, so `up` fails with "address
  already in use" on the likeliest machine for a first try. Said in the compose
  file, `.env.example`, the README and the site.

### Housekeeping

- Removed configuration for services this project does not use, inherited from
  upstream: Restyled, Codecov, the request-info and weekly-digest bots, a
  CircleCI packaging script, and two release scripts superseded by GitHub
  Actions.
- `pytest.ini` and `.coveragerc` moved into `pyproject.toml`; `CONTRIBUTING.md`
  and `SECURITY.md` into `.github/`; `worker.conf` into `bin/`. The repository
  root holds 26 files rather than 33.

## 0.1.0

First release of SQLDesk.

SQLDesk is a fork of Redash. This changelog starts here; the inherited work is
described in [NOTICE](NOTICE), and the upstream project keeps its own history.
What follows is what is different in this release.

### Visualizations

- Charts render with [Apache ECharts](https://echarts.apache.org/) instead of
  Plotly, and **animate between values**. When a number changes the chart moves
  from the old value to the new one rather than being thrown away and redrawn.
  Column, line, area, scatter, pie, bubble, heatmap and box all render this way,
  as do error bars.
- Box plots compute their five statistics here rather than in the charting
  library, using the same linear quantile definition as before, so existing
  boxes do not shift.
- The counter visualization counts up to its new value.
- Every bar on a bar chart gets its own axis label, tilting when they would
  collide instead of dropping the ones that do not fit.
- Bar charts start at zero. An axis that starts elsewhere draws one bar four
  times another for a difference of a few percent.
- The horizontal toggle turns the chart on its side. It previously only
  relabelled the ticks.
- Sankey, sunburst and the deprecated boxplot were rewritten on ECharts,
  retiring d3 version 3 — a dependency last current in 2016.
- Custom JavaScript charts are gone. They were written against the Plotly API
  and there is nothing left to run them; a chart saved as `custom` opens as a
  column chart that can be edited into something else.

### Performance

- **Production JavaScript is 4.2 MB, down from 9.6 MB.** Plotly and its map
  stack accounted for over half the bundle, and the visualization library was
  being published as CommonJS, which meant nothing in it could be tree-shaken.
- Cached query results are served without re-encoding the stored JSON
  (547 ms → 99 ms on a 27 MB result).
- The cache lookup has a composite index (66.7 ms → 0.064 ms).
- DuckDB connections are reused per process rather than reopened per query.

### Project

- Relicensed under the Apache License 2.0. The inherited BSD 2-Clause notice is
  preserved verbatim in [LICENSE.redash](LICENSE.redash).
- Telemetry removed. Nothing is reported anywhere; version checking is off
  unless `SQLDESK_VERSION_CHECK_URL` is set to an endpoint you control.
- Configuration reads `SQLDESK_*` environment variables, with `REDASH_*`
  honoured as a fallback so existing deployments keep working.
- Published as a container image at `ghcr.io/bot-netizen/sqldesk`.

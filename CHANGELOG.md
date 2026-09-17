# Changelog

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

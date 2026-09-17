# Changelog

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

- The usage-data prompt said data would be shared with "the Tealdash team".
  There is no such collection: the counts only ever go to an endpoint the
  operator sets in `TEALDASH_VERSION_CHECK_URL`, which is empty by default. The
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

First release of Tealdash.

Tealdash is a fork of Redash. This changelog starts here; the inherited work is
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
  unless `TEALDASH_VERSION_CHECK_URL` is set to an endpoint you control.
- Configuration reads `TEALDASH_*` environment variables, with `REDASH_*`
  honoured as a fallback so existing deployments keep working.
- Published as a container image at `ghcr.io/tdot-labs/tealdash`.

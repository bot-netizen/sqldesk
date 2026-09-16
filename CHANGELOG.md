# Changelog

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

---
title: SQLDesk, and what it is for
date: 2026-09-26
summary: >-
  A self-hosted place to query your data and build dashboards on it — and, in 0.6, an MCP server
  that answers questions from a catalog built out of the SQL your team has already written. What the fork
  changed, how the catalog is built, why metrics are proposed rather than assumed, and the one thing it
  cannot do yet.
lede: >-
  A self-hosted place to query your data and build dashboards on it. In 0.6 it also answers
  questions over the Model Context Protocol — from a catalog built out of the SQL your team has already
  written, on hardware you control.
description: >-
  A self-hosted place to query your data and build dashboards on it — and, in 0.6, an MCP server over
  your warehouse, on hardware you control.
next:
  label: The MCP guide
  link: /guide/mcp.html
---

SQLDesk is a fork of [Redash](https://github.com/getredash/redash), Apache 2.0, and it does what
Redash does: connect to a data source, write SQL, turn the result into a chart, put the chart on a dashboard
somebody actually looks at. Thirty-five-odd connectors, Python and React, runs in Docker or on Kubernetes.
Viewers are free, because there is nobody to charge you for them.

That part is not new and is not the interesting part. This is a first post, so here is what the fork is
*for*, and what 0.6 adds.

## What the fork changed

Mostly it made the thing cheaper to look at. A dashboard with five widgets behind one query used to fetch
and parse that query five times; now one request serves all of them. The charts moved off Plotly to Apache
ECharts, which is smaller and keeps up with data that changes while you are watching it. Dashboards can refresh
on the server rather than in a tab somebody left open — and only while a visible tab is actually
watching, so nobody pays for a dashboard on a television in an empty room.

Each of those is measured rather than asserted, and the numbers are in the commit that made
the change.

## 0.6: your warehouse, answerable

The new thing is an [MCP](https://modelcontextprotocol.io) server. Point a client at
`/mcp` with a SQLDesk API key and it gets eight tools, in the order they are meant to be used:

- `find_queries` and `find_dashboards` — look for work that already exists,
  because most questions have been answered before;
- `find_context`, `expand_table`, `list_data_sources` — understand
  the data;
- `check_sql` for the shape and `explain_query` for the cost;
- `run_query`, which runs one read — never a write — returns at most 1000 rows,
  the same ceiling a person clicking Execute gets, and runs on a worker like any other query.

The ordering is the point. A model that reads the plan before it runs the query, and looks for an existing
query before it writes a new one, behaves more like a careful colleague and less like a bill.

## The catalog is built from what you already have

Most teams have no data hub, no OpenMetadata, nobody filling in a modelling tool. But the warehouse states
its own structure, several engines carry `COMMENT ON` text nobody was reading, and every dashboard
in the building is built on SQL somebody wrote and saved.

So SQLDesk harvests all three. What exists, from the schema. What matters, from the query log: which tables
anyone uses, which columns anyone selects, which joins anyone writes. A warehouse with three thousand tables
and no usage data can only be ranked alphabetically; one with usage data can put `orders` in front
of `orders_backup_2019` without being told.

It learns only from queries that have *run* recently, measured by when they last ran rather than when
they were last edited. A dashboard that refreshes every morning and has not been touched in a year is the most
important thing in the warehouse. A query somebody tweaked last week and never ran again is not.

## Metrics are proposed, never assumed

`SUM(amount) AS gross_revenue` in a saved query is a person naming a metric. That is the one part
of a semantic layer that can be found rather than asked for, so SQLDesk finds them — the alias the author
chose becomes the name, and the count is how many distinct queries define it that way. Four teams agreeing
independently is a different proposition from one person trying it once.

Nothing is believed. Proposals sit under Admin → Catalog with **Agree** and
**Deny** beside them, and only an agreed definition reaches a model. A metric definition that is
merely plausible is worse than none, because the wrong revenue number is still a revenue number.

Two things it will not guess: an aggregate across a join is not attributed to either table, and
`SUM(price * qty)` is left for a person to write. Neither can be checked against a column.

## What people write down, you keep in git

Descriptions and agreed metrics export as cube-shaped YAML, one file per table, into a directory you can
commit from:

```
# in the server container, where manage is /app/manage.py
manage ai export /app/semantic   # catalog → files, then commit them
manage ai import /app/semantic   # files → catalog, on deploy
```

SQLDesk never speaks to git itself — no deploy key, no conflict handling — because the pipeline
you already have does that better, and a change to what a metric means should be a pull request rather than a
row somebody altered. Importing never creates anything the warehouse has not stated, and a file cannot redefine
what a measure computes: it may agree with a definition and describe it, not claim one nobody writes.

## On your own hardware

The Helm chart runs it on your cluster, with MCP behind a switch and, if you want it, a queue of its own so a
model exploring cannot slow down a dashboard somebody is watching:

```
mcp:
  enabled: true
  queue: mcp
  worker:
    enabled: true
```

Every call runs as the user whose API key it is and sees only the data sources that user can read; running
SQL needs the same full access the query editor does. There is no service account and no way to configure one,
because a tool server with more access than its user is a way to launder permissions. Every request leaves an audit row — who, when, which tool, the outcome, how long
— including the refused ones, which are the rows an audit exists for.

If your company signs in through SSO, that covers the browser and not this: MCP uses each person's own API
key, so the audit names a person rather than an integration.

## One honest limitation

This works today with a **local** MCP client — Claude Code on a laptop, on your VPN,
reaching your internal ingress:

```
claude mcp add --transport http sqldesk https://sqldesk.internal.example.com/mcp \
  --header "Authorization: Bearer <your API key>"
```

It does *not* work as a hosted connector in a chat app. Those are fetched by the vendor's servers
rather than by your device, so the endpoint would have to be reachable from the public internet — which
is the opposite of why you deployed it internally — and SQLDesk authenticates with an API key rather
than the OAuth flow those connectors expect. Both are solvable and neither is solved. If you deploy this
expecting to add it from a phone, you will be disappointed; deploy it expecting your engineers and analysts to
use it from their own machines, and it works now.

## Where it is

0.6 is at release candidate, published as
`ghcr.io/bot-netizen/sqldesk:0.6.0-rc.2`, and being validated. The
[MCP guide](/guide/mcp.html) covers setup, the tools, the audit and what it costs your warehouse;
[Deploying](/guide/deploying.html) covers Docker and Kubernetes.

If you try it, the thing worth telling us is what the catalog got wrong about your warehouse. That is the
part that only real data can test.

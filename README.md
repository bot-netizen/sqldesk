<div align="center">
  <h1>Tealdash</h1>
  <p><strong>One place for everything you do with data.</strong></p>
  <p>Query 35+ data sources, build dashboards, and share what you find — self-hosted, no per-seat pricing.</p>
  <p>
    <a href="https://tdot-labs.github.io/tealdash/">Website</a> &middot;
    <a href="CHANGELOG.md">Changelog</a> &middot;
    <a href="https://github.com/tdot-labs/tealdash/discussions">Discussions</a>
  </p>
  <p>
    <a href="https://github.com/tdot-labs/tealdash/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/tdot-labs/tealdash/actions/workflows/ci.yml/badge.svg"></a>
    <a href="LICENSE"><img alt="Licence" src="https://img.shields.io/badge/licence-Apache%202.0-blue"></a>
    <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-teal">
  </p>
</div>

---

Tealdash lets anyone connect to a data source, write a query, turn the result into a
visualization, and put it on a dashboard other people can use. SQL users get a fast
editor with schema browsing and scheduling; everyone else gets dashboards and alerts
built on that work.

It runs on your own infrastructure. Viewers are unlimited because there is nobody to
charge you for them.

## Features

- **Query editor** — schema browser, autocomplete, query formatting, parameters, scheduled refresh
- **35+ data sources** — PostgreSQL, MySQL, BigQuery, Snowflake, Databricks, Athena, ClickHouse, MongoDB, DuckDB and many more
- **File upload** — drop a CSV or Parquet file and query it with SQL, backed by DuckDB
- **Visualizations** — charts, tables, cohorts, funnels, maps, pivot tables
- **Dashboards** — arrange visualizations, filter across them, export to PDF or image
- **Alerts** — trigger on a query result and notify Slack, email, PagerDuty, webhooks and more
- **Permissions** — groups, per-data-source access, view-only roles, shareable public links

## Running it

Published images are at `ghcr.io/tdot-labs/tealdash`, built for amd64 and arm64.
Tealdash needs Postgres and Redis alongside it, and `compose.prod.yaml` wires up
all three:

```bash
cp .env.example .env
```

Fill in the three secrets it asks for, then:

```bash
docker compose -f compose.prod.yaml run --rm server create_db
docker compose -f compose.prod.yaml up -d
```

Tealdash comes up on `http://localhost:5000`. Set `TEALDASH_IMAGE` in `.env` to
pin a different tag.

> Keep `TEALDASH_SECRET_KEY`. Data-source passwords are encrypted with it, so
> changing it makes every stored credential unreadable.

## Developing

`compose.yaml` is the development setup — it builds from source and mounts the
working tree, so edits are picked up without rebuilding.

```bash
make env               # generate .env with generated secrets
make compose_build     # build the images
make create_database   # create the schema (once)
make up                # start redis, postgres, server, worker, scheduler
```

That comes up on `http://localhost:5001`.

For the frontend:

```bash
pnpm install --frozen-lockfile
pnpm start             # webpack dev server + viz-lib watch
```

## Configuration

Tealdash reads `TEALDASH_*` environment variables. If you are migrating an existing
Redash deployment, your `REDASH_*` variables are still honoured as a fallback — an
explicitly set `TEALDASH_*` always wins.

Tealdash does not phone home. Version checking is off unless you set
`TEALDASH_VERSION_CHECK_URL` to an endpoint you control.

## Tests

```bash
make test              # backend + frontend + lint
pnpm test              # frontend only (type-check + jest)
docker compose run --rm server tests   # backend only
```

## Architecture

- **Backend** — `tealdash/` (Python 3.13, Flask, SQLAlchemy, RQ)
- **Frontend** — `client/` (React, TypeScript, Webpack, Ant Design)
- **Visualizations** — `viz-lib/` (`@tealdash/viz`, its own pnpm workspace package)

Workers, the scheduler and the web server are separate processes, so changes to task
logic need the worker restarted, not just the server.

## Licence

Tealdash is licensed under the [Apache License 2.0](LICENSE).

Tealdash is a fork of [Redash](https://github.com/getredash/redash), which is
copyright (c) 2013-2020 Arik Fraimovich and licensed under BSD 2-Clause. That licence
and its copyright notice are preserved in [LICENSE.redash](LICENSE.redash) and apply
to all inherited code. See [NOTICE](NOTICE) for full attribution.

Tealdash is an independent project. It is not affiliated with, endorsed by, or
supported by the Redash project or its contributors.

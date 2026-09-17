# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tealdash is a web app for querying data sources (35+ SQL/NoSQL backends) and building visualizations/dashboards on top of the results. It's a Flask/Python backend + React/TypeScript frontend, with RQ (Redis Queue) workers handling query execution, scheduling, and alerts asynchronously.

- Backend: `tealdash/` (Python 3.13, Flask, SQLAlchemy 1.3, RQ)
- Frontend app: `client/` (React 16, TypeScript/JS, Webpack, Ant Design)
- Visualization library: `viz-lib/` (separate pnpm workspace package, `@tealdash/viz`, published as a dependency of `client/`)
- Tests: `tests/` (backend, pytest), `client/app/**/*.test.js` and `client/cypress/` (frontend)

## Development environment

Full local dev is Docker-based (Postgres + Redis + server + worker containers via `compose.yaml`). There is no lightweight non-Docker path for the backend — commands below assume Docker Compose unless noted.

```bash
make env              # generate .env with TEALDASH_COOKIE_SECRET / TEALDASH_SECRET_KEY
make compose_build     # build docker images
make create_database   # create Postgres schema (run once)
make up                # bring up redis/postgres/server/worker/scheduler
make down              # stop everything
make bash              # shell into the server container
make redis-cli          # redis-cli against the compose redis
```

Frontend dev server (build steps run outside Docker via pnpm):

```bash
pnpm install --frozen-lockfile
pnpm start             # webpack-dev-server + viz-lib watch, in parallel
pnpm run watch         # watch app + viz without the dev server
pnpm run build         # production build (cleans, builds viz-lib, then webpack)
```

## Commands

### Backend (Python)

```bash
make backend-unit-tests           # brings up postgres/redis, creates test DB, runs full suite in docker
docker compose run --rm server tests                     # run full suite directly (after `make up` + `make test_db`)
docker compose run --rm server tests tests/test_models.py            # single file
docker compose run --rm server tests tests/test_models.py::TestQuery::test_something  # single test
docker compose run --rm server tests --junitxml=junit.xml --cov=tealdash tests/  # matches CI invocation

make lint                          # ruff check . && black --check . --diff
ruff check .                       # lint only
black .                            # auto-format (CI runs `black --check .`)
make format                        # pre-commit run --all-files (black + ruff hooks)
```

Test DB connection is controlled by `TEALDASH_DATABASE_URL` (set to `postgresql://postgres@postgres/tests` inside the `tests` entrypoint in `bin/docker-entrypoint`). Query runner availability can be inspected with `docker compose run --rm server manage ds list_types`.

### Frontend (JS/TS)

```bash
pnpm run type-check                # tsc --noEmit against client/tsconfig.json
pnpm run jest                      # jest only (TZ=Africa/Khartoum, uses enzyme + jsdom)
pnpm test                          # type-check then jest (matches CI "frontend-unit-tests")
pnpm test:watch                     # jest --watch
npx jest client/app/path/to/Thing.test.js          # single frontend test file
npx jest -t "test name substring"                   # single test by name
pnpm --filter @tealdash/viz test     # run viz-lib's own jest suite
pnpm run lint                      # eslint over ./client (.js/.jsx/.ts/.tsx)
pnpm run lint:fix
pnpm run prettier                  # format client/app, client/cypress, viz-lib/src
```

Jest config lives inline in `package.json` (rootDir `./client`, module alias `@/` → `client/app/`, css/less mocked via `identity-obj-proxy`). `client/app/__tests__/` itself is excluded from the jest run (`testPathIgnorePatterns`) — it holds setup files (`enzyme_setup.js`, `mocks.js`), not specs.

### E2E (Cypress)

```bash
make frontend-unit-tests           # pnpm install (skips cypress/puppeteer binaries) + pnpm test
node client/cypress/cypress.js     # cypress runner wrapper used by `pnpm run cypress`
```
E2E specs live under `client/cypress/integration/`, driven against `.ci/compose.cypress.yaml` in CI.

### Combined

```bash
make test              # backend-unit-tests + frontend-unit-tests + lint
```

## Architecture

### Backend request flow

- `tealdash/app.py` defines the `Tealdash` Flask app class and `create_app()`, which wires together: `authentication`, `handlers`, `limiter` (flask-limiter), `mail`, `migrate` (flask-migrate), `security` (flask-talisman), `tasks`, webpack asset config, and DB init — in that order. Start here to see how subsystems attach to the app.
- `tealdash/handlers/` holds Flask-RESTful resources, one module per domain (`queries.py`, `dashboards.py`, `data_sources.py`, `alerts.py`, `users.py`, `embed.py`, `organization.py`, `admin.py`, etc.). `handlers/api.py` is the central `Api` object all resources register onto; `handlers/base.py` defines the shared `routes` Blueprint and base resource behavior (pagination, ordering, `BaseResource`/permission checks). `handlers/__init__.py.init_app()` is the aggregation point — new handler modules must be imported there to be mounted.
- `tealdash/permissions.py` implements the role/permission system (`require_permission`, `require_admin_or_owner`, view-only vs edit access) used as decorators across handlers.
- `tealdash/models/` is the SQLAlchemy layer, split into `models/__init__.py` (the bulk of domain models: `Query`, `DataSource`, `Dashboard`, `Widget`, `Visualization`, `Alert`, `Event`, etc.), `models/users.py` (`User`, `Group`, `ApiUser`, `AccessPermission`), `models/organizations.py`, `models/parameterized_query.py` (Mustache-based query parameterization, `ParameterizedQuery`), `models/changes.py` (change/version tracking mixin), `models/types.py` (custom SQLAlchemy column types, encrypted config), `models/base.py` (the `db` instance, generic FK support). Note: this is `tealdash/models/` (a package), not a single `models.py`.
- `tealdash/serializers/` converts model instances to API-facing dicts (kept separate from the models themselves).

### Query runners (data source plugin system)

- `tealdash/query_runner/__init__.py` defines the plugin contract: `BaseQueryRunner` (override `run_query`, `configuration_schema`, etc.), `BaseHTTPQueryRunner`, `BaseSQLQueryRunner`, the `TYPE_*` column-type constants, and `register()`/`get_query_runner()`/`import_query_runners()`. Each file in `tealdash/query_runner/` (one per data source, e.g. `pg.py`, `mysql.py`, `big_query.py`, `athena.py`, `mongodb.py`) implements one or more runner classes and calls `register(MyRunner)` at import time.
- Which runners are actually loaded is controlled by `settings.QUERY_RUNNERS` (see `tealdash/settings/`) and driven by `import_query_runners()` at startup (`tealdash/__init__.py`). Optional data-source SDKs live in the `all_ds` dependency group in `pyproject.toml` — a runner's dependency being uninstalled doesn't break the app, just makes that runner unavailable (`manage ds list_types` shows what's active).
- `tealdash/destinations/` is the analogous plugin system for alert destinations (Slack, email, webhooks, etc.), registered the same way (`import_destinations`).

### Async execution (RQ)

- `tealdash/worker.py` sets up the RQ `job` decorator (with StatsD instrumentation) and default queues: `periodic`, `emails`, `default` (operational) and `scheduled_queries`, `queries`, `schemas` (query-related).
- `tealdash/tasks/` holds the actual jobs: `tasks/queries/execution.py` (running a query against a data source, called both for ad-hoc "run now" and scheduled runs), `tasks/queries/maintenance.py` (scheduling/refresh logic), `tasks/alerts.py` (alert evaluation after query execution), `tasks/schedule.py` (periodic job registration via rq-scheduler), `tasks/general.py` (misc jobs like emails).
- Workers, the scheduler, and the web server are separate processes (see `bin/run` / `bin/worker.conf` / `compose.yaml`) — a change to task logic requires restarting the worker container, not just the server.

### Frontend structure

- `client/app/pages/` — one directory per route/feature (e.g. `queries/QuerySource.jsx` is the query editor, `dashboards/`, `alerts/`, `data-sources/`). `client/app/components/` holds shared/reusable UI. `client/app/services/` holds API clients and cross-cutting concerns (`query.js`, `dashboard.js`, `auth.js`, `data-source.js` — these wrap the REST API defined by `tealdash/handlers/`).
- `client/app/index.js` bootstraps the SPA; routing table is `client/app/services/routes.ts`.
- Visualizations are NOT in `client/` — they live in the separate `viz-lib/` package (`viz-lib/src/visualizations/`), built independently (`build:viz`/`watch:viz` scripts) and consumed by `client` as the `@tealdash/viz` workspace dependency (see `pnpm-workspace.yaml`). When changing chart/visualization behavior, look in `viz-lib/`, not `client/app`.
- Webpack config (`webpack.config.js`) and the babel-based build for `viz-lib` are separate pipelines — `pnpm run build` runs viz-lib's build first, then webpack over `client/`.

### Migrations

- `migrations/` contains Alembic/flask-migrate migrations for the SQLAlchemy models. Model changes generally need a corresponding migration; `tests/test_migrations.py` exercises them.

### Settings / configuration

- `tealdash/settings/__init__.py` centralizes environment-variable-driven configuration (feature flags, queue names, integrations). `tealdash/settings/dynamic_settings.py` and `organization.py` handle settings resolved at runtime/per-org rather than from env vars.

## Code style

- Python: formatted with **Black** (line length 119, see `[tool.black]` in `pyproject.toml`), linted with **ruff** (`select = ["C9", "E", "F", "W", "I001", "UP004"]`, max cyclomatic complexity 15, `migrations/` excluded from both).
- JavaScript/TypeScript: formatted with **Prettier**, linted with **ESLint** (`client/.eslintrc.js`). Pre-commit hooks (`.pre-commit-config.yaml`) run black/ruff automatically if installed.

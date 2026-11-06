# How things are done here

## Releases are named

The release title is **`SQLDesk <x.y.z> — <Name>`**, and the name is the
release's one idea. A release that does a little of everything is a release
nobody can describe.

| | |
|---|---|
| 0.4 | Live |
| 0.5 | Interface |
| 0.6 | MCP |
| 0.7 | Kafka Streams |
| 0.8 | Notebooks |

## Release notes are headings and bullets

Never paragraphs. The changelog is where prose belongs; the release page is
read by somebody deciding whether to upgrade. `##` per theme, a **bold
lead-in** on each bullet, and always three closing sections: **Images**,
**Upgrading from \<previous\>**, and **Verified before tagging**.

## Cutting a release

1. **Push the release branch early.** `release/0.5` accumulated 79 commits and
   met CI for the first time at RC; five of the six failures had been broken
   for weeks.
2. Bump the version everywhere it appears: `pyproject.toml`, `package.json`,
   `viz-lib/package.json`, `sqldesk/__init__.py`, `compose.prod.yaml`,
   `.env.example`, the README badge, `charts/sqldesk/Chart.yaml` (`appVersion`),
   and `CHANGELOG.md`.
3. **Regenerate `uv.lock`** if `pyproject.toml`'s version moved — it records
   the project's own version and `uv sync --frozen` fails on a mismatch. Run
   `uv` *in the container*, pinned: `uv==0.11.6`, the version the Dockerfile
   pins. A different uv rewrites the whole lock into an older format.
4. **Tag only when CI is green including `frontend-e2e-tests`.** The tag is
   what triggers the image build.
5. **Smoke-test the published image** through `compose.prod.yaml` before
   announcing: `/ping` and `/setup` answering, the scheduler registering its
   periodic jobs, and `refresh_queries` and `cleanup_query_results` running
   clean on the worker. CI never exercises `compose.prod.yaml`; doing this by
   hand on 2026-09-17 found three defects a fully green pipeline had missed.
6. Write the notes, create the release, then merge to `main`.

## Pushing

**There is one repository: `bot-netizen/sqldesk`.** It holds every branch,
every tag, every release, the Pages site at sqldesk.org and the
`ghcr.io/bot-netizen/sqldesk` packages. `origin` points at it and `gh`'s
default repo is set to it.

This used to be a trap and is written down because it caught somebody. The
clone's `origin` pointed at `bot-netizen/redash`, the abandoned fork this
project started from, while every release was actually cut on `sqldesk` — and
pushing a branch that had never existed on the fork *succeeded*, creating a
stray branch and starting its workflows, which then failed in confusing ways
for reasons that had nothing to do with the code. On 2026-10-28 a whole
release went to it before anybody noticed, and the fork was deleted the same
day.

**The check, before pushing anything to a repository you have not pushed to
in this session: `gh release list`.** The right repository has every release
on it. The wrong one has none, and that is the fastest question to ask.

## Tests

- **Mutation-test every new test.** Reintroduce the bug and confirm the test
  fails. Several tests in this project looked fine and passed against broken
  code.
- **A test that skips locally is a test nobody has run.** The dev image has no
  `confluent-kafka`, so the Kafka tests skip here and run only in CI — which
  is where two of them were found calling a method renamed hours earlier.
  Before pushing, run the suite the way CI does:

  ```
  docker compose run --rm --entrypoint bash server -c \
    "pip install --quiet confluent-kafka==2.6.1 && cd /app && \
     SQLDESK_DATABASE_URL=postgresql://postgres@postgres/tests python -m pytest tests/ -q"
  ```

  2312 passed / 10 skipped that way, against 2305 / 17 without it.
- **Lint after the last commit, not before it.** 0.7.2 met a red CI because I
  ran black and ruff, then committed one more fix whose expression got shorter
  and whose line then fitted on one. The linters are cheap; run them again
  immediately before the push.
- **Never run the suite as root.** `docker compose run --user root` is tempting
  when you need a `pip install` first, and it fails two tests for reasons that
  have nothing to do with your change: `test_connection_bad_test` expects
  sqlite to be unable to open `/notexist.db`, and root creates it, and
  `test_an_unwritable_directory_is_said_plainly` expects a chmod to mean
  something. Both pass as the `sqldesk` user. Install into a `--target`
  directory and set `PYTHONPATH` instead, or rebuild.
- **Never run two backend suites at once** — both `create_all`/`drop_all` the
  same database and the second fails 152 tests in a way that looks like a code
  fault.
- **Never pipe `docker compose run` into `head`.** `head` closes the pipe, the
  compose client dies of SIGPIPE, and the container keeps running the suite.
  That orphan is the cause of every "the test database got corrupted" episode
  here. Write to a file and grep the file.
- **`create_all` builds the search trigger only if the mappers are already
  configured.** `sqlalchemy_searchable`'s `make_searchable` attaches its
  per-table DDL listeners from the mapper `after_configured` event, so a
  `create_all` that runs before anything has configured the mappers creates
  `queries` without `queries_search_vector_trigger`. `search_vector` is then
  NULL for every row the table ever holds, every search returns nothing, and
  not one thing raises: the search tests in
  `tests/handlers/test_queries.py` just find 0 of 2. `tests/__init__.py`
  calls `configure_mappers()` before `create_all` for this reason. It was
  hidden rather than absent while the schema was rebuilt per test -- the
  first ORM use configured the mappers and every later test got its trigger
  -- which is why that one file failed when run on its own and
  passed in a full suite.
- **The backend suite needs the frontend built, or ten tests fail on a
  template.** `multi_org.html` is a webpack output in `client/dist/`, not a
  file in the repository, and the page handlers render it. A fresh worktree
  has no `client/dist`, so `tests/test_handlers.py`,
  `tests/handlers/test_embed.py`, `tests/test_security_headers.py`,
  `tests/models/test_users.py::TestUserDetail::test_sync` and
  `tests/test_authentication.py::TestJWTAuthentication::test_jwt_from_pem_file`
  fail with `jinja2.exceptions.TemplateNotFound: multi_org.html`. Nothing is
  wrong with them. Run `pnpm run build` in the worktree, or read ten
  template failures as "this checkout has no frontend build" and move on.
- **Compare suite timing per test, and expect the runner to swing by two.**
  `backend-unit-tests` on GitHub's shared `ubuntu-22.04` runners has taken
  25m12s and 46m13s for the same green code on `release/0.8`, and ~58 minutes
  three times. A slow runner reads exactly like a regression, and was written
  down as one twice. The wall clock will not tell you which you have; the
  per-file numbers will. The three ~58-minute runs (41234126211, 41238799209,
  41346028951) were uniformly **2.36-2.45x** slower than the 25-minute one
  across all 84 test files that take over five seconds -- among them
  `test_security_headers.py`, `models/test_users.py` and
  `ai/test_optimizer.py`, which 0.8 never touched. A code path one release
  added cannot slow those by the same factor as everything else. What settles
  it is the step *before* the tests: `Build Docker Images` took 136-142s on
  those three runs and 104-109s on the two fast ones, so the machine was
  already slower before a test had run, and nothing in a test suite slows
  down an image build. Judge the code by the `Run Tests` step divided by its
  test count, which the job summary does not give you: 1150s/2974 on v0.7.10
  against 1399s/3430 on release/0.8's fastest green run is **0.387s against
  0.408s per test**.

## Commits

One verified step per commit. The message says what changed and **why it was
wrong before** — the subject is a sentence, not a label. Autonomous work
commits as it goes rather than at the end.

## Code style

Black (line length 119) and ruff for Python; Prettier and ESLint for the
frontend. Black 23.1.0 crashes on this host's Python 3.13 — run it in a
container:

```
docker run --rm -v "$PWD":/w -w /w python:3.13-slim \
  sh -c "pip install -q ruff==0.8.4 black==23.1.0 && ruff check . && black --check ."
```

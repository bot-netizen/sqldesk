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

**Name the remote.** `git push` with no remote resolves to `origin`, which is
the abandoned `bot-netizen/redash` fork — and on a branch that has never been
pushed there it *succeeds*, creating a stray branch and starting its
workflows.

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

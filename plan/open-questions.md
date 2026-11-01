# Waiting on Iqbal

Delete an entry when it is answered, and write the answer where the work is.

## Blocking 0.7

- **A Slack bot token in a test workspace.** Share-to-Slack is driven against
  a stub of Slack's Web API, which covers the three-step upload, the
  pagination and the error translation — but not whether a real Slack renders
  the blocks as intended.
- **The OAuth consent page walked once in a browser.** Everything else about
  OAuth 2.1 for MCP is tested; the page itself needs a human session, and
  entering credentials to look at a page is not something to do.

## Decisions taken, recorded so they are not re-opened

- **Kafka ships in 0.7**, overriding a recommendation to defer it to 0.8.
- **Locked folders are changeable by administrators**, not frozen for
  everyone. The first design made them read-only even for admins; that was
  wrong.
- **A dashboard shows streams or saved queries, never both**, because a
  dashboard has one refresh interval. Streaming ones are offered seconds:
  2, 5, 10, 20, 30, 60, 120 — no hours, no days.
- **Running Streams is folded into Admin → Streaming Queries**, answered
  2026-10-03. The page was readable by everybody on purpose, so the slot count
  moves to the stream editor's status strip rather than disappearing behind
  Admin. See [0.7-nav.md](0.7-nav.md).
- **The nav is restructured for 0.7**: no vendor name in the bar, streaming
  becomes a half of Queries and of Dashboards rather than a section of its
  own, and `Streaming` is the kind while `Live` stays the refresh state.
  Recorded in [0.7-nav.md](0.7-nav.md).
- **"Streaming Data Sources"** is the name of the topics page under Settings,
  over a recommendation of "Streaming Tables".
- **MCP stayed in the Admin menu** because it was not on the list Iqbal gave,
  and dropping it makes the page unreachable.
- **`main` has not had 0.6 merged into it.** Offered; the answer was to carry
  on, so it waits for 0.7.

## Known-open, found but not fixed

- `HelpTrigger.jsx` builds 22 help links from
  `DOMAIN = "https://sqldesk.github.io/sqldesk"`. The site is at
  **bot-netizen**.github.io. Fixing it means deciding what the help system is
  for, not correcting a typo.
- `FEATURE_EXTENDED_ALERT_OPTIONS` is shipped to the client as
  `extendedAlertOptions` and read by nothing.
- `dashboards.schedule` and migration `f4b2c8d1e903` are vestigial —
  dashboard schedules were added in 0.2.0 and removed in 0.3.2 by request.

## The backend suite takes 57 minutes on release/0.8, against 21 on main

Measured on CI, same runner class, same workflow: `backend-unit-tests` ran
**21m09s** on main at v0.7.10 (run 40918598866) and **56m00s** on
`release/0.8` (run 41346028951, 3430 tests). A 2.7x regression this release
introduced, and nobody has found it.

What has been ruled out:

- **No pathological test.** The slowest handler test is 2.8s and the
  distribution is flat at ~0.6s. It is uniform per-test overhead, not one bad
  case.
- **Not `create_app`.** 0.855s on the first call, 0.039s thereafter.
- **Not Postgres tuning.** The dev compose and `.ci/compose.ci.yaml` both run
  with `fsync=off -c full_page_writes=off -c synchronous_commit=OFF`.

What is known: `BaseTestCase.setUp` does `db.drop_all(); db.create_all()` on
**every** test, which costs 0.44s against 38 tables -- about 25 minutes across
the suite on its own. That is mostly pre-existing rather than new, and the
table count has grown by roughly a tenth this release, which does not account
for 36 minutes.

**The experiment nobody has run**: time the same `drop_all`/`create_all` probe
against v0.7.10 and compare. If it is close, the cost is in the test bodies
and the suite needs a profile; if it is far, the schema is the answer and a
per-class or per-session schema with transactional rollback per test is worth
the change.

Does not block 0.8.0-rc.1. Worth settling before 0.8.0 final, because a suite
nobody will wait an hour for is a suite that stops being run -- which is how
CI came to be red on this branch for a week without anybody noticing.

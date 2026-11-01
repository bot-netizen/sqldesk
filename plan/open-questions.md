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

## The backend suite's time on CI swings between 25 and 60 minutes

Not a regression, and not a pattern either. `backend-unit-tests` on
`release/0.8`:

| Run | Result | Time |
|---|---|---|
| 41234126211 | 3 failed | 57m20s |
| 41238799209 | 3 failed | 59m36s |
| 41346028951 | 3 failed | 58m41s |
| 41351570395 | green | **25m12s** |
| 41353901161 | green | **46m13s** |

Against 21m09s on main at v0.7.10. The spread between two green runs of the
same code is 25 to 46 minutes, so this is runner variance rather than
anything in the suite, and the slowest honest reading of the branch is "about
twice main's, sometimes" -- for roughly a tenth more tests and four more
tables.

**Two wrong claims were made here before this one**, and they are recorded
rather than deleted. First, that the branch had a 2.7x regression -- drawn
from a single failing run. Then, that failing runs were slow and passing ones
fast -- which the 46-minute green run disproves. One measurement is not a
finding, and three correlated ones are not much better.

What is worth doing before 0.8.0 final is not an investigation but a
reduction: `BaseTestCase.setUp` does `db.drop_all(); db.create_all()` on
**every** test, 0.44s against 38 tables -- about 25 minutes across the suite,
and the dominant cost in it. Creating the schema once and rolling back a
transaction per test would take most of that back, on any runner. It is a
careful change: some tests may rely on a genuinely empty database or commit
outside the session.

Ruled out along the way: no pathological test (the slowest handler test is
2.8s, the distribution flat at ~0.6s); `create_app` is 0.855s once and 0.039s
thereafter; the dev and CI composes tune Postgres identically.

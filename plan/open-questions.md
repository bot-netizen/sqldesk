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
- Every `backend-unit-tests` run on release/0.8 ends with `nanobind: leaked 6
  types! / leaked 84 functions!` and a link to nanobind's refleaks page. It is
  DuckDB 2.0.0's binding layer — v0.7.10's runs with 1.5.6 print nothing — and
  it comes at interpreter shutdown, after the summary, so it changes neither
  the result nor the timing. The counts are identical across all five runs,
  failing and green, so nothing is accumulating. Noise, until something makes
  it matter.

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

What was worth doing here was not an investigation but a reduction, and it is
done. `BaseTestCase.setUp` did `db.drop_all(); db.create_all()` on **every**
test, which was the dominant cost in the suite. It now builds the schema once
per process and empties the tables with a single `TRUNCATE ... RESTART
IDENTITY CASCADE`. On one host, sequential runs against the same database:

| | tests | time |
|---|---|---|
| before | 3444 passed, 10 failed | 33m37s |
| after | 3447 passed, 10 failed | **15m42s** |

The same ten failures before and after, byte for byte -- all ten a checkout
with no frontend build rather than anything in the suite, which
[conventions.md](conventions.md) now names. The three extra passes are tests
guarding the reset itself. What CI makes of it is for CI to say.

Rolling back a transaction per test, which is what this section proposed, is
cheaper again and was not worth it: the session has to be rebound to a held
connection with a SAVEPOINT restarted after every `commit()`, and the tests
that rebuild the schema inside themselves, execute DDL, or write outside the
session would each need adapting to it. `TRUNCATE` changes nothing any test
can see and takes about nine tenths of the saving.

Doing it also brought out a real bug it had been hiding, fixed in the same
change and written down in [conventions.md](conventions.md): `create_all`
creates the full-text search trigger only if the mappers are already
configured. Rebuilding per test hid that, because the first ORM use
configured them and every later test got its trigger. Building once made the
first test decide for the whole run, so `tests/__init__.py` now calls
`configure_mappers()` first.

The probe this section once called the experiment nobody had run has now been
run, on one host and image for both branches: the cycle is **0.468s** against
release/0.8's 38 tables and **0.416s** against v0.7.10's 35. So the schema
grew a twelfth this release and is not where the swing comes from -- but it
was a little over half of each test, which is what made the reduction worth
doing. It did not drift either: 500 consecutive cycles in one database
stay flat, because autovacuum keeps up with the catalog churn.

Ruled out along the way: no pathological test (the slowest handler test is
2.8s, the distribution flat at ~0.6s); `create_app` is 0.855s once and 0.039s
thereafter; the dev and CI composes tune Postgres identically. Nothing this
release added sits on a path every test touches: `pools.py`,
`metrics/prometheus.py` and `monitor.py` are all imported lazily, and
`app.py` is unchanged. The per-file evidence for runner variance, and the way
to measure it, is in [conventions.md](conventions.md) under Tests.

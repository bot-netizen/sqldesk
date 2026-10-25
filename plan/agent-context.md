# What an agent is given, and what it costs

Measured 2026-10-25 against the minikube install, by calling the tools
through `mcp.handle` with the real catalog behind them. Numbers are bytes
from the actual responses; tokens are bytes ÷ 4, which is close enough for
English prose and slightly pessimistic for JSON.

## The measurement

**The tool list, which is sent on every turn of every conversation:**

| | bytes | ~tokens |
|---|---|---|
| 9 read tools (what a reader is offered) | 4,348 | **1,087** |
| 13 tools (what an admin with write access is offered) | ~6,100 | ~1,525 |

**The answers, which are paid once each, when a tool is actually called:**

| Tool | text | structuredContent | ~tokens |
|---|---|---|---|
| `find_dashboards` | 2,269 | 3,116 | **1,346** |
| `find_queries` | 952 | 900 | 463 |
| `find_context` | 614 | — | **153** |
| `list_data_sources` | 309 | — | 77 |
| `expand_table` | 309 | — | 77 |
| `find_measures` | 57 | 249 | 76 |
| `check_sql` | 213 | — | 53 |
| **Total for one full exploration** | 4,723 | 4,265 | **2,247** |

## What this says

**The descriptions are not the expensive part.** The entire semantic answer
to a question — tables, columns, what they mean, which measures are agreed,
and the warning that the catalog is 29 days stale — is `find_context` at
**153 tokens**. It is the cheapest thing in the system and it is what stops
the expensive failure: an agent guessing a column name, writing SQL that
runs, and returning a wrong answer that looks right. Nothing else here buys
as much for as little.

**The three description layers are not redundant, because they answer
different questions at different moments.** Table and column descriptions
say what the data means; a query description says whether somebody has
already answered this; a visualization description says which chart on a
board is the one being talked about. An agent that has only the first writes
SQL that already exists. An agent that has only the third cannot write SQL
at all.

**The confirmations are the best value per token in the whole design.** A
verified dashboard and an agreed measure are a handful of tokens that let an
agent *stop* — stop searching, stop hedging, stop asking the person. An
agent that cannot tell "this is the number finance uses" from "somebody once
wrote this" keeps looking, and looking costs more than the badge did.

**What is actually too much is enumeration, not description.**
`find_dashboards` spends 1,346 tokens on one question because it lists every
widget of an 80-widget dashboard. That is six times what the whole semantic
catalog costs.

**The schemas cost more than the answers.** 1,087 tokens go out on every
turn whether a tool is called or not. Over a twenty-turn conversation that is
~21,700 tokens of schema against ~2,200 tokens of answers: **the tool list
costs about ten times what the tools return.** Prompt caching hides most of
it when the list is stable, and a cache miss pays it again.

**`structuredContent` is sent with no `outputSchema` declared anywhere**
(zero occurrences in the module). It repeats about 90% of the text's bytes.
The protocol has it for clients that want typed data, but a client has no
schema to validate it against here, so most will either ignore it or put it
in the context beside the prose — paying twice for one answer.

## What changed, and what it bought (2026-10-25)

The first three were done the same day, and the same script re-measured them
against the same catalog.

| | before | after |
|---|---|---|
| Tool list, every turn | 1,087 tok | **892 tok** |
| `find_dashboards`, one question | 1,346 tok | **353 tok** |
| `find_queries` | 463 tok | 238 tok |
| `find_measures` | 76 tok | 14 tok |
| One full exploration | 2,247 tok | **967 tok** |

A 57% cut to what an exploration costs, and 195 tokens off every single turn.
Three changes did it:

- **`structuredContent` is gone.** It was sent with no `outputSchema`, so no
  client could rely on it, and it repeated ~90% of the text's bytes.
- **Panels of the same query collapse onto one line**, and four dashboards are
  described rather than eight, with "3 more match. Name one to see its panels."
  A board built to show one query twelve ways was most of the old cost.
- **The descriptions say what the tool does, when to reach for it, and the one
  constraint that is not obvious** -- and stop selling. The persuasion in
  `find_queries` ("which no amount of schema does") was 510 characters sent on
  every turn forever.

Held by `tests/handlers/test_mcp.py::TestWhatAnAnswerCosts`: no tool may send
`structuredContent`, panels of one query are one line, only four boards are
described, and a tool description may not pass 340 characters.

## What to change, in the order worth doing it

1. **Stop sending `structuredContent` without an `outputSchema`.** Either
   declare the schemas and cut the text to a one-line summary, or drop the
   structured copy. Saves ~47% of every answer's bytes.
2. **Cap the enumerations.** `find_dashboards` should give at most ~8 widgets
   per dashboard, collapse widgets that share a query, and say "72 more —
   name one to see it". Caps belong on every `find_*`, each with how to
   narrow rather than a bare truncation.
3. **Trim the tool descriptions.** `find_queries` spends 510 characters.
   Halving the prose across nine tools takes the per-turn cost from ~1,087 to
   roughly 700 without losing a distinction a model relies on.
4. **Do not merge the tools to save schema bytes.** Narrow, well-named tools
   produce fewer wrong calls, and a wrong call costs a whole round trip plus
   its answer — far more than the schema it saved. Trim the prose; keep the
   names.
5. **Keep the catalog, the descriptions and the confirmations as they are.**
   They are the cheap part and they are what makes the rest unnecessary.

Already right, and worth not breaking: `run_query` caps the SQL at 1,000
rows and renders only 50 into the context; `expand_table` is progressive, so
columns arrive only when asked for; an ambiguous table name produces a
refusal that names the candidates instead of guessing.

## Live, streaming, and whether anything should be pushed

**They are two different things and both earn their place.** *Streaming* is
a Kafka topic consumed into a DuckDB window. *Live* is any dashboard
refreshing itself on a schedule, over Postgres or Snowflake or anything
else. Merging them would mean either dropping auto-refresh for ordinary
sources or pretending a warehouse is a stream. What is wrong is the naming:
"live" and "streaming" sound like the same word to a new reader. **Auto-refresh**
and **Streaming** would not.

**Push was never built.** There is no SSE and no WebSocket anywhere in the
codebase — the roadmap line about pushing instead of polling never became
code. What exists is better than it sounds: a viewer checks in every 15
seconds and gets back a map of widget to *result id*, so a browser fetches
only the results that actually changed.

**Recommendation: do not build SSE next.** A held connection per viewer is
expensive in exactly the place this deployment is thin — gunicorn with
gthread has 8 threads per worker, so eight watchers would occupy a worker
entirely, and the stream worker would need its own fan-out to reach them.
The cheap 90% is an **adaptive poll**: back off toward 60 seconds while
nothing changes, drop to 5 while something does. Same freshness where it
matters, no connection arithmetic. Revisit push when there is an async
worker to hold the connections.

**Pagination of the result set: measured, and not worth building.** This
page said it was the biggest remaining win. That was reasoning, not
measurement, and measuring it says otherwise.

A 50,000-row, eight-column result -- 7.41 MB of JSON -- measured in a
browser on 2026-10-25:

| | full result | a 10,000-row window |
|---|---|---|
| gzipped over the wire | 0.86 MB (8.6:1) | 0.17 MB |
| on a 10 Mbit link | 0.7 s | 0.1 s |
| `JSON.parse` | 15 ms | ~3 ms |
| sort, filter and init per interaction | 26 ms | ~5 ms |

The browser is not struggling: fifty thousand rows parse in fifteen
milliseconds and sort in eighteen. Compression, which 0.7.2 added, already
took the transfer from 7.4 MB to 0.86. Windowing would save about six tenths
of a second on a slow link and twenty milliseconds of CPU.

And it would cost more than it saves on the server. `serialize_query_result_json`
deliberately never builds the object graph: the payload is already JSON in
Postgres, so the metadata is encoded and the stored bytes are dropped into a
slot in the string. That optimisation measured ~1 s of CPU saved on a 27 MB
result. Serving a *window* means parsing that payload and re-encoding a
slice -- undoing exactly that, on every request, on the worker.

So: **do not paginate at read time.** If very large results need bounding,
bound them where it is free -- a row ceiling applied when the result is
stored, so nothing enormous is ever written or served, and the byte-copy fast
path stays intact. That is a product decision (a capped result is a changed
answer), not a performance fix to be made quietly.

What is left, in order: **browser memory** on a dashboard holding several
large results at once, which none of the above addresses; and the
**adaptive poll** above, which is cheap.

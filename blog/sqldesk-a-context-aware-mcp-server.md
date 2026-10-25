---
title: "SQLDesk: a context-aware MCP server"
date: 2026-10-25
summary: >-
  Connect an agent to a database and it gets column names. Connect it to SQLDesk and it gets the
  catalog your team wrote, the queries they already answered, who owns each one and who confirmed it —
  and it can write back, as drafts, capped, and audited. The thirteen tools, what they return, and
  what they refuse.
lede: >-
  A schema tells an agent what columns exist. It does not say which revenue number finance uses, which
  dashboard somebody checked, or whether the table it is about to join was renamed last month. This is
  what SQLDesk hands an agent instead, and what it will not hand over at all.
description: >-
  The thirteen MCP tools in SQLDesk 0.7.7: what each returns, how ownership and confirmation travel
  with the answer, how writing back is gated and audited, and what the whole exchange costs in tokens.
next:
  label: The MCP guide
  link: /guide/mcp.html
---

Point an agent at a database and it can read the schema. It will find a table called `orders`, a
column called `amount`, and another called `status`. What it cannot find is that `amount` is gross
and refunds are subtracted somewhere else, that `status` has had five values since March and two of
them mean the same thing, or that somebody already wrote the query it is about to invent — and got it
right after three attempts and a conversation with finance.

So it guesses. The SQL runs, a number comes back, and nothing about the number says it is wrong.

SQLDesk 0.7.7 takes a different approach: an agent connects over the Model Context Protocol and is
given what your team has already written down. Not just the shape of the data — the meaning, the work
that exists, who owns it, and who checked it.

## Thirteen tools, in four groups

Nine of them read. Four of them write, and are only offered to somebody who may already do that same
thing by hand.

**Look for work that already exists.** `find_queries` searches saved queries by name, description and
their charts. `find_dashboards` does the same for dashboards. `find_measures` returns the numbers the
organization has agreed on. The point of all three is to answer a question with work somebody already
did, rather than with SQL nobody has reviewed.

**Understand the data.** `find_context` takes a question in plain English and returns the tables most
likely to answer it, their columns pruned to the ones people actually use, and the joins observed
between them. `expand_table` gives the full column detail for a named table when the pruned list is
not enough. `list_data_sources` says what is connected and what dialect each speaks.

**Check, then run.** `check_sql` parses SQL in the data source's own dialect and reports expensive
patterns — an unconditional join, `SELECT *` on a columnar table, a filter that defeats partition
pruning. Nothing is executed. `explain_query` returns the real plan from the data source.
`run_query` executes one read-only statement.

**Write back.** `save_query`, `update_query`, `propose_measure` and `update_table`. More on those
below, because the interesting part is not that they exist but what they are allowed to do.

## One call instead of forty

The usual shape of a database integration is `list_tables`, then `get_schema` for each one that looks
promising. On a warehouse of any size that is a long, expensive conversation that ends with the agent
holding every column of every table it guessed at.

`find_context` is one call. Ask it "revenue by region" and it answers with the handful of tables that
question is actually about, each with the columns people use, the joins that have been observed
between them, and — the part no schema carries — what the tables mean:

```
-- The quarterly revenue target per region, set by finance.
-- One row per region, replaced each quarter.
orders(amount numeric, ts timestamptz, region text, product text)
region_targets(region text, quarter text, target numeric)
revenue = SUM(amount) on orders   -- Gross, before refunds.
```

Five lines. "Gross, before refunds" is the difference between an answer and a wrong answer, and it is
written nowhere a schema reader can reach.

That catalog is built from what you already have — the tables your data sources expose, and the SQL
your team has already written against them — and then improved by people describing things in the
Catalog page. Nothing has to be modelled up front for it to be useful.

## When the catalog is out of date, it says so

A stale description is worse than no description, because it is believed. If the catalog has not been
harvested recently, every answer drawn from it carries a warning naming the sources involved and how
old it is:

```
-- Warning: this catalog has not been harvested for 29 days. It describes
-- Demo stream, File DS as it was then, so a column may have been renamed or
-- dropped since. Check anything surprising against the data source.
```

Only for the sources that answer could have drawn on, and nothing at all when everything is current —
a warning on every answer is a warning nobody reads by the third one.

## Who wrote it, and who confirmed it

This is the part that makes an agent's answer something you can act on rather than something you have
to go and verify yourself.

**Queries carry their owner and their last editor.** A result from `find_queries` says who wrote the
query, who changed it last, when it was updated, and which data source it runs against. An agent
choosing between two queries that both look relevant is not choosing blind.

**A confirmed query says so, and says who confirmed it.** Somebody can mark a query as verified: that
it answers a particular question correctly. That travels with the answer:

```
#567 Revenue by region [VERIFIED]
  verified by Dana Okafor on 2026-10-18 -- does this match the finance close?; checked against
  the October close, to the cent
```

The tool's own description tells the agent to prefer a verified result, unchanged, over SQL of its
own. The badge is not decoration — it is permission to stop looking.

**A dashboard cannot be verified silently.** Marking one requires saying what was checked. Try it
without and the API refuses: *"Say what was checked. A badge with no reason is one nobody can weigh."*
That note is returned to the agent along with who verified it and when. A verified dashboard is also
described before unverified ones, so a board somebody has read does not fall behind four nobody has
checked.

**Measures are proposed, never assumed.** A measure — `revenue = SUM(amount) on orders` — only reaches
anybody after a curator agrees it. `find_measures` returns the agreed ones with what each computes and
which table it comes from, and the tool's description tells an agent to ask before writing an
aggregate of its own: using the agreed one is the difference between the organization's number and a
plausible one.

**Descriptions remember where they came from.** Every catalog description records whether a person or
an agent wrote it, which person, and when. When an agent describes a table, that is visible as an
agent's description on the Catalog page, next to the ones people wrote, and a human description is
never silently replaced by a machine one — the write refuses unless it is told explicitly to
overwrite.

So when an answer arrives, the provenance arrives with it: this query, by this person, confirmed by
that person on that date, using a measure this organization agreed, from a catalog last refreshed on
this day.

## A question, end to end

Put together, one question looks like this. The agent asks the catalog what the question is about,
checks the SQL it drafts, and only then runs it:

```
> which regions are below their revenue target this quarter?

  find_context("revenue by region")
    -- The quarterly revenue target per region, set by finance.
    -- One row per region, replaced each quarter.
    orders(amount numeric, ts timestamptz, region text, product text)
    region_targets(region text, quarter text, target numeric)
    revenue = SUM(amount) on orders   -- Gross, before refunds.

  check_sql(...)    WARNING: no WHERE clause and no LIMIT
  run_query(...)    3 rows, 240 ms

  north   892,400   target 1,000,000   -11%
  west    631,900   target   750,000   -16%
  south   410,200   target   500,000   -18%
```

Three calls. The agent did not browse the schema, did not guess which column holds revenue, and was
told before it ran anything that its first draft would read the whole table. If a saved query had
already answered this, `find_queries` would have found it and the right answer would have been
somebody's existing work rather than new SQL.

## It knows what language your source speaks

Not every data source takes SQL. A Prometheus or Grafana Mimir source takes PromQL, and an agent that
sends it `SELECT` gets nothing useful.

Each data source declares the language its queries are written in, and the MCP tools believe it rather
than guessing from the connector's name. So `check_sql` parses in the right dialect, `run_query`
accepts a PromQL query against a Mimir source instead of refusing it as "not a read", and the
read-only rule is enforced in terms the language actually has. One list of tools, whatever is behind
them.

## The meaning can live in git

What a table means is written by people, and the place to review what people wrote is the place you
already review things.

So the catalog is the cache, and a directory of YAML is the record. What somebody types in the browser
is live at once — the next answer includes it. Exporting is a separate, deliberate step, and nothing
is committed for you:

```
manage ai export /app/semantic   # catalog → files, then commit them
manage ai import /app/semantic   # files → catalog
```

Which means a change to what `revenue` means can arrive as a pull request, be argued about in a diff,
and land with a reviewer's name on it — and an agent's answers change when that merges, not when
somebody edits a box nobody is watching.

## Reading is the default. Writing is a decision.

Every tool above reads. The four that write are gated four separate ways, and the gates are not
configuration — they are how the tools are offered at all.

**A personal API key, not an OAuth session.** A client connected through the OAuth flow holds
`mcp:read`. That was stated when OAuth was added and it is still true: an agent somebody connected
through their client cannot write. The write tools require a key the person generated themselves.

**The same permission the browser checks.** A reader who cannot create a query in the UI cannot create
one through MCP. `update_table` and `propose_measure` additionally require the catalog curation
permission. The tools are not even listed to a caller who may not call them, so an agent working for a
reader never sees a way to write and never tries one.

**Everything lands somewhere reversible.** A saved query arrives as a **draft** — it is not on the
Queries list until a person opens it and publishes it. A measure arrives as a **proposal** that
reaches nobody until a curator agrees it. The answer says so plainly: *"Saved as draft query 579, at
queries/579. It is a draft: open it in SQLDesk and publish it to put it on the Queries list."*

**A daily cap.** Fifty writes per person per day by default
(`SQLDESK_MCP_WRITES_PER_DAY`). An agent told to describe a warehouse will describe the entire
warehouse, and a loop getting it wrong will do it just as fast. Fifty is enough for somebody working
through their catalog and small enough that a mistake is a morning's review rather than a week's. The
refusal says which tool hit the limit, when it resets, and which setting raises it.

**And all of it is audited.** Every call is recorded — the tool, the person, the key, and for a write,
what it changed, before and after:

```
update_query   Dana Okafor   query 579: description: 'created by the audit pass'
                             -> 'reworded through MCP by the audit pass'
update_table   Dana Okafor   orders in Demo stream: 'One row per order...'
                             -> 'Edited through MCP...'
```

Refusals are audited too, which is the half people forget. An administrator can see not just what an
agent changed but what it tried to change and was stopped from doing.

## What it refuses, and why that is the useful part

A tool that fails vaguely teaches an agent nothing, so it tries again, differently, and fails again.
Every refusal here says what was wrong and what would be right.

Ask `run_query` to delete something and it will not: *"That statement contains DELETE; only reads can
be run from here."* Name a table that is in two data sources and it does not guess: *"'orders' is in 2
data sources (Demo stream, Redpanda Local Streams). Say which with `data_source`."* Ask about a table
nobody has: *"None of those tables are in the catalog."*

Each of those is one round trip that ends with the agent knowing what to do next, rather than three
that end with it fabricating something.

`run_query` also has limits that are not refusals so much as physics. It runs **on a worker**, not in
the web tier — as the owner of the key, appearing in the administrator's list of running queries and
cancellable there like any other. Its SQL is capped at **1,000 rows** whatever it asks for, and
**50 rows** are rendered into the model's context: enough to answer a question or see the shape of an
answer, not enough to drag a result set through a language model. If you want a cost ceiling before a
query runs — plan cost on Postgres, scanned bytes on BigQuery — those exist and are off until you set
them.

## What the whole conversation costs

Context is the budget an agent actually spends, so we measured it rather than guessed, against a real
catalog, before and after a round of trimming in 0.7.7:

| | Before | After |
|---|---|---|
| Tool list, sent on every turn | 1,087 tokens | **892** |
| `find_dashboards`, one question | 1,346 | **353** |
| `find_queries` | 463 | 238 |
| One full exploration | 2,247 | **967** |

Three things did it. The duplicate copy of every answer went: each result had been sent as prose *and*
as structured data, which repeated about 90% of its bytes for something no client could depend on.
Panels showing the same query collapsed onto one line — a board built to show one query twelve ways
was most of the old cost. And the tool descriptions stopped selling and started saying what the tool
does, when to reach for it, and the one constraint that is not obvious.

What did **not** change is the part that makes an agent correct. The whole semantic answer to a
question — tables, columns, meanings, agreed measures, staleness warning — is **153 tokens**. It is the
cheapest thing in the system and it is why everything else can be short.

## Connecting one

MCP is off until you turn it on, like everything heavy in SQLDesk. Switch it on, and a client connects
one of two ways.

**Through OAuth**, which is the one to prefer: the client is authorized in the browser as you, holds
`mcp:read`, and can be revoked without touching anything else. **Or with a personal API key**, as
`Authorization: Bearer <key>`, which is also the only way to reach the write tools.

Either way, what the agent can see is exactly what you can see: the same data sources, the same row
limits, the same groups. There is no service account with a wider view, and no second set of
credentials to keep in step with the first.

Your own profile page shows whether your connection has ever been used, which client is on the other
end, and the calls it has made — each with the tool, the outcome and how long it took. Deliberately
not the questions or the SQL: that endpoint carries neither, because your call history is not the
same thing as your work.

## What it does not do

Worth saying plainly, since the point of all of the above is that you can trust what comes back.

It does not write to your warehouse. `run_query` runs one read-only statement; the write tools change
SQLDesk's own catalog and query list, never your data.

It does not invent meaning. If nobody has described a table, the agent gets the columns and no
description, and the honest answer is thinner. The catalog is only as good as what your team has
written in it — which is also why describing things pays off immediately rather than eventually.

It is not a replacement for reading the query. A verified query tells you somebody checked it against
a question on a date. It does not tell you the data did not change the week after.

## Use it, and tell us what breaks

SQLDesk 0.7.7 is out: self-hosted, Apache 2.0, viewers free because there is nobody to charge you for
them. The [MCP guide](/guide/mcp.html) has the setup, the full tool reference and the settings; the
[releases page](/releases.html) has what else is in this one.

This is the first release where an agent can write back, and the gates around that — drafts,
proposals, the daily cap, the audit — are judgement calls we would rather get right than defend. If
fifty writes a day is wrong for how you work, if a refusal left your agent stuck instead of pointed
somewhere useful, or if there is a piece of provenance you need in the answer that is not there yet,
we want to hear it.

[Open an issue](https://github.com/bot-netizen/sqldesk/issues), and say what you were trying to do.

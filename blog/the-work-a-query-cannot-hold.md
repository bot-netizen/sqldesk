---
title: The work a query cannot hold
date: 2026-11-01
summary: >-
  Notebooks ship in 0.8, in beta. Five pieces of work that do not fit in one SELECT — a churn list
  that spans two warehouses, a month-end reconciliation, a cohort table, a reorder forecast, and the
  investigation that turns into a monthly report — written out as the cells you would actually type.
lede: >-
  A saved query answers a question that fits in one statement. A great deal of real analysis does not.
  Here is the work people take to a laptop instead, and what it looks like when it stays where your data
  lives.
description: >-
  Five real pieces of analysis that do not fit in one SELECT, written out cell by cell: cross-warehouse
  churn, month-end reconciliation, cohort retention, reorder forecasting, and turning an investigation
  into a scheduled report.
next:
  label: The notebooks guide
  link: /guide/notebooks.html
---

A saved query answers a question that fits in one statement. Most of the analysis people are actually
asked for does not. It is three queries against two warehouses, a join neither of them can do, a reshape
that is easier in pandas than in SQL, and a number at the end that somebody wants every Monday.

That work has a well-known home: a laptop. Somebody pulls two CSVs, opens Jupyter, and an hour later
pastes a chart into Slack. The answer is right, and almost everything around it is lost — the SQL, the
permissions, the lineage, and any chance of it running again next month without that person.

Notebooks are in SQLDesk 0.8, in beta, to keep that work where the data is. Below are five jobs that
come up in every company I have seen, written out as the cells you would type. They are deliberately
unglamorous.

## 1. A churn list that spans two warehouses

**The problem.** Contracts and invoices are in the Postgres behind the billing app. Product usage is in
the analytics warehouse. The question — *which paying accounts have gone quiet?* — needs both, and
neither database can see the other.

The usual answers are a nightly pipeline into one place, which is a project, or two CSV exports and a
VLOOKUP, which is a Tuesday that disappears.

**As a notebook.** One cell per source, then a cell that joins them.

```sql
-- accounts, against Billing (Postgres)
select account_id, name, mrr, renewal_date
from subscriptions
where status = 'active'
```

```sql
-- usage, against Analytics (BigQuery)
select account_id, count(*) as events, max(event_at) as last_seen
from events
where event_at > current_date - 90
group by account_id
```

```sql
-- at_risk — no data source, so it reads the two cells above
select a.name, a.mrr, a.renewal_date,
       coalesce(u.events, 0) as events_90d,
       u.last_seen
from accounts a
left join usage u on u.account_id = a.account_id
where coalesce(u.events, 0) < 10
  and a.renewal_date < current_date + 60
order by a.mrr desc
```

The third cell has **no data source**. It reads the cells above it as tables, in DuckDB, inside the
notebook. Neither warehouse learns about the other, and nobody had to build a pipeline to ask a question
that might turn out to be a bad question.

Put a chart on the last cell, give the notebook a cron of `0 7 * * 1`, and it is in front of the account
team every Monday morning.

## 2. Month-end reconciliation

**The problem.** The payment processor says one number. The ledger says another. Somebody spends the
first Tuesday of the month finding out which transactions account for the difference. This is not
analysis — it is a diff — and it is miserable in SQL because the two sides disagree about identifiers,
rounding, and when a day ends.

**As a notebook.** Two cells to pull each side, one to compare, one to explain.

```sql
-- processor, against Stripe's replica
select charge_id, amount_cents / 100.0 as amount, created_at::date as day
from charges where created_at >= date_trunc('month', current_date - 30)
  and created_at < date_trunc('month', current_date)
```

```sql
-- ledger, against the finance warehouse
select external_ref as charge_id, amount, posted_on as day
from gl_entries where account = '4000-revenue'
  and posted_on >= date_trunc('month', current_date - 30)
  and posted_on < date_trunc('month', current_date)
```

```python
# differences — Python, because the matching is fuzzier than a join
import pandas as pd

merged = processor.merge(ledger, on="charge_id", how="outer",
                         suffixes=("_processor", "_ledger"), indicator=True)

merged["gap"] = merged.amount_processor.fillna(0) - merged.amount_ledger.fillna(0)
differences = merged[(merged._merge != "both") | (merged.gap.abs() > 0.005)]
differences.sort_values("gap", key=abs, ascending=False)
```

The last line is a dataframe, so it becomes a table on the page — and a relation any cell below can read.
A fourth cell can group it by reason, and the PDF goes to whoever signs the close.

What makes this worth keeping in SQLDesk rather than a laptop is **the record**. Every run stores which
cells it read and how many rows came back. Next March, when somebody asks how the February gap was
explained, the notebook is the answer rather than a memory.

## 3. A cohort table

**The problem.** Retention by signup month. Everybody wants it; the SQL is famously horrible, because a
cohort table is a pivot and SQL pivots badly.

**As a notebook.** Do the easy half in SQL and the awkward half where it is three lines.

```sql
-- signups_and_activity, against the warehouse
select date_trunc('month', u.created_at) as cohort,
       date_trunc('month', e.event_at)   as active_month,
       count(distinct u.id)              as users
from users u join events e on e.user_id = u.id
group by 1, 2
```

```python
# retention
table = signups_and_activity.pivot(index="cohort", columns="active_month", values="users")
sizes = table.max(axis=1)
(table.div(sizes, axis=0) * 100).round(1)
```

Two lines of pandas against roughly forty of window functions and `filter (where …)`. The point is not
that SQL cannot do it. It is that the version you can still read in six months is the one that gets
maintained.

## 4. What to reorder, and when

**The problem.** Stock on hand is in the ERP. What is selling is in the orders database. The question —
*what runs out before the next delivery?* — is a small forecast, and small forecasts are exactly what
spreadsheets get wrong quietly.

```sql
-- on_hand, against the ERP
select sku, quantity, warehouse from inventory_levels
```

```sql
-- velocity, against the orders database
select sku,
       sum(quantity) filter (where ordered_at > current_date - 7)  / 7.0  as per_day_7,
       sum(quantity) filter (where ordered_at > current_date - 28) / 28.0 as per_day_28
from order_lines
where ordered_at > current_date - 28
group by sku
```

```python
# reorder
import numpy as np

stock = on_hand.groupby("sku", as_index=False).quantity.sum()
plan = stock.merge(velocity, on="sku", how="left").fillna(0)

# The faster of the two windows, so a line that is accelerating is not
# averaged back down into looking safe.
plan["per_day"] = plan[["per_day_7", "per_day_28"]].max(axis=1)
plan["days_left"] = np.where(plan.per_day > 0, plan.quantity / plan.per_day, np.inf)
plan["order_now"] = plan.days_left < 21

plan[plan.order_now].sort_values("days_left")
```

The judgement — *the faster of the two windows* — is the whole value of the cell, and it is written down
where the next person can argue with it. In a spreadsheet it is a formula in F7.

## 5. The investigation that becomes a report

This is the one that matters most, and it is a lifecycle rather than a query.

Someone asks why margin fell last quarter. You do not know, so you poke: revenue by product, then by
region, then costs, then one product line that looks wrong, then a per-unit calculation that explains
most of it. Six or seven steps, each one deciding the next.

In a query editor that work is destructive — you edit the same statement over and over, and the step
that turned out to matter is gone by the time you know it mattered. In a notebook the steps stay, named
and visible, with their outputs under them.

Then it ends well, and the answer is wanted every quarter. Three things, and none of them is a rewrite:

- **Fold the dead ends away.** They are still there; they are just not in the way.
- **Title the cells** that carry the argument, so the contents list down the side reads like a document.
- **Schedule it, share it.** A cron for the day after close, and a PDF or a link for whoever asked.

The investigation and the report are the same artefact. That is the part Jupyter gets right and a BI
tool usually does not.

## The rules that keep this honest

Three decisions shape all of the above, and they are worth stating because they are the ones people
expect to be different.

**A cell is named, not numbered.** A later cell reads an earlier one by its name, so inserting, deleting
and reordering leave every reference pointing at what it meant. Title a cell and the name follows —
*Orders, cleaned* becomes `orders_cleaned` — and the name sits on the cell in monospace, one click to
copy it. Under each editor is a line naming what that cell can read, and typing in a cell completes
against the cells above and the columns inside them. You should never have to remember a name.

**A Python cell computes; it cannot query.** It reads an earlier cell's output and nothing else. That
rule is there for what it removes: no credential ever reaches the interpreter, because there is nothing
there for it to reach. Python runs in a separate container that can be denied egress entirely. Anything
that needs the warehouse needs a SQL cell above it — which also means every byte that enters a notebook
came through a data source permission somebody granted.

**Stale is shown and never corrected for you.** If a cell you read has re-run since, this cell says so
and is left exactly as it was. The number on screen is still the number that was computed. Re-running is
your decision, and staleness carries: if A feeds B and B feeds C, re-running A marks both. Every notebook
tool with a session can rot; most of them rot silently.

## Beta, and what it means

Notebooks are in beta in 0.8. Use them — nothing here will lose your work, because a notebook is rows in
the database like a query or a dashboard, and the handoff between cells is a file that re-running
rebuilds. What may change between releases is the shape of the page and what a cell is allowed to do.

The things they do not do yet are worth saying plainly. A cell's chart cannot become a dashboard widget:
refreshing a widget backed by cell seven means running cells one to seven on an interpreter, which is a
scheduling design rather than a widget. Nothing writes back to a data source. Alerts watch a query, not a
cell — a notebook that needs to raise something should end in a query an alert is watching.

The [notebooks guide](/guide/notebooks.html) has the rest: how the handoff is stored, what a Spark
cluster changes, and how to turn the Python interpreter on without handing it anything it should not
have.

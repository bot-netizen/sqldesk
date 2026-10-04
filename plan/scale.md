# What breaks at 500 concurrent users

Worked out on 2026-10-03, from the code and from the running install. The
figures are measured where they say measured. Re-measure rather than trusting
these after any of it changes.

## The ceilings, in the order they are met

**1. Gunicorn runs sync workers, four of them, on one replica.**
`bin/docker-entrypoint` has no `-k`, so **four concurrent HTTP requests** is
the whole web tier. One 3 MB result fetch holds a worker for its duration.
500 viewers checking in every 15s is 20–33 req/s before anybody loads a page.
Nothing else matters until this is fixed.

**2. Postgres connections run out before the web tier scales.** SQLAlchemy
defaults to 5 + 10 overflow *per process*; four workers is up to 60 per
replica, and Postgres ships with `max_connections=100`. The third replica
meets `FATAL: sorry, too many clients already`. Nothing in the chart sets
`SQLALCHEMY_POOL_SIZE`.

**3. Redis has no `maxmemory` and no volume.** It holds RQ job state, stream
slots and live check-ins. Unbounded until the container limit kills it, and a
restart loses every in-flight query. It must be `noeviction` — evicting a key
loses a running query silently.

**4. The uploads volume pins every worker to one node.** `ReadWriteOnce`
mounts on one node, so the chart gives the workers affinity to the server's.
A `ReadWriteMany` class (EFS, Filestore, Azure Files, NFS) removes it.

**5. No HPA, no PDB, no topology spread** in the chart. Scaling is
`kubectl scale`, and a node drain can take the whole web tier.

**6. The scheduler is a singleton with no leader election.** If it dies
nothing refreshes, and the only signal is Outdated Queries growing.

**7. Results travel through the web tier and are rebuilt per viewer.**
Measured on 20k×8 (3.3 MB): `JSON.parse` 14 ms, `QueryResult.update()`
**960 ms** on the browser's main thread. One dashboard pays once since 0.5;
100 viewers of it pay 100 times.

## Result formats, measured 2026-10-04

20,000 rows x 8 columns -- the shape in 7 above. Encode and decode are Python
in the container; "gzipped" is what *would* cross the wire if anything
compressed it.

| representation | encode ms | decode ms | bytes | gzipped |
|---|---|---|---|---|
| row dicts (today) | 112 | 35 | 3,715,944 | 420,514 |
| row arrays | 106 | 16 | 1,675,944 | 371,130 |
| columnar JSON | 86 | 9 | 1,636,062 | 299,780 |
| Arrow IPC | 2 | 0 | 1,319,256 | 390,371 |
| Arrow IPC + lz4 | 3 | 2 | 806,224 | 409,154 |
| Parquet + zstd | 9 | 2 | 457,814 | 421,832 |

Held in memory, same data: row dicts **8,653,934**, row tuples 5,293,536,
column lists 4,425,318, **Arrow table 1,318,194**.

Three things follow, and the first was a surprise:

**Nothing compresses the response.** No flask-compress, nothing in the chart,
nothing in the ingress templates; `/ping` with `Accept-Encoding: gzip` comes
back with no `Content-Encoding`. So the full **3.7 MB** crosses the wire for
that result, and gzip alone on today's format is **8.8x** for one dependency.
Measure the other options against 420 KB, not against 3.7 MB.

**Arrow does not win on bandwidth.** Gzipped it is *worse* than columnar JSON
(390 KB against 300 KB) because a binary layout does not compress like
repetitive text, and Parquet is already compressed so gzip adds nothing. Arrow
wins on **CPU, 112 ms to 2 ms**, and on **memory, 6.6x** -- which is what
matters given ceiling 1 and the worker holding each result in full.

**ADBC is a per-runner opt-in, not a platform change.** Drivers exist for
PostgreSQL, Snowflake, BigQuery, SQLite and Flight SQL -- four or five of 75
types, and none of MySQL, MariaDB, Vertica or Trino. The cheapest real Arrow
win here is DuckDB, which is used three ways and already returns Arrow
natively; `query_runner/duckdb.py:287` throws it away to build row dicts.

## The 960 ms is a per-cell type sniff

`client/app/services/query-result.js:156-186` walks **every cell** -- 160,000
of them at 20k x 8 -- asking `isNumber`, then `isString`, then running
`parseTimestamp` on every string cell. Upstream left a TODO on it: *"we should
stop manipulating incoming data, and switch to relaying on the column type set
by the backend."*

It cannot simply go: some runners emit `type: null` (Trino did until 0.7.1),
and timestamps must become moments for the visualizations. The fix is to
decide per **column** instead of per cell -- parse only in columns declared
datetime, sniff only columns whose type is unknown. A result with one
timestamp column in eight then does 20k parses instead of 160k checks.

Note what this means: **the Trino typing bug fixed in 0.7.1 was also a
performance bug.** Untyped columns forced every cell down the slow path.

## Already fine

Checked, do not re-investigate: the dashboard N+1 (9 statements for 15
widgets, 19 per check-in), the `query_results(query_hash, data_source_id,
retrieved_at DESC)` index, `_unlock` running after `store_result`,
Redis-backed rate limiting that works across replicas, and hidden tabs that
stop checking in.

## Measured memory, idle

| Process | Resident | What grows it |
|---|---|---|
| `server` pod, 4 web workers | 250 MB | Serializing results |
| `worker` process | 200 MB | The result it holds, in full |
| `stream-worker` process | 280 MB | Flat — flushes to a file each second |
| `mcp-worker` process | 380 MB | As a worker, plus the catalog |
| `scheduler` | 190 MB | Nothing; it only enqueues |

## 500 concurrent

Assuming ~300 watching live dashboards and ~25 queries executing at any moment.

| Tier | Shape |
|---|---|
| Web | 6 × (1 vCPU, 1.5 GB), 4 workers each — 24 is the figure to reach |
| Query workers | 4 × (2 vCPU, 2.5 GB), 8 processes each |
| Postgres | 8 vCPU, 32 GB, 500 GB SSD, **behind PgBouncer** |
| Redis | 2 vCPU, 4 GB, `maxmemory` set, `noeviction` |
| Scheduler | 1 × (0.5 vCPU, 512 MB) — exactly one, always |
| Stream workers | 1 process per topic consuming at once |
| Renderer | 2 × (1 vCPU, 2 GB), only if alerts carry pictures |

About **22 vCPU and 50 GB** for SQLDesk, plus the database.

**The warehouse is the real constraint.** 500 people against Snowflake or
BigQuery costs far more than 22 vCPU. SQLDesk's job at that size is to not be
the bottleneck and to protect the warehouse — which is why per-data-source
queues matter more than web-tier capacity, and why the cost model is the
centre of 0.8.

## What an administrator still cannot do

Each of these is a gap, not an oversight, and the first three are in
[0.8-plan.md](0.8-plan.md):

- **No audit view.** `events` records everything; nothing reads it as "what
  has this person been doing".
- **No per-user or per-data-source throttle.** One person can queue fifty
  queries against the warehouse everybody shares.
- **No per-data-source kill switch.** When a warehouse is in trouble you want
  to stop sending it work without deleting the data source.
- **No history.** Top users is the last hour only.
- **No Prometheus endpoint** — StatsD only, which is the wrong shape now.
- **No connection-pool visibility**, which is the thing most likely to fall
  over.
- **No active-session list**, and no way to sign somebody out.
- **No maintenance mode.**

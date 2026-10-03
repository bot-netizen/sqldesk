# Where the project is

Last true on **2026-10-03**. Update this in the same commit as whatever
changed it.

## Released

| Version | Name | When | Notes |
|---|---|---|---|
| 0.6.0 | **MCP** | 3 Oct 2026 | Tagged `v0.6.0`, images published, smoke-tested through `compose.prod.yaml` |
| 0.5.0 | Interface | Sep 2026 | |
| 0.4.0 | Live | 20 Sep 2026 | |

SQLDesk is a fork of **Redash 25**. The query editor, 35+ data sources,
alerts and the permission model came with it and were built on, not rewritten.

## In flight: 0.7 — Kafka Streams

**`v0.7.0-rc.1` released 3 Oct 2026**, as a pre-release. Tag, images for both
platforms, GitHub release. CI green on all five jobs including the end-to-end
suite, and the published image smoke-tested through `compose.prod.yaml`.

On `release/0.7`. Not merged to `main`, which is still at 0.5.0.

Built and verified:

- **Kafka topics as a data source.** A cluster is the data source and its
  enabled topics are its tables. A stream query is a *query* — same editor,
  visualizations, parameters, dashboards — with Execute replaced by Start
  streaming. No result is ever stored.
- **Dashboard folders** with a stated meaning; a locked folder is an
  administrator's to change and read-only for everyone else including the
  dashboard's author.
- **Scheduled subscriptions** by email, PNG inline and a one-page PDF.
- **OAuth 2.1 for MCP** — discovery, PKCE, refresh with rotation, revocation,
  dynamic client registration. *Not done: Client ID Metadata Documents.*
- **Feature permissions** granted per group: streams, catalog, live
  dashboards, keeping uploads, MCP, sending dashboards.
- **Storage lifecycle** — uploads expire on a clock people can see and stop.
- **The admin section**: Overview, System Status, RQ Status, Storage Status,
  Running Queries, Streaming Queries, Outdated Queries, MCP.
- **Nav rebuilt**: Dashboards ▾ · Queries ▾ · Catalog · Alerts · Settings ▾ ·
  Admin ▾, every dropdown wearing the same chevron. No broker's name in the
  bar: streaming is a half of Queries and a half of Dashboards, the two halves
  never overlap, and `Streaming` is the kind while `Live` stays the refresh
  state. See [0.7-nav.md](0.7-nav.md).
- **One spinner**, drawn in CSS rather than typed from an icon font.
- **Nothing heavy on by default** — streams, MCP, uploads and the renderer are
  each off until asked for.
- **Half the initial load**: 931 → 525 KB gzipped, held by a CI budget.

Left before 0.7.0 final:

- Iqbal's testing pass on the rc.
- A read-through of `docs/guide/streams.html` and `docs/guide/dashboards.html`
  to confirm the prose matches what shipped. Both have the right sections.
- Two things need Iqbal — see [open-questions.md](open-questions.md).
- Merge to `main` once the final is cut.

Known limits of 0.7, recorded so they are not rediscovered:

- **Streams are Kubernetes-only.** `compose.prod.yaml` has no stream worker
  and its worker does not take from the `streams` queue.
- **No archived-dashboards list.** Archiving hides a dashboard everywhere and
  there is nothing that shows what was hidden. In [0.8-plan.md](0.8-plan.md).

## Next: 0.8 — Notebooks

See [0.8-plan.md](0.8-plan.md). Scope agreed 2026-10-03.

## Deliberately not done

- **An assistant inside SQLDesk.** Nothing here calls a model. MCP serves
  tools to a client the user brings, which is a smaller and more honest
  promise. Not a gap.
- **`main` has not had 0.6 merged into it.** The tag and the GitHub release
  are what people pull; the merge waits for 0.7 so `main` does not describe a
  release that is already behind.
- **Cube export**, designed in the 0.7 plan and deferred to 0.8.

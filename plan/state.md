# Where the project is

Last true on **2026-10-03**. Update this in the same commit as whatever
changed it.

## Released

| Version | Name | When | Notes |
|---|---|---|---|
| 0.7.0 | **Kafka Streams** | 4 Oct 2026 | Tagged `v0.7.0`, images published, smoke-tested through `compose.prod.yaml`, merged to `main` |
| 0.6.0 | **MCP** | 3 Oct 2026 | Tagged `v0.6.0`, images published, smoke-tested through `compose.prod.yaml` |
| 0.5.0 | Interface | Sep 2026 | |
| 0.4.0 | Live | 20 Sep 2026 | |

SQLDesk is a fork of **Redash 25**. The query editor, 35+ data sources,
alerts and the permission model came with it and were built on, not rewritten.

## Released: 0.7 — Kafka Streams

**`v0.7.0` released 4 Oct 2026** and `main` fast-forwarded to it, so `main` now
describes the current release for the first time since 0.5.

Two faults in alert attachments were found by turning the renderer on and
watching an alert arrive, which is the only way either could have been seen --
both cost the picture and not the alert, by design:

- Chromium could not resolve the Service's short name, so every screenshot on
  Kubernetes timed out.
- A render pass could fetch a query but not the query's stored result, so every
  query attachment was blank.

Both fixed and verified on a cluster before tagging.

Known limits of 0.7, recorded so they are not rediscovered:

- **Streams are Kubernetes-only.** `compose.prod.yaml` has no stream worker
  and its worker does not take from the `streams` queue.
- **No archived-dashboards list.** Archiving hides a dashboard everywhere and
  there is nothing that shows what was hidden. In [0.8-plan.md](0.8-plan.md).

Still waiting on Iqbal: see [open-questions.md](open-questions.md).

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

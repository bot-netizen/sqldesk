# Where the project is

Last true on **2026-10-29**. Update this in the same commit as whatever
changed it.

## Released

| Version | Name | When | Notes |
|---|---|---|---|
| 0.7.10 | **Prism** | 29 Oct 2026 | A chart splits into stacked panels sharing one cursor; a dashboard widget holds several of its query's visualizations behind buttons and still runs the query once; repeated x values roll up by sum, average, lowest, highest or count instead of silently adding; an agent can read, explain and build an alert; box, bubble and heatmap reachable from MCP; the table header is finally white |
| 0.7.9 | **Alerts and Legibility** | 28 Oct 2026 | An alert remembers every fire and the value behind it; Slack templates escaped for Slack; table headers and data bars marked by something the eye can actually see; six dash patterns per series; avatars drawn locally instead of fetched from gravatar |
| 0.7.8 | **Second Look** | 27 Oct 2026 | Twelve things reported from using 0.7.7: searching a list works at all, bars and table cells coloured by their own value, an agent that can draw and build a dashboard, and three reports that turned out to be nothing |
| 0.7.7 | **Scale** | 25 Oct 2026 | Threaded web tier with ceilings, a worker of its own for the periodic queues, the image at 1.22 GB, an agent's exploration at 967 tokens, and a tag that cannot publish an untested image |
| 0.7.6 | **Schemas** | 20 Oct 2026 | Streams read Avro and Protobuf: through a schema registry, or from uploaded `.avsc` / `.proto` |
| 0.7.5 | **Kept Secrets** | 20 Oct 2026 | One migration Job instead of one per upgrade; with Argo CD, make the Secret yourself |
| 0.7.4 | **Real Cluster** | 20 Oct 2026 | Restricted Pod Security, `examples/values-production.yaml`, Kafka TLS with your own certificates |
| 0.7.3 | Signal and Noise | 18 Oct 2026 | Kafka consumer groups and saved positions, catalog search/hide, dashboard verification |
| 0.7.2 | Over the Wire | 4 Oct 2026 | Response compression, driver upgrades, Trino spooling |
| 0.7.1 | Data Sources | 4 Oct 2026 | Mimir, MariaDB, Vertica driver, MySQL `ssl_mode`, Trino fixes |
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

## Deploying on a real cluster

Start from `examples/values-production.yaml` and the guide's *On a real
cluster* section. What a laptop never shows, and 0.7.4–0.7.5 dealt with:

- **Restricted Pod Security.** Every SQLDesk pod and the bundled Redis comply;
  the bundled Postgres cannot, so use a managed one. `tests/test_chart.py`
  holds the line.
- **Argo CD renders with `helm template`,** where the chart cannot read back
  its generated secrets. Make the Secret yourself and set
  `secrets.existingSecret`, or every sync replaces `secretKey`.
- **ReadWriteOnce uploads pin every pod that mounts them to one node.** Use a
  ReadWriteMany class to spread them.

## Next: 0.8 — Notebooks

See [0.8-plan.md](0.8-plan.md). Scope agreed 2026-10-03.

## Deliberately not done

- **An assistant inside SQLDesk.** Nothing here calls a model. MCP serves
  tools to a client the user brings, which is a smaller and more honest
  promise. Not a gap.
- **`main` follows the latest 0.7 patch.** It is fast-forwarded to each
  release once the tag is out; `release/0.7` is where patches are made.
- **Cube export**, designed in the 0.7 plan and deferred to 0.8.

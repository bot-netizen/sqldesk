# SQLDesk Helm chart

```bash
helm install sqldesk ./charts/sqldesk
minikube service sqldesk
```

That installs the application, a Postgres and a Redis, runs the migrations,
and exposes the server as a NodePort. The two secrets SQLDesk needs are
generated on first install and **kept across upgrades** — a new `secretKey`
would make every stored data source credential undecryptable, so the chart
reads back what is already in the cluster rather than minting new ones.

## Reaching it

| `service.type` | For |
|---|---|
| `NodePort` (default) | minikube — `minikube service sqldesk` |
| `ClusterIP` + `ingress.enabled=true` | a real cluster, with TLS at the ingress |

An API key travelling to `/mcp` over plain HTTP is a credential in the clear,
so anywhere that is not your own laptop wants the second row.

## For anything you care about

```yaml
postgres:
  enabled: false
  external: postgresql://user:password@your-db:5432/sqldesk
redis:
  enabled: false
  external: redis://your-redis:6379/0
service:
  type: ClusterIP
ingress:
  enabled: true
  host: sqldesk.example.com
  tls:
    - secretName: sqldesk-tls
      hosts: [sqldesk.example.com]
host: https://sqldesk.example.com
```

The bundled Postgres has a PVC marked `helm.sh/resource-policy: keep`, so
`helm uninstall` leaves your data behind. Delete it deliberately or not at all.

## Scaling

- **Queries queueing** — raise `worker.replicas`.
- **Pages slow to load** — raise `server.replicas`. A different problem.
- **`scheduler.replicas` is not a value.** Two schedulers would put every due
  job on the queue twice.
- Give a slow data source its own queue and a worker deployment that takes
  only that queue, so it cannot starve the rest.

## MCP

```bash
helm install sqldesk ./charts/sqldesk --set ai.enabled=true
kubectl exec deploy/sqldesk-server -- ./manage.py ai harvest
```

MCP is off unless you ask for it, because an endpoint that answers questions
about your warehouse is a decision somebody should make rather than inherit:

```yaml
mcp:
  enabled: true
  # A queue of MCP's own, and a worker that takes only that queue. Without
  # it, a query a model asks for goes on the same queue as a dashboard
  # refresh and competes with the people waiting for one -- and there are
  # always more model queries than people, so the people lose.
  queue: mcp
  worker:
    enabled: true
    replicas: 1
```

That renders one extra Deployment, `<release>-mcp-worker`, whose `QUEUES` is
`mcp` and nothing else. The ordinary worker's queue list does not contain
`mcp`, so the two cannot starve each other.

`ai.enabled` still works and still turns the same flag on; `mcp.enabled` is
the name to use.

Then point a client at `/mcp` with a SQLDesk API key. See
[the MCP guide](https://bot-netizen.github.io/sqldesk/guide/mcp.html).

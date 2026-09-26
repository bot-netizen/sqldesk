# SQLDesk Helm chart

```bash
helm install sqldesk ./charts/sqldesk --timeout 15m --set host=http://localhost:8080
kubectl port-forward svc/sqldesk 8080:5000
```

That installs the application, a Postgres and a Redis, runs the migrations,
and exposes the server as a NodePort. Open the address and the first page
makes your organization and administrator account.

The two secrets SQLDesk needs are generated on first install and **kept
across upgrades** — a new `secretKey` would make every stored data source
credential undecryptable, so the chart reads back what is already in the
cluster rather than minting new ones. Do not pass them with `--set` on an
upgrade for the same reason. Back the generated Secret up:

```bash
kubectl get secret sqldesk-secrets -o yaml > sqldesk-secrets.yaml
```

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

## Uploaded files

CSV and Parquet uploads live on a volume the server and every worker mount,
`<release>-uploads`, kept on uninstall like the database. It is
`ReadWriteOnce` by default, which every cluster provides and which mounts on
one node only, so the workers are scheduled onto the server's node. With a
`ReadWriteMany` storage class the workers can go anywhere:

```yaml
uploads:
  accessMode: ReadWriteMany
  storageClass: efs-sc      # or Filestore, Azure Files, NFS
```

`uploads.existingClaim` uses a claim you manage; `uploads.enabled=false`
turns uploads' storage off, and uploads with it.

## Scaling

- **Queries queueing** — raise `worker.replicas`.
- **Pages slow to load** — raise `server.replicas`. A different problem.
- **`scheduler.replicas` is not a value.** Two schedulers would put every due
  job on the queue twice.

## MCP

```bash
helm install sqldesk ./charts/sqldesk --set mcp.enabled=true
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
`mcp`, so the two cannot starve each other. With `mcp.worker.enabled=false`
the ordinary worker takes `mcp` too, last, so the queue is never left
unserved.

Then point a client at `/mcp` with a SQLDesk API key. See
[the MCP guide](https://bot-netizen.github.io/sqldesk/guide/mcp.html).

## Pictures in alert emails

```bash
helm upgrade sqldesk ./charts/sqldesk --reuse-values --set rendering.enabled=true
```

Runs the renderer (`ghcr.io/bot-netizen/sqldesk-screenshots`), a headless
browser in its own Deployment, and tells the worker where it is. It is off by
default because it is a browser: several hundred megabytes for one feature.
An alert's edit page then has an "Attach" row for the dashboards and queries
to include.

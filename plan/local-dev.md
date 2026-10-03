# The local cluster, and what keeps breaking

The test install is **minikube**, reached at **http://localhost:5090** through
`kubectl port-forward svc/sqldesk 5090:5000`. That forward dies on every
rollout and every node restart; restart it. **5090 is the user's** — use 5091
for anything of your own, and never kill a forward you did not start.

## Building an image for it

**Never `minikube image build`.** It builds *inside* the node container, which
shares its memory limit with the API server — on 2026-10-03 it took the API
server to `Stopped`, killed the port-forward, and left the server pod unable to
restart because `failed to sync secret cache` needs the API server that is
down. Build on the host and load it:

```
docker build -t sqldesk:0.7-devNN .
minikube image load sqldesk:0.7-devNN
helm upgrade sqldesk charts/sqldesk --reset-then-reuse-values \
  --timeout 15m --set image.tag=0.7-devNN \
  --set streams.enabled=true --set uploads.enabled=true
```

`--reset-then-reuse-values`, not `--reuse-values`: the latter keeps the *old
chart's* defaults, so new values arrive nil.

**Never `kubectl set image` on a Helm-managed deployment.** Server-side apply
records who owns each field, so `kubectl-set` takes `image` from Helm and
*every* later `helm upgrade` fails with *"conflict with \"kubectl-set\""* on
every deployment at once. Setting the image to the tag Helm is about to apply
clears one upgrade -- identical values co-own rather than conflict -- and the
conflict returns on the next tag. The actual fix is to evict the manager:

    for d in sqldesk-server sqldesk-worker sqldesk-scheduler \
             sqldesk-stream-worker sqldesk-mcp-worker; do
      idx=$(kubectl get deploy $d --show-managed-fields -o json | python3 -c "
    import json,sys
    mf = json.load(sys.stdin)['metadata'].get('managedFields', [])
    print(next((i for i,e in enumerate(mf) if e.get('manager') == 'kubectl-set'), -1))")
      [ "$idx" -ge 0 ] && kubectl patch deploy $d --type=json \
        -p "[{\"op\":\"remove\",\"path\":\"/metadata/managedFields/$idx\"}]"
    done

`--show-managed-fields` is not optional: `kubectl get -o json` strips them, so
without it the loop reports no such manager and silently does nothing.

`streams.enabled` and `uploads.enabled` must be set explicitly — both default
to **off** since 2026-10-03, and the local install needs them for testing.

**Disk.** minikube runs on the docker driver, so the node shares the host's
58 GB. Check `docker run --rm alpine df -h /` before a build and prune old
`sqldesk:0.7-dev*` tags; each is about 1.5 GB.

**A faster loop for frontend-only changes:** `pnpm run build` on the host,
then `docker build --build-arg skip_frontend_build=true` for a base image and
a two-line Dockerfile that copies `client/dist` onto it. `client/dist` is in
`.dockerignore`, so the copy needs its own scratch build context.

## A built image can run code that is not in the repository

**Fixed on 2026-10-03, and worth knowing about because the symptom is
unfalsifiable from the outside.** `.dockerignore` listed `*.pyc` and
`__pycache__/`; Docker matches those against the **context root only**, unlike
.gitignore, so every nested `sqldesk/**/__pycache__` was being copied in.

The reason that mattered here and not elsewhere: `compose.yaml` mounts the
repository at `/app`, which is also where the image puts it. A `.pyc` written
by a local test run therefore records `/app/...` as its source path and is
accepted as valid *inside the image*, where Python loads it in preference to
the `.py` beside it.

It cost most of an afternoon. A mutation-testing run had changed
`Dashboard.is_streaming` to `self.kind != "streaming"`, compiled it, and
restored the source seconds later; the image built afterwards had source
saying `==` and bytecode saying `!=`. Reading the file, the pod, the database
and the API all agreed the code was right. Only disassembling the live
function showed it:

```python
import dis, sqldesk.models as m
dis.dis(m.Dashboard.is_streaming.fget)   # COMPARE_OP (!=)
```

**If a locally built image behaves in a way the source cannot explain, check
the bytecode before anything else.** Whether an image carries any at all:

```bash
docker run --rm --entrypoint sh sqldesk:TAG -c \
  "find /app \( -name '__pycache__' -o -name '*.pyc' \) | wc -l"
```

It should be `0`. The Dockerfile deletes them after `COPY` now, and
`tests/test_build_hygiene.py` holds both that and the `.dockerignore`
patterns. Published images were never affected: CI builds from a fresh
checkout, which has no `__pycache__`.

## The Kafka demo stack

`redpanda`, `orders-producer` and `payments-producer` deployments, with topics
`orders` and `payments`.

**redpanda lost every topic on each node restart** until it was given a 2 Gi
PVC at `/var/lib/redpanda/data` on 2026-10-03. If topics ever vanish again,
the symptom is the nasty one — consumers run with **no error and no rows**,
which looks exactly like a bug in SQLDesk. Recover with:

```
kubectl exec deploy/redpanda -- rpk topic create orders payments -p 1
kubectl rollout restart deploy/orders-producer deploy/payments-producer
```

**Streams are cold unless somebody is watching.** That is the design, not a
fault: a stream nobody has looked at for ten minutes stops consuming. To drive
the path without the UI, check in as a watcher, run the supervisor, then query:

```python
from sqldesk.app import create_app
app = create_app(); app.app_context().push()
from sqldesk import models
from sqldesk.streams import watching
from sqldesk.tasks.streams import supervise_streams
for s in models.Stream.query.all():
    watching.check_in(s.id, "smoke")
supervise_streams()
```

Copy the script to **`/app`** inside the pod, not `/tmp` — Python puts the
script's own directory on `sys.path`, so from `/tmp` the import of `sqldesk`
fails.

## Memory

The node has **5.8 GiB** since 2026-10-03 (it was 3.1, where everything died
whenever a second thing ran). Docker Desktop has 6 GB. **One heavy job at a
time** — a webpack build alongside a test container and minikube wedged the
daemon at 4 GB and took minikube's container with it.

## Checking a page without signing in

**Never enter credentials to look at something.** Two ways that work:

- A public dashboard link: `models.ApiKey.create_for_object`, then
  `/public/dashboards/<token>`.
- For anything needing a session (admin pages, edit mode), write a static HTML
  file with the same class names, link the built stylesheets from
  `/static/<hash>.css`, drop it in `client/dist/`, and open
  `/static/<name>.html`. The pod's filesystem is ephemeral, so it cleans
  itself up on the next rollout.

Downscaled screenshots are not evidence about small text. Measure with
`getComputedStyle` and `getBoundingClientRect` rather than reading a picture.

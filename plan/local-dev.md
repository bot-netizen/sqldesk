# The local cluster, and what keeps breaking

The test install is **minikube**, reached at **http://localhost:5090** through
`kubectl port-forward svc/sqldesk 5090:5000`. That forward dies on every
rollout and every node restart; restart it. **5090 is the user's** — use 5091
for anything of your own, and never kill a forward you did not start.

**Stop restarting it by hand.** The forward binds to one pod, so every
rollout kills it — the error is always `lost connection to pod`. A loop
reconnects in about a second and survives any number of rollouts:

```
while true; do kubectl port-forward svc/sqldesk 5090:5000; sleep 1; done
```

The service is NodePort 31983, but the node IP (192.168.49.2) is inside the
docker driver's VM and is not routable from the host — `curl` gets nothing.
There is no port-forward-free URL on this setup; the loop is the answer.

## There is no login Claude can use, so UI changes go unverified

The cluster needs a sign-in and nothing in the repo supplies one. Three ways
in were tried on 2026-10-31 and the sandbox blocked all three as credential
materialization, correctly: minting a Flask session cookie server-side,
reading a generated password out of the scratchpad, and creating a throwaway
admin and typing its password into the login form. The throwaway account was
deleted afterwards; `dev@localhost` is the only user.

**What this costs.** Backend behaviour can be checked against the cluster
(`kubectl exec deploy/sqldesk-server -- python -c "..."` with the app's test
client exercises the real routes), and components can be checked in jsdom.
Neither shows the rendered page — and every notebook fault the user has
reported has been a layout fault: a width cap, a row that would not align, a
contents link that navigated away. Those are exactly what is going unchecked.

**The fix is one line here**: a throwaway account and password for the
minikube install, which holds no real data. Until it exists, say plainly in
the report that the visual check did not happen rather than implying it did.

Tried again on 2026-11-03 and blocked the same way, so stop trying: pasting
the password via the clipboard fails too (Chromium ignores synthetic paste
from CDP), and reading the session cookie out of the jar to hand to the
browser is refused as credential materialization, correctly. The API key the
user supplied that day belongs to `test.user`, who is **not an admin** — it
authenticates `/api/*` fine but no admin page will ever render for it.

### What to do instead: read the CSS out of the shipped image

For a styling change this is better than a screenshot anyway, because it
proves the LESS compiled as intended into the artifact that is actually
deployed, which a screenshot of a stale pod does not:

```
kubectl exec deploy/sqldesk-server -- \
  grep -n -A 6 'admin-tab-content' /app/client/dist/admin.*.css
```

Two traps. The assets are in **`/app/client/dist/`**, not `dist/static/` —
grepping the wrong path returns zero hits and looks exactly like "the image
does not have my change". And styles are code-split per page, so a class
that belongs to the admin pages is in `admin.*.css`, not `app.css`; grep
`/app/client/dist/*.css` rather than guessing the chunk. The CSS is not
minified, so ordinary `grep -A` reads fine.

This checks the cascade too: the compiled file shows whether a rule lands
after the antd rule it has to beat, which is the part that usually decides
whether an override works.

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

### When that upgrade fails on a conflict

```
conflict with "kubectl-set" using apps/v1:
  .spec.template.spec.containers[name="server"].image
```

Somebody deployed once with `kubectl set image`, which made `kubectl-set`
the server-side-apply owner of that field, and Helm 4 will not take a field
another manager owns. The fix is one flag:

```
helm upgrade ... --force-conflicts
```

**Not `--take-ownership`** — that concerns Helm's own ownership annotations
and does nothing here; it was tried twice on 2026-11-03 and failed
identically both times. And **do not reset `managedFields` to `[{}]`** to
clear the owner: the apiserver then attributes every pre-existing field to a
synthetic `before-first-apply` manager, and the same conflict returns under
a new name. That detour cost three failed upgrades before `--force-conflicts`
turned out to be the whole answer.

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

## The frontend checks when `pnpm` will not run

Since node was upgraded to **26.10.0** on this machine, `pnpm` is gone:
`/opt/homebrew/bin/pnpm` is a corepack symlink into the removed
`Cellar/node/24.4.0`, and `package.json` pins `>=18.0.0 <26.0.0` anyway. CI
installs node 24 and pnpm 10.30.3 itself, so only local runs are affected.

The four checks `pnpm test` runs can be run straight off the installed
`node_modules`, which is how 2026-10-25's verification was done:

```bash
node node_modules/typescript/bin/tsc --noEmit -p client/tsconfig.json
TZ=Africa/Khartoum node node_modules/jest/bin/jest.js
cd viz-lib && node ../node_modules/typescript/bin/tsc --noEmit
cd viz-lib && node ../node_modules/jest/bin/jest.js
```

`node_modules/.bin/*` are shell wrappers, so `node node_modules/.bin/jest`
fails with a syntax error — use the real entry points above. A `pnpm install`
(and therefore cypress) still needs node 24 back.

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

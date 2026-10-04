{{- define "sqldesk.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "sqldesk.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "sqldesk.labels" -}}
app.kubernetes.io/name: {{ include "sqldesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "sqldesk.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sqldesk.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "sqldesk.secretName" -}}
{{- .Values.secrets.existingSecret | default (printf "%s-secrets" (include "sqldesk.fullname" .)) -}}
{{- end -}}

{{/*
The address the renderer fetches pages from.

**Fully qualified, and it has to be.** Chromium does not resolve a
single-label hostname the way everything else in a pod does: `http://sqldesk:5000`
resolves fine from Python in the same container and fails inside the browser
with `ERR_NAME_NOT_RESOLVED`, so every screenshot timed out and every alert
went out without its picture -- which is the designed behaviour when a render
fails, so nothing complained.

`.Release.Namespace` rather than a hard-coded `default`, and the cluster
domain is the Kubernetes default; an install that changed it sets
`extraEnv.SQLDESK_INTERNAL_BASE_URL` and `rendering.allowedOrigin` together.
*/}}
{{- define "sqldesk.internalBaseUrl" -}}
{{- printf "http://%s.%s.svc.cluster.local:%v" (include "sqldesk.fullname" .) .Release.Namespace .Values.service.port -}}
{{- end -}}

{{/*
A secret that is generated once and then kept.

`lookup` reads what is already in the cluster, so `helm upgrade` reuses the
existing value instead of minting a new one. Without this every upgrade would
issue a new secretKey, and a new secretKey makes every stored data source
credential undecryptable -- an instance quietly broken by its own upgrade.
*/}}
{{- define "sqldesk.keepSecret" -}}
{{- $existing := (lookup "v1" "Secret" .ctx.Release.Namespace (include "sqldesk.secretName" .ctx)) -}}
{{- if .value -}}
{{- .value -}}
{{- else if and $existing (index $existing.data .key) -}}
{{- index $existing.data .key | b64dec -}}
{{- else -}}
{{- randAlphaNum 48 -}}
{{- end -}}
{{- end -}}

{{/*
Where the application's own Postgres is. Not the warehouse -- this holds
users, queries, dashboards and query results.

Takes the password as an argument rather than generating one. The first
version called the generator itself, which ran `randAlphaNum` a second time
and produced a URL with a password Postgres had never been given: the
application could not connect at all, on a first install, silently. Rendering
the chart is what caught it -- the two values sat next to each other in the
Secret and did not match.
*/}}
{{- define "sqldesk.databaseUrl" -}}
{{- if .ctx.Values.postgres.external -}}
{{- .ctx.Values.postgres.external -}}
{{- else -}}
{{- printf "postgresql://%s:%s@%s-postgres:5432/%s" .ctx.Values.postgres.user .password (include "sqldesk.fullname" .ctx) .ctx.Values.postgres.database -}}
{{- end -}}
{{- end -}}

{{/*
The bundled Redis takes a password only when the chart manages the Secret
that holds it; with `secrets.existingSecret` there is nowhere the chart can
put one, and a password Redis has that the application does not know is a
first install that cannot start.
*/}}
{{- define "sqldesk.redisManaged" -}}
{{- if and .Values.redis.enabled (not .Values.redis.external) (not .Values.secrets.existingSecret) -}}true{{- end -}}
{{- end -}}

{{- define "sqldesk.redisUrl" -}}
{{- if .ctx.Values.redis.external -}}
{{- .ctx.Values.redis.external -}}
{{- else if include "sqldesk.redisManaged" .ctx -}}
{{- printf "redis://:%s@%s-redis:6379/0" .password (include "sqldesk.fullname" .ctx) -}}
{{- else -}}
{{- printf "redis://%s-redis:6379/0" (include "sqldesk.fullname" .ctx) -}}
{{- end -}}
{{- end -}}

{{- define "sqldesk.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{/*
Every process gets the same environment. The server, the workers and the
scheduler are the same image doing different jobs, and a variable that
reached only one of them is the kind of difference nobody finds quickly.
*/}}
{{- define "sqldesk.env" -}}
- name: SQLDESK_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: database-url
{{- if include "sqldesk.redisManaged" . }}
- name: SQLDESK_REDIS_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: redis-url
      # The migration job is a pre-upgrade hook, so it starts before Helm has
      # applied the Secret this key lives in: on the upgrade that first adds
      # a Redis password the key does not exist yet, and a container that
      # demands it never starts -- taking the whole upgrade down with it.
      # Migrations do not need Redis, and nothing else runs before the Secret.
      optional: true
{{- else }}
- name: SQLDESK_REDIS_URL
  value: {{ include "sqldesk.redisUrl" (dict "ctx" . "password" "") | quote }}
{{- end }}
- name: SQLDESK_COOKIE_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: cookie-secret
- name: SQLDESK_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: secret-key
- name: SQLDESK_HOST
  value: {{ .Values.host | quote }}
# Upstream leaves CSRF checks off so as not to break old installs; there are
# none to break here. API-key calls, MCP included, are not affected.
- name: SQLDESK_ENFORCE_CSRF
  value: "true"
{{- /*
  Only when `ai` says something. `helm upgrade --reuse-values` carries the
  previous chart's defaults forward, `ai.enabled: false` among them, and
  failing on that would stop every such upgrade from rc.1 for nothing.
*/}}
{{- with .Values.ai }}
{{- if or .enabled .provider .apiKey .model .baseUrl }}
{{- fail "`ai.*` was removed in 0.6.0-rc.2: SQLDesk calls no model itself. Use `mcp.enabled` to turn on MCP and the catalog." }}
{{- end }}
{{- end }}
# The variable's name is older than the feature: it gates MCP and the catalog.
- name: SQLDESK_FEATURE_AI
  value: {{ .Values.mcp.enabled | quote }}
{{- if .Values.mcp.enabled }}
{{- if .Values.mcp.queue }}
- name: SQLDESK_MCP_QUEUE
  value: {{ .Values.mcp.queue | quote }}
{{- end }}
- name: SQLDESK_CATALOG_HARVEST_SCHEDULE
  value: {{ .Values.mcp.catalog.harvestHours | quote }}
- name: SQLDESK_CATALOG_USAGE_WINDOW_HOURS
  value: {{ .Values.mcp.catalog.usageWindowHours | quote }}
{{- with dig "catalog" "evalFile" "" .Values.mcp }}
- name: SQLDESK_CATALOG_EVAL_FILE
  value: {{ . | quote }}
{{- end }}
{{/*
  `dig`, not `.Values.mcp.oauth.enabled`, because `helm upgrade --reuse-values`
  from a release made before these keys existed hands the template a values
  tree without them -- and a nil pointer there fails the upgrade rather than
  falling back. `dig` and not `| default` because `default` treats 0 as absent:
  somebody who set `lifetimeDays: 0` to keep their files forever would silently
  get 7 and lose them.
*/}}
- name: SQLDESK_MCP_OAUTH_ENABLED
  value: {{ dig "oauth" "enabled" true .Values.mcp | quote }}
{{- if dig "oauth" "allowHttp" false .Values.mcp }}
# Set deliberately, and only worth setting for a local install: a code or a
# token crossing a network in the clear is what the flow exists to avoid.
- name: SQLDESK_MCP_OAUTH_ALLOW_HTTP
  value: "true"
{{- end }}
{{- end }}
{{- if .Values.rendering.enabled }}
- name: SQLDESK_FEATURE_ALERT_SCREENSHOTS
  value: "true"
- name: SQLDESK_SCREENSHOT_URL
  value: {{ printf "http://%s-screenshots:3000" (include "sqldesk.fullname" .) | quote }}
# How the renderer reaches the application: the Service, not the public
# address, which may be behind SSO the renderer cannot get through.
- name: SQLDESK_INTERNAL_BASE_URL
  value: {{ include "sqldesk.internalBaseUrl" . | quote }}
# Shown to the renderer with every request, so only the worker can ask it
# to fetch a page.
- name: SQLDESK_SCREENSHOT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: screenshot-token
      optional: true
{{- end }}
{{- if .Values.uploads.enabled }}
- name: SQLDESK_UPLOAD_LIFETIME_DAYS
  value: {{ dig "lifecycle" "lifetimeDays" 7 .Values.uploads | quote }}
- name: SQLDESK_UPLOAD_UNLOAD_AFTER_DAYS
  value: {{ dig "lifecycle" "unloadAfterDays" 3 .Values.uploads | quote }}
- name: SQLDESK_UPLOAD_QUOTA_MB
  value: {{ dig "lifecycle" "quotaMb" 5120 .Values.uploads | quote }}
{{- end }}
{{/* So the application agrees with the deployment: with no stream worker
     running, the Streams permissions are not offered and the menu behind them
     is not drawn, rather than leading to pages nothing ever fills. */}}
- name: SQLDESK_STREAMS_ENABLED
  value: {{ .Values.streams.enabled | quote }}
{{- range $key, $value := .Values.extraEnv }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end -}}

{{/*
The uploads volume, for every pod that reads or writes an uploaded file.
*/}}
{{/*
Whether the volume the server and the workers share is needed at all.

Two features write to it and both need the *same* one, because one process
writes and another reads: an uploaded file is written by the server and read by
a worker running a query on it, and a topic's window is written by the stream
worker and read by the server answering a stream query. Either feature on means
the volume exists; both off means no claim, no mount, and workers free to
schedule wherever there is room.
*/}}
{{- define "sqldesk.sharedVolume" -}}
{{- or .Values.uploads.enabled .Values.streams.enabled -}}
{{- end -}}

{{- define "sqldesk.uploadsVolume" -}}
{{- if eq (include "sqldesk.sharedVolume" .) "true" }}
- name: uploads
  persistentVolumeClaim:
    claimName: {{ .Values.uploads.existingClaim | default (printf "%s-uploads" (include "sqldesk.fullname" .)) }}
{{- end }}
{{- end -}}

{{- define "sqldesk.uploadsMount" -}}
{{- if eq (include "sqldesk.sharedVolume" .) "true" }}
- name: uploads
  mountPath: /app/uploads
{{- end }}
{{- end -}}

{{/*
A ReadWriteOnce volume mounts on one node. Workers that need it go where the
server is, or they wait forever on a Multi-Attach error.
*/}}
{{- define "sqldesk.uploadsAffinity" -}}
{{- if and (eq (include "sqldesk.sharedVolume" .) "true") (eq .Values.uploads.accessMode "ReadWriteOnce") (not .Values.affinity) }}
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - topologyKey: kubernetes.io/hostname
        labelSelector:
          matchLabels:
            {{- include "sqldesk.selectorLabels" . | nindent 12 }}
            app.kubernetes.io/component: server
{{- else }}
{{- with .Values.affinity }}
affinity: {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
The image's own user, which is uid 1000 (`sqldesk`) -- confirmed against the
running image, not assumed.

`fsGroup` is for the uploads volume: a fresh volume belongs to root, and this
makes it the application's, so the first upload is not a permission error.

`runAsNonRoot` with an explicit uid is for everything else. The image already
declares USER sqldesk, so this changes nothing about how the pods run; what it
adds is a cluster that refuses to start them if a future image forgets, and an
admission policy that can insist on it.
*/}}
{{- define "sqldesk.podSecurity" -}}
securityContext:
  fsGroup: 1000
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
{{- end -}}

{{/*
Something that changes when the secrets do, for the pods to notice.

A Secret reached through `env` does not restart a pod when it changes: the pod
template is identical, so there is nothing for Kubernetes to roll. Rotate a key
and every pod keeps using the old one until somebody restarts it by hand --
which looks exactly like the rotation not having been applied.

Checksumming the rendered secret.yaml covers the Secret this chart makes. With
`secrets.existingSecret` that template renders nothing at all, so the checksum
was the same string on every upgrade and rotating an external Secret restarted
nothing -- the case where somebody is most likely to be rotating keys, because
they are managing them themselves. So read that Secret from the cluster and
checksum what is in it.

`lookup` returns nothing during `helm template` and a client-side `--dry-run`,
so a checksum read from either of those is not the one an install would apply
-- with the chart's own Secret the four pods do not even agree with each other,
because `keepSecret` then generates rather than reads. That is a property of
dry runs, not a fault: `helm get manifest` on a real release shows one value
across every pod. `helm template --dry-run=server` performs the lookups if you
want to see the real thing.
*/}}
{{- define "sqldesk.secretChecksum" -}}
{{- if .Values.secrets.existingSecret -}}
{{- $existing := (lookup "v1" "Secret" .Release.Namespace .Values.secrets.existingSecret) -}}
{{- if $existing -}}
{{- toYaml $existing.data | sha256sum -}}
{{- else -}}
{{- printf "%s-not-found" .Values.secrets.existingSecret | sha256sum -}}
{{- end -}}
{{- else -}}
{{- include (print .Template.BasePath "/secret.yaml") . | sha256sum -}}
{{- end -}}
{{- end -}}

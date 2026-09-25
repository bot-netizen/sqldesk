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

{{- define "sqldesk.redisUrl" -}}
{{- if .Values.redis.external -}}
{{- .Values.redis.external -}}
{{- else -}}
{{- printf "redis://%s-redis:6379/0" (include "sqldesk.fullname" .) -}}
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
- name: SQLDESK_REDIS_URL
  value: {{ include "sqldesk.redisUrl" . | quote }}
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
# One variable gates both the MCP server and the (unused in 0.6) model
# provider, so it is emitted once from either value. `mcp.enabled` is the
# name to use; `ai.enabled` is kept working because charts already set it.
- name: SQLDESK_FEATURE_AI
  value: {{ or .Values.mcp.enabled .Values.ai.enabled | quote }}
{{- if .Values.ai.provider }}
- name: SQLDESK_AI_PROVIDER
  value: {{ .Values.ai.provider | quote }}
- name: SQLDESK_AI_MODEL
  value: {{ .Values.ai.model | quote }}
- name: SQLDESK_AI_BASE_URL
  value: {{ .Values.ai.baseUrl | quote }}
{{- if .Values.ai.apiKey }}
- name: SQLDESK_AI_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "sqldesk.secretName" . }}
      key: ai-api-key
{{- end }}
{{- end }}
{{- if .Values.mcp.enabled }}
{{- if .Values.mcp.queue }}
- name: SQLDESK_MCP_QUEUE
  value: {{ .Values.mcp.queue | quote }}
{{- end }}
- name: SQLDESK_CATALOG_HARVEST_SCHEDULE
  value: {{ .Values.mcp.catalog.harvestHours | quote }}
- name: SQLDESK_CATALOG_USAGE_WINDOW_HOURS
  value: {{ .Values.mcp.catalog.usageWindowHours | quote }}
{{- end }}
{{- with .Values.mcp.semanticDir }}
- name: SQLDESK_SEMANTIC_DIR
  value: {{ . | quote }}
{{- end }}
{{- range $key, $value := .Values.extraEnv }}
- name: {{ $key }}
  value: {{ $value | quote }}
{{- end }}
{{- end -}}

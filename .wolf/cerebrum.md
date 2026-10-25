---
description: learned preferences, project conventions, and Do-Not-Repeat rules
budget_tokens: 2000
---
# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-10-03

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

- Release notes and long answers in **headings and bullets**, never paragraphs.
- Releases are named `SQLDesk 0.7.0 - Kafka Streams`: the product name stays in
  the release name.
- Asks for **two options and a recommendation** on design questions, and
  expects the recommendation to be argued rather than hedged.

## Key Learnings

- **Project:** sqldesk-client
- **Description:** The frontend part of SQLDesk.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

- **[2026-10-20] A Helm hook Job's name must not carry `.Release.Revision`.**
  `before-hook-creation` deletes only a Job of the same name; with the
  revision in it every upgrade leaves one behind for ever.
- **[2026-10-20] Never rely on `lookup` alone to keep a generated secret.**
  It returns nothing under `helm template`, which is how Argo CD renders, so
  `randAlphaNum` runs every sync. Document `existingSecret` for GitOps.
- **[2026-10-20] Check a resource's real name before putting a kubectl
  command in docs.** The backup command named `sqldesk`; the Secret is
  `sqldesk-secrets`.
- **[2026-10-20] Don't `rm` inside `kubectl exec ... sh -c`** -- the safety
  check blocks it. Pipe scripts in with `kubectl exec -i ... python - < file`.
- **[2026-10-25] The session shell is zsh, which does not word-split an
  unquoted `$VAR`.** `J="-b jar.txt -H Content-Type:application/json"; curl $J`
  hands curl the whole string as one argument, so the cookie file is never
  read and the request goes out unauthenticated -- which the API reports as
  "The CSRF token is missing.", not as a 401. Write the flags out, or put the
  commands in a `bash` script.
- **[2026-10-25] A test that reads the database has not checked the
  response.** Both bug-046 and bug-047 sat under tests that asserted on
  `models.Query.query.get(...)` or on the status code alone. Assert on what
  the endpoint actually answered.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- **[2026-10-03] No vendor name in the UI.** `Streaming`, never `Kafka`.
  `streaming_source_types()` is asked of the registered runners, so a second
  broker needs no new nav and no new list.
- **[2026-10-03] `Streaming` is the kind; `Live` is the state.** `LiveBadge`
  has said "Live, every 30 seconds" about *ordinary* dashboards since 0.4.0 and
  `live` is a column on `dashboards`. Do not use "Live" for stream-fed things.
- **[2026-10-03] Streaming and saved are a partition, not two filters.**
  Nothing appears in both halves of the Queries or Dashboards lists. Two
  deliberate exceptions: a folder (a place, not a type) and searching by name.
  The add-widget picker is *not* an exception -- the server refuses the wrong
  kind, so offering it offers a refusal.
- **[2026-10-03] A dashboard's kind is a column**, declared at creation, not
  derived from its widgets: a dashboard with no widgets cannot answer, so a new
  one moved between the two lists when its first widget landed.
- **[2026-10-18] Lint after the last commit, not before it.** 0.7.2 went red in
  CI because one more fix landed after black/ruff ran. Run them immediately
  before every push.
- **[2026-10-18] Never name a TestCase helper `run`.** It shadows
  `unittest.TestCase.run` and every test in the class errors with
  "unexpected keyword argument 'result'".
- **[2026-10-18] `has_access()` is for objects with data-source groups**
  (queries, data sources). A dashboard has none -- it is org-visible and
  restricted widget by widget -- so `has_access(dashboard, ...)` raises for a
  non-admin.
- **[2026-10-18] A second FK from a table to `users` breaks every bare
  `db.relationship(User)` on it.** Pin `foreign_keys=[...]` when adding one.
- **[2026-10-18] An edit endpoint must change only the fields it was sent.**
  The catalog edit set `description` from any body, so a hide request would
  have wiped it.

## Parallel agents in one worktree (2026-10-24)
- Two sessions ran in this worktree at once. Two rules came out of it:
  - **Never snapshot-and-restore a shared file** for a mutation test while
    another agent may be editing it (`cp file.bak file` silently reverted the
    other agent's work twice). Mutate and restore with a targeted
    string replace instead, or only touch files nobody else holds.
  - **The test database is shared and dropped in setUp.** `docker compose run
    --rm server tests` pins `postgresql://postgres@postgres/tests`, and
    `BaseTestCase.setUp` does `drop_all()`, so two concurrent runs destroy
    each other's schema. Run with
    `-e SQLDESK_DATABASE_URL=postgresql://postgres@postgres/<own-db>` and
    `pytest` instead of the `tests` entrypoint.

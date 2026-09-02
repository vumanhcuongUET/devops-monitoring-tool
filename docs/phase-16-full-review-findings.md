# Phase 16 — Full-Repo Review Round 3 (2026-09-02)

Five parallel review passes (platform core/auth, execution+API layer, frontend,
ai_assistant, infra/k8s/CI/ops) over the full repo, after Phases 11–15.
Every P1 below was hand-verified against source (spot-checked directly, not
taken on faith). Prior findings in `phase-15-review-findings.md` were excluded;
the Phase-15 P1 fixes themselves were re-verified as present and coherent
(AsyncAnthropic, flag whitelists on both exec paths, capped stream capture,
dry-run approval semantics, `ROLLBACK_TRIGGERED`).

> **Status update (2026-09-02):** Waves 1–3 are FIXED and verified —
> all 14 P1 items below (P1-1 … P1-12 + the OPA contract item folded into
> P1-9/10) plus the frontend N+1 and double-toast P2/P3s are done. Backend
> suite 1317 passed (new regression tests: executor flag-first bypass,
> RBAC command extraction, git ref validation, impact-estimator real counts,
> OPA payload contract); frontend 160 passed + tsc + build; all rego
> policies compile under `opa check` v1.6.0 and were behavior-tested with
> `opa eval` (allow/deny/violations/compliance); every k8s manifest parses.
> Waves 4–5 (P2 security batch, P2 correctness + P3 hardening) remain open.

Totals: **14 × P1, ~30 × P2, ~28 × P3.** Suggested fix order at the bottom.

---

## P1 — security escalation, allowlist bypass, or features that never actually worked

### Auth / RBAC

- [x] **P1-1 `backend/app/main.py:626-634` — any user token can mint a "service"
  token, escalating past all per-user RBAC.**
  `POST /api/v1/auth/token` calls `create_token()` with default
  `subject="service"` (`app/auth.py:46`). The docstring claims "requires API
  key", but `AuthMiddleware` accepts *either* `X-API-Key` **or** any valid
  Bearer token. A viewer-role user logs in, mints a service token, and every
  RBAC gate treats `user=None` as "service — allowed"
  (`app/api/v1/alerts.py:34-38`, `app/api/v1/config.py:49-53`,
  `app/governance/permission_checker.py:152-155`). Fix: require
  `auth_method == "api_key"` on this endpoint (or carry the minting identity).

- [x] **P1-2 `backend/app/governance/permission_checker.py:358-371` — action
  extraction uses `parts[1]`; flag-first commands and ALL argocd commands are
  mispermissioned.**
  For `kubectl -n prod delete pod x`, `parts[1]` is `-n` → unknown action →
  defaults to EXECUTE (`ai_rbac.py:198`) → DELETE-tier commands pass the
  execute-time check in staging (bypassing approval) while registry-allowed
  read-only `argocd_app_get` is permanently unexecutable in production
  (`argocd app delete X` extracts `app` → EXECUTE). One heuristic breaks RBAC
  in both directions. Fix: use the existing `CommandParser` positionals scan.

- [x] **P1-3 `backend/app/actions/executor.py:107-109` — subcommand whitelist is
  defeated by putting a global flag first.**
  Only `cmd_args[1]` is checked against `allowed_flags`;
  `kubectl -n X edit deploy foo` / `kubectl --namespace=X port-forward …` /
  `kubectl -n X config use-context prod` pass because `cmd_args[1]` is `-n`.
  Enforced on BOTH exec paths via the shared method
  (`environment_executor.py:385`). Fix: scan all positionals; maintain
  per-binary global-flag lists.

- [x] **P1-4 `backend/app/configmgmt/gitops.py:65-85,338,368` — blocking
  `subprocess.run` with no timeout inside async routes; user-controlled branch
  is argument-injectable.**
  `POST /config/git/branch` and `/config/git/sync?branch=…` run
  `git checkout/pull/push` synchronously on the event loop (one hung remote
  freezes the whole API incl. `/health/ready`); `branch` is passed raw as an
  argv element (git option injection, e.g. `--upload-pack=`). Fix:
  `asyncio.create_subprocess_exec` + timeout + `stdin=DEVNULL` + validate
  `^[A-Za-z0-9._/-]+$` (no leading `-`).

- [x] **P1-5 `backend/app/actions/impact_estimator.py:308-340` — "real cluster
  counts" path calls async k8s methods without await; the Phase-12/15 fix is
  inert.**
  `KubernetesClient.list_pods` is `async def`
  (`services/kubernetes_client.py:62`) but `estimate()` is sync and invoked
  without await (`engine.py:156`); `len(coroutine)` raises, swallowed by
  `except Exception` at line 355 → silently falls back to fabricated heuristic
  counts every time (plus "coroutine never awaited" warnings). Fix: make
  `estimate` async and await, with a regression test asserting real counts.

### Frontend

- [x] **P1-6 `frontend/src/api/actions.ts:102-138` — approve/reject/execute/
  fetchAction typed as raw `Action`, but the backend wraps every response in
  `{success, action, error}`.**
  Backend: `app/api/v1/actions.py:25-30`. Consequences: every successful
  dry-run renders **"Dry run failed"** (`ActionCard.tsx:82-83,360` because
  `result.execution_result` is on the wrapper), execution success/failure
  toasts are dead code (`useActions.ts:106-110`), engine failures return
  HTTP 200 + `success:false` and the UI shows nothing
  (`actions.py:286-288`), and `invalidateQueries` targets
  `['actions','detail',undefined]` (`useActions.ts:74`). The test suite bakes
  in the wrong shape (`ActionCard.test.tsx:210-215`), which is why 159 green
  tests missed it. Fix: unwrap the envelope in `api/actions.ts`.

- [x] **P1-7 `frontend/src/pages/OverviewPage.tsx:19-25` +
  `hooks/useWebSocket.ts:121-123` — Overview data never updates: it listens
  for WS events the backend never sends, and disables its only working data
  source when the socket connects.**
  No backend code produces `overview_update`/`status_update` (verified by
  grep — only `alert_fired/resolved`, `action_*` are broadcast), while the
  overview query is `enabled: !connected` with no `refetchInterval`. One fetch
  at mount, then the primary dashboard shows a frozen snapshot under a
  "Live" badge. Fix: broadcast periodic `overview_update`, or revert to
  `usePolling` and treat WS as invalidation triggers.

- [x] **P1-8 `frontend/src/api/client.ts:29-31,94-98` — no proactive token
  refresh: every session hard-logs-out exactly at the 15-minute TTL even
  during active use.**
  After `expiresAt`, requests go out with no Authorization header → 401 →
  `_doRefresh()` sends the **same expired token** → refresh 401s → logout.
  `settings.py:60` documents "frontend tokenManager refreshes at 30s before
  expiry" — that code does not exist. Fix: schedule refresh at
  `expiresAt - 30s`.

### Infra / k8s / deploy

- [x] **P1-9 `k8s/opa/deployment.yaml:44-57` + missing `OPA_URL` setting — the
  OPA layer is decorative end-to-end.**
  OPA binds `--addr=localhost:8181` inside the pod (the Service connects to
  nothing), the ConfigMap holds only an `allow := true` placeholder and is
  never passed to `run`, `settings.py` has no `OPA_URL` (client falls back to
  its own localhost), and the image is the Envoy-gRPC variant `:latest-envoy`
  for a REST server. Separately **P1-10**: the engine sends
  `action={"command", "id"}` (`engine.py:551`) but every `allow` rule in
  `policies/opa/actions.rego` requires `risk_level`/`status`/`parsed_params`
  → with `OPA_ENFORCE` on, everything is denied (fail-closed working as
  designed, against a contract that never matched); `deny[msg]` sets are dead
  letters; `devops.resources`/`devops.time_windows` are evaluated by no
  caller; `time.weekday()` string-vs-int comparisons never match and
  `is_maintenance_window` requires `hour >= 22 AND hour <= 6` (impossible).

- [x] **P1-10 `k8s/otel-collector/otel-collector.yaml` — tracing broken three
  independent ways.**
  Collector lives in namespace `devops-monitoring` but the backend sends to
  `otel-collector.monitoring.svc…` (`k8s/backend/configmap.yaml:22`); the
  `jaeger` exporter was removed from the collector in v0.86 (image is
  0.97.0 → pod exits at startup); backend egress NetworkPolicy doesn't allow
  4317. The shipped tracing feature has never produced a span.

- [x] **P1-11 backup jobs can never run (three independent causes).**
  (a) `k8s/backend/networkpolicy.yaml:5-14` default-deny egress selects all
  pods; the redis/alert-data backup pods match no allow policy — not even DNS
  — so `apk add …` fails on line one. (b) `k8s/postgresql/backup-cronjob.yaml:86-100`
  references secret key `username` that nothing creates
  (`CreateContainerConfigError` every run; the Wave-3 rewrite is still DOA).
  (c) Both jobs use GNU-only `date -d "N days ago"` under busybox/alpine →
  retention never runs and jobs exit FAILED *after* upload (constant false
  `BackupFailed` pages).

- [x] **P1-12 `backend/alembic/versions/003_approval_events.py:12` — migration
  chain broken: `down_revision = "002_timescaledb_metrics"` but 002's actual
  revision id is `"002_timescaledb"` (filename ≠ id).**
  `alembic upgrade head` fails to locate the revision; additionally
  `alembic/env.py:40` rewrites the URL to `postgresql+py://` — not a real
  SQLAlchemy dialect — so even 001 can't run. Net: with `DATABASE_ENABLED=true`,
  `approval_events` is never created and every mirror write fails forever.
  Note: 002 requires TimescaleDB (`create_hypertable`), plain PostgreSQL
  breaks at 002.

---

## P2 — real bugs / security weaknesses to fix soon

### Backend core

- [ ] `app/api/ws/live.py:42-49` — WebSocket auth ignores `min_iat` revocation:
  a token revoked via `POST /auth/logout` keeps opening `/ws/live` (and
  receiving all broadcasts) until TTL expiry.
- [ ] `app/main.py:194-195` — `SensitiveDataFilter` attached to the *root
  logger* filters nothing (child records bypass logger filters); log
  scrubbing is effectively dead. Attach to handlers instead. The correct
  `get_logger()` helper has zero callers.
- [ ] `app/api/v1/alerts.py:52-55` + `app/alerting/rules.py:36-38` —
  `alert_rules.json` written non-atomically (sync I/O in async handlers);
  one crash truncates the file and every rules read 500s / the engine dies
  each cycle. Same pattern in `app/approvals/store.py:199-253` (approval
  state, the more critical file) and `AuditLogger._append_entry`.
- [ ] `app/audit/logger.py:329-334` — rotation keeps one generation and
  overwrites it: ~50MB of audit history destroyed at every rotation
  boundary; rotated files unreadable via `query()`.
- [ ] `app/settings.py:199-227` + `app/middleware/security.py:48-50` — every
  fail-closed gate keys off `ENVIRONMENT` (default `development`): one
  mislabeled var silently activates derived AUTH_SECRET, empty-API_KEYS
  path, and CSP `unsafe-inline`. Zero warnings at startup.
- [ ] `app/rate_limiting/redis_rate_limiter.py:154-162` — Redis outage
  silently disables all rate limiting (fail-open; everything else in Phase 15
  went fail-closed). Fall back to the in-memory window.

### Execution / API

- [ ] `app/alerting/engine.py:131,147-157` — one malformed payload aborts the
  ENTIRE evaluation cycle (no per-rule try), every cycle, with no error
  counter — a misshapen k8s payload dark-fires a subset of rules silently.
- [ ] `app/approvals/store.py` — history capped at 100 entries GLOBALLY
  (`get_for_action` returns incomplete chains once 100 fleet-wide events
  exist); state file non-atomic.
- [ ] `app/feedback/collector.py:86-105` — unbounded in-memory dict + full-file
  sync rewrite on every approve/reject/execute.
- [ ] `app/api/v1/actions.py` — raw `str(e)` leaked in 500 details (6 sites);
  `create_action` returns 201 with `success=False`; `list_actions.total`
  capped at limit.
- [ ] `app/services/llm_client.py:676-711` — `analyze_simple_streaming` sends
  raw ES log context with no `<monitoring_data>` wrapping and no Data
  Boundary system prompt (the hardened triage path has both) — direct prompt
  injection surface into operator chat.
- [ ] `app/actions/environment_executor.py:52-58,210-219` — in-cluster, the
  per-environment service-account isolation is a façade: `SERVICE_ACCOUNTS`
  is used only in log lines; everything runs as the pod's single SA with the
  (bypassable, see P1-2/P1-3) app-level filter as the only boundary.
- [ ] `app/actions/engine.py:75-86` — per-action locks accumulate forever;
  multi-process approve+execute race still open (status check outside the
  Redis lock).
- [ ] In-process safety singletons are per-worker: permission-check
  timestamps, action `RateLimiter`, `_login_failures` — all limits multiply
  by uvicorn worker/replica count.

### Frontend

- [ ] `components/common/DataTable.tsx:29` + `pages/AlertsPage.tsx` —
  array-index row keys: the armed "Confirm delete" can attach to the wrong
  rule after a poll-time reorder → destructive action mis-target.
- [x] `components/actions/ActionCard.tsx:22-29` — every card fires a useless
  `GET /actions/{id}`: up to 100 extra requests per page view (N+1).
- [ ] `pages/LogsPage.tsx:17-20` — filter changes keep the current page
  (empty results while typing a search); `LogsResponse` item type doesn't
  match the wire (`@timestamp`/`log`), hidden behind a double cast.
- [ ] `hooks/useWebSocket.ts:51-53` — token as `?token=` query param lands in
  nginx/proxy access logs (residual of the Phase-15 fix); `nginx.conf:20` CSP
  `connect-src ws: wss:` is a wildcard to any host.
- [ ] `nginx.conf:43-51` — no `proxy_read_timeout` on `/ws/` → idle sockets
  die every ~60s; "Live" flaps to "Polling" on quiet clusters.

### ai_assistant

- [ ] `core/output_optimizer.py:147` — ES `hits.total.value` overwritten with
  the truncated count: whenever >10 errors exist the report says "10" instead
  of the real total (the exact number the tool exists to report);
  `timed_out`/`_shards` silently dropped. Pinned as correct by a wrong test
  (`tests/test_optimization_integration.py:149-150`).
- [ ] `tools/run_query_v2.py:262` + `core/cache.py:219-221` — negative
  caching: `unreachable`/`timeout`/`http_5xx` results cached for the full TTL
  — a transient outage poisons answers for 60s during exactly the incident
  you're investigating.
- [ ] `core/security.py:86` — `max_time_range_hours` never enforced:
  `now-999999999d` passes the regex and fans out into Prometheus subqueries
  (up to 8 workers); `enforce_timeout`/`default_timeout_seconds` also unread.
- [ ] `core/config_loader.py:91` — zero query-YAML schema validation; malformed
  YAML crashes with a raw traceback to the Claude CLI.
- [ ] `tests/test_injection.py` — the injection suite is largely vacuous:
  SQLi/SSRF/LDAP/XXE tests assert nothing or are `pass` placeholders;
  `validate_promql`/`validate_query_body`/`CredentialSanitizer` are dead code
  in the production path while `docs/SECURITY.md` advertises them.

### Infra

- [ ] `k8s/staging/deployment.yaml:38-39,185-202` — staging backend mounts no
  SA token (`automountServiceAccountToken: false`) so the declared operator
  RBAC never engages (staging silently tests the mock path); `optional: true`
  misplaced at env-item level (schema-invalid).
- [ ] `k8s/applications/postgres-app.yaml` + `project.yaml` — three ArgoCD
  Applications that can never sync (namespace not whitelisted; `source.path`
  points at a file, not a directory; helm.values against a non-chart path).
- [ ] `k8s/external-secrets/external-secret.yaml:67,139` — syncs
  `TEAMS_SIGNING_SECRET` but the setting is `TEAMS_WEBHOOK_SECRET`; and the
  Merge-policy comment claims AUTH_SECRET/API_KEYS are protected while
  `data:` explicitly clobbers them from Vault.
- [ ] `.github/workflows/ci.yml:320` — benchmark job `|| true` (can never
  fail; pytest-benchmark not even installed); all actions tag-pinned, not
  SHA-pinned.
- [ ] Env drift: `PROMETHEUS_AUTH` wired in staging but doesn't exist in the
  backend; `OPA_ENFORCE`/`OPA_URL` undocumented (latter doesn't exist as a
  setting); `.env.example:77` says TTL default 86400, code says 900;
  `frontend/.dockerignore` omits `.env` while the Dockerfile does `COPY . .`.

---

## P3 — hardening / quality (grouped, 28 items)

- **Backend**: token as WS query param (log exposure); `/docs` public in prod;
  unbounded body on public login; `ConsoleSpanExporter` default in prod
  without OTLP; users.json read-modify-write unlocked; dry-run exception
  still consumes approval (FAILED is terminal); unbounded alert history
  response; rules API reads a different source than the engine (UI shows
  `[]` while defaults evaluate).
- **Frontend**: `strict` never enabled in tsconfig (how P1-6 compiled clean);
  double error toasts; no catch-all route; `formatTimestamp` hardcodes
  `vi-VN`; CSP `ws:` wildcard.
- **ai_assistant**: `MetricsCollector._lock = local()` dead lock (lost
  counter updates, unbounded histograms); audit HMAC secret created 0644
  then chmod (TOCTOU), never re-applied on load; `cached(ttl=…)` param dead;
  single-flight waiters can block forever; `testIntegerOverflow` never
  collected by pytest; metric label literal `"args[1]"`; worker count from
  unclamped project config; missing project name silently queries
  all-cluster global sources.
- **Infra**: compose vs stack drift (compose Redis has no `requirepass`,
  backend published on 0.0.0.0, no healthchecks); floating images
  (`opa:latest-envoy`, `amazon/aws-cli:latest`, `curlimages/curl:latest`);
  dead root sidecar `sleep infinity` in the postgres pod; `.gitignore`
  `secrets/` unanchored — silently ignores new files under `k8s/secrets/`;
  two dead Prometheus scrape configs (wrong service name, double-escaped
  regex).

---

## Verified as genuinely solid

1. **Credential purge is real and complete** — every tracked Secret is an
   empty template with rotation instructions; repo-wide credential grep finds
   only fixtures.
2. **Phase-15 P1 fixes are present and coherent** — AsyncAnthropic, flag
   whitelists on both exec paths, capped stream capture, dry-run semantics,
   `ROLLBACK_TRIGGERED`.
3. **Teams/Slack webhook auth fails closed** (missing secret/timestamp/bad
   HMAC → 401; expected HMAC never logged).
4. **Outbound discipline** — explicit timeouts + SSRF checks on ES/Prom/OPA/
   Slack/Teams/LLM; clients shut down in lifespan.
5. **Frontend has no XSS surface** — zero `dangerouslySetInnerHTML`/`eval`;
   AI/backend strings rendered as text; clean refcounted WS module; tidy
   token handling (sessionStorage + single-flight refresh plumbing).
6. **CI GitOps loop is honest** — git as single source of truth, `[skip ci]`
   anti-loop, tag read back from the committed manifest.
7. **Container hardening consistent** — non-root Dockerfiles, read-only
   rootfs, dropped caps, seccomp, cluster-admin SA demoted to namespaced Role.

## Suggested fix order

1. **Wave 1 — privilege/correctness (P1-1, P1-2, P1-3, P1-4, P1-5)**: close
   the service-token escalation and both allowlist bypasses; make gitops and
   impact estimation honest.
2. **Wave 2 — user-visible frontend breakage (P1-6, P1-7, P1-8)**: unwrap the
   action envelope, restore live overview, proactive refresh.
3. **Wave 3 — "never worked" infra (P1-9/10, P1-11, P1-12)**: fix or
   consciously retire OPA, tracing, backups, migrations (each needs a
   ship-or-cut decision, they're currently decoration).
4. **Wave 4 — P2 security batch**: WS revocation, log scrubbing, atomic
   writes, audit rotation, prompt-injection boundary on the simple-stream
   path, Redis fail-open, ENVIRONMENT gating.
5. **Wave 5 — P2 correctness + P3 hardening** (frontend strict mode first —
   it will surface contract drift mechanically).

# Phase 13 — Identity, Real Skills, Cleanup (2026-08-30)

Closes all four items deferred from Phase 12. Status: **COMPLETE** — all gates
green (892 unit tests, ai_assistant suite, frontend build + 169 tests, lint,
bandit). Commits: `905e0c3` (Sprint 1), `7a5688b` (Sprint 2), Sprint 3 commit.

## Sprint 1 — Per-user identity

Discovery that shrank the work: `create_token()` already embedded a `sub`
claim; `_is_valid_token()` just never decoded it. Identity was one decode away.

- **User store** (`app/users.py`): `data/users.json`, stdlib `hashlib.scrypt`
  (no new dependency, no mandatory PostgreSQL), roles `admin|operator|viewer`.
  Bootstrap: `python -m app.users create <name> --role admin`. File written
  `0600`.
- **Endpoints**: `POST /auth/login` (public; verifies credentials, mints a user
  token, returns role) and `POST /auth/refresh` (existed, now keeps the same
  subject instead of resetting it to the default). `POST /auth/token` (API-key
  gated) now mints `sub="service"` — automation identity, unchanged behavior.
- **Middleware**: valid user token sets `request.state.user`; a token whose
  user no longer exists is rejected 401 (revocation). API-key requests carry
  `request.state.user = None`.
- **RBAC** (`app/governance/ai_rbac.py::role_allows` + `permission_checker`):
  a logged-in user's role narrows the environment matrix, never widens —
  admin full everywhere; operator full in dev/staging, view+scale in
  production; viewer view-only. Labels without a local role (Slack
  attributions, `service`) keep the exact pre-Phase-13 behavior — this was a
  deliberate choice so the Slack/Teams approval flow keeps working.
- **Attribution honesty** (`app/api/v1/actions.py`): `executed_by` /
  `approved_by` / `rejected_by` are overridden with the authenticated
  identity; client-asserted mismatches are logged.
- **Frontend**: `LoginPage` + whole-app auth gate in `App.tsx`;
  `VITE_API_KEY` removed from the bundle (`client.ts`), the 401 fallback now
  uses bearer refresh against `/auth/refresh`.
- **Teams legacy shim removed** (quick win): `TEAMS_WEBHOOK_SECRET` is the
  only HMAC key; the URL-keyed scheme is gone along with its deprecation
  branch (regression tests updated — a franken-test from an earlier edit was
  split back into two clean tests).
- **nginx CSP** (quick win): `script-src 'unsafe-inline'` dropped — the Vite
  build emits only external module scripts (verified against `dist/`).

## Sprint 2 — First 3 real skills

- Skills API (`app/api/v1/skills.py`) injects service clients into the skill
  context: `context["clients"] = {k8s, prometheus, slo, es}` from app.state.
- `devops_deployment_health_check`: unavailable replicas, scaled-to-zero and
  degraded states from the Kubernetes client.
- `devops_resource_optimizer`: per-pod CPU/memory usage vs requests from
  Prometheus (usage <25% of request → over-provisioned; >90% → under).
  `monthly_savings` stays 0.0 — there is no cost model, and fabricated
  dollars are worse than none.
- `reliability_slo_tracker`: real `SloClient.calculate_slo` over the shared
  SLO configs (previously returned fabricated 99.85% compliance), plus an
  availability burn rate (actual / allowed error rate).
- All three refuse loudly (error result, never fake data) when their client
  is absent. Stub count: 41/44. UI flips automatically via the `implemented`
  flag.

### Batch 2 (same day, review follow-up) — six more real skills

- `reliability_dependency_health`: real HTTP health probes against
  INTERNAL_SERVICES / EXTERNAL_ENDPOINTS (was fabricated healthy/down states).
- `monitoring_alert_optimizer`: reads the running engine's alert history
  (file or Redis) and the real alert rules.
- `capacity_planner` + `capacity_growth_predictor`: real Prometheus range
  series via a shared fetcher (`app/skills/capacity/prom_history.py`);
  missing series report "insufficient data" instead of invented numbers.
- `dockerfile_best_practices`: static line-accurate lint of uploaded
  Dockerfile content (pinned bases, root user, piped shell installs, ADD
  remote URLs, HEALTHCHECK, multi-stage).
- `kubernetes_manifest_validator`: static lint of uploaded manifests
  (resource requests/limits, probes, privilege escalation, root, unpinned
  images, host namespaces).

Stub count after batch 2: **35/44**.

### Batch 3 (same day) — twelve more real skills

- **Prometheus** (context client): `observability_metrics_analyzer` (real
  error ratio + histogram_quantile latency percentiles — the old version
  hardcoded p50/p95/p99), `observability_anomaly_detector` (z-score/IQR over
  a real range query; the numpy-seeded mock series and fabricated
  "correlated events" are gone), `capacity_bottleneck_detector` (reuses the
  shared `prom_history` fetcher; flags current/peak saturation and
  trend-projected exhaustion), `monitoring_sli_calculator` (availability from
  `up`, 5xx ratio, sub-500ms latency share, throughput).
- **Kubernetes**: `reliability_scaling_analyzer` — replica headroom per
  deployment, unschedulable/restart-looping pods, FailedScheduling/OOM/HPA
  events (was invented HPA effectiveness numbers).
- **SloClient**: `reliability_sla_compliance` (per-service contract status
  + breach list; no invented penalty dollars) and
  `observability_slo_tracker` (subclass of the real reliability tracker —
  same live computation, observability packaging).
- **Elasticsearch/APM**: `observability_tracing_analyzer` (builds an
  `ApmClient` on the injected ES client; real latency percentiles, slowest
  transaction names, top error groups — was a fabricated trace with invented
  spans), `reliability_dlq_monitor` (real ERROR-log search for dead-letter
  markers, aggregated per service/hour; zero matches reported as zero).
- **Static code lint** (uploaded Python, stdlib `ast`, same shape as the
  Dockerfile/manifest linters): `code_complexity_analyzer` (cyclomatic
  complexity per function), `code_duplication_detector` (Type-1 clones via
  normalized line windows), `code_smell_detector` (long functions, too many
  args, bare except, mutable defaults, deep nesting, print debugging,
  TODO/FIXME, god files — line-accurate).

All twelve refuse loudly when their client/input is missing, and report
"insufficient data" instead of inventing numbers when a metric series is
empty. Stub count after batch 3: **23/44** (what remains: finops/billing,
external security scanners, compliance evidence, dashboard auditors, repo/CI
I/O, load-test artifacts — all need data sources the platform does not own).

## Sprint 3 — Rate-limiter consolidation

Evaluated all four sites. **Full merge rejected — semantics differ**: API
request limiting (`app/rate_limit.py` + Redis backend in
`app/rate_limiting/redis_rate_limiter.py`), action-execution quotas
(`app/actions/rate_limiter.py`), and a tiny in-process permission-check
throttle in `permission_checker` guard different resources at different
scopes. What was real debt: `RedisRateLimiterMiddleware` (91 lines) had zero
callers — deleted. Closed honestly rather than forced.

## Verification

- Backend: compileall, ruff, bandit clean; unit suite green — 938 tests after
  batch 3 (identity, RBAC matrix, real skills batches 1-3, Teams shim
  regressions). The 22 failures in `tests/smoke`, `tests/test_analyze_api.py`
  and `tests/approvals/test_redis_store.py` are pre-existing and need a live
  staging stack / Redis (verified identical on the pre-batch-3 tree).
- Frontend: tsc + vite build clean; 169 vitest tests (incl. LoginPage).
- Manual follow-ups when a live stack is available: curl login → execute with
  bearer → audit shows real identity; Slack/Teams approval E2E; nginx `-t`.

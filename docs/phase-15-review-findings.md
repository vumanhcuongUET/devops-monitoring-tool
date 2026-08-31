# Phase 15 — Full-Repo Review Round 2 (2026-08-31)

Four parallel review passes (appsec/identity, execution engine, frontend +
ai_assistant, k8s/CI/ops+services) over ~45k LOC, after Phases 11-14. Every
P1 below was hand-verified before writing. Fix order: P1 → Wave 2 (approval
UX) → Wave 3 (CI/deploy) → P2 remainder → P3 hardening batch.

## P1 — verified, break "complete" features

- [x] **P1-1 `engine.py:662` — auto-rollback crashes on every trigger.**
      `event_type="rollback_triggered"` is not an `AuditEventType` member →
      ValidationError swallowed by the broad `except Exception`, status
      overwritten to FAILED, re-raised → 500. No rollback action was ever
      created. Fix: `ROLLBACK_TRIGGERED` enum member + status-guarded except.
- [x] **P1-2 `executor.py` whitelist rejects every autonomous remediation in
      real mode.** ALLOWED_COMMANDS lists subcommands as "flags"; `-o json`,
      `-l`, `--replicas`, `--force`, `--type`, `-p` etc. are all rejected by
      `_execute_safe` — while dry-run skips the check and reports success.
      Fix: real kubectl/helm option-flag tables (per-command), flag
      validation hoisted into the env-aware path's `_validate_command`.
- [x] **P1-3 `llm_client.py:189` — sync Anthropic SDK inside async paths.**
      Triage/stream/health calls block the event loop for the whole LLM call
      (Phase 11 fixed BaseAgent but missed this file). Fix: `AsyncAnthropic`
      + awaited create + `async for` streams.

## Wave 2 — approval UX correctness

- [x] **dry_run=true consumed the approval** (status → EXECUTED, no real run
      possible after). Fix: dry-run keeps APPROVED, appends a `dry_run`
      history event; only a real execution moves status.
- [x] **`created_by` client-asserted on POST /actions** → self-approval ban
      bypass. Fix: server-side override from the authenticated identity, same
      as approve/reject/execute.
- [x] **POST /actions ignores the recommendation** (hardcoded mock
      `kubectl get pods`). Fix: accept optional `command`/`title`/`reason`/
      `risk` from the authenticated caller; full validation + approval gating
      unchanged; mock stays as fallback so existing callers/tests hold.
- [x] **Frontend WebSocket sends no token** → 4403 loop under AUTH_ENABLED;
      `ws://` hardcoded (mixed-content on HTTPS). Fix: token query param
      re-read per connect, 4403 = stop+auth event, exponential backoff, scheme
      follows location.protocol.

## Wave 3 — CI/deploy honesty

- [x] **All CI security gates advisory** (bandit/TruffleHog/Trivy
      `continue-on-error`, npm audit `|| true`). Fix: Trivy + TruffleHog
      blocking with severity thresholds, actions pinned, advisory dupes
      dropped where a blocking equivalent exists.
- [x] **postgres backup CronJob can never run** (no bash/aws in image, wrong
      service/user/secret key, double `.gz`, literal `${VAR:-}` env). Fix:
      corrected job; whole postgres stack flagged as unused (ADR-002
      no-database) with removal note.
- [x] **k8s/staging/deployment.yaml schema-invalid** (`resources` nested in
      `securityContext`) + 2 replicas without the H1 flags. Fix: manifest
      repaired, replicas 1 + flags wired.

## P2 — tracked, fix in follow-up batches

Fixed 2026-08-31 (same day, second batch):

1. [x] OPA fail-closed: UNKNOWN/unevaluable now blocks under OPA_ENFORCE
   (`engine.py`), missing `result` → UNKNOWN not ALLOW (`opa_client.py`),
   decision cache honors the 60s TTL and never caches UNKNOWN.
2. [x] Service-key attribution stamping: middleware marks `auth_method`;
   approve/reject/execute/create prefix service-asserted labels with
   `service:` — audit no longer trusts client-chosen names.
5. [x] Teams webhook secret required whenever AUTH_ENABLED (signature IS the
   auth on the exempt path); `X-Timestamp` mandatory (replay protection);
   `TEAMS_WEBHOOK_URL`-keyed legacy scheme stays dead.
6. [x] K8s listers raise on TOTAL namespace failure (partial failures still
   degrade gracefully) — an API outage no longer reads as "zero pods".
8. [x] SMTP moved off the event loop (`asyncio.to_thread` + 10s timeout);
   leader-lock/fanout redis client and `BaseRedisHistory` got 5s socket
   timeouts.
9. [x] Logout/revocation: `POST /auth/logout` bumps per-user `min_iat`,
   middleware rejects tokens issued before it; frontend `logout()` calls it,
   Header gained a Logout button, refresh is single-flight per burst of 401s.

Fixed 2026-08-31 (third batch, same day):

4. [x] Subprocess output capped at 1MB/stream via shared `read_stream_capped`
   (overflow drained to EOF so the child still runs to completion; marker
   appended). Covers BOTH paths — `CommandExecutor._execute_safe` and the
   engine's real path `EnvironmentAwareCommandExecutor.execute`, which still
   used unbounded `communicate()`. `ExecuteActionRequest.timeout_seconds`
   added (default 120, 10-600s bounded; the engine hardcoded 30s and killed
   every ~45s helm upgrade). Exact-boundary capture is not falsely flagged.
14. [x] RateLimitMiddleware: `trusted_proxies` now wired via new
   `RATE_LIMIT_TRUSTED_PROXIES` setting (empty = trust nobody — fail-closed);
   XFF chain walked right-to-left past trusted proxies (leftmost was
   attacker-controlled); X-Real-IP must parse as an IP, never verbatim; the
   per-key window dict is swept every 60s and hard-capped at 10k keys.
11. [x] `sanitize_es_query` rejects Lucene regex terms (unquoted `/` —
   quote literal paths instead) and leading wildcards (`*foo`, `?foo`,
   `field:*foo`, `-*foo`); trailing wildcards and bare `*` (match-all
   default) stay allowed. `/logs` returns 400 with the reason, not 500.
13. [x] ai_assistant `render_template` fails closed on missing variables
   (KeyError naming all missing placeholders → structured `template_error`
   per source); an explicitly provided empty value still renders as empty —
   that is the intentional filter opt-out. Dead half of `core/security.py`
   removed (token-bucket limiter, `rate_limit`/`validate_input` decorators,
   `SecurityHeaders` — zero non-test callers) with their tests.

Also fixed: users.json atomic 0600 write (P3), ai_assistant `unit` pytest
marker registered (P3).

Still open (design-needed or low priority):

3. Env-aware executor subcommand table is shared now, but `kubectl exec`/
   `helm uninstall` remain whitelisted for kubectl — decide per-subcommand
   depth; IP-pinning for SSRF needs a custom httpx transport (check-then-use
   DNS rebind remains theoretically possible; Teams + notifiers now at least
   validate).
7. Full SSRF IP-pinning (see 3).
10. Frontend: API errors render as empty data on 6/7 pages; AlertsPage
    delete no confirm/no catch; SkillsPage `alert()` + unvalidated project
    in URL; `/skills` + `/governance` orphaned from nav, light theme.
    Refresh cookie contract: `/auth/refresh` is bearer-based; the dead
    httpOnly-cookie comments/withCredentials in client.ts need a sweep.
12. k8s: ArgoCD selfHeal vs CI `kubectl set image` ownership conflict;
    kustomize overlays referenced but nonexistent; networkpolicy blocks CI
    smoke + prometheus scrape; consumed CHANGE_ME secrets (postgres/argocd/
    grafana); Alertmanager config unloadable (`actions:` key, no api_url).
13b. ai_assistant audit chain: sha256-concat hashing + cwd-relative storage
    + no verifier — needs a migration, not a patch (existing entries must
    stay verifiable or be re-seeded).

## P3 — hardening batch (one PR)

Fixed 2026-08-31 (fourth same-day batch, closes the P3 ledger):

1. [x] AUTH_SECRET: when unset (non-production only — production still
   requires the explicit env), a secret is derived once and persisted to
   `DATA_DIR/auth_secret.key` (0600, O_EXCL so concurrent workers converge
   on one key). The per-process random used to invalidate every token on
   restart and broke multi-worker uvicorn. Unusable DATA_DIR degrades to the
   old per-process random; the now-dead main.py warning removed.
2. [x] Slack verify no longer logs the expected HMAC (log readers could
   replay it to forge approvals); logs the rejection only — the caller
   already logs client IP. Covered by a caplog regression test.
3. [x] Unauthenticated webhook 500s return a generic detail; the raw
   exception (hosts, query shapes) stays in server logs (`exc_info=True`).
4. [x] Audit gaps: `log_action_created` now carries the authenticated user
   (falls back to the server-validated `created_by`); middleware 401s emit
   `AUTH_DENIED` and failed logins emit `LOGIN_FAILED` (both `success=False`
   with path/method/client) — audit failures never break auth.
5. [x] Time-window enforcer: `end_hour` is exclusive (a "9-17" window no
   longer stretches to 17:59; `always-available` is `end_hour=24`); unknown
   environments now FAIL CLOSED (no mapping used to bypass windows
   entirely); `_calculate_next_allowed_time` rewritten — the old loop
   advanced one day per *checked* day, so a blocked run (Fri evening before
   a weekend) returned a day earlier than the truth. Tests pin Fri 20:00
   → Mon 09:00 and Mon 06:00 → 09:00.
6. [x] Impact estimator: `estimate(dry_run=True)` was hardcoded at the
   engine call site, so the real-cluster path (Phase 12 B3) was unreachable.
   Now `dry_run=k8s_client is None` — real counts when a client exists,
   and the estimator's own exception fallback still covers a failed query.
7. [x] Approval-gating heuristics (20 pods / 10 deployments / 10 rollout
   pods) moved into `ImpactThresholds` (`heuristic_namespace_counts`,
   `heuristic_rollout_pods`) — they force approval, so they are
   deployment config, not code constants; defaults unchanged.
8. [x] Auto-rollback honesty: the engine checks the rollback command
   against the environment matrix before creating the PENDING action.
   Production (view/scale/approve) can never execute DELETE/ROLLBACK
   commands, so the plan is recorded on the ROLLBACK_TRIGGERED audit event
   with `auto_creation: "skipped"` + `skip_reason` for manual execution
   instead of creating an action that dies with PermissionError at execute.
9. [x] OPA client hygiene: the UNKNOWN-result warning is generic (raw
   exception stays in server logs); the decision cache is swept once past
   1000 keys — distinct inputs previously accumulated forever.
10. [x] Frontend: dead httpOnly-cookie contract removed from `client.ts`
    (`withCredentials` + stale comments) — `/auth/refresh` is
    bearer-based; the test now asserts no cookie contract. (npm audit
    gating itself was already made blocking-at-critical in Wave 3.)

## Explicitly clean (verified this round)

Token HMAC + revocation, scrypt params + timing equalization, CORS/CSP
headers, path traversal guards, action state machine under per-action lock,
leader-lock Lua correctness, ES/Prom client timeouts/pooling, prompt cache
placement, frontend: no keys in bundle, no XSS sinks, sessionStorage tokens,
ai_assistant: no subprocess surface, env-only secrets, yaml.safe_load
everywhere, real CI test gates for all three suites.

## Status

Wave 1-3 fixed same-day (2026-08-31); P2-4 closed in the third same-day batch
(capped capture on both execution paths + bounded `timeout_seconds`); the P3
hardening batch closed in the fourth (see above). Remaining open items are
the design-needed P2s: 3/7 (per-subcommand depth + full SSRF IP-pinning),
10 (frontend error-state UX), 12 (k8s ArgoCD/kustomize/networkpolicy/secrets
cleanup), 13b (ai_assistant audit-chain migration).

Gates at P3 close (2026-08-31): backend 990 unit tests green (incl. the 13
new P3 tests: secret persistence, HMAC log hygiene, AUTH_DENIED/rollback
prod behavior, window math), ruff/bandit/compileall clean, frontend tsc +
159 vitest + build + npm-audit (0 vulnerabilities) clean. Phase-12 manual
smoke re-run from the third batch: 18/18 GREEN with the new dry-run
semantics (dry-run keeps APPROVED; same-action real execute; no rate-limit
wait needed since dry runs no longer burn the cooldown slot).

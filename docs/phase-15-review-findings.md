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

1. OPA enforcement fail-open ×3 (`engine.py:552` except→allow; missing
   `result`→allow; decision cache without TTL). Make UNKNOWN→DENY when
   OPA_ENFORCE, honor 60s TTL.
2. Service-key (API-key) calls keep client-asserted `approved_by`/
   `executed_by` → forge attribution; stamp `service:<key-id>` server-side.
3. env-aware executor validation floor is argv[0]+substrings;
   `kubectl exec`/`helm uninstall` pass if approved — enforce subcommand
   table + remove `exec` unless needed. (Related: `executor.py` whitelist
   dead on the engine path.)
4. Subprocess output unbounded; engine timeout hardcode 30s — cap captured
   bytes, add `timeout_seconds` to ExecuteActionRequest.
5. Teams webhook signature optional outside production + no IP allowlist +
   replay when X-Timestamp absent (P0 the moment staging is untrusted).
6. K8s client swallows errors → outages read as healthy zeros; raise when
   all namespaces fail.
7. SSRF check-then-use DNS rebind (validate+connect not IP-pinned) in
   `safe_post`/notifiers; sync `getaddrinfo` on loop.
8. Sync `smtplib` in async notifier (no timeout); redis leader-lock client
   without socket timeouts (double-engine risk on hung Redis).
9. Frontend: refresh flow expects an httpOnly cookie the backend never
   issues; no logout/revocation endpoint; refresh not single-flight.
10. Frontend: API errors render as empty data on 6/7 pages; AlertsPage
    delete no confirm/no catch; SkillsPage `alert()` + unvalidated project
    in URL; `/skills` + `/governance` orphaned from nav, light theme.
11. `sanitize_es_query` permits Lucene operators (wildcard/regex DoS).
12. k8s: ArgoCD selfHeal vs CI `kubectl set image` ownership conflict;
    kustomize overlays referenced but nonexistent; networkpolicy blocks CI
    smoke + prometheus scrape; consumed CHANGE_ME secrets (postgres/argocd/
    grafana); Alertmanager config unloadable (`actions:` key, no api_url).
13. ai_assistant: missing template var silently empties query filters
    (data-widening); ~50% of security.py dead; audit chain sha256-concat +
    cwd-relative + no verifier.
14. RateLimitMiddleware: no trusted_proxies (ingress → one global bucket),
    unbounded per-key dict; `X-Real-IP` accepted verbatim.

## P3 — hardening batch (one PR)

AUTH_SECRET per-process random breaks multi-worker/dev persistence (derive
from file under DATA_DIR); users.json non-atomic write + chmod-after; Slack
verify logs expected HMAC (replayable) — log failure+IP only; raw `str(e)` in
unauthenticated webhook 500s; audit gaps (`log_action_created` lacks user;
401s/login failures unaudited); time-window next-allowed math + end-hour
off-by-one + unknown-env fail-open; impact estimator real-cluster path
unreachable (dry_run=True hardcoded); engine hardcodes approval-gating
constants (20 pods/10 replicas); rollback actions auto-created can never
execute in production (DELETE not in prod matrix); OPA client log hygiene;
frontend api `WS_URL`/constants cleanup; npm audit gating strategy.

## Explicitly clean (verified this round)

Token HMAC + revocation, scrypt params + timing equalization, CORS/CSP
headers, path traversal guards, action state machine under per-action lock,
leader-lock Lua correctness, ES/Prom client timeouts/pooling, prompt cache
placement, frontend: no keys in bundle, no XSS sinks, sessionStorage tokens,
ai_assistant: no subprocess surface, env-only secrets, yaml.safe_load
everywhere, real CI test gates for all three suites.

## Status

Wave 1-3 fixed same-day (2026-08-31); P2/P3 above are the tracked ledger for
follow-up batches. Gates at close: backend 1182 unit tests green (+10
fail-first tests), ruff/bandit/compileall clean, frontend tsc + 159 vitest +
build + npm-audit clean, phase-12 manual smoke re-run 18/18 GREEN with the
new dry-run semantics (dry-run keeps APPROVED; same-action real execute;
no rate-limit wait needed since dry runs no longer burn the cooldown slot).

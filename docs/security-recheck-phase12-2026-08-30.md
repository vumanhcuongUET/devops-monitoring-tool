# Security Re-Check — Phase 12 Sprints 1–3 (2026-08-30)

Re-review of the security-relevant changes from the Phase 12 review-fix pass
(plan: `docs/phase-12-review-fixes.md`): the enforcement gaps S3–S6, the bug
fixes B1–B5, and the wire-or-delete removals. Scope: current master
(`6f1ea7e` + the paired fixes commit). Same bar as
`security-recheck-phase11-2026-08-29.md`. Verdict: **APPROVED, no blocking
findings** (two LOW findings fixed in the paired commit, see below).

## 1. S3 — Webhook paths exempt from bearer/api-key auth

Context: approval webhooks from Slack/Teams must be reachable without the
shared API key; their own HMAC signature is the authentication.

**Verified sound:**

- `AuthMiddleware` (`app/main.py`) exempts exactly one prefix,
  `/api/v1/approvals/webhook/`, and only when `AUTH_ENABLED`. The only routes
  under that prefix are the Slack and Teams handlers in
  `app/approvals/webhook.py`; no other route shares the prefix.
- Slack handler (`app/approvals/webhook.py:122`): signature verification is
  unconditional — missing `SLACK_SIGNING_SECRET` → HTTP 500 fail-closed, bad
  signature → 401. Replay window enforced via
  `X-Slack-Request-Timestamp` + `hmac.compare_digest`. Optional
  `ALLOWED_WEBHOOK_IPS` layer on top.
- Teams handler (`app/approvals/webhook.py:277`): fail-closed in production
  without `TEAMS_WEBHOOK_SECRET`; bad signature → 401.
- Rationale documented in the `AuthMiddleware` docstring: signature IS the
  authentication for these paths.

## 2. S4 — Teams webhook HMAC key

Context: the original scheme keyed the HMAC with the webhook URL (not a
secret). Phase 12 introduced `TEAMS_WEBHOOK_SECRET` (declared in
`app/config.py`, default empty) with a one-release deprecation shim.

**Verified sound:**

- Key resolution order: `TEAMS_WEBHOOK_SECRET` → legacy `TEAMS_WEBHOOK_URL`
  keying (with deprecation warning per request) → none (fail-closed in
  production, 500).
- Verification uses `hmac.compare_digest`; the legacy scheme is accepted only
  with a logged warning and is documented as a custom scheme, not Microsoft's
  official one.
- `docs/security-review-2026-08-20.md` addendum status: the shim is still
  present and documented as such — removal is due next release (open item).

## 3. S5 — Binary whitelist at the executor

Context: the first argv token of any executed command must come from the
shared whitelist `{kubectl, helm, argocd}` (`app/actions/parser.py`).

**Verified sound:**

- `EnvironmentAwareCommandExecutor._validate_command` enforces the whitelist
  before subprocess, importing `ALLOWED_BINARIES` from `parser.py` (one
  source of truth with the parser).
- The `CommandExecutor` flag/pattern layers (forbidden shell metacharacters,
  `shlex.split`-based argv execution without shell) remain as defense in
  depth; dry-run path performs the same validation before simulating.

**Finding fixed during this review (F2, LOW):**

- `shlex.split(command)[0]` raised `IndexError` on an empty/whitespace-only
  command and `ValueError` on unbalanced quotes — both surfaced as HTTP 500
  from the trust boundary instead of a clean validation failure. `_validate_command`
  now returns `False` for both (logged), and `execute()` converts that to its
  normal `ValueError("Command validation failed: …")` rejection. Regression
  tests in `tests/unit/test_actions/test_environment_executor.py`
  (`test_validate_rejects_malformed_command`,
  `test_execute_malformed_command_returns_value_error`).

## 4. S6 — Approval integrity (self-approval ban + approver permission)

**Verified sound:**

- `approve_action` calls `_check_approval_integrity`: self-approval blocked
  unless `ALLOW_SELF_APPROVAL` (default `False`), then
  `_check_decision_permission` requires the `approve` permission for the
  action's environment via `PermissionChecker`.
- Integrity runs before any state mutation (`set_status`, audit, history) —
  a failed check leaves the action PENDING.
- Audit log + approval history record the approver attribution for every
  decision.

**Finding fixed during this review (F1, LOW):**

- `reject_action` performed no integrity check; the plan named
  `approve_action`/`reject_action` both. Reject is now gated by
  `_check_decision_permission` (it is an approval-flow decision, so it needs
  `approve` permission). Self-reject stays deliberately allowed — a creator
  cancelling their own pending request gains no privilege, and blocking it
  would strand actions in PENDING. Refactored the permission part into
  `_check_decision_permission`, reused by both paths. Regression tests:
  `test_reject_without_permission_blocked`, `test_reject_by_creator_allowed`
  in `tests/unit/test_actions/test_engine.py`.

## 5. B1/B2/B5 — Slack view await, dry-run, phantom logout

**Verified sound:**

- Both `engine.get_action(action_id)` call sites in
  `app/approvals/webhook.py` (Slack view + Teams view, lines 241/444) are
  awaited — the "View" button no longer crashes with a coroutine object.
- `request.dry_run` is threaded into `env_aware_executor.execute(...,
  dry_run=request.dry_run)`; executor skips the subprocess and labels stdout
  `DRY RUN:`; action history, audit log, and the learning loop all carry the
  `dry_run` flag. Permission + rate-limit checks are unchanged (a dry run
  still proves authorization).
- Frontend `logout()` (`frontend/src/api/client.ts`) only clears the local
  token — the phantom `POST /auth/logout` (endpoint does not exist) is gone.

## 6. Wire-or-delete removals with security relevance

- **Dead CSP nonce system deleted** — the backend serves no HTML, so the
  per-request nonce never reached an inline script; production now serves the
  stricter static `script-src 'self'` (see the phase 11 recheck update).
- **`APIKeyAuth`/`BearerAuth` deleted** (zero callers; `AuthMiddleware` does
  the work) — no parallel/unmaintained auth path remains.
- **Multi-layer cache (2,411 lines) deleted** — removes an unmounted
  middleware and the `l2_cache` plumbing; no auth-relevant behavior change.
- **Optimization package deleted** — decorative endpoints gone; fewer
  unauthenticated surfaces (they were behind auth, but every dead endpoint is
  one less thing to audit).

## 7. Open items (no code change now)

- **Teams HMAC has no replay window** — Slack verifies a request timestamp;
  the Teams scheme signs the body only. A captured valid request can be
  replayed later. Acceptable for an internal tool (requests are idempotent
  once an action leaves PENDING — a replayed decision fails with
  "not pending"), but worth a timestamp check if Teams flows grow.
- **Teams verification disabled outside production** — with no
  `TEAMS_WEBHOOK_SECRET`, non-production accepts unsigned webhooks (warning
  logged). Matches the documented single-operator posture; production
  fail-closed.
- **Legacy Teams URL-keyed shim** — remove next release as documented.
- **`data/` PVC is `ReadWriteOnce`** (`k8s/backend/deployment.yaml`) — fine
  today (backend runs 1 replica); revisit with the H1 multi-replica work if
  rule-editing endpoints must run on every replica.

## 8. Gate status at review time

- `python -m compileall -q app` — pass
- `ruff check .` — pass
- `bandit -r app -q -ll` — pass
- Backend unit suite — 861 passed (857 + 4 new regression tests)
- ai_assistant suite — 262 passed, 2 skipped
- Frontend build (`tsc -b` + vite) — pass
- Existing E2E approval-flow tampered-signature regression guard — still green

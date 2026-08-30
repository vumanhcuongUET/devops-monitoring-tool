# Security Re-Review — Phase 11 Sprint 4 (2026-08-29)

Re-review of the two changes the Phase 8 security review (docs/security-review-2026-08-20.md)
flagged for follow-up: the nonce-based CSP header change and the K8s client auth fix.
Scope: current master, commit e9a2253. Verdict: **APPROVED, no blocking findings**.

## 1. CSP header change (app/middleware/security.py)

Context: Phase 8 Sprint 1 Day 2 replaced hash-based CSP with nonce-based CSP; Phase 11
Sprint 2 removed the hash helpers. Re-reviewed the current implementation end to end.

**Verified sound:**

- Nonce generation uses `secrets.token_urlsafe(16)` (128-bit, CSP nonce-safe).
- Environment for the dev `unsafe-inline` relaxation comes from `request.state.environment`
  falling back to `settings.ENVIRONMENT` — server-controlled, never from client headers.
- Production sends `script-src 'self' 'nonce-…'` with no `unsafe-inline`; `frame-ancestors 'none'`,
  `base-uri 'self'`, `form-action 'self'`, `upgrade-insecure-requests` all present.
- `X-CSP-Nonce` header adds no exposure: the nonce is already public in the CSP header of
  the same response; the browser injects it into inline scripts.
- Deleted hash helpers introduced no gap: nonces don't require hashes, and the dev-only
  `unsafe-inline` branch is correctly gated on `environment == "development" and not nonce`.

**Findings fixed during this review (commit paired with this note):**

- **Nonce map leak (LOW, fixed)** — `dispatch()` called `nonce_manager.cleanup_request()`
  only on the success path. An exception from downstream left the `id(request)`-keyed
  entry in `CSPNonceManager._request_nonce` forever → unbounded memory growth under
  repeated error responses, and `id()` reuse across GC'd requests could hand a later
  request a stale nonce. Cleanup is now in a `finally` block.
- **Duplicate `frame-ancestors 'none'` directive** — present in both the base list and the
  "additional directives" list; browsers take the first, later ones ignored (and some
  validators flag it). Removed the dup.

**Open items (no code change now, deployment-level):**

- **HSTS behind TLS-terminating proxy** — RESOLVED in the debt-cleanup commit:
  HSTS is now emitted at the edge via nginx ingress annotations (`hsts: "true"`,
  `hsts-max-age: 31536000`, `hsts-include-subdomains`), and the backend Dockerfile
  CMD gained `--proxy-headers` with `FORWARDED_ALLOW_IPS` set to the pod CIDR in
  `k8s/backend/configmap.yaml`, so `request.url.scheme` reflects the ingress scheme
  and application-level HSTS also works.
- **`X-XSS-Protection: 1; mode=block`** is deprecated (modern browsers ignore it). Kept for
  legacy browsers; harmless. No action.

## 2. K8s client auth fix (app/services/kubernetes_client.py)

Context: Phase 9 Day 4 replaced a bare `client.Configuration()` (no credentials → all
calls 401) with `client.Configuration.get_default_copy()`, which preserves the credentials
loaded by `load_kube_config()` / `load_incluster_config()`.

**Verified sound:**

- Credential flow correct: `load_kube_config(KUBECONFIG_PATH)` when the env var is set,
  else `load_incluster_config()` for in-cluster serviceaccount, then `get_default_copy()`
  carries those creds into the API client. This was the intended Phase 9 fix and it holds.
- Creds never logged; client methods return empty lists when the client is unavailable
  (clean degradation, no misleading data shown as truth).
- In-cluster path uses the pod's serviceaccount token — standard, no secret material in code.

**Finding fixed during this review:**

- `configuration.connection_pool_size = getattr(...)` was assigned **twice** (a copy-paste
  duplicate); removed.

**Notes (no action):**

- `except Exception: self._available = init-failure` → the client degrades to returning
  empty lists. Intentional for a monitoring surface: better an empty K8s page than a 500.
  Consider a warning log at init failure — currently silent (bandit-silent, but worth a log).
- `getattr(settings, "K8S_MAX_CONNECTIONS", 10)` — `K8S_MAX_CONNECTIONS` is not a declared
  field on Settings; `getattr` with default is doing silent config. Declare the field or
  inline the default.

## 3. Gate status at review time

- `python -m compileall -q app` — pass
- `ruff check .` — pass (rules pinned in backend/ruff.toml)
- `bandit -r app -q -ll` — pass (B108 nosec on the miner-detection pattern string)
- Backend unit suite 726 + integration incl. new E2E approval flow — pass (760 total)
- E2E approval flow (added this sprint) already caught and fixed 3 real prod-path bugs
  (audit API mismatch, Slack form parsing, parsed_params dict access) — see the E2E commit 6e0722c
  and the gate commit fc86ec4.

E2E also added a tampered-signature regression guard for the Slack webhook.

## Update 2026-08-30 — CSP nonce control removed

The nonce-based CSP documented above was deleted in the Phase 12 follow-up pass
(CSPNonceManager, `use_nonce`, `X-CSP-Nonce` — dead code: the backend serves no HTML,
so a per-request nonce never reached any inline script, and the id(request)-keyed map
was the very leak this review fixed). Production now serves the stricter static
`script-src 'self'` (no nonce, no unsafe-inline; dev keeps `unsafe-inline`).
See `backend/app/middleware/security.py`. The review findings above are historical.

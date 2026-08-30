# Phase 14 — Full-Repo Review & Fixes (2026-08-30)

Four review passes (ponytail ×2 over-engineering, security, SA/DevOps
architecture) over the whole tree, then every actionable finding fixed.
Commits: `07ad8c8` (security), `9e7ea62` (ops/state), `d8718db` (backend
ponytail), `cd75874` (deploy/CI/DR), `5607dcf` (frontend ponytail), plus the
ai_assistant cleanup.

## Security fixes (`07ad8c8`)

- **CRITICAL — alert-rule → kubectl bypass closed.** `POST/PUT/DELETE
  /alerts/rules` now require operator/admin (viewers 403), hard-cap 500
  rules, and **strip `autonomous_action`** — autonomous remediation is
  server-side config only. The engine takes the execution environment from
  server settings and ignores `labels.environment` (was client-controlled).
  `AutonomousExecutor` enforces a server-owned `AUTONOMOUS_ACTION_RISK`
  table through the previously **dead** `check_risk_level` (zero callers);
  unknown action types default to high risk → blocked.
- **Config API**: mutations need operator+; audit `author` overridden by the
  authenticated identity (was client-supplied → attribution forgery);
  `_safe_project` kills the `project="../../x"` path traversal into the
  version store and `git add projects/…`.
- **TOCTOU**: approve/reject/execute serialized per action id (asyncio
  locks) — concurrent executes can no longer both observe APPROVED and
  double-run a mutating command. Multi-process deployments still need the
  Redis store's compare-and-set (documented residual).
- **Creation-time RBAC**: `create_action_from_recommendation` narrows by the
  authenticated user (viewers could stage born-APPROVED actions);
  missing-environment default unified to `production`.
- **Rate-limit control made real**: `permission_checker._check_rate_limit`
  never appended to its window (could not trip). Skills: `resource_optimizer`
  validates `namespace` (was interpolated raw into PromQL + kubectl strings).

## Architecture / operations (`9e7ea62`, `cd75874`)

- **Container startup fixed**: config subsystem paths via
  `settings.CONFIG_STORAGE_PATH`/`DATA_DIR`; init degrades gracefully. The
  old `__file__/../../configs` resolved to `/configs` in-image → mkdir
  PermissionError → crash loop under `readOnlyRootFilesystem`.
- **CWD-independent state**: every file store (users, alert rules/state/
  history, SLO configs, approvals, audit, feedback) resolves through
  `settings.DATA_DIR` — running uvicorn from another directory no longer
  creates a parallel empty `data/` tree.
- **Audit durability**: append-only JSONL + 50MB rotation + one-time
  migration (old writer rewrote the whole file per event and silently
  truncated to 1000 entries).
- **Layering**: SLO config store extracted to `app/services/
  slo_config_store.py`; router/reporter/skills no longer import from the API
  layer. Skill registry results FIFO-capped (was an unbounded dict).
- **k8s/CI aligned with reality**: real GHCR images (were placeholders),
  bigger requests, DATA_DIR/CONFIG_STORAGE_PATH wired, backend PDB removed
  (minAvailable:1 + replicas:1 froze voluntary evictions), CI deploy
  names/namespace/health-route fixed, prod pinned to sha tags, new
  manifests-validate gate. Compose redis got a volume.
- **DR runbook** rewritten around the actual file-backed JSON state (the old
  one described a postgres-0/pg_promote flow that never existed). Dead
  config trees (`config/`, `config-repo/`) deleted; validator repointed at
  `configs/`.

## Ponytail cuts (`d8718db`, `5607dcf`, ai_assistant)

- Backend ~14k lines: 23 stub skills collapsed into one `CatalogStubSkill`
  + metadata table (catalog contract unchanged: 44/21/23); dead services
  deleted (token_optimizer, log_sampler, anomaly_detector,
  time_series_compressor, resource_limiter, timescaledb) — **scipy dropped**;
  6 orphan shell scripts deleted.
- Frontend ~1.8k lines: dead hooks/components, tokenManager shrink,
  recharts → inline SVG, fake banner removal. **recharts dropped**.
- ai_assistant: flag-off adapter layer, redis cache/single-flight,
  CircuitBreaker, audit reader/verifier, barrel — removed (see commit).

## Verification

- Backend: compileall, ruff, bandit(-ll) clean; unit+integration 909 green.
- Frontend: tsc+vite build, eslint, vitest 159/159.
- ai_assistant: own suite green (see commit).
- The 22 pre-existing live-stack failures (smoke/redis/analyze-api) are
  unchanged and environment-only.

## Known residuals (accepted, documented)

1. Multi-process approve/execute CAS needs the Redis store (per-process
   locks only).
2. Remediation actions still run through the pod's in-cluster context; the
   env-aware executor route is a future refactor — moot while autonomous
   actions are server-config-only and medium-risk-only.
3. Autonomous rate limiter is in-memory (resets per process).
4. 23 stub skills remain stubs pending real external data sources
   (billing, scanners, Grafana, CI, load-test artifacts).
5. Alert-engine heartbeat/`/health/ready` with live dependency pings —
   recommended next (finding C7 of the architecture pass, not yet built).

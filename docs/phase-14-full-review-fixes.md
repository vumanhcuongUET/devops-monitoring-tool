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

## Token optimization follow-up (2026-08-30)

What was done:

- **Usage capture everywhere** (was: output-only on TriageCard, nothing
  else). New `app/llm_metrics.py` exports
  `llm_input_tokens_total`/`llm_output_tokens_total` (labels: path, model)
  and `llm_api_requests_total` (name differs from `llm_requests_total` in
  `app/api/v1/metrics.py`, which already owns that series with labels
  [model, status]). Recorded at every call site: triage, both streaming
  paths (`message_start.usage.input_tokens` +
  `message_delta.usage.output_tokens`), agents (`_query_claude`), and
  `health_check`. TriageCard.tokens_used is now input+output.
- **Compact JSON prompts**: all `json.dumps(indent=2)` in
  `llm_client._build_user_prompt` and the simple-stream context dump are
  compact — pretty-printing roughly halved again the payload token count
  for zero quality gain.
- **ES `_source` projection**: `search_logs` projects
  `["message","level","service","@timestamp","log"]` by default
  (widenable via `source_includes=`). All existing callers (logs API,
  analyze context, dlq_monitor skill, frontend LogsPage) read only these
  fields.
- **Log severity quotas** replace the blunt `logs[:50]`:
  `sample_logs_by_severity()` in `llm_client` keeps
  critical:5/error:10/warning:10/info:5 when >50 logs arrive and notes
  "showing N of M logs by severity (…)" in the prompt. The analyze
  endpoint now fetches 200 logs so quotas have something to sample.
- **ModelSelector actually wired**: `orchestrator.analyze` scores each
  agent's own sub-context, picks a tier, and passes `model=` into
  `agent.analyze` (agents/`_query_claude` accept the override; stubs
  without the param are still called positionally — backward compatible).
  Selected models surface in `result["models"]` and execution history.
- **Fast-tier routing**: simple-stream and `health_check` run on
  `ModelSelector.MODELS["fast"]`. That id was previously the fabricated
  `claude-haiku-4-20250101` (no such Anthropic model — every low-complexity
  routing would have 404'd); corrected to `claude-haiku-4-5-20251001`.
  Triage generation stays on the configured Sonnet model.
- **Prompt caching**: system prompts carry
  `cache_control: {"type": "ephemeral"}` on triage, main streaming and all
  agent calls (applied unconditionally — sub-1024-token prompts are simply
  not cached, no error).

Expected effect: 40-60% fewer input tokens per triage/stream call (compact
JSON + projection + quotas), cache-read pricing on repeated system
prompts, haiku pricing on simple questions/health probes, and per-path
token spend finally visible in Prometheus.

Note: the Phase 6/9/10 "token reduction" claims referenced code that was
never wired (ModelSelector stored but unused; indent + full `_source`
shipping unchanged). This follow-up makes those reductions real; earlier
percentage claims were aspirational until now.

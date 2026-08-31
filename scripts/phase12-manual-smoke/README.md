# Phase 12 Manual Smoke (exit criterion)

Live-stack verification of the full approval chain: **create → approve
(different user) → dry-run execute → execute**, plus Slack signed-webhook
approve + view. First run 2026-08-31 (17/17 green) — it found 5 real bugs,
fixed in the same pass (see `docs/phase-12-review-fixes.md`).

## Run

```bash
bash scripts/phase12-manual-smoke/setup.sh   # isolated DATA_DIR, users, fake kubectl, uvicorn :8123
python scripts/phase12-manual-smoke/smoke.py # needs backend venv (httpx); takes ~6 min
```

`smoke.py` must run with the repo's python env (cwd anywhere). The stack binds
127.0.0.1:8123; teardown: `pkill -f "[u]vicorn app.main:app"` + delete
`/tmp/phase12-smoke`.

## What the environment fakes (and why)

- **fake `kubectl`** on PATH — no cluster here; the sentinel log proves the
  executor really invoked the binary with `--context/--kubeconfig` argv.
- **`~/.kube/config-staging`** stub — env_aware_executor requires the env's
  kubeconfig to exist before executing; staging is `always-available`, so the
  execute steps run there.
- **300s wait** between the real and dry-run executions — the action
  rate-limiter cooldown (300s per project+type) is by-design enforcement,
  deliberately not bypassed.
- Production execute is asserted to be **blocked by the time window** (first
  run was a Sunday; business-hours) and audited — negative path on purpose.

## Bugs found by this smoke (all fixed)

1. `APPROVE` unreachable in staging/production — matrix + missing
   action→permission mapping made every approval impossible (admin included).
2. RBAC denials on approve/reject/execute returned 500 instead of 403.
3. `GET /actions/{id}` 500'd — stored state omits `id`, never re-injected.
4. Slack/Teams webhooks 401'd at the auth middleware whenever AUTH_ENABLED —
   the exempt prefix `/api/v1/approvals/webhook/` doesn't match the real
   mount `/approvals/webhook/*`.
5. Every real execution 500'd **after** the subprocess ran — deduped
   `ExecutionResult` lost `environment`/`command`, pydantic silently ignored
   the constructor kwargs, `_log_execution` crashed on the missing attribute,
   and the action never reached EXECUTED.

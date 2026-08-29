# Multi-Agent AI Architecture

> **Phase 10 — Sprint 3 (Days 11–15)** · Status: ✅ Complete (2026-08-26)

The multi-agent system coordinates six specialized AI agents for comprehensive
incident analysis. Each agent owns one domain, runs in parallel, and its
results are aggregated with confidence scoring and consensus voting.

## Architecture

```
POST /api/v1/agents/analyze {context}
        │
        ▼
┌─────────────────────────────┐
│   AgentOrchestrator         │
│  1. Select agents by context│
│  2. Run agents in parallel  │      ┌──────────────┐
│  3. Aggregate + dedupe recs │────► │ Claude API   │
│  4. Consensus vote if low   │      │ (mockable    │
│     confidence or conflicts │      │  boundary)   │
└─────────────────────────────┘      └──────────────┘
```

Module layout (`backend/app/agents/`):

| File | Purpose |
|------|---------|
| `base.py` | `BaseAgent` ABC: prompt template, Claude query, context validation, confidence scoring |
| `orchestrator.py` | Agent selection, parallel execution, aggregation, consensus voting |
| `model_selector.py` | Complexity-based model tiering with cost limits |
| `log_agent.py` | Error patterns, anomalies, error bursts, root-cause hints from logs |
| `metrics_agent.py` | Trends, anomalies, capacity risk from Prometheus metrics |
| `k8s_agent.py` | Pod/node health, resource utilization, scheduling & config issues |
| `cost_agent.py` | Rightsizing and idle-resource cost opportunities |
| `security_agent.py` | Vulnerability and misconfiguration findings |
| `performance_agent.py` | Latency/trace analysis with optimization recommendations |

## Agents

| Registry key | Internal name | Auto-selected when context contains | Model tier default |
|--------------|---------------|-------------------------------------|--------------------|
| `log` | `log-analyst` | `logs`, `log_entries` | Sonnet |
| `metrics` | `metrics-analyst` | `metrics`, `prometheus_data` | Sonnet |
| `k8s` | `k8s-expert` | `k8s_state`, `cluster_state` | Sonnet |
| `cost` | `cost-optimizer` | `resources`, `cost_data` | Haiku |
| `security` | `security-analyst` | `security_data`, `vulnerabilities` | Sonnet |
| `performance` | `performance-analyst` | `performance_data`, `traces` | Sonnet |

Selection is driven purely by context keys — an empty container (`[]`, `{}`)
does **not** trigger the corresponding agent.

## API Endpoints

All endpoints live under `/api/v1/agents` (router registered in
`backend/app/api/router.py`; orchestrator injected in `backend/app/main.py`
lifespan).

### POST `/api/v1/agents/analyze`

```bash
curl -X POST http://localhost:8000/api/v1/agents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "project": "meinvoice",
      "logs": [{"level": "ERROR", "message": "TimeoutError: DB timeout",
                "timestamp": "2026-08-25T10:00:00Z"}],
      "metrics": {"cpu_usage": 85},
      "k8s_state": {"pods": [{"name": "api-2", "status": "CrashLoopBackOff",
                              "restarts": 5}]}
    },
    "agents": ["log", "metrics"],     # optional; omit for auto-select
    "consensus_threshold": 0.6        # optional
  }'
```

Response shape:

```json
{
  "agents": {"log": {"agent": "log-analyst", "insights": {...}, "confidence": 0.9}},
  "insights": {"log": {...}},
  "recommendations": ["URGENT: ...", "Scale up ..."],
  "confidence": 0.85,
  "errors": [],
  "consensus": {"recommendations": {}, "agreement_level": 1.0},
  "agents_used": ["log", "metrics"],
  "agents_successful": 2,
  "total_agents": 2,
  "execution_time": 1.42,
  "timestamp": "2026-08-26T09:00:00"
}
```

Guards:
- Context payload ≤ 512 KB and ≤ 50 top-level keys (400 / 413 otherwise)
- Unknown agent names rejected at validation time (422)
- Missing orchestrator or `ANTHROPIC_API_KEY` → 503

### GET `/api/v1/agents/health`

Per-agent health. Returns `"orchestrator": "unavailable"` instead of a 5xx so
dashboards can distinguish "not deployed" from "failing".

### GET `/api/v1/agents/history`

Last 100 executions: context keys, agents run, success count, timestamp.

## Orchestration Behavior

**Parallel execution** — all selected agents run concurrently under
`asyncio.gather` with per-agent timeouts (default 30s). A failure in one agent
never fails the analysis; it is recorded in `errors`.

**Consensus voting** — triggered when overall confidence < threshold, more than
5 distinct recommendations exist, or any agent reports a *critical* finding
with < 0.7 confidence. Recommendations are majority-voted (`votes ≥ N/2 + 1`)
and winners carry their agreement ratio.

**Recommendation merging** — case-insensitive dedup, then priority keywords
(`critical`, `urgent`, `immediate`, `security`) float to the front.

## Model Selection & Cost Control

`ModelSelector` scores complexity (0–1) from data volume, source count and
explicit hints (`requires_deep_analysis`, `multi_hop_reasoning`,
`complex_correlation`), then maps:

| Score | Tier | Model |
|-------|------|-------|
| < 0.3 | fast | claude-haiku-4-20250101 |
| 0.3–0.7 | balanced | claude-sonnet-4-20250514 |
| ≥ 0.7 | capable | claude-opus-4-20250514 |

When a `cost_limit` is configured, selection walks tiers cheap→expensive and
picks the first within budget regardless of complexity; task-type shortcuts
are available via `get_model_for_task("root_cause_analysis")`.

## Testing

| Suite | File | Focus |
|-------|------|-------|
| API unit | `tests/unit/test_api/test_agents_api.py` | Endpoint guards, injection pattern |
| Orchestrator unit | `tests/unit/test_agents/test_orchestrator.py` | Selection, aggregation, consensus, failures |
| Selector unit | `tests/unit/test_agents/test_model_selector.py` | Complexity scoring, budgets, estimates |
| Integration | `tests/integration/test_multi_agent_e2e.py` | Real agents end-to-end, Claude mocked |
| Performance | `tests/performance/test_multi_agent_perf.py` | SLA (<10s), overhead (<50ms), concurrency |

```bash
pytest tests/unit/test_agents tests/unit/test_api/test_agents_api.py -v          # units
pytest tests/integration/test_multi_agent_e2e.py -v                              # e2e
pytest tests/performance/test_multi_agent_perf.py -m benchmark -v                # perf
```

No test issues real Claude calls — the LLM boundary is always faked.

## Monitoring

Prometheus rules ship in `k8s/monitoring/agent-metrics.yaml`:

- Recording rules: `agent:invocations_rate5m`, `agent:error_ratio5m`,
  `agent:duration_p95_5m`, `agent:cost_per_minute`
- Alerts: `OrchestratorDown` (critical), `HighAgentErrorRate`,
  `HighAgentLatency` (P95 > 10s), `AgentTimeoutSpike`, `HighAgentCost`
  (> $1/hour projection)

## Known Design Decisions

- **Empty containers don't select agents** — `{"logs": []}` is treated as "no
  log data", matching truthiness semantics throughout `_determine_agents`.
- **Dual K8s shapes supported** — pods may arrive as full K8s API objects
  (`status.phase`, `metadata.name`) or simplified dicts (`status: "Running"`,
  flat `name`); both count toward health.
- **Mixed metric values accepted** — `{"cpu_usage": 85}` scalars and time
  series (`{"cpu": {"values": [...]}}`) coexist; trends/anomalies only consume
  series data.

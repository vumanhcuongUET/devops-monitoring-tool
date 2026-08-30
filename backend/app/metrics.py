"""Prometheus instrumentation for the multi-agent AI system.

Emit the series that k8s/monitoring/agent-metrics.yaml alerts on. Without
this module those rules query absent series and can never fire — a silent
monitoring failure (review finding A1, 2026-08-29).
"""
from prometheus_client import Counter, Gauge, Histogram

AGENT_INVOCATIONS = Counter(
    "agent_invocations_total",
    "Agent analyze() invocations by agent and outcome",
    ["agent_name", "status"],
)
AGENT_DURATION = Histogram(
    "agent_duration_seconds",
    "Agent analyze() wall time",
    ["agent_name"],
)
AGENT_TIMEOUTS = Counter(
    "agent_timeouts_total",
    "Agent analyze() timeouts",
    ["agent_name"],
)
ORCHESTRATOR_UP = Gauge(
    "devops_monitor_orchestrator_up",
    "1 if the agent orchestrator loaded with agents attached",
)
# Phase 14 residual #2: alert-engine heartbeat + honest eval-error signal.
# Label is `source`, not `rule_id` — rules are user-editable config (capped at
# 500), so per-rule cardinality would be unbounded in practice; `source` is
# the fixed fetcher set (elasticsearch/apm/prometheus/kubernetes), which is
# exactly the axis an operator pages on ("which dependency is failing?").
ALERT_EVAL_ERRORS = Counter(
    "alert_eval_errors_total",
    "Alert rule metric fetches that raised, by source",
    ["source"],
)
ALERT_ENGINE_LAST_SUCCESS = Gauge(
    "alert_engine_last_success_timestamp",
    "Unix time of the last fully completed alert evaluation cycle (0 = never)",
)

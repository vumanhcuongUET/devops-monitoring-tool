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

# Platform HTTP metrics (SA finding A): request volume and latency for the API
# itself, recorded by HTTPMetricsMiddleware in app/main.py. The route label is
# the PATTERN the router matched ("/api/v1/alerts/rules/{rule_id}"), never the
# raw path — one series per request id would cardinality-explode Prometheus on
# any parameterized route.
#
# Naming: NOT "http_requests_total"/"http_request_duration_seconds" —
# app/api/v1/metrics.py already registers those names (declared there but
# never incremented) and a second registration with different labels raises
# prometheus_client DuplicateTimeseries at import time. Same situation, same
# fix as LLM_REQUESTS in app/llm_metrics.py.
HTTP_REQUESTS_TOTAL = Counter(
    "http_server_requests_total",
    "HTTP requests by method, route pattern and status code",
    ["method", "route_pattern", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_server_request_duration_seconds",
    "HTTP request wall time by method, route pattern and status code",
    ["method", "route_pattern", "status"],
    # API-latency buckets: sub-100ms for cached/fast reads, 100ms-1s for
    # ES/Prometheus-backed queries, and 2.5-10s so a request that hits
    # REQUEST_TIMEOUT_SECONDS (5s) still lands in a bucket, not +Inf.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# SA finding B: leader-lock health, flipped by app/alerting/leader.py at every
# acquire/renew/release. 1 = this pod's last attempt succeeded; 0 = it failed
# or the lock was released. The `lock` label is the fixed two-entry set
# (alert-engine, slo-reporter) — bounded by construction, unlike a per-rule or
# per-pod label, which would grow with fleet size.
LEADER_LOCK_UP = Gauge(
    "leader_lock_up",
    "1 if this pod's last leader-lock acquire/renew succeeded, 0 on failure or release",
    ["lock"],
)

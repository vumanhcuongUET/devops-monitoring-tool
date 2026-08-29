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
# ponytail: AgentResponse carries no token usage — cost is wired when
# BaseAgent surfaces response.usage. Metric exists so the alert fires once it does.
AGENT_COST = Counter(
    "agent_cost_usd_total",
    "Estimated agent spend in USD",
    ["agent_name"],
)
ORCHESTRATOR_UP = Gauge(
    "devops_monitor_orchestrator_up",
    "1 if the agent orchestrator loaded with agents attached",
)

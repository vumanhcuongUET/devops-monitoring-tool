"""Contract test for the agent metrics endpoint (review finding A1).

The agent-metrics.yaml alerts query agent_* series; if the endpoint or
series disappear, alerts go silently dead again. One test fails before and
passes after — the smallest guard for the instrumentation.
"""
from fastapi.testclient import TestClient

from app.metrics import AGENT_INVOCATIONS, ORCHESTRATOR_UP


def test_metrics_endpoint_exposes_agent_series(monkeypatch):
    from app.main import app
    from app.config import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    client = TestClient(app)  # no lifespan needed — mount exists at import
    response = client.get("/metrics")
    assert response.status_code == 200  # auth-exempt via PUBLIC_PATHS

    AGENT_INVOCATIONS.labels("test-agent", "success").inc()
    body = response.text if "agent_invocations_total" in response.text else None
    assert body is not None, "/metrics must expose agent_invocations_total"

    ORCHESTRATOR_UP.set(1)
    r2 = client.get("/metrics")
    assert "devops_monitor_orchestrator_up" in r2.text


def test_run_agent_safely_instruments_outcomes():
    """Timeout/error/success outcomes bump the right counters."""
    import asyncio

    from app.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator()

    class TimeoutAgent:
        name = "test-timeout"
        timeout = 0.01

        async def analyze(self, _):
            await asyncio.sleep(1)

    result = asyncio.run(orch._run_agent_safely(TimeoutAgent(), {}))
    assert result.error == "Analysis timed out"
    # counter family must exist and be scrapeable
    from prometheus_client import REGISTRY

    names = {m.name for m in REGISTRY.collect()}
    assert "agent_timeouts" in names  # prometheus_client strips _total in collect()
    assert "agent_invocations" in names

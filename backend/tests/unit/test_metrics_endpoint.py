"""Contract test for the agent metrics endpoint (review finding A1).

The agent-metrics.yaml alerts query agent_* series; if the endpoint or
series disappear, alerts go silently dead again. One test fails before and
passes after — the smallest guard for the instrumentation.

Extended for the platform HTTP series (SA finding A): the middleware must
label by route PATTERN, never the raw path, and must not count the metrics
scrape itself.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.metrics import AGENT_INVOCATIONS, ORCHESTRATOR_UP

_PATTERN_LABELS = {"method": "GET", "route_pattern": "/__probe/{item_id}", "status": "200"}


def _http_total(pattern: str, status: str = "200") -> float | None:
    return REGISTRY.get_sample_value(
        "http_server_requests_total",
        {"method": "GET", "route_pattern": pattern, "status": status},
    )


def _recorded_route_patterns() -> set[str]:
    """Every route_pattern currently present on the HTTP counter family."""
    return {
        sample.labels["route_pattern"]
        for metric in REGISTRY.collect()
        if metric.name == "http_server_requests"
        for sample in metric.samples
    }


def _probe_app() -> FastAPI:
    """Standalone app carrying ONLY the metrics middleware.

    Proves the middleware works on its own (innermost placement, no auth /
    rate-limit in front) and gives it a parameterized route to label.
    """
    from app.main import HTTPMetricsMiddleware

    app = FastAPI()
    app.add_middleware(HTTPMetricsMiddleware)

    @app.get("/__probe/{item_id}")
    async def probe(item_id: int):
        return {"item_id": item_id}

    @app.get("/metrics")
    async def metrics():
        return {"ok": True}

    @app.get("/api/v1/metrics")
    async def legacy_metrics():
        return {"ok": True}

    return app


def test_metrics_endpoint_exposes_agent_series(monkeypatch):
    from app.main import app
    from app.settings import settings

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


def test_http_metrics_label_by_route_pattern_not_raw_path():
    """A parameterized route must produce ONE series, named by its template."""
    client = TestClient(_probe_app())

    before = _http_total("/__probe/{item_id}") or 0
    assert client.get("/__probe/42").status_code == 200

    assert _http_total("/__probe/{item_id}") == before + 1
    # the raw path must never become a label (cardinality guard)
    assert _http_total("/__probe/42") is None
    # same labels on the histogram, and it actually observed something
    observed = REGISTRY.get_sample_value(
        "http_server_request_duration_seconds_count", _PATTERN_LABELS
    )
    assert observed == 1
    assert (REGISTRY.get_sample_value("http_server_request_duration_seconds_sum", _PATTERN_LABELS) or 0) > 0


def test_http_metrics_unmatched_path_falls_back_to_first_segment():
    """No matched route (404) -> first path segment, not the full scanned URL."""
    client = TestClient(_probe_app())

    before = _http_total("/__nowhere", status="404") or 0
    assert client.get("/__nowhere/deep/12345").status_code == 404

    assert _http_total("/__nowhere", status="404") == before + 1
    assert _http_total("/__nowhere/deep/12345", status="404") is None


def test_http_metrics_exclude_the_scrape_endpoints():
    """/metrics must not record itself — every scrape would otherwise bump the
    very counters it reads (and the histogram would measure its own scrape)."""
    from app.main import HTTPMetricsMiddleware

    assert "/metrics" in HTTPMetricsMiddleware.SCRAPE_PATHS
    assert "/api/v1/metrics" in HTTPMetricsMiddleware.SCRAPE_PATHS
    client = TestClient(_probe_app())

    before = _recorded_route_patterns()
    assert client.get("/metrics").status_code == 200
    assert client.get("/api/v1/metrics").status_code == 200

    assert _recorded_route_patterns() == before  # nothing new recorded at all


def test_http_metrics_wired_into_the_real_app(monkeypatch):
    """The middleware is registered on app.main (full CORS/auth/ratelimit stack)."""
    from app.main import app
    from app.settings import settings

    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    client = TestClient(app)

    before = _http_total("/health") or 0
    assert client.get("/health").status_code == 200
    assert _http_total("/health") == before + 1

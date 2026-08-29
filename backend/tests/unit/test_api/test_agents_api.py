"""
Unit tests for the Agents API (Phase 10 Sprint 3 integration).

Tests POST /api/v1/agents/analyze, GET /api/v1/agents/health and
GET /api/v1/agents/history with an injected fake orchestrator -
no LLM calls involved.
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1 import agents as agents_api


class FakeOrchestrator:
    """Deterministic stand-in for AgentOrchestrator."""

    def __init__(self, analyze_result=None):
        self.analyze_result = analyze_result or {
            "agents": {},
            "insights": {"log": {"patterns": ["timeout"]}},
            "recommendations": ["Scale up deployment"],
            "confidence": 0.85,
            "errors": [],
            "agents_used": ["log"],
            "agents_successful": 1,
            "total_agents": 1,
            "execution_time": 0.42,
        }
        self.last_call = None

    async def analyze(self, context, agents=None, consensus_threshold=0.6):
        self.last_call = {
            "context": context,
            "agents": agents,
            "consensus_threshold": consensus_threshold,
        }
        return dict(self.analyze_result)

    async def health_check(self):
        return {
            "orchestrator": "healthy",
            "agents": {"log": {"agent": "log", "status": "healthy"}},
            "total_agents": 6,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def get_execution_history(self):
        return [{"context_keys": ["logs"], "agents": ["log"], "success_count": 1}]


@pytest.fixture
def client_factory(monkeypatch):
    """Create a test app with the agents router and inject a fake orchestrator."""
    created = []
    # Fake orchestrator never calls Claude, so a dummy key satisfies the guard
    monkeypatch.setattr(agents_api.settings, "ANTHROPIC_API_KEY", "test-key")

    def _make(orchestrator):
        app = FastAPI()
        app.include_router(agents_api.router)
        agents_api.set_agent_instances(orchestrator)
        created.append(orchestrator)
        return app

    yield _make

    # Reset module state so other tests start clean
    agents_api.set_agent_instances(None)


@pytest.mark.unit
@pytest.mark.api
class TestAgentsAPI:
    """Test suite for /api/v1/agents endpoints."""

    @pytest.mark.asyncio
    async def test_analyze_returns_aggregated_result(self, client_factory):
        orchestrator = FakeOrchestrator()
        app = client_factory(orchestrator)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/agents/analyze",
                json={"context": {"logs": [{"message": "timeout"}]}},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["confidence"] == 0.85
        assert "Scale up deployment" in data["recommendations"]
        assert data["agents_used"] == ["log"]
        # Verify orchestrator received sanitized parameters
        assert orchestrator.last_call["context"] == {"logs": [{"message": "timeout"}]}
        assert orchestrator.last_call["consensus_threshold"] == 0.6

    @pytest.mark.asyncio
    async def test_analyze_with_explicit_agents_and_threshold(self, client_factory):
        orchestrator = FakeOrchestrator()
        app = client_factory(orchestrator)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/agents/analyze",
                json={
                    "context": {"metrics": {}},
                    "agents": ["log", "metrics"],
                    "consensus_threshold": 0.8,
                },
            )

        assert response.status_code == 200
        assert orchestrator.last_call["agents"] == ["log", "metrics"]
        assert orchestrator.last_call["consensus_threshold"] == 0.8

    @pytest.mark.asyncio
    async def test_analyze_rejects_unknown_agent(self, client_factory):
        app = client_factory(FakeOrchestrator())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/agents/analyze",
                json={"context": {}, "agents": ["hacker"]},
            )

        assert response.status_code == 422
        assert "hacker" in response.text

    @pytest.mark.asyncio
    async def test_analyze_rejects_oversized_context(self, client_factory):
        app = client_factory(FakeOrchestrator())

        big_context = {"logs": "x" * (agents_api.MAX_CONTEXT_BYTES + 1)}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/agents/analyze", json={"context": big_context}
            )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_analyze_requires_orchestrator(self, client_factory):
        app = client_factory(None)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/agents/analyze", json={"context": {"logs": []}}
            )

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_health_reports_agent_status(self, client_factory):
        app = client_factory(FakeOrchestrator())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/agents/health")

        assert response.status_code == 200
        data = response.json()
        assert data["orchestrator"] == "healthy"
        assert data["total_agents"] == 6

    @pytest.mark.asyncio
    async def test_health_without_orchestrator_is_unavailable(self, client_factory):
        app = client_factory(None)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/agents/health")

        assert response.status_code == 200
        assert response.json()["orchestrator"] == "unavailable"

    @pytest.mark.asyncio
    async def test_history_returns_executions(self, client_factory):
        app = client_factory(FakeOrchestrator())

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/agents/history")

        assert response.status_code == 200
        executions = response.json()["executions"]
        assert len(executions) == 1
        assert executions[0]["success_count"] == 1

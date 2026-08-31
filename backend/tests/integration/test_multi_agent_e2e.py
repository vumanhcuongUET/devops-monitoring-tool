"""
Integration tests for the multi-agent system (Phase 10 Sprint 3).

Exercises the full pipeline with REAL agent implementations
(pre-processing, prompt building, response parsing, confidence scoring)
and orchestrator wiring - only the Claude API boundary is mocked via
BaseAgent._query_claude. No network calls.
"""

from unittest.mock import AsyncMock

import pytest

from app.agents.base import BaseAgent
from app.agents.model_selector import ModelSelector
from app.agents.orchestrator import AgentOrchestrator

CLAUDE_ANALYSIS_RESPONSE = """ANALYSIS:
Multiple services reporting database connection failures under sustained load.

ERROR PATTERNS:
- TimeoutError: 12 occurrences in the last 30 minutes

ROOT CAUSE HYPOTHESIS:
Database connection pool exhaustion on the primary cluster.

CONFIDENCE: 0.85

RECOMMENDATION: Increase connection pool size for the API deployment
RECOMMENDATION: Restart the meinvoice-api pods to clear leaked connections
"""


@pytest.fixture
def mock_claude(monkeypatch):
    """Replace the Claude boundary on BaseAgent with a canned analysis."""
    fake = AsyncMock(return_value=CLAUDE_ANALYSIS_RESPONSE)

    async def _query(self, user_message, max_tokens=1024, model=None):
        return await fake(user_message, max_tokens=max_tokens)

    monkeypatch.setattr(BaseAgent, "_query_claude", _query)
    return fake


@pytest.fixture
def orchestrator(monkeypatch) -> AgentOrchestrator:
    """Real orchestrator with all six real agents wired up."""
    from app.settings import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    return AgentOrchestrator(model_selector=ModelSelector())


REALISTIC_INCIDENT_CONTEXT = {
    "project": "meinvoice",
    "logs": [
        {
            "level": "ERROR",
            "message": "TimeoutError: Database connection timeout",
            "timestamp": "2026-08-25T10:00:00Z",
        },
        {
            "level": "ERROR",
            "message": "TimeoutError: Database connection timeout",
            "timestamp": "2026-08-25T10:01:00Z",
        },
        {
            "level": "WARN",
            "message": "High memory usage detected",
            "timestamp": "2026-08-25T10:02:00Z",
        },
        {
            "level": "INFO",
            "message": "Health check passed",
            "timestamp": "2026-08-25T10:03:00Z",
        },
    ],
    "metrics": {"cpu_usage": 85, "memory_usage": 90, "response_time_p95": 2500},
    "k8s_state": {
        "pods": [
            {"name": "api-1", "status": "Running", "restarts": 0},
            {"name": "api-2", "status": "CrashLoopBackOff", "restarts": 5},
        ]
    },
}


@pytest.mark.integration
class TestMultiAgentEndToEnd:
    """Full workflow: selection -> parallel run -> aggregation."""

    @pytest.mark.asyncio
    async def test_incident_analysis_runs_relevant_agents(
        self, orchestrator, mock_claude
    ):
        result = await orchestrator.analyze(REALISTIC_INCIDENT_CONTEXT)

        assert result["agents_used"] == ["log", "metrics", "k8s"]
        assert result["agents_successful"] == 3
        assert result["total_agents"] == 3
        assert result["errors"] == []
        assert set(result["insights"].keys()) == {"log-analyst", "metrics-analyst", "k8s-expert"}
        assert result["execution_time"] >= 0

        # Every agent parsed recommendations from the mocked Claude response
        assert len(result["recommendations"]) >= 2
        assert any("connection pool" in r.lower() or "pool" in r.lower() for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_log_agent_preprocessing_feeds_prompt(
        self, orchestrator, mock_claude
    ):
        logs = REALISTIC_INCIDENT_CONTEXT["logs"]

        await orchestrator.analyze({"logs": logs}, agents=["log"])

        prompt = mock_claude.call_args.args[0]
        # Real preprocessing artifacts must appear in the built prompt
        assert "'unknown'" in prompt  # service placeholder from analyze()
        assert "Total log entries: 4" in prompt
        assert "Error entries: 2" in prompt

    @pytest.mark.asyncio
    async def test_confidence_reflects_data_volume(
        self, orchestrator, mock_claude
    ):
        rich_logs = [
            {"level": "INFO", "message": f"entry {i}"} for i in range(100)
        ]

        result = await orchestrator.analyze({"logs": rich_logs}, agents=["log"])

        log_result = result["agents"]["log-analyst"]
        # _calculate_confidence(quality=0.9 for >50 logs, volume bonus)
        assert log_result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_history_recorded_for_e2e_run(self, orchestrator, mock_claude):
        await orchestrator.analyze(REALISTIC_INCIDENT_CONTEXT)
        await orchestrator.analyze({"metrics": {"cpu": 50}}, agents=["metrics"])

        history = orchestrator.get_execution_history()
        assert len(history) == 2
        assert history[0]["success_count"] == 3
        assert history[1]["agents"] == ["metrics"]

    @pytest.mark.asyncio
    async def test_health_check_with_real_agents(self, orchestrator):
        health = await orchestrator.health_check()

        assert health["orchestrator"] == "healthy"
        assert health["total_agents"] == 6
        # Health entries are keyed by registry key, each carrying the
        # agent's internal display name
        assert set(health["agents"].keys()) == {
            "log", "metrics", "k8s", "cost", "security", "performance",
        }

    @pytest.mark.asyncio
    async def test_parallel_execution_with_model_selector(
        self, orchestrator, mock_claude
    ):
        selector = ModelSelector(default_model="balanced")
        # Moderate complexity incident -> balanced tier
        model = selector.select_model(REALISTIC_INCIDENT_CONTEXT)

        assert model == ModelSelector.MODELS["balanced"]

        result = await orchestrator.analyze(
            REALISTIC_INCIDENT_CONTEXT, agents=["log", "metrics"]
        )
        assert result["agents_successful"] == 2

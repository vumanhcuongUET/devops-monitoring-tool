"""
Unit tests for the AgentOrchestrator (Phase 10 Sprint 3).

Covers agent auto-selection, parallel execution, result aggregation,
consensus voting, recommendation deduplication/prioritization,
execution history and health checks - all with fake agents, no LLM calls.
"""

import asyncio
from typing import Any

import pytest

from app.agents.base import AgentResponse
from app.agents.orchestrator import AgentOrchestrator


class FakeAgent:
    """Deterministic stand-in for a BaseAgent."""

    def __init__(
        self,
        name: str,
        insights: dict[str, Any] | None = None,
        recommendations: list[str] | None = None,
        confidence: float = 0.8,
        error: str | None = None,
        raise_exc: bool = False,
        delay: float = 0.0,
        timeout: float = 5.0,
    ):
        self.name = name
        self.timeout = timeout
        self.insights = insights if insights is not None else {"finding": "ok"}
        self.recommendations = recommendations or []
        self.confidence = confidence
        self.error = error
        self.raise_exc = raise_exc
        self.delay = delay
        self.calls = 0
        self.last_context: dict[str, Any] | None = None

    async def analyze(self, context: dict[str, Any]) -> AgentResponse:
        self.calls += 1
        self.last_context = context
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_exc:
            raise RuntimeError(f"{self.name} exploded")
        return AgentResponse(
            agent_name=self.name,
            insights=self.insights,
            confidence=self.confidence,
            recommendations=self.recommendations,
            error=self.error,
        )

    async def health_check(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "status": "healthy",
            "timestamp": "2026-08-26T00:00:00",
        }


@pytest.fixture
def orchestrator(monkeypatch):
    """Orchestrator with real constructor but fake agents swapped in.

    A dummy API key keeps the real agents' Anthropic clients constructible;
    they are then replaced so no LLM call can ever happen.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    orch = AgentOrchestrator()
    orch.agents = {}
    return orch


def install_agents(orch: AgentOrchestrator, *agents: FakeAgent) -> None:
    orch.agents = {a.name: a for a in agents}


@pytest.mark.unit
class TestAgentSelection:
    """Auto-selection of agents based on context keys."""

    def test_selects_log_agent_for_logs(self, orchestrator):
        assert orchestrator._determine_agents({"logs": [{"message": "x"}]}) == ["log"]

    def test_selects_metrics_agent_for_prometheus_data(self, orchestrator):
        assert orchestrator._determine_agents({"prometheus_data": {"cpu": 1}}) == ["metrics"]

    def test_selects_k8s_agent_for_cluster_state(self, orchestrator):
        assert orchestrator._determine_agents({"cluster_state": {"pods": 1}}) == ["k8s"]

    def test_selects_cost_agent_for_resources(self, orchestrator):
        assert orchestrator._determine_agents({"resources": {"cpu_requests": 1}}) == ["cost"]

    def test_selects_security_agent_for_vulnerabilities(self, orchestrator):
        assert orchestrator._determine_agents({"vulnerabilities": [{"cve": "x"}]}) == ["security"]

    def test_selects_performance_agent_for_traces(self, orchestrator):
        assert orchestrator._determine_agents({"traces": [{"span": 1}]}) == ["performance"]

    def test_multi_source_context_selects_all_relevant_agents(self, orchestrator):
        context = {
            "logs": [{"message": "err"}],
            "metrics": {"cpu": 90},
            "k8s_state": {"pods": []},
        }
        assert orchestrator._determine_agents(context) == ["log", "metrics", "k8s"]

    def test_empty_context_selects_no_agents(self, orchestrator):
        assert orchestrator._determine_agents({}) == []


@pytest.mark.unit
class TestAnalyzeWorkflow:
    """End-to-end orchestration with fake agents."""

    @pytest.mark.asyncio
    async def test_analyze_auto_selects_and_aggregates(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent("log", insights={"patterns": 2}, confidence=0.9),
            FakeAgent("metrics", insights={"cpu_high": True}, confidence=0.7),
        )
        context = {"logs": [{"message": "e"}], "metrics": {"cpu": 95}}

        result = await orchestrator.analyze(context)

        assert result["agents_used"] == ["log", "metrics"]
        assert result["agents_successful"] == 2
        assert result["total_agents"] == 2
        assert result["confidence"] == pytest.approx(0.8)
        assert result["insights"]["log"] == {"patterns": 2}
        assert result["errors"] == []
        assert result["execution_time"] >= 0

    @pytest.mark.asyncio
    async def test_analyze_with_explicit_agents_skips_selection(self, orchestrator):
        metrics_agent = FakeAgent("metrics", confidence=0.9)
        log_agent = FakeAgent("log")
        install_agents(orchestrator, log_agent, metrics_agent)

        result = await orchestrator.analyze({}, agents=["metrics"])

        assert result["agents_used"] == ["metrics"]
        assert metrics_agent.calls == 1
        assert log_agent.calls == 0

    @pytest.mark.asyncio
    async def test_analyze_no_matching_agents_returns_error(self, orchestrator):
        install_agents(orchestrator, FakeAgent("log"))

        result = await orchestrator.analyze({})

        assert "error" in result
        assert result["agents_used"] == []

    @pytest.mark.asyncio
    async def test_analyze_passes_context_to_every_agent(self, orchestrator):
        agent_a = FakeAgent("log")
        agent_b = FakeAgent("metrics")
        install_agents(orchestrator, agent_a, agent_b)
        context = {"logs": [1], "metrics": {"cpu": 1}}

        await orchestrator.analyze(context)

        assert agent_a.last_context is context
        assert agent_b.last_context is context

    @pytest.mark.asyncio
    async def test_unknown_explicit_agent_is_skipped(self, orchestrator):
        log_agent = FakeAgent("log")
        install_agents(orchestrator, log_agent)

        result = await orchestrator.analyze({}, agents=["log", "nonexistent"])

        assert result["agents_used"] == ["log", "nonexistent"]
        assert result["agents_successful"] == 1
        assert log_agent.calls == 1


@pytest.mark.unit
class TestFailureHandling:
    """Agent failures must degrade gracefully, not break the analysis."""

    @pytest.mark.asyncio
    async def test_raising_agent_recorded_as_error(self, orchestrator):
        bad = FakeAgent("log", raise_exc=True)
        good = FakeAgent("metrics", confidence=0.9)
        install_agents(orchestrator, bad, good)

        result = await orchestrator.analyze(
            {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}, consensus_threshold=1.1
        )

        assert result["agents_successful"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["agent"] == "log"
        assert "exploded" in result["errors"][0]["error"]
        # Successful agent's insights still aggregated
        assert "metrics" in result["insights"]

    @pytest.mark.asyncio
    async def test_timeout_produces_error_response(self, orchestrator):
        slow = FakeAgent("log", delay=0.5, timeout=0.05)
        fast = FakeAgent("metrics", confidence=0.9)
        install_agents(orchestrator, slow, fast)

        result = await orchestrator.analyze(
            {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}, consensus_threshold=1.1
        )

        timed_out = next(e for e in result["errors"] if e["agent"] == "log")
        assert timed_out["error"] == "Analysis timed out"
        assert result["agents_successful"] == 1

    @pytest.mark.asyncio
    async def test_confidence_ignores_failed_agents(self, orchestrator):
        failed = FakeAgent("log", confidence=0.9, error="No logs provided")
        healthy = FakeAgent("metrics", confidence=0.6)
        install_agents(orchestrator, failed, healthy)

        result = await orchestrator.analyze(
            {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}, consensus_threshold=0.1
        )

        # Only the successful (healthy) agent contributes to average confidence
        assert result["confidence"] == pytest.approx(0.6)


@pytest.mark.unit
class TestConsensusVoting:
    """Consensus triggers on low confidence or many recommendations."""

    @pytest.mark.asyncio
    async def test_consensus_runs_below_threshold(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent("log", confidence=0.4, recommendations=["Scale up deployment"]),
            FakeAgent("metrics", confidence=0.45, recommendations=["Scale up deployment"]),
        )
        context = {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}

        result = await orchestrator.analyze(context)  # default threshold 0.6

        consensus = result.get("consensus")
        assert consensus is not None
        rec = consensus["recommendations"]["Scale up deployment"]
        assert rec["votes"] == 2
        assert rec["agreement"] == pytest.approx(1.0)
        assert consensus["agreement_level"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_majority_filter_excludes_single_votes(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent("log", confidence=0.3, recommendations=["Restart pods"]),
            FakeAgent("metrics", confidence=0.3, recommendations=["Scale up"]),
            FakeAgent("k8s", confidence=0.3, recommendations=["Drain node"]),
        )
        context = {"logs": [{"message": "e"}], "metrics": {"cpu": 90}, "k8s_state": {"pods": [{"name": "p"}]}}

        result = await orchestrator.analyze(context)

        votes = result["consensus"]["recommendations"]
        # Majority needs 2 of 3 votes - each recommendation got exactly 1
        assert votes == {}

    @pytest.mark.asyncio
    async def test_no_consensus_when_confident_and_focused(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent("log", confidence=0.95, recommendations=["Scale up deployment"]),
            FakeAgent("metrics", confidence=0.9),
        )
        context = {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}

        result = await orchestrator.analyze(context)

        assert "consensus" not in result

    @pytest.mark.asyncio
    async def test_critical_finding_with_low_confidence_triggers_consensus(
        self, orchestrator
    ):
        install_agents(
            orchestrator,
            FakeAgent("security", confidence=0.65, insights={"overall_risk": "critical"}),
        )
        context = {"security_data": {"findings": [1]}}

        result = await orchestrator.analyze(context, consensus_threshold=0.6)

        assert "consensus" in result


@pytest.mark.unit
class TestRecommendationAggregation:
    """Dedup + priority ordering of merged recommendations."""

    @pytest.mark.asyncio
    async def test_duplicates_removed_case_insensitive(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent("log", recommendations=["Scale up the API"], confidence=0.9),
            FakeAgent("metrics", recommendations=["scale up the api"], confidence=0.9),
        )

        result = await orchestrator.analyze(
            {"logs": [{"message": "e"}], "metrics": {"cpu": 90}}, consensus_threshold=1.1
        )

        assert result["recommendations"].count("Scale up the API") == 1

    @pytest.mark.asyncio
    async def test_priority_keywords_ordered_first(self, orchestrator):
        install_agents(
            orchestrator,
            FakeAgent(
                "security",
                recommendations=["Enable network policy"],
                confidence=0.9,
            ),
            FakeAgent(
                "log",
                recommendations=["URGENT: rotate credentials"],
                confidence=0.9,
            ),
        )

        result = await orchestrator.analyze(
            {"security_data": {"findings": [1]}, "logs": [{"message": "e"}]}, consensus_threshold=1.1
        )

        assert result["recommendations"][0] == "URGENT: rotate credentials"


@pytest.mark.unit
class TestHistoryAndHealth:
    """Execution history tracking and health checks."""

    @pytest.mark.asyncio
    async def test_history_records_each_execution(self, orchestrator):
        install_agents(orchestrator, FakeAgent("log", confidence=0.9))
        context = {"logs": [{"message": "e"}]}

        await orchestrator.analyze(context)
        await orchestrator.analyze(context)

        history = orchestrator.get_execution_history()
        assert len(history) == 2
        assert history[0]["context_keys"] == ["logs"]
        assert history[0]["agents"] == ["log"]
        assert history[0]["success_count"] == 1

    def test_history_capped_at_100_entries(self, orchestrator):
        orchestrator._execution_history = [
            {"context_keys": [], "agents": []} for _ in range(150)
        ]

        assert len(orchestrator.get_execution_history()) == 100

    @pytest.mark.asyncio
    async def test_health_check_reports_all_agents(self, orchestrator):
        install_agents(orchestrator, FakeAgent("log"), FakeAgent("metrics"))

        health = await orchestrator.health_check()

        assert health["orchestrator"] == "healthy"
        assert health["total_agents"] == 2
        assert set(health["agents"].keys()) == {"log", "metrics"}
        assert all(a["status"] == "healthy" for a in health["agents"].values())

    @pytest.mark.asyncio
    async def test_health_check_survives_unhealthy_agent(self, orchestrator):
        bad = FakeAgent("log")

        async def broken_health_check():
            raise RuntimeError("health probe failed")

        bad.health_check = broken_health_check
        install_agents(orchestrator, bad, FakeAgent("metrics"))

        health = await orchestrator.health_check()

        assert health["agents"]["log"]["status"] == "unhealthy"
        assert health["agents"]["metrics"]["status"] == "healthy"

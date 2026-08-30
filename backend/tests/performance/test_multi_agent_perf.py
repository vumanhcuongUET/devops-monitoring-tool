"""
Performance tests for the multi-agent system (Phase 10 Sprint 3 - Day 15).

Validates orchestration overhead stays well within the SLA budget with
the Claude boundary mocked, and that model selection is cheap enough
to run on every request.

Run with: pytest backend/tests/performance/test_multi_agent_perf.py -v -m benchmark
"""

import time
from unittest.mock import AsyncMock

import pytest

from app.agents.base import BaseAgent
from app.agents.model_selector import ModelSelector
from app.agents.orchestrator import AgentOrchestrator

# Performance targets (SLA)
TARGET_FULL_ANALYSIS_SECONDS = 10.0  # plan SLA for multi-agent analysis
TARGET_ORCHESTRATION_OVERHEAD_MS = 50.0  # aggregation adds little vs LLM latency
TARGET_MODEL_SELECTION_MS = 5.0  # per-request cost of picking a model


def _build_context(num_logs: int = 50) -> dict:
    return {
        "project": "meinvoice",
        "logs": [
            {"level": "INFO" if i % 5 else "ERROR",
             "message": f"log entry {i}",
             "timestamp": f"2026-08-26T10:{i % 60:02d}:00Z"}
            for i in range(num_logs)
        ],
        "metrics": {"cpu_usage": 50, "memory_usage": 60},
    }


@pytest.fixture
def orchestrator(monkeypatch) -> AgentOrchestrator:
    """Orchestrator whose agents hit a mocked Claude API."""
    from app.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    orch = AgentOrchestrator(model_selector=ModelSelector())
    return orch


@pytest.fixture
def mock_claude(monkeypatch):
    """Instant canned Claude responses so latency measures orchestration only."""
    fake = AsyncMock(return_value="ANALYSIS: ok\nCONFIDENCE: 0.8")

    async def _query(self, user_message, max_tokens=1024, model=None):
        return await fake(user_message, max_tokens=max_tokens)

    monkeypatch.setattr(BaseAgent, "_query_claude", _query)
    return fake


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestMultiAgentPerformance:
    """Latency characteristics of orchestrated multi-agent analysis."""

    async def test_full_analysis_within_sla(self, orchestrator, mock_claude):
        """2-agent analysis must complete under the 10s SLA."""
        context = _build_context()

        start = time.perf_counter()
        result = await orchestrator.analyze(context)
        duration = time.perf_counter() - start

        assert duration < TARGET_FULL_ANALYSIS_SECONDS, (
            f"Analysis took {duration:.2f}s (target <{TARGET_FULL_ANALYSIS_SECONDS}s)"
        )
        assert result["agents_successful"] == 2

    async def test_orchestration_overhead_is_minimal(self, orchestrator, mock_claude):
        """Aggregation/consensus overhead must be milliseconds, not seconds.

        Compares a single agent call against two parallel ones; the delta
        isolates aggregation work from LLM latency.
        """
        context = _build_context()

        start = time.perf_counter()
        await orchestrator.analyze(context, agents=["log"])
        single = time.perf_counter() - start

        start = time.perf_counter()
        await orchestrator.analyze(context, agents=["log", "metrics"])
        double = time.perf_counter() - start

        overhead_ms = (double - single) * 1000
        assert overhead_ms < TARGET_ORCHESTRATION_OVERHEAD_MS, (
            f"Aggregation added {overhead_ms:.1f}ms "
            f"(target <{TARGET_ORCHESTRATION_OVERHEAD_MS}ms)"
        )

    async def test_model_selection_latency(self):
        """Model selection must be fast enough for every request."""
        selector = ModelSelector()
        contexts = [_build_context(num_logs=10 * (i + 1)) for i in range(25)]

        start = time.perf_counter()
        for ctx in contexts:
            selector.select_model(ctx)
        per_call_ms = (time.perf_counter() - start) / len(contexts) * 1000

        assert per_call_ms < TARGET_MODEL_SELECTION_MS, (
            f"select_model averaged {per_call_ms:.2f}ms "
            f"(target <{TARGET_MODEL_SELECTION_MS}ms)"
        )

    async def test_concurrent_analyses_scale(self, orchestrator, mock_claude):
        """Ten concurrent analyses must all succeed promptly."""
        import asyncio

        contexts = [_build_context() for _ in range(10)]

        start = time.perf_counter()
        results = await asyncio.gather(
            *[orchestrator.analyze(ctx) for ctx in contexts]
        )
        duration = time.perf_counter() - start

        assert all(r["agents_successful"] == 2 for r in results)
        assert duration < TARGET_FULL_ANALYSIS_SECONDS, (
            f"10 concurrent analyses took {duration:.2f}s"
        )

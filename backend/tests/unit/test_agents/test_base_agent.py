"""Unit tests for BaseAgent._query_claude — token-optimization behaviors.

Covers the model override plumbing, system-prompt caching and usage
recording added in the Phase 14 follow-up. No network calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import Message, TextBlock, Usage
from prometheus_client import REGISTRY

from app.agents.base import AgentResponse, BaseAgent
from app.config import settings


def _metric(name: str, path: str, model: str) -> float:
    return REGISTRY.get_sample_value(name, {"path": path, "model": model}) or 0.0


class StubAgent(BaseAgent):
    """Minimal concrete agent."""

    def get_prompt_template(self) -> str:
        return "You are a stub expert."

    async def analyze(self, context, model=None) -> AgentResponse:
        text = await self._query_claude(str(context), model=model)
        return AgentResponse(agent_name=self.name, insights={"text": text})


def _sdk_message(text: str = "ok", input_tokens: int = 11, output_tokens: int = 4):
    return Message(
        id="msg_stub",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        model="stub-model",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    stub = StubAgent(name="stub")
    stub.client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=_sdk_message()))
    )
    return stub


@pytest.mark.unit
class TestQueryClaude:
    async def test_uses_configured_model_by_default(self, agent):
        await agent._query_claude("hello")

        assert agent.client.messages.create.call_args.kwargs["model"] == agent.model

    async def test_model_override_is_passed_through(self, agent):
        await agent._query_claude("hello", model="claude-haiku-4-5-20251001")

        assert (
            agent.client.messages.create.call_args.kwargs["model"]
            == "claude-haiku-4-5-20251001"
        )

    async def test_system_prompt_is_cache_control_marked(self, agent):
        await agent._query_claude("hello")

        system = agent.client.messages.create.call_args.kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["text"] == "You are a stub expert."
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    async def test_usage_is_recorded_under_agents_path(self, agent):
        before_in = _metric("llm_input_tokens_total", "agents", agent.model)
        before_out = _metric("llm_output_tokens_total", "agents", agent.model)

        text = await agent._query_claude("hello")

        assert text == "ok"
        assert _metric("llm_input_tokens_total", "agents", agent.model) == before_in + 11
        assert _metric("llm_output_tokens_total", "agents", agent.model) == before_out + 4

    async def test_usage_recorded_under_overridden_model(self, agent):
        model = "claude-haiku-4-5-20251001"
        before_in = _metric("llm_input_tokens_total", "agents", model)

        await agent._query_claude("hello", model=model)

        assert _metric("llm_input_tokens_total", "agents", model) == before_in + 11

    async def test_request_counter_counts_every_call(self, agent):
        before = _metric("llm_api_requests_total", "agents", agent.model)

        await agent._query_claude("hello")
        await agent._query_claude("again")

        assert _metric("llm_api_requests_total", "agents", agent.model) == before + 2

    async def test_api_failure_still_raises(self, agent):
        agent.client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await agent._query_claude("hello")


@pytest.mark.unit
class TestAgentModelParam:
    async def test_analyze_forwards_model_to_query(self, agent):
        """The public entry point must take the orchestrator's override."""
        seen = {}

        async def fake_query(user_message, max_tokens=1024, model=None):
            seen["model"] = model
            seen["user_message"] = user_message
            return "done"

        agent._query_claude = fake_query

        response = await agent.analyze({"logs": [1]}, model="haiku-tier")

        assert seen["model"] == "haiku-tier"
        assert seen["user_message"] == str({"logs": [1]})
        assert response.insights == {"text": "done"}

    async def test_analyze_without_model_uses_none(self, agent):
        seen = {}

        async def fake_query(user_message, max_tokens=1024, model=None):
            seen["model"] = model
            return "done"

        agent._query_claude = fake_query

        await agent.analyze({})

        assert seen["model"] is None

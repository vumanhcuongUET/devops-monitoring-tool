"""
Unit tests for LLMClient.

Tests the LLM client functionality including:
- Triage card generation
- Health checks
- Prompt building
- Response parsing
- Token optimization: compact JSON, severity quotas, usage recording,
  prompt caching, fast-tier routing (2026-08-30 follow-up)
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from anthropic import APIError
from anthropic.types import (
    Message,
    MessageDeltaUsage,
    RawContentBlockDeltaEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    TextBlock,
    TextDelta,
    Usage,
)
from prometheus_client import REGISTRY

from app.config import settings
from app.services.llm_client import (
    FAST_MODEL,
    LLMClient,
    LOG_SEVERITY_QUOTAS,
    sample_logs_by_severity,
)


def _metric(name: str, path: str, model: str) -> float:
    return REGISTRY.get_sample_value(name, {"path": path, "model": model}) or 0.0


def _message(text: str, input_tokens: int = 0, output_tokens: int = 0) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text=text)],
        model="claude-sonnet-4-20250514",
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _stream_events(input_tokens: int, output_tokens: int, text: str):
    """Raw MessageStreamEvent sequence mimicking the Anthropic wire format."""
    return [
        RawMessageStartEvent.model_construct(
            type="message_start",
            message=_message("", input_tokens=input_tokens),
        ),
        RawContentBlockDeltaEvent.model_construct(
            type="content_block_delta",
            index=0,
            delta=TextDelta(type="text_delta", text=text),
        ),
        RawMessageDeltaEvent.model_construct(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="end_turn"),
            usage=MessageDeltaUsage(output_tokens=output_tokens),
        ),
    ]


class FakeMessages:
    """Stands in for anthropic.AsyncAnthropic().messages."""

    def __init__(self, message=None, events=None):
        self.message = message
        self.events = events or []
        self.create_kwargs: dict | None = None
        self.stream_kwargs: dict | None = None

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        return self.message

    def stream(self, **kwargs):
        self.stream_kwargs = kwargs
        outer = self

        class _Stream:
            async def __aenter__(self):
                self._it = iter(outer.events)
                return self

            async def __aexit__(self, *exc):
                return False

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration from None

        return _Stream()


@pytest.fixture
def llm(monkeypatch):
    """Real LLMClient wired to a fake Anthropic SDK client."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    client = LLMClient()
    client.client = SimpleNamespace(messages=FakeMessages())
    return client


@pytest.mark.unit
@pytest.mark.service
class TestLLMClient:
    """Test suite for LLMClient."""

    @pytest.mark.asyncio
    async def test_generate_triage_card_returns_triage_card(self, mock_llm_client):
        """Test that generate_triage_card returns a valid triage card."""
        result = await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-001",
            alert_message="High error rate detected",
            time_range_minutes=60
        )

        assert "project" in result
        assert "incident_id" in result
        assert "summary" in result
        assert "severity" in result
        assert "findings" in result
        assert "recommendations" in result
        assert result["project"] == "test"

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_status(self, mock_llm_client):
        """Test that health_check returns healthy status."""
        result = await mock_llm_client.health_check()

        assert result["status"] == "healthy"
        assert "model" in result

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_findings(self, mock_llm_client):
        """Test that generate_triage_card can return findings."""
        mock_llm_client.generate_triage_card = AsyncMock(return_value={
            "project": "test",
            "incident_id": "test-001",
            "summary": "Database connection timeout",
            "severity": "high",
            "findings": [
                {
                    "type": "root_cause",
                    "title": "Database connection pool exhausted",
                    "severity": "critical",
                    "confidence": 0.9,
                    "evidence": ["Connection timeout errors", "High wait time"]
                }
            ],
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Check database connectivity",
                    "command": "kubectl exec -n test -- pg_isready"
                }
            ]
        })

        result = await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-001",
            alert_message="Database errors"
        )

        assert len(result["findings"]) == 1
        assert result["findings"][0]["type"] == "root_cause"
        assert len(result["recommendations"]) == 1

    @pytest.mark.asyncio
    async def test_health_check_with_api_error(self, mock_llm_client):
        """Test that health_check handles API errors."""
        mock_llm_client.health_check = AsyncMock(
            side_effect=APIError(MagicMock(), "API request failed", body=None)
        )

        with pytest.raises(APIError):
            await mock_llm_client.health_check()

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_custom_time_range(self, mock_llm_client):
        """Test that generate_triage_card accepts custom time ranges."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-002",
            time_range_minutes=30
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_triage_card_with_severity_threshold(self, mock_llm_client):
        """Test that generate_triage_card accepts severity threshold."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-003",
            severity_threshold="high"
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_triage_card_without_recommendations(self, mock_llm_client):
        """Test that generate_triage_card can skip recommendations."""
        await mock_llm_client.generate_triage_card(
            project="test-project",
            incident_id="test-004",
            include_recommendations=False
        )

        mock_llm_client.generate_triage_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_with_different_models(self, mock_llm_client):
        """Test that health_check reports configured model."""
        mock_llm_client.health_check = AsyncMock(return_value={
            "status": "healthy",
            "model": "claude-opus-4-20250514"
        })

        result = await mock_llm_client.health_check()

        assert result["model"] == "claude-opus-4-20250514"


@pytest.mark.unit
class TestCompactJsonPrompts:
    """Token optimization: prompts must use compact JSON, not indent=2."""

    def _prompt(self, llm, logs=None, metrics=None):
        return llm._build_user_prompt(
            project="test",
            incident_id="i-1",
            alert_message="boom",
            context_data={"logs": logs or [], "metrics": metrics or {}},
            time_range=timedelta(minutes=30),
        )

    def test_log_json_block_is_single_line(self, llm):
        prompt = self._prompt(llm, logs=[{"level": "ERROR", "message": "x\nystack"}])

        dump = prompt.split("```json")[1].split("```")[0].strip()
        # Compact serialization: the JSON payload is one line (escaped \n
        # inside messages is fine — that's data, not formatting).
        assert len(dump.splitlines()) == 1

    def test_metrics_json_block_is_compact(self, llm):
        prompt = self._prompt(llm, metrics={"cpu": 90, "mem": {"used": 1, "total": 2}})

        block = prompt.split("```json")[1].split("```")[0].strip()
        assert "\n" not in block
        assert '"mem": {"used": 1' in block  # separators without padding


@pytest.mark.unit
class TestSeverityQuotaSampling:
    """sample_logs_by_severity replaces the blunt logs[:50] cut."""

    @staticmethod
    def _logs(counts: dict[str, int]) -> list[dict]:
        logs = []
        for level, n in counts.items():
            logs.extend({"level": level, "message": f"{level} {i}"} for i in range(n))
        return logs

    def test_small_batches_pass_through_untouched(self):
        logs = self._logs({"ERROR": 10, "INFO": 20})

        kept, note = sample_logs_by_severity(logs)

        assert kept == logs
        assert note is None

    def test_boundary_of_50_is_not_sampled(self):
        logs = self._logs({"INFO": 50})

        kept, note = sample_logs_by_severity(logs)

        assert len(kept) == 50
        assert note is None

    def test_large_batches_are_capped_by_quota(self):
        logs = self._logs({"CRITICAL": 12, "ERROR": 80, "WARNING": 40, "INFO": 5})
        assert len(logs) == 137

        kept, note = sample_logs_by_severity(logs)

        by_level = {}
        for log in kept:
            by_level[log["level"]] = by_level.get(log["level"], 0) + 1
        assert by_level == {
            "CRITICAL": 5,
            "ERROR": 10,
            "WARNING": 10,
            "INFO": 5,
        }
        assert len(kept) == sum(LOG_SEVERITY_QUOTAS.values()) == 30
        assert note is not None
        assert "showing 30 of 137 logs by severity" in note
        # Per-severity breakdown surfaces what was dropped
        assert "error 10/80" in note

    def test_quota_keeps_most_recent_first_per_bucket(self):
        # ES returns desc-by-timestamp; earlier entries win the quota.
        logs = [{"level": "ERROR", "message": f"err-{i}"} for i in range(20)] + [
            {"level": "INFO", "message": f"info-{i}"} for i in range(40)
        ]

        kept, _note = sample_logs_by_severity(logs)

        kept_errors = [log for log in kept if log["level"] == "ERROR"]
        assert kept_errors == logs[:10]

    def test_unknown_and_missing_levels_bucket_as_info(self):
        logs = [
            {"level": "TRACE", "message": "t"},
            {"message": "no level"},
            {"level": "FATAL", "message": "f"},
        ] * 20  # 60 entries -> triggers sampling

        kept, _note = sample_logs_by_severity(logs)

        assert len([log for log in kept if log.get("level") in ("TRACE", None)]) <= 5
        assert len([log for log in kept if log.get("level") == "FATAL"]) <= 5

    def test_prompt_embeds_sampling_note(self, llm):
        logs = self._logs({"ERROR": 40, "INFO": 30})

        prompt = llm._build_user_prompt(
            project="p",
            incident_id=None,
            alert_message=None,
            context_data={"logs": logs},
            time_range=timedelta(minutes=30),
        )

        # error quota 10 + info quota 5 of 70 total
        assert "showing 15 of 70 logs by severity" in prompt


@pytest.mark.unit
class TestUsageRecording:
    """Every call site must feed the llm_*_tokens_total counters."""

    @pytest.mark.asyncio
    async def test_triage_records_input_and_output_tokens(self, llm):
        llm.client.messages.message = _message(
            '{"summary": "s", "severity": "low"}', input_tokens=100, output_tokens=50
        )
        before_in = _metric("llm_input_tokens_total", "triage", llm.model)
        before_out = _metric("llm_output_tokens_total", "triage", llm.model)

        card = await llm.generate_triage_card(
            request=MagicMock(
                project="p",
                incident_id="i",
                alert_message="a",
                time_range_minutes=60,
                include_recommendations=True,
            ),
            context_data={},
        )

        assert _metric("llm_input_tokens_total", "triage", llm.model) == before_in + 100
        assert _metric("llm_output_tokens_total", "triage", llm.model) == before_out + 50
        # tokens_used is now the honest total, not output-only
        assert card.tokens_used == 150

    @pytest.mark.asyncio
    async def test_streaming_captures_usage_from_events(self, llm):
        llm.client.messages.events = _stream_events(
            input_tokens=120, output_tokens=42, text='{"summary": "s"}'
        )
        before_in = _metric("llm_input_tokens_total", "stream", llm.model)
        before_out = _metric("llm_output_tokens_total", "stream", llm.model)

        chunks = [c async for c in llm.analyze_with_streaming(
            project="p", incident_id=None, alert_message=None, context_data={}
        )]

        assert _metric("llm_input_tokens_total", "stream", llm.model) == before_in + 120
        assert _metric("llm_output_tokens_total", "stream", llm.model) == before_out + 42
        assert any('"type": "complete"' in c for c in chunks)

    @pytest.mark.asyncio
    async def test_simple_stream_records_usage_on_fast_model(self, llm):
        llm.client.messages.events = _stream_events(
            input_tokens=15, output_tokens=7, text="short answer"
        )
        before_in = _metric("llm_input_tokens_total", "simple_stream", FAST_MODEL)
        before_req = _metric("llm_api_requests_total", "simple_stream", FAST_MODEL)

        _chunks = [c async for c in llm.analyze_simple_streaming(
            context={"cpu": 50}, question="what is wrong?"
        )]

        assert _metric("llm_input_tokens_total", "simple_stream", FAST_MODEL) == before_in + 15
        assert _metric("llm_output_tokens_total", "simple_stream", FAST_MODEL) >= 7
        assert _metric("llm_api_requests_total", "simple_stream", FAST_MODEL) == before_req + 1

    @pytest.mark.asyncio
    async def test_health_check_records_usage_on_fast_model(self, llm):
        llm.client.messages.message = _message("OK", input_tokens=3, output_tokens=1)
        before_req = _metric("llm_api_requests_total", "health", FAST_MODEL)
        llm._health_cache = None  # bypass the 5-minute TTL

        healthy = await llm.health_check()

        assert healthy is True
        assert _metric("llm_api_requests_total", "health", FAST_MODEL) == before_req + 1
        assert _metric("llm_output_tokens_total", "health", FAST_MODEL) >= 1


@pytest.mark.unit
class TestModelRouting:
    """Cheap paths must not burn the full triage model."""

    @pytest.mark.asyncio
    async def test_simple_stream_uses_fast_model(self, llm):
        llm.client.messages.events = _stream_events(10, 5, "hi")

        _chunks = [c async for c in llm.analyze_simple_streaming(
            context={}, question="q"
        )]

        assert llm.client.messages.stream_kwargs["model"] == FAST_MODEL
        assert FAST_MODEL != llm.model  # sanity: fast tier differs from default

    @pytest.mark.asyncio
    async def test_health_check_uses_fast_model(self, llm):
        llm.client.messages.message = _message("OK")
        llm._health_cache = None

        await llm.health_check()

        assert llm.client.messages.create_kwargs["model"] == FAST_MODEL

    @pytest.mark.asyncio
    async def test_triage_stays_on_configured_model(self, llm):
        llm.client.messages.message = _message('{"summary": "s"}')

        await llm.generate_triage_card(
            request=MagicMock(
                project="p",
                incident_id=None,
                alert_message=None,
                time_range_minutes=60,
                include_recommendations=True,
            ),
            context_data={},
        )

        assert llm.client.messages.create_kwargs["model"] == llm.model


@pytest.mark.unit
class TestPromptCaching:
    """System prompts carry cache_control so repeat calls hit the cache."""

    def _assert_cached(self, system):
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        assert "Triage Card" in system[0]["text"]

    @pytest.mark.asyncio
    async def test_triage_system_block_is_cached(self, llm):
        llm.client.messages.message = _message('{"summary": "s"}')

        await llm.generate_triage_card(
            request=MagicMock(
                project="p",
                incident_id=None,
                alert_message=None,
                time_range_minutes=60,
                include_recommendations=True,
            ),
            context_data={},
        )

        self._assert_cached(llm.client.messages.create_kwargs["system"])

    @pytest.mark.asyncio
    async def test_streaming_system_block_is_cached(self, llm):
        llm.client.messages.events = _stream_events(10, 5, "x")

        _chunks = [c async for c in llm.analyze_with_streaming(
            project="p", incident_id=None, alert_message=None, context_data={}
        )]

        self._assert_cached(llm.client.messages.stream_kwargs["system"])

"""
LLM Client Service - Claude API integration for Triage Card generation.

This module handles communication with Anthropic's Claude API to generate
AI-powered incident analysis and recommendations.

Based on strategic roadmap: docs/chien_luoc_tong_the.md (Giai đoạn 1)
"""

import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
from anthropic.types import Message

from app.agents.model_selector import ModelSelector
from app.config import settings
from app.llm_metrics import record_request, record_usage
from app.models.triage_card import (
    Finding,
    FindingType,
    Recommendation,
    SeverityLevel,
    TriageCard,
    TriageCardRequest,
)

# Cheap fast-tier model for low-stakes calls (simple-stream Q&A, health
# probes). Single source of truth is the selector's tier table — do not
# duplicate model ids here.
FAST_MODEL = ModelSelector.MODELS["fast"]

# Per-severity keep quotas applied when a log payload is too large to ship
# wholesale (see sample_logs_by_severity). Sum = 30 logs max.
LOG_SEVERITY_QUOTAS: dict[str, int] = {
    "critical": 5,
    "error": 10,
    "warning": 10,
    "info": 5,
}
# Quotas only kick in above this many log entries.
LOG_QUOTA_TRIGGER = 50

_LEVEL_TO_BUCKET = {
    "critical": "critical",
    "fatal": "critical",
    "alert": "critical",
    "emerg": "critical",
    "error": "error",
    "err": "error",
    "warn": "warning",
    "warning": "warning",
    # everything else (info/debug/trace/missing) lands in the info bucket
}


def _bucket_for_log(log: Any) -> str:
    """Map a log entry to its severity bucket (default: info)."""
    if not isinstance(log, dict):
        return "info"
    level = str(log.get("level", "")).lower().strip()
    return _LEVEL_TO_BUCKET.get(level, "info")


def sample_logs_by_severity(
    logs: list[Any],
    quotas: dict[str, int] | None = None,
    trigger: int = LOG_QUOTA_TRIGGER,
) -> tuple[list[Any], str | None]:
    """Sample oversized log lists by severity quotas.

    Replaces the old blunt ``logs[:50]`` cut, which starved the model of
    critical entries while flooding it with info noise. When more than
    ``trigger`` logs arrive, keep at most ``quotas`` entries per severity
    bucket (most recent first — ES returns desc-by-timestamp) and drop the
    rest. Original relative order is preserved.

    Returns:
        (kept_logs, note) where note is None when no sampling was applied,
        else a human-readable summary to embed in the prompt.
    """
    quotas = quotas if quotas is not None else LOG_SEVERITY_QUOTAS
    logs = list(logs or [])
    if len(logs) <= trigger:
        return logs, None

    seen: dict[str, int] = {bucket: 0 for bucket in ("critical", "error", "warning", "info")}
    kept: dict[str, int] = {bucket: 0 for bucket in seen}
    sampled: list[Any] = []

    for log in logs:
        bucket = _bucket_for_log(log)
        seen[bucket] += 1
        if kept[bucket] < quotas.get(bucket, 0):
            sampled.append(log)
            kept[bucket] += 1

    breakdown = ", ".join(f"{b} {kept[b]}/{seen[b]}" for b in seen)
    note = f"showing {len(sampled)} of {len(logs)} logs by severity ({breakdown})"
    return sampled, note


def _usage_tokens(usage: Any, field: str) -> int:
    """Read a token count off an Anthropic usage object/dict; 0 if absent."""
    if usage is None:
        return 0
    value = usage.get(field) if isinstance(usage, dict) else getattr(usage, field, 0)
    return int(value or 0)


class LLMClient:
    """
    Client for Anthropic Claude API.

    Handles prompt construction, API calls, and response parsing for
    Triage Card generation.
    """

    # System prompt - defines the AI's role and behavior
    SYSTEM_PROMPT = """You are a DevOps Expert AI Assistant specialized in incident analysis and troubleshooting.

Your role is to analyze monitoring data (logs, metrics, alerts) and generate structured Triage Cards that help DevOps teams quickly understand and respond to system issues.

## Your Output Format

You must respond with a JSON object containing:
{
  "summary": "One-paragraph executive summary of the situation",
  "severity": "critical|high|medium|low|info",
  "status": "investigating|mitigating|resolved",
  "findings": [
    {
      "type": "root_cause|symptom|contributing_factor|anomaly|configuration_issue|dependency_issue",
      "title": "Brief title",
      "description": "Detailed description",
      "severity": "critical|high|medium|low|info",
      "source": "elasticsearch|prometheus|kubernetes|apm",
      "evidence": "Supporting data points",
      "confidence": 0.0-1.0
    }
  ],
  "recommendations": [
    {
      "priority": 1-10,
      "action": "What to do",
      "command": "kubectl command or API call",
      "reason": "Why this action",
      "risk": "critical|high|medium|low|info",
      "estimated_impact": "Expected outcome"
    }
  ]
}

## Your Analysis Approach

1. **Identify the immediate problem** - What's failing right now?
2. **Trace the root cause** - Use the provided data to find the likely cause
3. **Assess impact** - What services/users are affected?
4. **Recommend actions** - Prioritized by urgency and impact

## Important Guidelines

- Be concise but thorough. Focus on actionable insights.
- Cite evidence from the provided data.
- If data is insufficient, state what additional information is needed.
- For commands, use actual kubectl, helm, or argocd syntax.
- Confidence scores: 0.9-1.0 = very certain, 0.7-0.9 = likely, 0.5-0.7 = possible, <0.5 = speculative.
- Default to medium severity if uncertain.
- Always recommend human verification before executing critical actions.

You communicate in Vietnamese by default, unless the user specifically requests English."""

    # Anthropic prompt caching: the system prompt (~90 lines) is identical on
    # every call, so marking it ephemeral-cached bills repeat reads at the
    # discounted cache-read rate. Harmless below the ~1024-token cache
    # minimum (the API simply doesn't cache).
    @staticmethod
    def _cached_system(prompt: str) -> list[dict[str, Any]]:
        return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]

    def __init__(self):
        """Initialize the Claude API client."""
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL
        self._health_cache: bool | None = None
        self._health_cache_time: float = 0

    def _build_user_prompt(
        self,
        project: str,
        incident_id: str | None,
        alert_message: str | None,
        context_data: dict[str, Any],
        time_range: timedelta,
    ) -> str:
        """Build the user prompt with incident context and monitoring data."""

        time_desc = f"{time_range.total_seconds() / 60:.0f} phút" if time_range.total_seconds() < 3600 else f"{time_range.total_seconds() / 3600:.1f} giờ"

        prompt_parts = [
            "# Phân tích sự cố (Incident Analysis)",
            "",
            f"**Project:** {project}",
            f"**Thời gian phân tích:** {time_desc} gần nhất",
        ]

        if incident_id:
            prompt_parts.append(f"**Incident ID:** {incident_id}")

        if alert_message:
            prompt_parts.extend([
                "",
                "## Alert / Mô tả sự cố",
                f"{alert_message}",
            ])

        # Add monitoring data sections
        prompt_parts.extend([
            "",
            "## Dữ liệu giám sát (Monitoring Data)",
            "",
        ])

        # Elasticsearch / Logs
        if context_data.get("logs"):
            sampled_logs, sampling_note = sample_logs_by_severity(context_data["logs"])
            if sampling_note:
                prompt_parts.extend([
                    f"*Note: {sampling_note}; the rest were truncated by severity quota.*",
                    "",
                ])
            prompt_parts.extend([
                "### Logs (Elasticsearch)",
                "```json",
                # Compact JSON — indent=2 roughly tripled payload size for no
                # model-quality gain (token-optimization follow-up).
                json.dumps(sampled_logs, ensure_ascii=False),
                "```",
                "",
            ])

        # APM Data
        if context_data.get("apm"):
            prompt_parts.extend([
                "### APM (Application Performance Monitoring)",
                "```json",
                json.dumps(context_data["apm"], ensure_ascii=False),
                "```",
                "",
            ])

        # Prometheus Metrics
        if context_data.get("metrics"):
            prompt_parts.extend([
                "### Metrics (Prometheus)",
                "```json",
                json.dumps(context_data["metrics"], ensure_ascii=False),
                "```",
                "",
            ])

        # Kubernetes State
        if context_data.get("kubernetes"):
            prompt_parts.extend([
                "### Kubernetes State",
                "```json",
                json.dumps(context_data["kubernetes"], ensure_ascii=False),
                "```",
                "",
            ])

        # Existing Alerts
        if context_data.get("alerts"):
            prompt_parts.extend([
                "### Active Alerts",
                "```json",
                json.dumps(context_data["alerts"], ensure_ascii=False),
                "```",
                "",
            ])

        prompt_parts.extend([
            "",
            "---",
            "",
            "Dựa trên dữ liệu above, hãy tạo Triage Card (JSON format như specified).",
            "Focus trên việc tìm root cause và recommend actionable steps.",
        ])

        return "\n".join(prompt_parts)

    async def generate_triage_card(
        self,
        request: TriageCardRequest,
        context_data: dict[str, Any],
    ) -> TriageCard:
        """
        Generate a Triage Card using Claude API.

        Args:
            request: The triage card request with project, alert details
            context_data: Monitoring data from various sources (logs, metrics, etc.)

        Returns:
            TriageCard with AI-generated analysis

        Raises:
            anthropic.APIError: If the API call fails
            ValueError: If response parsing fails
        """
        time_range = timedelta(minutes=request.time_range_minutes)

        # Build the prompt
        user_prompt = self._build_user_prompt(
            project=request.project,
            incident_id=request.incident_id,
            alert_message=request.alert_message,
            context_data=context_data,
            time_range=time_range,
        )

        # Call Claude API
        try:
            record_request(path="triage", model=self.model)
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=settings.AI_MAX_TOKENS,
                system=self._cached_system(self.SYSTEM_PROMPT),
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent, factual outputs
            )

            usage = getattr(message, "usage", None)
            record_usage(path="triage", model=self.model, usage=usage)

            # Extract the response
            response_text = self._extract_json_from_message(message)

            total_tokens = (
                _usage_tokens(usage, "input_tokens") + _usage_tokens(usage, "output_tokens")
            )

            # Parse into TriageCard
            return self._parse_triage_card(
                response_text=response_text,
                project=request.project,
                incident_id=request.incident_id,
                time_range=time_range,
                request=request,
                model_used=self.model,
                tokens_used=total_tokens or None,
            )

        except anthropic.APIError as e:
            raise ValueError(f"Claude API error: {e}") from e
        except Exception as e:
            raise ValueError(f"Triage card generation failed: {e}") from e

    def _extract_json_from_message(self, message: Message) -> str:
        """Extract JSON content from Claude response."""
        # Get the text content from the response
        content_blocks = message.content
        text_content = ""

        for block in content_blocks:
            if block.type == "text":
                text_content += block.text

        # Try to extract JSON from markdown code blocks
        if "```json" in text_content:
            # Extract from ```json...```
            start = text_content.find("```json") + 7
            end = text_content.find("```", start)
            if end > start:
                return text_content[start:end].strip()
        elif "```" in text_content:
            # Extract from ```...```
            start = text_content.find("```") + 3
            end = text_content.find("```", start)
            if end > start:
                return text_content[start:end].strip()

        # Fallback: try parsing the entire response as JSON
        return text_content.strip()

    def _parse_triage_card(
        self,
        response_text: str,
        project: str,
        incident_id: str | None,
        time_range: timedelta,
        request: TriageCardRequest,
        model_used: str,
        tokens_used: int | None,
    ) -> TriageCard:
        """Parse JSON response into TriageCard model."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text[:500]}...") from e

        # Build findings
        findings = []
        for f_data in data.get("findings", []):
            try:
                findings.append(
                    Finding(
                        type=FindingType(f_data.get("type", "symptom")),
                        title=f_data.get("title", "Unknown"),
                        description=f_data.get("description", ""),
                        severity=SeverityLevel(f_data.get("severity", "info")),
                        source=f_data.get("source", "unknown"),
                        evidence=f_data.get("evidence"),
                        confidence=f_data.get("confidence", 0.5),
                    )
                )
            except ValueError:
                # Skip invalid finding but continue
                continue

        # Build recommendations (if requested)
        recommendations = []
        if request.include_recommendations:
            for r_data in data.get("recommendations", []):
                try:
                    recommendations.append(
                        Recommendation(
                            priority=r_data.get("priority", 5),
                            action=r_data.get("action", ""),
                            command=r_data.get("command"),
                            reason=r_data.get("reason", ""),
                            risk=SeverityLevel(r_data.get("risk", "medium")),
                            estimated_impact=r_data.get("estimated_impact"),
                        )
                    )
                except ValueError:
                    # Skip invalid recommendation
                    continue

        # Build triage card
        now = datetime.now(timezone.utc)
        return TriageCard(
            generated_at=now,
            project=project,
            incident_id=incident_id,
            summary=data.get("summary", "No summary provided"),
            severity=SeverityLevel(data.get("severity", "medium")),
            status=data.get("status", "investigating"),
            time_window_start=now - time_range,
            time_window_end=now,
            findings=findings,
            recommendations=recommendations,
            related_alerts=data.get("related_alerts", []),
            affected_services=data.get("affected_services", [project]),
            model_used=model_used,
            tokens_used=tokens_used,
        )

    async def analyze_with_streaming(
        self,
        project: str,
        incident_id: str | None,
        alert_message: str | None,
        context_data: dict[str, Any],
        time_range_minutes: int = 60,
    ) -> AsyncIterator[str]:
        """
        Analyze context and stream response token by token.

        This is a streaming version of generate_triage_card that yields
        JSON-formatted chunks compatible with the frontend.

        Args:
            project: Project name
            incident_id: Optional incident identifier
            alert_message: Alert description
            context_data: Monitoring data from various sources
            time_range_minutes: Time range for analysis (minutes)

        Yields:
            JSON-formatted chunks:
            - {"type": "token", "text": "...", "done": false}
            - {"type": "complete", "done": true, "full_response": "..."}
        """
        time_range = timedelta(minutes=time_range_minutes)

        # Build the prompt
        user_prompt = self._build_user_prompt(
            project=project,
            incident_id=incident_id,
            alert_message=alert_message,
            context_data=context_data,
            time_range=time_range,
        )

        full_response = ""
        input_tokens = 0
        output_tokens = 0

        try:
            record_request(path="stream", model=self.model)
            # Create streaming message
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=settings.AI_MAX_TOKENS,
                system=self._cached_system(self.SYSTEM_PROMPT),
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
                temperature=0.3,
            ) as stream:

                async for chunk in stream:
                    if chunk.type == "message_start":
                        # Input token count rides on message_start.usage
                        start_usage = getattr(
                            getattr(chunk, "message", None), "usage", None
                        )
                        input_tokens = _usage_tokens(start_usage, "input_tokens")

                    elif chunk.type == "content_block_delta":
                        if hasattr(chunk.delta, "text") and chunk.delta.text:
                            text = chunk.delta.text
                            full_response += text

                            # Yield formatted chunk
                            yield json.dumps({
                                "type": "token",
                                "text": text,
                                "done": False,
                            }) + "\n"

                    elif chunk.type == "message_delta":
                        # Final cumulative output count rides on message_delta.usage
                        delta_usage = getattr(chunk, "usage", None)
                        output_tokens = _usage_tokens(delta_usage, "output_tokens")
                        # Message complete, send final summary
                        if hasattr(chunk.delta, "stop_reason"):
                            yield json.dumps({
                                "type": "complete",
                                "text": "",
                                "done": True,
                                "stop_reason": chunk.delta.stop_reason,
                                "full_response": full_response,
                            }) + "\n"

            record_usage(
                path="stream",
                model=self.model,
                usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            )

        except anthropic.APIError as e:
            # Send error chunk
            yield json.dumps({
                "type": "error",
                "done": True,
                "error": f"Claude API error: {e}",
            }) + "\n"
        except Exception as e:
            yield json.dumps({
                "type": "error",
                "done": True,
                "error": f"Streaming failed: {e}",
            }) + "\n"

    async def analyze_simple_streaming(
        self,
        context: dict[str, Any],
        question: str,
    ) -> AsyncIterator[str]:
        """
        Simple streaming analysis for basic questions.

        This is a lighter version for quick queries without full triage card generation.

        Args:
            context: Context data (logs, metrics, etc.)
            question: User question to answer

        Yields:
            JSON-formatted chunks
        """
        # Build simple prompt
        prompt_parts = [
            "# Question",
            f"{question}",
            "",
            "# Context",
            "```json",
            json.dumps(context, ensure_ascii=False),
            "```",
            "",
            "Answer the question based on the context above. Be concise and actionable.",
        ]

        user_prompt = "\n".join(prompt_parts)
        full_response = ""
        input_tokens = 0
        output_tokens = 0

        try:
            record_request(path="simple_stream", model=FAST_MODEL)
            # Short questions don't need the full triage model — route them
            # to the cheap fast tier (haiku) instead of the configured default.
            async with self.client.messages.stream(
                model=FAST_MODEL,
                max_tokens=min(settings.AI_MAX_TOKENS, 2000),  # Lower limit for simple queries
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.3,
            ) as stream:

                async for chunk in stream:
                    if chunk.type == "message_start":
                        start_usage = getattr(
                            getattr(chunk, "message", None), "usage", None
                        )
                        input_tokens = _usage_tokens(start_usage, "input_tokens")

                    elif chunk.type == "content_block_delta":
                        if hasattr(chunk.delta, "text") and chunk.delta.text:
                            text = chunk.delta.text
                            full_response += text

                            yield json.dumps({
                                "type": "token",
                                "text": text,
                                "done": False,
                            }) + "\n"

                    elif chunk.type == "message_delta":
                        delta_usage = getattr(chunk, "usage", None)
                        output_tokens = _usage_tokens(delta_usage, "output_tokens")
                        if hasattr(chunk.delta, "stop_reason"):
                            yield json.dumps({
                                "type": "complete",
                                "text": "",
                                "done": True,
                                "stop_reason": chunk.delta.stop_reason,
                                "full_response": full_response,
                            }) + "\n"

            record_usage(
                path="simple_stream",
                model=FAST_MODEL,
                usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
            )

        except Exception as e:
            yield json.dumps({
                "type": "error",
                "done": True,
                "error": str(e),
            }) + "\n"

    async def health_check(self) -> bool:
        """
        Check if the Claude API is accessible.

        Uses caching with 5-minute TTL to avoid excessive API calls.
        """
        now = time.time()
        cache_ttl = 300  # 5 minutes

        # Return cached result if still valid
        if self._health_cache is not None and (now - self._health_cache_time) < cache_ttl:
            return self._health_cache

        try:
            # Simple API call with minimal tokens. Runs on the cheap fast
            # tier — a liveness probe doesn't need the triage model.
            record_request(path="health", model=FAST_MODEL)
            message = await self.client.messages.create(
                model=FAST_MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": "OK"}],
            )
            record_usage(path="health", model=FAST_MODEL, usage=getattr(message, "usage", None))
            self._health_cache = True
        except Exception:
            self._health_cache = False

        self._health_cache_time = now
        return self._health_cache


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create the singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        _llm_client = LLMClient()
    return _llm_client

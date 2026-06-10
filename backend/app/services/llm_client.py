"""
LLM Client Service - Claude API integration for Triage Card generation.

This module handles communication with Anthropic's Claude API to generate
AI-powered incident analysis and recommendations.

Based on strategic roadmap: docs/chien_luoc_tong_the.md (Giai đoạn 1)
"""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import anthropic
from anthropic.types import Message

from app.config import settings
from app.models.triage_card import (
    Finding,
    FindingType,
    Recommendation,
    SeverityLevel,
    TriageCard,
    TriageCardRequest,
)


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

    def __init__(self):
        """Initialize the Claude API client."""
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL
        self._health_cache: Optional[bool] = None
        self._health_cache_time: float = 0

    def _build_user_prompt(
        self,
        project: str,
        incident_id: Optional[str],
        alert_message: Optional[str],
        context_data: dict[str, Any],
        time_range: timedelta,
    ) -> str:
        """Build the user prompt with incident context and monitoring data."""

        time_desc = f"{time_range.total_seconds() / 60:.0f} phút" if time_range.total_seconds() < 3600 else f"{time_range.total_seconds() / 3600:.1f} giờ"

        prompt_parts = [
            f"# Phân tích sự cố (Incident Analysis)",
            f"",
            f"**Project:** {project}",
            f"**Thời gian phân tích:** {time_desc} gần nhất",
        ]

        if incident_id:
            prompt_parts.append(f"**Incident ID:** {incident_id}")

        if alert_message:
            prompt_parts.extend([
                f"",
                f"## Alert / Mô tả sự cố",
                f"{alert_message}",
            ])

        # Add monitoring data sections
        prompt_parts.extend([
            f"",
            f"## Dữ liệu giám sát (Monitoring Data)",
            f"",
        ])

        # Elasticsearch / Logs
        if "logs" in context_data and context_data["logs"]:
            prompt_parts.extend([
                f"### Logs (Elasticsearch)",
                f"```json",
                json.dumps(context_data["logs"][:50], ensure_ascii=False, indent=2),
                f"```",
                f"",
            ])

        # APM Data
        if "apm" in context_data and context_data["apm"]:
            prompt_parts.extend([
                f"### APM (Application Performance Monitoring)",
                f"```json",
                json.dumps(context_data["apm"], ensure_ascii=False, indent=2),
                f"```",
                f"",
            ])

        # Prometheus Metrics
        if "metrics" in context_data and context_data["metrics"]:
            prompt_parts.extend([
                f"### Metrics (Prometheus)",
                f"```json",
                json.dumps(context_data["metrics"], ensure_ascii=False, indent=2),
                f"```",
                f"",
            ])

        # Kubernetes State
        if "kubernetes" in context_data and context_data["kubernetes"]:
            prompt_parts.extend([
                f"### Kubernetes State",
                f"```json",
                json.dumps(context_data["kubernetes"], ensure_ascii=False, indent=2),
                f"```",
                f"",
            ])

        # Existing Alerts
        if "alerts" in context_data and context_data["alerts"]:
            prompt_parts.extend([
                f"### Active Alerts",
                f"```json",
                json.dumps(context_data["alerts"], ensure_ascii=False, indent=2),
                f"```",
                f"",
            ])

        prompt_parts.extend([
            f"",
            f"---",
            f"",
            f"Dựa trên dữ liệu above, hãy tạo Triage Card (JSON format như specified).",
            f"Focus trên việc tìm root cause và recommend actionable steps.",
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
            message = self.client.messages.create(
                model=self.model,
                max_tokens=settings.AI_MAX_TOKENS,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent, factual outputs
            )

            # Extract the response
            response_text = self._extract_json_from_message(message)

            # Parse into TriageCard
            return self._parse_triage_card(
                response_text=response_text,
                project=request.project,
                incident_id=request.incident_id,
                time_range=time_range,
                request=request,
                model_used=self.model,
                tokens_used=message.usage.output_tokens if hasattr(message, "usage") else None,
            )

        except anthropic.APIError as e:
            raise ValueError(f"Claude API error: {e}")
        except Exception as e:
            raise ValueError(f"Triage card generation failed: {e}")

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
        incident_id: Optional[str],
        time_range: timedelta,
        request: TriageCardRequest,
        model_used: str,
        tokens_used: Optional[int],
    ) -> TriageCard:
        """Parse JSON response into TriageCard model."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text[:500]}...")

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
            except ValueError as e:
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
        now = datetime.utcnow()
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
            # Simple API call with minimal tokens
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "OK"}],
            )
            self._health_cache = True
        except Exception:
            self._health_cache = False

        self._health_cache_time = now
        return self._health_cache


# Singleton instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        _llm_client = LLMClient()
    return _llm_client

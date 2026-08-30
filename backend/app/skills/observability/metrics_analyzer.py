"""Observability Metrics Analyzer Skill — real Prometheus data (Phase 13).

Was a stub: latency percentiles were hardcoded and the client was constructed
locally (so it never saw the live one). Now every number comes from the
Prometheus client injected via context["clients"]["prometheus"]; missing
metrics are reported as "insufficient data", never fabricated.
"""

from __future__ import annotations

import logging
from typing import Any

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)

# Percentile queries over the request-duration histogram (seconds -> ms).
_LATENCY_EXPR = (
    'histogram_quantile({q}, sum by (le) (rate(http_request_duration_seconds_bucket[{h}h])))'
)
_ERROR_RATE_EXPR = (
    '100 * sum(rate(http_requests_total{{status=~"5.."}}[{h}h])) '
    "/ sum(rate(http_requests_total[{h}h]))"
)


def _scalar(rows: list[dict[str, Any]]) -> float | None:
    """First sample value of an instant-query result, or None when empty."""
    for row in rows or []:
        value = row.get("value")
        if value and len(value) == 2:
            try:
                return float(value[1])
            except (TypeError, ValueError):
                continue
    return None


class MetricsAnalyzerSkill(BaseSkill):
    """Analyze live Prometheus metrics: error rate, latency, utilization."""

    skill_id = "observability_metrics_analyzer"
    name = "Observability Metrics Analyzer"
    description = (
        "Analyze live Prometheus metrics: request/error rates, latency "
        "percentiles (p50/p95/p99) and node resource utilization."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "2.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        try:
            hours = max(int(parameters.get("time_range_hours", 1)), 1)
            prom = ((context or {}).get("clients") or {}).get("prometheus")
            if prom is None:
                raise RuntimeError(
                    "No Prometheus client in context['clients']['prometheus'] — "
                    "skill requires a live metrics source"
                )

            latency: dict[str, float | None] = {}
            for label, quantile in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99)):
                seconds = _scalar(
                    await prom.query(_LATENCY_EXPR.format(q=quantile, h=hours))
                )
                latency[label] = round(seconds * 1000, 1) if seconds is not None else None

            error_rate = _scalar(await prom.query(_ERROR_RATE_EXPR.format(h=hours)))
            cpu = await prom.get_cpu_percent()
            memory = await prom.get_memory_percent()

            available = [
                k for k, v in (("error_rate", error_rate), *latency.items()) if v is not None
            ]
            missing = [
                k for k, v in (("error_rate", error_rate), *latency.items()) if v is None
            ]

            warnings = []
            if error_rate is not None and error_rate > 1.0:
                warnings.append(f"Elevated error rate: {error_rate:.2f}%")
            if latency.get("p95") is not None and latency["p95"] > 500:
                warnings.append(f"High P95 latency: {latency['p95']}ms")
            if cpu > 80:
                warnings.append(f"High CPU usage: {cpu:.1f}%")
            if memory > 85:
                warnings.append(f"High memory usage: {memory:.1f}%")

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9 if available else 0.5,
                data={
                    "project": project,
                    "window_hours": hours,
                    "error_rate_percent": round(error_rate, 3) if error_rate is not None else None,
                    "latency_ms": latency,
                    "resource_utilization": {
                        "cpu_percent": round(cpu, 1),
                        "memory_percent": round(memory, 1),
                    },
                    "metrics_available": available,
                    "metrics_missing": missing,
                    "message": (
                        "No HTTP service metrics found for the requested window"
                        if not available
                        else None
                    ),
                },
                warnings=warnings,
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Metrics analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        data = result.data
        recommendations = []

        if data.get("error_rate_percent") is not None and data["error_rate_percent"] > 1.0:
            recommendations.append(Recommendation(
                title="High error rate",
                description=(
                    f"Error rate is {data['error_rate_percent']}% over the last "
                    f"{data['window_hours']}h — above the 1% investigation threshold."
                ),
                priority=SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))

        p95 = (data.get("latency_ms") or {}).get("p95")
        if p95 is not None and p95 > 500:
            recommendations.append(Recommendation(
                title="High P95 latency",
                description=f"P95 latency is {p95}ms (threshold 500ms).",
                priority=SkillPriority.MEDIUM,
                action_type="optimize",
                risk_level="medium",
            ))

        resources = data.get("resource_utilization") or {}
        if resources.get("cpu_percent", 0) > 80:
            recommendations.append(Recommendation(
                title="High CPU utilization",
                description=f"Cluster CPU at {resources['cpu_percent']}%.",
                priority=SkillPriority.MEDIUM,
                action_type="scale",
                risk_level="medium",
            ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        hours = parameters.get("time_range_hours", 1)
        if not isinstance(hours, (int, float)) or hours <= 0:
            return False, ["time_range_hours must be a positive number"]
        return True, []

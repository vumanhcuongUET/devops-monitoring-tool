"""Observability Tracing Analyzer Skill — real APM data (Phase 13).

Was a stub returning a fabricated trace with invented spans. Now it builds
an ApmClient on top of the injected Elasticsearch client and aggregates the
real apm-*-transaction* / apm-*-error* indices: latency percentiles, error
rate, slowest transaction names and top error groups.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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


class TracingAnalyzerSkill(BaseSkill):
    """Analyze distributed tracing health from real APM aggregations."""

    skill_id = "observability_tracing_analyzer"
    name = "Observability Tracing Analyzer"
    description = (
        "Analyze distributed traces from real APM data: latency percentiles, "
        "error rate, slowest transactions and top error groups."
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
            service = parameters.get("service_name") or project
            hours = max(int(parameters.get("time_range_hours", 1)), 1)
            min_duration_ms = float(parameters.get("min_duration_ms", 100))

            es = ((context or {}).get("clients") or {}).get("es")
            if es is None:
                raise RuntimeError(
                    "No Elasticsearch client in context['clients']['es'] — "
                    "skill requires a live APM data source"
                )

            from app.services.apm_client import ApmClient

            apm = ApmClient(es)
            end = datetime.now(timezone.utc)
            start = (end - timedelta(hours=hours)).isoformat()
            end_iso = end.isoformat()

            summary = await apm.get_summary(start=start, end=end_iso)
            transactions = await apm.get_transactions(
                service=service or None, start=start, end=end_iso
            )
            errors = await apm.get_errors(
                service=service or None, start=start, end=end_iso
            )

            if not summary.get("throughput"):
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=[
                        f"No APM transactions found for service {service!r} over the "
                        f"last {hours}h — cannot analyze traces"
                    ],
                )

            slowest = sorted(
                (t for t in transactions if t["latency_p95"] >= min_duration_ms),
                key=lambda t: t["latency_p95"],
                reverse=True,
            )[:10]
            top_errors = sorted(errors, key=lambda e: e["count"], reverse=True)[:10]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "service": service,
                    "window_hours": hours,
                    "summary": summary,
                    "slowest_transactions": [
                        {
                            "name": t["name"],
                            "latency_p50_ms": t["latency_p50"],
                            "latency_p95_ms": t["latency_p95"],
                            "latency_p99_ms": t["latency_p99"],
                            "throughput": t["throughput"],
                        }
                        for t in slowest
                    ],
                    "top_error_groups": top_errors,
                },
                warnings=[
                    w
                    for w in (
                        f"High error rate: {summary['error_rate_percent']}%"
                        if summary.get("error_rate_percent", 0) > 1.0
                        else None,
                        f"High P99 latency: {summary['latency_p99']}ms"
                        if summary.get("latency_p99", 0) > 1000
                        else None,
                    )
                    if w
                ],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Trace analysis failed: {e!s}"],
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

        slowest = data.get("slowest_transactions", [])
        if slowest:
            worst = slowest[0]
            recommendations.append(Recommendation(
                title=f"Slowest transaction: {worst['name']}",
                description=(
                    f"P95 {worst['latency_p95_ms']}ms over the last "
                    f"{data['window_hours']}h — profile this path first."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="optimize",
                risk_level="medium",
            ))

        errors = data.get("top_error_groups", [])
        if errors:
            top = errors[0]
            recommendations.append(Recommendation(
                title=f"Top error group: {top.get('type', 'Unknown')}",
                description=(
                    f"{top.get('count', 0)} occurrences: {top.get('message', '')[:200]}"
                ),
                priority=SkillPriority.HIGH,
                action_type="fix",
                risk_level="high",
            ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        hours = parameters.get("time_range_hours", 1)
        if not isinstance(hours, (int, float)) or hours <= 0:
            return False, ["time_range_hours must be a positive number"]
        return True, []

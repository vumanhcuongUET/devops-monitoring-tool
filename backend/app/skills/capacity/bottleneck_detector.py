"""Capacity Bottleneck Detector Skill — real Prometheus series (Phase 13).

Was a stub generating synthetic utilization data. Now reuses the shared
node-exporter history fetcher (planner/growth-predictor) and flags real
saturation: current pressure, peak pressure and trend-projected exhaustion.
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
from app.skills.capacity.prom_history import fetch_metric_series

logger = logging.getLogger(__name__)

# Saturation thresholds (% of the resource).
WARNING_PERCENT = 80.0
CRITICAL_PERCENT = 90.0
FORECAST_DAYS = 7


def _linear_slope(values: list[float]) -> float:
    """Least-squares slope per sample; 0.0 for flat/short series."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    denom = sum((i - mean_x) ** 2 for i in range(n))
    if denom == 0:
        return 0.0
    return sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values)) / denom


class BottleneckDetectorSkill(BaseSkill):
    """Detect resource bottlenecks from real node utilization history."""

    skill_id = "capacity_bottleneck_detector"
    name = "Capacity Bottleneck Detector"
    description = (
        "Detect CPU/memory/disk bottlenecks from real Prometheus utilization "
        "history: current pressure, peaks and trend-projected exhaustion."
    )
    category = SkillCategory.CAPACITY
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
            days = max(int(parameters.get("days", 7)), 1)
            prom = ((context or {}).get("clients") or {}).get("prometheus")
            if prom is None:
                raise RuntimeError(
                    "No Prometheus client in context['clients']['prometheus'] — "
                    "skill requires a live metrics source"
                )

            series = await fetch_metric_series(prom, ["cpu", "memory", "disk"], days=days)
            bottlenecks = []
            resources: dict[str, dict[str, Any]] = {}

            for resource, values in series.items():
                if not values:
                    resources[resource] = {"status": "insufficient_data"}
                    continue

                current = sum(values[-3:]) / len(values[-3:])
                peak = max(values)
                slope = _linear_slope(values)
                # Project forward with the per-sample slope; hourly step means
                # samples/day ≈ len(values)/days.
                samples_per_day = max(len(values) / days, 1)
                projected = current + slope * samples_per_day * FORECAST_DAYS

                severity = None
                if current >= CRITICAL_PERCENT or peak >= CRITICAL_PERCENT:
                    severity = "critical"
                elif current >= WARNING_PERCENT or peak >= WARNING_PERCENT:
                    severity = "warning"
                elif projected >= CRITICAL_PERCENT:
                    severity = "projected"

                entry = {
                    "status": "ok" if severity is None else "bottleneck",
                    "current_percent": round(current, 1),
                    "peak_percent": round(peak, 1),
                    "trend_percent_per_day": round(slope * samples_per_day, 2),
                    "projected_percent_7d": round(min(projected, 100.0), 1),
                }
                resources[resource] = entry
                if severity:
                    bottlenecks.append({"resource": resource, "severity": severity, **entry})

            usable = [r for r in resources.values() if r.get("status") != "insufficient_data"]
            if not usable:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=[
                        "No node-exporter utilization series returned by Prometheus "
                        f"over the last {days}d — cannot detect bottlenecks"
                    ],
                )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "days_analyzed": days,
                    "resources": resources,
                    "bottlenecks": bottlenecks,
                    "summary": {
                        "resources_analyzed": len(usable),
                        "bottleneck_count": len(bottlenecks),
                        "critical": sum(1 for b in bottlenecks if b["severity"] == "critical"),
                    },
                },
                warnings=[
                    f"{b['resource']} at {b['current_percent']}% ({b['severity']})"
                    for b in bottlenecks
                    if b["severity"] != "projected"
                ],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Bottleneck detection failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        for b in result.data.get("bottlenecks", []):
            recommendations.append(Recommendation(
                title=f"{b['resource']} bottleneck ({b['severity']})",
                description=(
                    f"{b['resource']} at {b['current_percent']}% now, peak "
                    f"{b['peak_percent']}%, projected {b['projected_percent_7d']}% "
                    f"in {FORECAST_DAYS}d."
                ),
                priority=SkillPriority.HIGH if b["severity"] == "critical" else SkillPriority.MEDIUM,
                action_type="scale",
                risk_level="high" if b["severity"] == "critical" else "medium",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        days = parameters.get("days", 7)
        if not isinstance(days, int) or days <= 0:
            return False, ["days must be a positive integer"]
        return True, []

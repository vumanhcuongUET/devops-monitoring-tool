"""SLI Calculator Skill — real Prometheus SLIs (Phase 13).

Was a stub computing indicators from synthetic metric data. Now every SLI is
a live PromQL computation over the injected Prometheus client: availability
from `up`, error rate from 5xx ratios, fast-latency share from the request
duration histogram, and raw throughput.
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

_EXPRS = {
    "error_rate_percent": (
        '100 * sum(rate(http_requests_total{{status=~"5.."}}[{h}h])) '
        "/ sum(rate(http_requests_total[{h}h]))"
    ),
    "latency_sli_percent": (
        '100 * sum(rate(http_request_duration_seconds_bucket{{le="0.5"}}[{h}h])) '
        "/ sum(rate(http_request_duration_seconds_count[{h}h]))"
    ),
    "throughput_rps": "sum(rate(http_requests_total[{h}h]))",
}


def _scalar(rows: list[dict[str, Any]]) -> float | None:
    for row in rows or []:
        value = row.get("value")
        if value and len(value) == 2:
            try:
                return float(value[1])
            except (TypeError, ValueError):
                continue
    return None


class SLICalculatorSkill(BaseSkill):
    """Calculate service level indicators from live Prometheus data."""

    skill_id = "monitoring_sli_calculator"
    name = "SLI Calculator"
    description = (
        "Calculate availability, error-rate, fast-latency share and throughput "
        "SLIs from live Prometheus metrics."
    )
    category = SkillCategory.MONITORING
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
            hours = max(int(parameters.get("time_window_hours", 24)), 1)
            prom = ((context or {}).get("clients") or {}).get("prometheus")
            if prom is None:
                raise RuntimeError(
                    "No Prometheus client in context['clients']['prometheus'] — "
                    "skill requires a live metrics source"
                )

            slis: dict[str, Any] = {}

            # Availability per monitored job from the up probe.
            up_rows = await prom.query(f"avg_over_time(up[{hours}h]) * 100")
            availability: dict[str, float] = {}
            for row in up_rows or []:
                labels = row.get("metric", {})
                job = labels.get("job") or labels.get("instance") or "unknown"
                value = row.get("value")
                if value and len(value) == 2:
                    try:
                        availability[job] = round(float(value[1]), 3)
                    except (TypeError, ValueError):
                        continue
            if availability:
                slis["availability_percent_by_job"] = availability
                slis["availability_percent"] = round(
                    sum(availability.values()) / len(availability), 3
                )

            for name, expr in _EXPRS.items():
                value = _scalar(await prom.query(expr.format(h=hours)))
                if value is not None:
                    slis[name] = round(value, 3)

            if not slis:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=[
                        f"No SLI source metrics (up / http_requests_total / "
                        f"http_request_duration_seconds) found over the last {hours}h"
                    ],
                )

            objectives = {
                "availability_percent": 99.9,
                "error_rate_percent": 0.1,
                "latency_sli_percent": 99.0,
            }
            slis["objectives"] = objectives
            slis["breaches"] = [
                {"sli": name, "value": slis[name], "objective": objective}
                for name, objective in objectives.items()
                if name in slis
                and (
                    slis[name] < objective
                    if name != "error_rate_percent"
                    else slis[name] > objective
                )
            ]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "project": project,
                    "window_hours": hours,
                    "slis": slis,
                },
                warnings=[f"SLI breach: {b['sli']}={b['value']}" for b in slis["breaches"]],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"SLI calculation failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        for breach in result.data.get("slis", {}).get("breaches", []):
            recommendations.append(Recommendation(
                title=f"SLI breach: {breach['sli']}",
                description=(
                    f"{breach['sli']} is {breach['value']} against objective "
                    f"{breach['objective']} over the analysis window."
                ),
                priority=SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        hours = parameters.get("time_window_hours", 24)
        if not isinstance(hours, (int, float)) or hours <= 0:
            return False, ["time_window_hours must be a positive number"]
        return True, []

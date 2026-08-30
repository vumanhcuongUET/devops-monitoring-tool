"""Reliability DLQ Monitor Skill — real Elasticsearch logs (Phase 13).

Was a stub inventing DLQ entries. This platform's dead-letter signal lives
in its logs, so the skill searches real ERROR logs for dead-letter/dlq
markers through the injected Elasticsearch client and aggregates what is
actually there: counts per service, hourly trend and the raw recent
messages. No matching logs means zero DLQ signals — reported as such.
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

# Log markers that indicate a dead-letter event. The query is bounded to the
# message field by the ES client itself.
_DLQ_QUERY = "message:(dead OR letter) OR dlq"


class DLQMonitorSkill(BaseSkill):
    """Monitor dead-letter signals from real error logs."""

    skill_id = "reliability_dlq_monitor"
    name = "Reliability DLQ Monitor"
    description = (
        "Monitor dead-letter queue signals from real ERROR logs: counts per "
        "service, hourly trend and recent messages."
    )
    category = SkillCategory.RELIABILITY
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
            hours = max(int(parameters.get("time_range_hours", 24)), 1)
            service = parameters.get("service") or None

            es = ((context or {}).get("clients") or {}).get("es")
            if es is None:
                raise RuntimeError(
                    "No Elasticsearch client in context['clients']['es'] — "
                    "skill requires a live log source"
                )

            end = datetime.now(timezone.utc)
            start = (end - timedelta(hours=hours)).isoformat()
            end_iso = end.isoformat()

            hits, total = await es.search_logs(
                query=_DLQ_QUERY,
                level="ERROR",
                service=service,
                start=start,
                end=end_iso,
                size=200,
            )

            by_service: dict[str, int] = {}
            by_hour: dict[str, int] = {}
            messages: list[dict[str, Any]] = []
            for hit in hits:
                svc = hit.get("service") or "unknown"
                by_service[svc] = by_service.get(svc, 0) + 1
                ts = (hit.get("@timestamp") or "")[:13]  # YYYY-MM-DDTHH
                if ts:
                    by_hour[ts] = by_hour.get(ts, 0) + 1
                if len(messages) < 20:
                    messages.append({
                        "timestamp": hit.get("@timestamp"),
                        "service": svc,
                        "message": str(hit.get("message") or hit.get("log") or "")[:300],
                    })

            trend = "stable"
            if len(by_hour) >= 2:
                hours_sorted = sorted(by_hour)
                recent = sum(by_hour[h] for h in hours_sorted[len(hours_sorted) // 2:])
                older = sum(by_hour[h] for h in hours_sorted[: len(hours_sorted) // 2])
                if recent > older * 1.5:
                    trend = "increasing"
                elif older > recent * 1.5:
                    trend = "decreasing"

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.85,
                data={
                    "window_hours": hours,
                    "total_dlq_signals": total,
                    "by_service": dict(
                        sorted(by_service.items(), key=lambda kv: kv[1], reverse=True)
                    ),
                    "by_hour": dict(sorted(by_hour.items())),
                    "trend": trend,
                    "recent_messages": messages,
                    "message": (
                        "No dead-letter signals found in ERROR logs"
                        if total == 0
                        else None
                    ),
                },
                warnings=[
                    f"{total} dead-letter signals in the last {hours}h",
                    f"DLQ signals increasing ({trend})",
                ]
                if total and trend == "increasing"
                else ([f"{total} dead-letter signals in the last {hours}h"] if total else []),
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"DLQ monitoring failed: {e!s}"],
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
        if data.get("total_dlq_signals"):
            worst = max(data.get("by_service", {}).items(), key=lambda kv: kv[1], default=None)
            recommendations.append(Recommendation(
                title=f"{data['total_dlq_signals']} dead-letter signals",
                description=(
                    f"Found in the last {data['window_hours']}h"
                    + (f", mostly from {worst[0]} ({worst[1]})" if worst else "")
                    + f". Trend: {data['trend']}."
                ),
                priority=SkillPriority.CRITICAL if data["total_dlq_signals"] > 100 else SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        hours = parameters.get("time_range_hours", 24)
        if not isinstance(hours, (int, float)) or hours <= 0:
            return False, ["time_range_hours must be a positive number"]
        return True, []

"""SLA Compliance Skill — real SLO computations (Phase 13).

Was a stub returning fabricated compliance history and penalty figures.
Now it evaluates the same SLO configs as the API/Slack reporter through the
injected SloClient and reports which service contracts are currently met.
Penalties are not computed — there is no contract data to derive them from,
and invented dollars are worse than none.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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


class SLAComplianceSkill(BaseSkill):
    """Check service SLA compliance from real SLO results."""

    skill_id = "reliability_sla_compliance"
    name = "SLA Compliance Checker"
    description = (
        "Check contractual service-level compliance from real SLO results: "
        "per-service status, error budget and breach list."
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
            service = parameters.get("service") or project
            slo_client = ((context or {}).get("clients") or {}).get("slo")
            if slo_client is None:
                raise RuntimeError(
                    "No SloClient in context['clients']['slo'] — skill requires "
                    "a live SLO data source"
                )

            from app.services.slo_config_store import load_configs as _load_configs
            from app.models.slo import SloConfig

            configs = [
                SloConfig(**c)
                for c in _load_configs()
                if c.get("enabled", True)
                and (not service or c.get("service_name") == service)
            ]
            if not configs:
                return AnalysisResult(
                    success=True,
                    skill_id=self.skill_id,
                    confidence=0.9,
                    data={
                        "services": [],
                        "message": f"No SLO/SLA configs found for service {service!r}",
                    },
                )

            services = []
            for cfg in configs:
                result = await slo_client.calculate_slo(cfg)
                services.append({
                    "service": result.service_name,
                    "slo_type": result.slo_type,
                    "target_percent": result.target,
                    "current_percent": round(result.current_value, 3),
                    "compliant": result.current_value >= result.target,
                    "status": result.status,
                    "error_budget_remaining_percent": round(
                        result.error_budget_remaining_percent, 2
                    ),
                    "window_days": result.window_days,
                    "total_requests": result.total_requests,
                })

            compliant = sum(1 for s in services if s["compliant"])
            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "services": services,
                    "summary": {
                        "services_tracked": len(services),
                        "compliant": compliant,
                        "breached": len(services) - compliant,
                        "overall_compliance_percent": round(
                            100 * compliant / len(services), 1
                        ),
                        "evaluated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "breaches": [
                        s for s in services if not s["compliant"]
                    ],
                },
                warnings=[
                    f"SLA breach: {s['service']} ({s['slo_type']}) at "
                    f"{s['current_percent']}% vs target {s['target_percent']}%"
                    for s in services
                    if not s["compliant"]
                ],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"SLA compliance check failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        for breach in result.data.get("breaches", []):
            recommendations.append(Recommendation(
                title=f"SLA breach: {breach['service']}",
                description=(
                    f"{breach['slo_type']} at {breach['current_percent']}% vs "
                    f"target {breach['target_percent']}%; error budget remaining "
                    f"{breach['error_budget_remaining_percent']}%."
                ),
                priority=SkillPriority.CRITICAL
                if breach["status"] == "breached"
                else SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        return True, []

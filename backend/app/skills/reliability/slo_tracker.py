"""SLO Tracker skill — real SLO status via SloClient (Phase 13).

Was a stub returning fabricated compliance numbers. Now loads the same SLO
configs as the API and the Slack reporter (data/slo_configs.json or the
defaults YAML), computes real availability/latency SLOs through SloClient,
and derives burn rate from target vs current.
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


class SLOTrackerSkill(BaseSkill):
    """Track SLO compliance and error budget from real APM data."""

    skill_id = "reliability_slo_tracker"
    name = "SLO Tracker"
    description = "Track Service Level Objective compliance and error budget"
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
        """Analyze real SLO compliance for `project` (or all configured services).

        Args:
            project: Service name; empty string = all enabled configs
            parameters: optional {"service": "..."} override
            context: registry context; needs context["clients"]["slo"]
        """
        try:
            service = parameters.get("service") or project
            clients = (context or {}).get("clients") or {}
            slo_client = clients.get("slo")
            if slo_client is None:
                raise RuntimeError(
                    "No SloClient in context['clients']['slo'] — skill requires a live SLO data source"
                )

            configs = self._load_configs(service)
            if not configs:
                return AnalysisResult(
                    success=True,
                    skill_id=self.skill_id,
                    confidence=0.9,
                    data={
                        "services": [],
                        "message": f"No SLO configs found for service {service!r}",
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
                    "error_budget_remaining_percent": round(
                        result.error_budget_remaining_percent, 2
                    ),
                    "status": result.status,
                    "window_days": result.window_days,
                    "total_requests": result.total_requests,
                    "burn_rate": self._burn_rate(result),
                })

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "services": services,
                    "summary": {
                        "tracked": len(services),
                        "compliant": sum(1 for s in services if s["compliant"]),
                        "breached": sum(1 for s in services if s["status"] == "breached"),
                    },
                    "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            logger.error(f"SLO tracking failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"SLO tracking failed: {e!s}"],
            )

    def _load_configs(self, service: str) -> list:
        """SLO configs for one service (or all enabled when service empty)."""
        from app.api.v1.slo import _load_configs
        from app.models.slo import SloConfig

        raw = _load_configs()
        configs = [SloConfig(**c) for c in raw if c.get("enabled", True)]
        if service:
            configs = [c for c in configs if c.service_name == service]
        return configs

    def _burn_rate(self, result) -> float | None:
        """Availability burn rate: how fast the error budget is burning
        relative to plan (1.0 = on plan). None when not derivable."""
        if result.slo_type != "availability" or result.target >= 100:
            return None
        allowed = 100 - result.target
        actual = 100 - result.current_value
        if allowed <= 0:
            return None
        return round(actual / allowed, 2)

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Recommendations for non-compliant services."""
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        for svc in result.data.get("services", []):
            if svc["compliant"] and svc["status"] not in ("warning", "critical"):
                continue
            recommendations.append(Recommendation(
                title=f"SLO at risk: {svc['service']} ({svc['slo_type']})",
                description=(
                    f"Current {svc['current_percent']}% vs target {svc['target_percent']}%, "
                    f"error budget remaining {svc['error_budget_remaining_percent']}%"
                    + (f", burn rate {svc['burn_rate']}x" if svc["burn_rate"] else "")
                    + "."
                ),
                priority=SkillPriority.HIGH if svc["status"] in ("critical", "breached") else SkillPriority.MEDIUM,
                action_type="manual",
                risk_level="high" if svc["status"] in ("critical", "breached") else "medium",
            ))
        return recommendations

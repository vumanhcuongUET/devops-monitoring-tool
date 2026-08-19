"""Capacity Planner Skill - Forecast capacity needs based on trends."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillPriority,
    AnalysisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)


class CapacityPlannerSkill(BaseSkill):
    """Plan capacity needs based on usage trends and patterns.

    This skill analyzes:
    - Resource utilization trends
    - Growth patterns
    - Seasonal variations
    - Bottleneck predictions
    """

    skill_id = "capacity_planner"
    name = "Capacity Planner"
    description = "Plan capacity needs based on trends and patterns"
    category = SkillCategory.CAPACITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"
    requires_prometheus = True

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run capacity planning analysis.

        Args:
            project: Project name
            parameters: Analysis parameters
                - forecast_days: Days to forecast (default: 30)
                - threshold_percent: Capacity threshold (default: 80)
            context: Registry context

        Returns:
            AnalysisResult with capacity forecasts
        """
        try:
            forecast_days = parameters.get("forecast_days", 30)
            threshold = parameters.get("threshold_percent", 80)

            # Fetch metrics
            metrics = await self._fetch_metrics(project, context)

            # Analyze trends
            cpu_trend = self._analyze_trend(metrics.get("cpu", []))
            memory_trend = self._analyze_trend(metrics.get("memory", []))
            disk_trend = self._analyze_trend(metrics.get("disk", []))

            # Generate forecasts
            cpu_forecast = self._forecast_capacity(cpu_trend, forecast_days, threshold)
            memory_forecast = self._forecast_capacity(memory_trend, forecast_days, threshold)
            disk_forecast = self._forecast_capacity(disk_trend, forecast_days, threshold)

            # Calculate overall capacity needs
            capacity_needs = self._calculate_capacity_needs(
                cpu_forecast, memory_forecast, disk_forecast, threshold
            )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.8,
                data={
                    "forecast_days": forecast_days,
                    "threshold_percent": threshold,
                    "cpu": cpu_forecast,
                    "memory": memory_forecast,
                    "disk": disk_forecast,
                    "capacity_needs": capacity_needs,
                    "recommendations_summary": self._generate_summary(
                        cpu_forecast, memory_forecast, disk_forecast
                    ),
                },
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Capacity planning failed: {str(e)}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate capacity planning recommendations.

        Args:
            analysis_id: Analysis ID
            project: Project name

        Returns:
            List of recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        data = result.data
        needs = data.get("capacity_needs", {})

        # CPU capacity recommendations
        if needs.get("cpu", {}).get("action_required"):
            recommendations.append(Recommendation(
                title="Scale CPU capacity",
                description=needs["cpu"]["reason"],
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1 hour",
                risk_level="low",
                commands=[
                    f"# Current replicas: {needs['cpu']['current']}",
                    f"# Recommended: {needs['cpu']['recommended']}",
                    "kubectl scale deployment --replicas=<recommended>",
                ],
            ))

        # Memory capacity recommendations
        if needs.get("memory", {}).get("action_required"):
            recommendations.append(Recommendation(
                title="Increase memory capacity",
                description=needs["memory"]["reason"],
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="2 hours",
                risk_level="low",
                commands=[
                    "# Increase pod memory limits",
                    "kubectl set resources deployment <name> --limits=memory=<new-value>",
                ],
            ))

        # Disk capacity recommendations
        if needs.get("disk", {}).get("action_required"):
            recommendations.append(Recommendation(
                title="Expand disk capacity",
                description=needs["disk"]["reason"],
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="4 hours",
                risk_level="medium",
                commands=[
                    "# Expand PVC or add nodes",
                    "kubectl edit pvc <pvc-name>",
                    "# Or expand cluster storage",
                ],
            ))

        return recommendations

    async def _fetch_metrics(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Fetch metrics from Prometheus."""
        # Implementation would query Prometheus
        # For now, return mock data
        return {
            "cpu": [50, 55, 60, 65, 70, 72, 75],
            "memory": [60, 62, 65, 68, 70, 72, 74],
            "disk": [40, 42, 45, 48, 50, 52, 55],
        }

    def _analyze_trend(self, data_points: list[float]) -> dict[str, Any]:
        """Analyze trend in data points."""
        if len(data_points) < 2:
            return {"trend": "unknown", "growth_rate": 0}

        # Simple linear regression
        first_avg = sum(data_points[:3]) / min(3, len(data_points))
        last_avg = sum(data_points[-3:]) / min(3, len(data_points))

        growth_rate = ((last_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0

        if growth_rate > 10:
            trend = "increasing_rapidly"
        elif growth_rate > 5:
            trend = "increasing"
        elif growth_rate < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "growth_rate": growth_rate,
            "current_value": data_points[-1] if data_points else 0,
            "average_value": sum(data_points) / len(data_points) if data_points else 0,
        }

    def _forecast_capacity(
        self,
        trend: dict[str, Any],
        days: int,
        threshold: float,
    ) -> dict[str, Any]:
        """Forecast capacity needs."""
        current = trend.get("current_value", 0)
        growth_rate = trend.get("growth_rate", 0) / 100

        # Linear forecast
        forecasts = []
        for day in range(1, days + 1):
            forecasted = current * (1 + growth_rate * day / 30)
            forecasts.append({
                "day": day,
                "date": (datetime.now(timezone.utc) + timedelta(days=day)).strftime("%Y-%m-%d"),
                "value": max(0, forecasted),
            })

        # Find when threshold is exceeded
        threshold_day = None
        for i, f in enumerate(forecasts):
            if f["value"] >= threshold:
                threshold_day = i + 1
                break

        return {
            "forecasts": forecasts,
            "threshold_exceeded_day": threshold_day,
            "action_required": threshold_day is not None and threshold_day <= 30,
        }

    def _calculate_capacity_needs(
        self,
        cpu: dict,
        memory: dict,
        disk: dict,
        threshold: float,
    ) -> dict[str, Any]:
        """Calculate overall capacity needs."""
        needs = {}

        for resource, forecast in [("cpu", cpu), ("memory", memory), ("disk", disk)]:
            if forecast.get("action_required"):
                current_value = forecast.get("forecasts", [{}])[0].get("value", 0)
                days_until = forecast.get("threshold_exceeded_day", 30)

                # Calculate recommended capacity (20% headroom)
                recommended = current_value * 1.2

                needs[resource] = {
                    "action_required": True,
                    "current": current_value,
                    "recommended": recommended,
                    "days_until_threshold": days_until,
                    "reason": f"{resource.capitalize()} will exceed {threshold}% threshold in {days_until} days",
                }
            else:
                needs[resource] = {"action_required": False}

        return needs

    def _generate_summary(
        self,
        cpu: dict,
        memory: dict,
        disk: dict,
    ) -> dict[str, Any]:
        """Generate summary of capacity needs."""
        action_required = [
            r for r in [cpu, memory, disk] if r.get("action_required")
        ]

        return {
            "total_actions_required": len(action_required),
            "urgency": "high" if len(action_required) >= 2 else "medium" if action_required else "low",
            "resources_affected": [r for r, f in [("cpu", cpu), ("memory", memory), ("disk", disk)] if f.get("action_required")],
        }

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        errors = []

        forecast_days = parameters.get("forecast_days", 30)
        if not isinstance(forecast_days, int) or forecast_days < 1 or forecast_days > 365:
            errors.append("forecast_days must be between 1 and 365")

        threshold = parameters.get("threshold_percent", 80)
        if not isinstance(threshold, (int, float)) or threshold < 1 or threshold > 100:
            errors.append("threshold_percent must be between 1 and 100")

        return len(errors) == 0, errors

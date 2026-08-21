"""Capacity Planner Skill - Forecast capacity needs and plan infrastructure scaling.

This skill analyzes historical metrics to:
- Forecast future capacity requirements
- Plan infrastructure scaling
- Identify capacity gaps before they cause issues
- Recommend optimal scaling strategies
"""

import logging
from datetime import datetime, timedelta
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
    """Plan capacity requirements and forecast infrastructure needs.

    This skill analyzes historical usage patterns to:
    - Forecast CPU, memory, and storage requirements
    - Predict when capacity limits will be reached
    - Recommend optimal scaling strategies
    - Plan infrastructure provisioning

    Requires:
    - Prometheus metrics access
    - 30+ days of historical data recommended
    - Current cluster capacity information
    """

    skill_id = "capacity_planner"
    name = "Capacity Planner"
    description = "Forecast capacity needs and plan infrastructure scaling"
    category = SkillCategory.CAPACITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Capacity Planner skill."""
        super().__init__(config)
        self.forecast_horizon_days = 90  # Default 90-day forecast

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze capacity requirements and generate forecast.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context (e.g., project config)

        Returns:
            AnalysisResult with capacity forecast and recommendations
        """
        try:
            # Extract parameters
            horizon_days = parameters.get("forecast_horizon_days", 90)
            resource_types = parameters.get("resource_types", ["cpu", "memory", "storage"])
            growth_rate = parameters.get("growth_rate", None)  # If None, auto-calculate

            logger.info(f"Starting capacity planning for {project}, horizon: {horizon_days} days")

            # Analyze current capacity
            current_capacity = await self._get_current_capacity(project, context)

            # Analyze historical usage trends
            usage_trends = await self._analyze_usage_trends(
                project,
                resource_types,
                context
            )

            # Calculate growth rates
            calculated_growth = self._calculate_growth_rates(usage_trends)

            # Forecast future capacity needs
            forecast = self._forecast_capacity(
                current_capacity,
                usage_trends,
                calculated_growth if growth_rate is None else growth_rate,
                horizon_days,
            )

            # Identify capacity gaps
            gaps = self._identify_capacity_gaps(current_capacity, forecast)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                current_capacity,
                forecast,
                gaps,
                calculated_growth,
            )

            # Build result
            data = {
                "current_capacity": current_capacity,
                "usage_trends": usage_trends,
                "growth_rates": calculated_growth,
                "forecast": forecast,
                "capacity_gaps": gaps,
                "forecast_horizon_days": horizon_days,
                "analysis_date": datetime.now().isoformat(),
            }

            confidence = self._calculate_confidence(usage_trends, current_capacity)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Capacity planning failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _get_current_capacity(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Get current cluster capacity for the project.

        Returns:
            Dict with current capacity info
        """
        # Mock implementation - in real scenario, query cluster API
        return {
            "cpu_cores": 100,
            "cpu_allocatable": 90,
            "memory_gb": 400,
            "memory_allocatable_gb": 360,
            "storage_gb": 2000,
            "storage_allocatable_gb": 1800,
            "node_count": 20,
            "pod_capacity": 220,
            "pods_running": 120,
        }

    async def _analyze_usage_trends(
        self,
        project: str,
        resource_types: list[str],
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze historical usage trends.

        Returns:
            Dict with usage trend data
        """
        # Mock implementation - in real scenario, query Prometheus
        trends = {}

        for resource_type in resource_types:
            if resource_type == "cpu":
                trends[resource_type] = {
                    "current_usage_percent": 45,
                    "avg_usage_30d_percent": 42,
                    "max_usage_30d_percent": 78,
                    "trend": "increasing",  # increasing, decreasing, stable
                    "daily_values": [40, 41, 42, 43, 44, 45],  # Last 5 days
                }
            elif resource_type == "memory":
                trends[resource_type] = {
                    "current_usage_percent": 55,
                    "avg_usage_30d_percent": 52,
                    "max_usage_30d_percent": 85,
                    "trend": "increasing",
                    "daily_values": [50, 51, 52, 54, 55],
                }
            elif resource_type == "storage":
                trends[resource_type] = {
                    "current_usage_percent": 35,
                    "avg_usage_30d_percent": 33,
                    "max_usage_30d_percent": 40,
                    "trend": "stable",
                    "daily_values": [33, 33, 34, 34, 35],
                }

        return trends

    def _calculate_growth_rates(self, usage_trends: dict[str, Any]) -> dict[str, float]:
        """Calculate growth rates from usage trends.

        Returns:
            Dict with growth rates (percentage per month)
        """
        growth_rates = {}

        for resource_type, trend_data in usage_trends.items():
            daily_values = trend_data.get("daily_values", [])
            if len(daily_values) >= 2:
                # Calculate simple linear growth
                first_value = daily_values[0]
                last_value = daily_values[-1]
                if first_value > 0:
                    growth_percent = ((last_value - first_value) / first_value) * 100
                    # Extrapolate to monthly (30 days)
                    growth_rates[resource_type] = growth_percent * (30 / len(daily_values))
                else:
                    growth_rates[resource_type] = 0.0
            else:
                growth_rates[resource_type] = 0.0

        return growth_rates

    def _forecast_capacity(
        self,
        current_capacity: dict[str, Any],
        usage_trends: dict[str, Any],
        growth_rates: dict[str, float],
        horizon_days: int,
    ) -> dict[str, Any]:
        """Forecast capacity needs over time horizon.

        Returns:
            Dict with forecast data
        """
        forecast = {
            "forecasts": [],
        }

        # Generate forecasts at 30-day intervals
        for day in range(30, horizon_days + 1, 30):
            period_forecast = {
                "day": day,
                "date": (datetime.now() + timedelta(days=day)).strftime("%Y-%m-%d"),
                "resource_forecasts": {},
            }

            for resource_type, trend_data in usage_trends.items():
                current_usage = trend_data["current_usage_percent"]
                growth_rate = growth_rates.get(resource_type, 0.0)

                # Project usage
                projected_usage = current_usage * (1 + (growth_rate / 100) * (day / 30))

                period_forecast["resource_forecasts"][resource_type] = {
                    "projected_usage_percent": round(projected_usage, 1),
                    "growth_rate_percent": round(growth_rate, 1),
                    "risk_level": self._assess_risk_level(projected_usage),
                }

            forecast["forecasts"].append(period_forecast)

        return forecast

    def _assess_risk_level(self, usage_percent: float) -> str:
        """Assess risk level based on usage percentage.

        Returns:
            Risk level: critical, high, medium, low
        """
        if usage_percent >= 90:
            return "critical"
        elif usage_percent >= 75:
            return "high"
        elif usage_percent >= 50:
            return "medium"
        else:
            return "low"

    def _identify_capacity_gaps(
        self,
        current_capacity: dict[str, Any],
        forecast: dict[str, Any],
    ) -> dict[str, Any]:
        """Identify capacity gaps in the forecast.

        Returns:
            Dict with capacity gap information
        """
        gaps = []

        for period_forecast in forecast["forecasts"]:
            for resource_type, resource_forecast in period_forecast["resource_forecasts"].items():
                if resource_forecast["risk_level"] in ["critical", "high"]:
                    gaps.append({
                        "resource_type": resource_type,
                        "day": period_forecast["day"],
                        "date": period_forecast["date"],
                        "projected_usage": resource_forecast["projected_usage_percent"],
                        "risk_level": resource_forecast["risk_level"],
                    })

        return {
            "has_gaps": len(gaps) > 0,
            "gap_count": len(gaps),
            "gaps": gaps,
            "first_gap_date": gaps[0]["date"] if gaps else None,
        }

    def _generate_recommendations(
        self,
        current_capacity: dict[str, Any],
        forecast: dict[str, Any],
        gaps: dict[str, Any],
        growth_rates: dict[str, float],
    ) -> list[Recommendation]:
        """Generate capacity planning recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check if capacity gaps exist
        if gaps["has_gaps"]:
            first_gap = gaps["gaps"][0]
            days_until_gap = first_gap["day"]

            recommendations.append(Recommendation(
                title="Plan capacity expansion",
                description=f"Capacity shortage predicted for {first_gap['resource_type']} "
                          f"by {first_gap['date']} ({days_until_gap} days from now)",
                impact="high",
                effort="medium",
                priority="critical" if days_until_gap < 30 else "high",
                actions=[
                    f"Add 20% more {first_gap['resource_type']} capacity before {first_gap['date']}",
                    "Review auto-scaling policies",
                    "Consider right-sizing over-provisioned resources",
                ],
            ))

        # Recommend scaling strategies
        for resource_type, growth_rate in growth_rates.items():
            if growth_rate > 10:  # >10% monthly growth
                recommendations.append(Recommendation(
                    title=f"Implement auto-scaling for {resource_type}",
                    description=f"{resource_type} usage growing at {growth_rate:.1f}%/month, "
                              f"auto-scaling recommended",
                    impact="medium",
                    effort="low",
                    priority="high",
                    actions=[
                        f"Configure Horizontal Pod Autoscaler for {resource_type}",
                        "Set appropriate scaling thresholds (70% target)",
                        "Test scaling behavior in staging",
                    ],
                ))

        # Recommend monitoring
        recommendations.append(Recommendation(
            title="Set up capacity monitoring alerts",
            description="Configure alerts for capacity thresholds",
            impact="medium",
            effort="low",
            priority="medium",
            actions=[
                "Alert at 70% capacity usage",
                "Critical alert at 85% capacity usage",
                "Weekly capacity review reports",
            ],
        ))

        return recommendations

    def _calculate_confidence(
        self,
        usage_trends: dict[str, Any],
        current_capacity: dict[str, Any],
    ) -> float:
        """Calculate confidence in the analysis.

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.7  # Base confidence

        # Increase confidence if we have good trend data
        for trend_data in usage_trends.values():
            daily_values = trend_data.get("daily_values", [])
            if len(daily_values) >= 5:
                confidence += 0.05

        return min(confidence, 1.0)

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate forecast_horizon_days
        horizon_days = parameters.get("forecast_horizon_days", 90)
        if not isinstance(horizon_days, int) or horizon_days < 1 or horizon_days > 365:
            errors.append("forecast_horizon_days must be an integer between 1 and 365")

        # Validate resource_types
        resource_types = parameters.get("resource_types", [])
        if resource_types:
            valid_types = ["cpu", "memory", "storage", "pods"]
            for rt in resource_types:
                if rt not in valid_types:
                    errors.append(f"Invalid resource_type: {rt}. Must be one of {valid_types}")

        # Validate growth_rate if provided
        growth_rate = parameters.get("growth_rate")
        if growth_rate is not None:
            if not isinstance(growth_rate, (int, float)):
                errors.append("growth_rate must be a number")
            elif growth_rate < -100 or growth_rate > 100:
                errors.append("growth_rate must be between -100 and 100")

        return len(errors) == 0, errors


    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Get recommendations based on analysis results.

        Args:
            analysis_id: ID of previous analysis result
            project: Project/service name

        Returns:
            List of recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        return result.recommendations or []
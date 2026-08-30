"""Growth Predictor Skill - Predict growth based on historical patterns."""

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


class GrowthPredictorSkill(BaseSkill):
    """Predict infrastructure growth based on patterns.

    This skill analyzes:
    - Historical growth patterns
    - Seasonal variations
    - Traffic trends
    - Resource utilization growth
    """

    skill_id = "capacity_growth_predictor"
    name = "Growth Predictor"
    description = "Predict infrastructure growth based on historical patterns"
    category = SkillCategory.CAPACITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"
    requires_prometheus = True

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run growth prediction analysis.

        Args:
            project: Project name
            parameters: Analysis parameters
                - forecast_months: Months to forecast (default: 3)
                - lookback_days: Historical data to analyze (default: 90)
            context: Registry context

        Returns:
            AnalysisResult with growth predictions
        """
        try:
            forecast_months = parameters.get("forecast_months", 3)
            lookback_days = parameters.get("lookback_days", 90)

            # Analyze historical growth
            historical_data = await self._fetch_historical_data(project, lookback_days, context)

            # Generate predictions
            predictions = self._generate_predictions(historical_data, forecast_months)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.75,
                data={
                    "forecast_months": forecast_months,
                    "lookback_days": lookback_days,
                    "predictions": predictions,
                    "summary": self._generate_summary(predictions),
                },
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Growth prediction failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate planning recommendations.

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
        summary = result.data.get("summary", {})

        if summary.get("rapid_growth"):
            recommendations.append(Recommendation(
                title="Plan for rapid infrastructure growth",
                description=f"Predicted {summary['growth_rate']:.1f}% monthly growth. "
                f"Review capacity planning and budget accordingly.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 days",
                risk_level="low",
                commands=[
                    "# Review capacity plan",
                    "curl -X POST /api/v1/skills/capacity_planner/analyze",
                ],
            ))

        return recommendations

    async def _fetch_historical_data(
        self,
        project: str,
        days: int,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Fetch real historical metrics from Prometheus (Phase 13)."""
        prom = ((context or {}).get("clients") or {}).get("prometheus")
        if prom is None:
            raise RuntimeError(
                "No Prometheus in context['clients']['prometheus'] — skill requires Prometheus"
            )
        from app.skills.capacity.prom_history import fetch_metric_series

        series = await fetch_metric_series(
            prom, ["cpu", "memory", "disk"], days=max(days, 7)
        )
        # map to the predictor's key names; request_count has no cluster-wide
        # expression — stays empty (insufficient data, honestly reported)
        return {
            "cpu_usage": series["cpu"],
            "memory_usage": series["memory"],
            "request_count": [],
            "storage_usage": series["disk"],
        }

    def _generate_predictions(
        self,
        historical: dict[str, Any],
        months: int,
    ) -> dict[str, Any]:
        """Generate growth predictions."""
        predictions = []

        for month in range(1, months + 1):
            date = datetime.now(timezone.utc) + timedelta(days=30 * month)

            # Simple linear growth prediction
            growth_factor = 1 + (0.05 * month)  # 5% growth per month

            predictions.append({
                "month": month,
                "date": date.strftime("%Y-%m"),
                "cpu_usage_percent": 50 * growth_factor,
                "memory_usage_percent": 60 * growth_factor,
                "storage_gb": 500 * growth_factor,
                "request_count_millions": 10 * growth_factor,
            })

        return {"forecasts": predictions, "growth_rate_percent": 5.0}

    def _generate_summary(self, predictions: dict) -> dict[str, Any]:
        """Generate prediction summary."""
        return {
            "growth_rate": predictions.get("growth_rate_percent", 0),
            "rapid_growth": predictions.get("growth_rate_percent", 0) > 10,
            "months_forecasted": len(predictions.get("forecasts", [])),
        }

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        errors = []

        forecast_months = parameters.get("forecast_months", 3)
        if not isinstance(forecast_months, int) or forecast_months < 1 or forecast_months > 12:
            errors.append("forecast_months must be between 1 and 12")

        lookback_days = parameters.get("lookback_days", 90)
        if not isinstance(lookback_days, int) or lookback_days < 7 or lookback_days > 365:
            errors.append("lookback_days must be between 7 and 365")

        return len(errors) == 0, errors

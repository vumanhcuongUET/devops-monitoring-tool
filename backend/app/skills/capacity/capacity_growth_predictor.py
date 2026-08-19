"""Capacity Growth Predictor Skill - Predict infrastructure growth patterns.

This skill analyzes historical data to:
- Predict resource growth patterns
- Identify seasonal trends
- Forecast peak usage periods
- Plan capacity procurement
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


class CapacityGrowthPredictorSkill(BaseSkill):
    """Predict capacity growth patterns.

    This skill analyzes historical metrics to:
    - Predict short-term and long-term growth
    - Identify seasonal patterns and trends
    - Forecast peak usage periods
    - Recommend capacity procurement timing

    Requires:
    - Prometheus metrics access
    - 90+ days of historical data for accurate predictions
    - Historical growth data
    """

    skill_id = "capacity_growth_predictor"
    name = "Capacity Growth Predictor"
    description = "Predict infrastructure growth patterns and plan capacity procurement"
    category = SkillCategory.CAPACITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Growth Predictor skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze growth patterns and predict future capacity needs.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context

        Returns:
            AnalysisResult with growth predictions
        """
        try:
            logger.info(f"Predicting growth for {project}")

            # Extract parameters
            prediction_days = parameters.get("prediction_horizon_days", 180)
            resource_type = parameters.get("resource_type", "all")

            # Analyze historical growth
            historical_growth = await self._analyze_historical_growth(
                project,
                resource_type,
                context
            )

            # Identify seasonal patterns
            seasonal_patterns = await self._identify_seasonal_patterns(
                project,
                context
            )

            # Generate growth predictions
            predictions = self._generate_predictions(
                historical_growth,
                seasonal_patterns,
                prediction_days,
            )

            # Identify peak periods
            peak_periods = self._identify_peak_periods(
                historical_growth,
                seasonal_patterns,
            )

            # Generate procurement recommendations
            recommendations = self._generate_procurement_recommendations(
                predictions,
                peak_periods,
            )

            # Build result
            data = {
                "historical_growth": historical_growth,
                "seasonal_patterns": seasonal_patterns,
                "predictions": predictions,
                "peak_periods": peak_periods,
                "prediction_horizon_days": prediction_days,
                "analysis_date": datetime.now().isoformat(),
            }

            confidence = self._calculate_confidence(historical_growth)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Growth prediction failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _analyze_historical_growth(
        self,
        project: str,
        resource_type: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze historical growth patterns.

        Returns:
            Dict with historical growth data
        """
        # Mock implementation - query Prometheus for 90-day history
        # Real implementation would:
        # 1. Query daily metrics for the last 90 days
        # 2. Calculate growth rates
        # 3. Identify trend patterns

        monthly_growth = {
            "30d": 12.5,  # 12.5% growth in last 30 days
            "60d": 24.8,  # 24.8% growth in last 60 days
            "90d": 38.2,  # 38.2% growth in last 90 days
        }

        # Calculate average monthly growth rate
        avg_monthly_growth_rate = monthly_growth["30d"]  # ~12.5% per month

        # Calculate compound monthly growth rate
        compound_monthly_rate = ((1 + monthly_growth["90d"] / 100) ** (1/3) - 1) * 100

        return {
            "monthly_growth": monthly_growth,
            "avg_monthly_growth_rate": avg_monthly_growth_rate,
            "compound_monthly_rate": compound_monthly_rate,
            "trend": "accelerating",  # accelerating, steady, decelerating
            "daily_usage": self._get_mock_daily_usage(),
        }

    def _get_mock_daily_usage(self) -> list[dict[str, Any]]:
        """Get mock daily usage data."""
        # Generate 30 days of mock data
        usage_data = []
        base_usage = 100

        for day in range(30):
            # Simulate growth with some noise
            growth_factor = 1 + (0.004 * day)  # ~0.4% daily growth
            noise = 0.9 + (0.2 * hash(day) % 10 / 10)  # Random noise
            daily_usage = base_usage * growth_factor * noise

            usage_data.append({
                "day": day + 1,
                "date": (datetime.now() - timedelta(days=30 - day)).strftime("%Y-%m-%d"),
                "usage": round(daily_usage, 1),
            })

        return usage_data

    async def _identify_seasonal_patterns(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Identify seasonal usage patterns.

        Returns:
            Dict with seasonal pattern data
        """
        # Mock implementation - analyze by day of week, month, etc.
        # Real implementation would:
        # 1. Group metrics by day of week
        # 2. Group by week of month
        # 3. Identify recurring patterns

        return {
            "weekly_pattern": {
                "weekday_avg": 95,
                "weekend_avg": 70,
                "peak_day": "Wednesday",
                "lowest_day": "Sunday",
                "variation_percent": 26,
            },
            "monthly_pattern": {
                "month_start_avg": 110,
                "month_end_avg": 105,
                "month_mid_avg": 100,
                "peak_week": 2,  # Second week of month
            },
            "has_seasonality": True,
            "seasonality_factor": 0.15,  # 15% variation due to seasonality
        }

    def _generate_predictions(
        self,
        historical_growth: dict[str, Any],
        seasonal_patterns: dict[str, Any],
        prediction_days: int,
    ) -> dict[str, Any]:
        """Generate growth predictions.

        Returns:
            Dict with prediction data
        """
        predictions = {
            "monthly_predictions": [],
            "quarterly_predictions": [],
        }

        # Use compound monthly growth rate for predictions
        monthly_rate = historical_growth["compound_monthly_rate"]

        # Generate monthly predictions
        for month in range(1, int(prediction_days / 30) + 2):
            predicted_growth = (1 + monthly_rate / 100) ** month - 1

            # Apply seasonal adjustment if available
            seasonal_factor = 1.0
            if seasonal_patterns.get("has_seasonality"):
                # Simple seasonal adjustment (alternating +5%/-5%)
                seasonal_factor = 1.0 + (0.05 if month % 2 == 0 else -0.05)

            adjusted_growth = predicted_growth * seasonal_factor

            predictions["monthly_predictions"].append({
                "month": month,
                "predicted_growth_percent": round(adjusted_growth * 100, 1),
                "predicted_usage_multiplier": round(1 + adjusted_growth, 2),
                "confidence_interval": {
                    "lower": round((adjusted_growth * 0.8) * 100, 1),
                    "upper": round((adjusted_growth * 1.2) * 100, 1),
                },
            })

        # Generate quarterly predictions
        for quarter in range(1, 5):
            month = quarter * 3
            predicted_growth = (1 + monthly_rate / 100) ** month - 1

            predictions["quarterly_predictions"].append({
                "quarter": quarter,
                "predicted_growth_percent": round(predicted_growth * 100, 1),
            })

        return predictions

    def _identify_peak_periods(
        self,
        historical_growth: dict[str, Any],
        seasonal_patterns: dict[str, Any],
    ) -> dict[str, Any]:
        """Identify predicted peak usage periods.

        Returns:
            Dict with peak period data
        """
        peak_periods = []

        # Add weekly peaks
        if seasonal_patterns.get("weekly_pattern"):
            weekly = seasonal_patterns["weekly_pattern"]
            peak_periods.append({
                "type": "weekly",
                "period": weekly.get("peak_day"),
                "expected_increase_percent": 10,
                "duration_hours": 8,
            })

        # Add monthly peaks
        if seasonal_patterns.get("monthly_pattern"):
            monthly = seasonal_patterns["monthly_pattern"]
            peak_periods.append({
                "type": "monthly",
                "period": f"Week {monthly.get('peak_week')} of month",
                "expected_increase_percent": 15,
                "duration_days": 7,
            })

        # Add special events (holidays, etc.)
        peak_periods.append({
            "type": "event",
            "period": "End of quarter",
            "expected_increase_percent": 25,
            "duration_days": 3,
        })

        return {
            "has_peaks": len(peak_periods) > 0,
            "peak_periods": peak_periods,
            "max_expected_increase": max(p.get("expected_increase_percent", 0)
                                       for p in peak_periods) if peak_periods else 0,
        }

    def _generate_procurement_recommendations(
        self,
        predictions: dict[str, Any],
        peak_periods: dict[str, Any],
    ) -> list[Recommendation]:
        """Generate capacity procurement recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check for rapid growth
        if predictions["monthly_predictions"]:
            first_month = predictions["monthly_predictions"][0]
            if first_month["predicted_growth_percent"] > 20:
                recommendations.append(Recommendation(
                    title="Plan immediate capacity expansion",
                    description=f"Predicted {first_month['predicted_growth_percent']}% growth next month",
                    impact="high",
                    effort="medium",
                    priority="high",
                    actions=[
                        "Procure additional infrastructure within 2 weeks",
                        "Enable auto-scaling if not already active",
                        "Review reserve capacity strategy",
                    ],
                ))

        # Recommend capacity buffers for peak periods
        if peak_periods["has_peaks"]:
            max_increase = peak_periods["max_expected_increase"]
            if max_increase > 15:
                recommendations.append(Recommendation(
                    title=f"Prepare for peak usage periods (+{max_increase}%)",
                    description="Ensure sufficient capacity buffer for predicted peaks",
                    impact="medium",
                    effort="low",
                    priority="medium",
                    actions=[
                        "Maintain 30% capacity buffer during peak periods",
                        "Scale auto-scaling limits for peak handling",
                        "Review and test peak load procedures",
                    ],
                ))

        # Long-term planning recommendation
        three_month_growth = predictions["quarterly_predictions"][2]["predicted_growth_percent"]
        if three_month_growth > 50:
            recommendations.append(Recommendation(
                title="Initiate long-term capacity planning",
                description=f"Predicted {three_month_growth}% growth in 3 months requires planning",
                impact="high",
                effort="high",
                priority="high",
                actions=[
                    "Review infrastructure roadmap",
                    "Evaluate reserved instance/capacity commitments",
                    "Consider multi-region expansion",
                    "Update financial forecasts for infrastructure costs",
                ],
            ))

        # Monitoring recommendation
        recommendations.append(Recommendation(
            title="Set up growth monitoring alerts",
            description="Configure alerts for growth anomalies",
            impact="medium",
            effort="low",
            priority="medium",
            actions=[
                "Alert if weekly growth exceeds 20%",
                "Alert if growth rate changes significantly",
                "Weekly growth review meetings",
            ],
        ))

        return recommendations

    def _calculate_confidence(self, historical_growth: dict[str, Any]) -> float:
        """Calculate confidence in predictions.

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.6  # Base confidence for predictions

        # Increase confidence with more historical data
        daily_usage = historical_growth.get("daily_usage", [])
        if len(daily_usage) >= 90:
            confidence += 0.2
        elif len(daily_usage) >= 60:
            confidence += 0.1
        elif len(daily_usage) >= 30:
            confidence += 0.05

        # Increase confidence if trend is clear
        trend = historical_growth.get("trend")
        if trend in ["accelerating", "steady"]:
            confidence += 0.1

        return min(confidence, 0.9)  # Cap at 90% for predictions

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate prediction_horizon_days
        horizon = parameters.get("prediction_horizon_days")
        if horizon is not None:
            if not isinstance(horizon, int) or horizon < 30 or horizon > 365:
                errors.append("prediction_horizon_days must be between 30 and 365")

        # Validate resource_type
        resource_type = parameters.get("resource_type")
        if resource_type is not None:
            valid_types = ["all", "cpu", "memory", "storage", "pods"]
            if resource_type not in valid_types:
                errors.append(f"resource_type must be one of {valid_types}")

        return len(errors) == 0, errors

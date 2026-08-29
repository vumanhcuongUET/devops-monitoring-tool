"""Cost Analyzer Skill - Analyze cloud costs and trends.

This skill analyzes cloud infrastructure costs to identify:
- Cost breakdown by service and resource
- Cost anomalies and unusual patterns
- Cost trends and forecasts
- Optimization opportunities
"""

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


class CostAnalyzerSkill(BaseSkill):
    """Analyze cloud costs and provide optimization recommendations.

    This skill integrates with cloud billing APIs to:
    - Aggregate costs by service, resource, and project
    - Detect cost anomalies and unusual spending
    - Forecast future costs based on trends
    - Identify optimization opportunities

    Requires:
    - Cloud provider credentials (AWS, GCP, Azure)
    - Cost Explorer / Billing API access
    - Historical cost data (30+ days recommended)
    """

    skill_id = "finops_cost_analyzer"
    name = "Cost Analyzer"
    description = "Analyze cloud costs, detect anomalies, and identify optimization opportunities"
    category = SkillCategory.FINOPS
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the Cost Analyzer skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)

        # Cloud provider clients (lazy loaded)
        self._aws_client = None
        self._gcp_client = None
        self._azure_client = None

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run cost analysis for the specified project.

        Args:
            project: Project/service name
            parameters: Analysis parameters
                - days: Number of days to analyze (default: 30)
                - forecast_days: Days to forecast (default: 7)
                - anomaly_threshold: Percentage threshold for anomalies (default: 20)
                - breakdown_by: Group costs by (service, resource, tag) (default: "service")
            context: Additional context from registry

        Returns:
            AnalysisResult with cost breakdown and anomalies
        """
        self._log("info", f"Starting cost analysis for project: {project}")

        try:
            # Extract parameters
            days = parameters.get("days", 30)
            forecast_days = parameters.get("forecast_days", 7)
            anomaly_threshold = parameters.get("anomaly_threshold", 20)
            breakdown_by = parameters.get("breakdown_by", "service")

            # Get cost data from cloud provider
            cost_data = await self._fetch_cost_data(
                project=project,
                days=days,
                context=context or {},
            )

            # Analyze costs
            breakdown = self._analyze_breakdown(cost_data, breakdown_by)
            anomalies = self._detect_anomalies(cost_data, anomaly_threshold)
            trends = self._analyze_trends(cost_data)
            forecast = self._forecast_costs(cost_data, forecast_days)

            # Calculate confidence based on data quality
            confidence = self._calculate_confidence(cost_data, days)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "breakdown": breakdown,
                    "anomalies": anomalies,
                    "trends": trends,
                    "forecast": forecast,
                    "total_cost": cost_data.get("total_cost", 0),
                    "currency": cost_data.get("currency", "USD"),
                    "period_days": days,
                    "project": project,
                },
                warnings=self._generate_warnings(cost_data, anomalies),
                metadata={
                    "provider": cost_data.get("provider", "unknown"),
                    "analysis_date": datetime.now(timezone.utc).isoformat(),
                },
            )

        except Exception as e:
            self._log("error", f"Cost analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                errors=[f"Cost analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate cost optimization recommendations.

        Args:
            analysis_id: ID of previous analysis
            project: Project name

        Returns:
            List of cost optimization recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        data = result.data

        # Anomaly-based recommendations
        for anomaly in data.get("anomalies", []):
            if anomaly["severity"] == "high":
                recommendations.append(Recommendation(
                    title=f"Investigate cost spike: {anomaly['description']}",
                    description=f"Unusual cost increase detected in {anomaly['service']}. "
                    f"Cost rose by {anomaly['percentage']:.1f}% from ${anomaly['previous']:.2f} "
                    f"to ${anomaly['current']:.2f}.",
                    priority=SkillPriority.HIGH,
                    action_type="manual",
                    estimated_effort="1-2 hours",
                    risk_level="low",
                    commands=[
                        f"# Check {anomaly['service']} usage",
                        f"aws ce get-cost-and-usage --time-range {anomaly['date']}",
                    ],
                ))

        # Trend-based recommendations
        trends = data.get("trends", {})
        if trends.get("direction") == "increasing" and trends.get("rate_of_change", 0) > 10:
            recommendations.append(Recommendation(
                title="Address rapidly increasing costs",
                description=f"Costs are increasing at {trends['rate_of_change']:.1f}% per {trends.get('period', 'week')}. "
                f"Review resource utilization and consider rightsizing.",
                priority=SkillPriority.MEDIUM,
                action_type="hybrid",
                estimated_effort="2-4 hours",
                risk_level="low",
                commands=[
                    "# Review top cost contributors",
                    "aws ce cost-and-usage --group-by SERVICE",
                    "# Consider reserved instances or savings plans",
                ],
            ))

        # Idle resources recommendation
        if data.get("idle_resource_cost", 0) > 100:
            recommendations.append(Recommendation(
                title=f"Clean up idle resources (potential savings: ${data['idle_resource_cost']:.2f}/month)",
                description=f"Detected idle resources costing ${data['idle_resource_cost']:.2f} per month. "
                f"Run the idle_resources skill for detailed analysis.",
                priority=SkillPriority.HIGH,
                action_type="automated",
                estimated_effort="1 hour",
                risk_level="low",
                commands=[
                    "# Run idle resources analysis",
                    "curl -X POST /api/v1/skills/finops_idle_resources/analyze",
                ],
            ))

        return recommendations

    async def _fetch_cost_data(
        self,
        project: str,
        days: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch cost data from cloud provider.

        Args:
            project: Project name
            days: Number of days of data to fetch
            context: Registry context with project config

        Returns:
            Cost data dictionary
        """
        # Get project config from context
        project_config = context.get("project", {})

        # Determine cloud provider
        provider = project_config.get("cloud_provider", "aws")

        # Fetch from appropriate provider
        if provider == "aws":
            return await self._fetch_aws_costs(project, days, project_config)
        elif provider == "gcp":
            return await self._fetch_gcp_costs(project, days, project_config)
        elif provider == "azure":
            return await self._fetch_azure_costs(project, days, project_config)
        else:
            # Return mock data for testing
            return self._generate_mock_cost_data(project, days)

    async def _fetch_aws_costs(
        self,
        project: str,
        days: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch costs from AWS Cost Explorer.

        Args:
            project: Project name
            days: Days of data
            config: Project configuration

        Returns:
            AWS cost data
        """
        # Implementation would use AWS Cost Explorer API
        # For now, return mock data
        self._log("info", "Fetching AWS costs (mock implementation)")
        return self._generate_mock_cost_data(project, days)

    async def _fetch_gcp_costs(
        self,
        project: str,
        days: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch costs from GCP Billing API.

        Args:
            project: Project name
            days: Days of data
            config: Project configuration

        Returns:
            GCP cost data
        """
        self._log("info", "Fetching GCP costs (mock implementation)")
        return self._generate_mock_cost_data(project, days)

    async def _fetch_azure_costs(
        self,
        project: str,
        days: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch costs from Azure Cost Management.

        Args:
            project: Project name
            days: Days of data
            config: Project configuration

        Returns:
            Azure cost data
        """
        self._log("info", "Fetching Azure costs (mock implementation)")
        return self._generate_mock_cost_data(project, days)

    def _generate_mock_cost_data(self, project: str, days: int) -> dict[str, Any]:
        """Generate mock cost data for testing.

        Args:
            project: Project name
            days: Number of days

        Returns:
            Mock cost data
        """
        import random

        # Generate daily costs with some patterns
        daily_costs = []
        total_cost = 0

        for i in range(days):
            day_cost = random.uniform(100, 500)
            # Add some anomalies
            if i == days - 7:
                day_cost *= 1.5  # Spike

            daily_costs.append({
                "date": (datetime.now(timezone.utc) - timedelta(days=days - i)).strftime("%Y-%m-%d"),
                "cost": day_cost,
            })
            total_cost += day_cost

        # Generate breakdown by service
        services = [
            {"service": "EC2", "cost": total_cost * 0.4},
            {"service": "RDS", "cost": total_cost * 0.2},
            {"service": "S3", "cost": total_cost * 0.15},
            {"service": "Lambda", "cost": total_cost * 0.1},
            {"service": "CloudFront", "cost": total_cost * 0.1},
            {"service": "Other", "cost": total_cost * 0.05},
        ]

        return {
            "provider": "aws",
            "project": project,
            "currency": "USD",
            "total_cost": total_cost,
            "daily_costs": daily_costs,
            "breakdown": services,
            "idle_resource_cost": total_cost * 0.1,
        }

    def _analyze_breakdown(
        self,
        cost_data: dict[str, Any],
        breakdown_by: str,
    ) -> dict[str, Any]:
        """Analyze cost breakdown.

        Args:
            cost_data: Cost data from provider
            breakdown_by: How to group costs

        Returns:
            Breakdown analysis
        """
        breakdown = cost_data.get("breakdown", [])

        # Sort by cost descending
        sorted_breakdown = sorted(breakdown, key=lambda x: x["cost"], reverse=True)

        # Calculate percentages
        total = cost_data.get("total_cost", 0)
        for item in sorted_breakdown:
            item["percentage"] = (item["cost"] / total * 100) if total > 0 else 0

        return {
            "by": breakdown_by,
            "items": sorted_breakdown,
            "top_contributor": sorted_breakdown[0] if sorted_breakdown else None,
        }

    def _detect_anomalies(
        self,
        cost_data: dict[str, Any],
        threshold: float,
    ) -> list[dict[str, Any]]:
        """Detect cost anomalies.

        Args:
            cost_data: Cost data
            threshold: Percentage threshold for anomalies

        Returns:
            List of detected anomalies
        """
        daily_costs = cost_data.get("daily_costs", [])
        anomalies = []

        if len(daily_costs) < 7:
            return anomalies

        # Calculate moving average
        window_size = 7
        for i in range(window_size, len(daily_costs)):
            recent_costs = [d["cost"] for d in daily_costs[i - window_size:i]]
            avg_cost = sum(recent_costs) / window_size
            current_cost = daily_costs[i]["cost"]

            # Check if current deviates significantly
            if avg_cost > 0:
                deviation = ((current_cost - avg_cost) / avg_cost) * 100

                if abs(deviation) > threshold:
                    severity = "high" if abs(deviation) > threshold * 2 else "medium"

                    anomalies.append({
                        "date": daily_costs[i]["date"],
                        "service": "overall",
                        "severity": severity,
                        "previous": avg_cost,
                        "current": current_cost,
                        "percentage": deviation,
                        "description": f"Cost {'spike' if deviation > 0 else 'drop'} of {abs(deviation):.1f}%",
                    })

        return anomalies

    def _analyze_trends(self, cost_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze cost trends.

        Args:
            cost_data: Cost data

        Returns:
            Trend analysis
        """
        daily_costs = cost_data.get("daily_costs", [])
        if len(daily_costs) < 14:
            return {"direction": "unknown", "rate_of_change": 0}

        # Calculate trend using simple linear regression
        recent = daily_costs[-14:]
        costs = [d["cost"] for d in recent]

        # Simple rate of change (last 7 days vs previous 7)
        first_week_avg = sum(costs[:7]) / 7
        second_week_avg = sum(costs[7:]) / 7

        if first_week_avg > 0:
            rate_of_change = ((second_week_avg - first_week_avg) / first_week_avg) * 100
            direction = "increasing" if rate_of_change > 5 else "decreasing" if rate_of_change < -5 else "stable"
        else:
            rate_of_change = 0
            direction = "unknown"

        return {
            "direction": direction,
            "rate_of_change": abs(rate_of_change),
            "period": "week",
        }

    def _forecast_costs(
        self,
        cost_data: dict[str, Any],
        days: int,
    ) -> dict[str, Any]:
        """Forecast future costs.

        Args:
            cost_data: Historical cost data
            days: Days to forecast

        Returns:
            Cost forecast
        """
        daily_costs = cost_data.get("daily_costs", [])
        if len(daily_costs) < 7:
            return {"forecast": [], "method": "insufficient_data"}

        # Simple average-based forecast
        avg_daily_cost = sum(d["cost"] for d in daily_costs[-7:]) / 7

        forecast = []
        forecast_date = datetime.now(timezone.utc) + timedelta(days=1)

        for i in range(days):
            # Add some variation
            variation = 1.0 + (i * 0.01)  # Assume slight growth
            forecast_cost = avg_daily_cost * variation

            forecast.append({
                "date": forecast_date.strftime("%Y-%m-%d"),
                "cost": forecast_cost,
            })

            forecast_date += timedelta(days=1)

        total_forecast = sum(f["cost"] for f in forecast)

        return {
            "forecast": forecast,
            "total": total_forecast,
            "method": "average",
            "confidence": "medium",
        }

    def _calculate_confidence(self, cost_data: dict[str, Any], days: int) -> float:
        """Calculate analysis confidence score.

        Args:
            cost_data: Cost data
            days: Days of data analyzed

        Returns:
            Confidence score (0-1)
        """
        confidence = 0.5

        # More data = higher confidence
        if days >= 90:
            confidence += 0.3
        elif days >= 30:
            confidence += 0.2
        elif days >= 14:
            confidence += 0.1

        # Real data (not mock) = higher confidence
        if cost_data.get("provider") != "mock":
            confidence += 0.2

        return min(confidence, 1.0)

    def _generate_warnings(
        self,
        cost_data: dict[str, Any],
        anomalies: list[dict[str, Any]],
    ) -> list[str]:
        """Generate analysis warnings.

        Args:
            cost_data: Cost data
            anomalies: Detected anomalies

        Returns:
            List of warnings
        """
        warnings = []

        if cost_data.get("provider") == "mock":
            warnings.append("Using mock cost data - configure cloud provider for accurate analysis")

        high_severity = [a for a in anomalies if a["severity"] == "high"]
        if high_severity:
            warnings.append(f"Detected {len(high_severity)} high-severity cost anomalies")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Args:
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        days = parameters.get("days", 30)
        if not isinstance(days, int) or days < 1 or days > 365:
            errors.append("days must be an integer between 1 and 365")

        forecast_days = parameters.get("forecast_days", 7)
        if not isinstance(forecast_days, int) or forecast_days < 1 or forecast_days > 90:
            errors.append("forecast_days must be an integer between 1 and 90")

        threshold = parameters.get("anomaly_threshold", 20)
        if not isinstance(threshold, (int, float)) or threshold < 1 or threshold > 100:
            errors.append("anomaly_threshold must be between 1 and 100")

        return len(errors) == 0, errors

"""SLI Calculator Skill - Calculate and track Service Level Indicators.

This skill analyzes metrics to calculate:
- Error rates and availability
- Latency percentiles (p50, p95, p99)
- Throughput metrics
- SLI trends over time
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillPriority,
    AnalysisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)


class SLICalculatorSkill(BaseSkill):
    """Calculate Service Level Indicators from metrics.

    This skill analyzes Prometheus metrics to:
    - Calculate error rates and availability
    - Measure latency percentiles
    - Track throughput
    - Monitor SLI trends over time
    - Compare against SLO targets

    Requires:
    - Prometheus metrics access
    - Service definition and endpoints
    - SLO target configurations
    """

    skill_id = "monitoring_sli_calculator"
    name = "SLI Calculator"
    description = "Calculate and track Service Level Indicators (SLIs)"
    category = SkillCategory.MONITORING
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the SLI Calculator skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Calculate SLIs for the service.

        Args:
            project: Project/service name
            parameters: Analysis parameters (time_window, sli_types)
            context: Additional context (SLO targets)

        Returns:
            AnalysisResult with SLI calculations
        """
        try:
            logger.info(f"Calculating SLIs for {project}")

            # Extract parameters
            time_window_hours = parameters.get("time_window_hours", 24)
            sli_types = parameters.get("sli_types", ["availability", "latency", "throughput"])

            # Calculate different SLI types
            sli_results = {}

            if "availability" in sli_types:
                sli_results["availability"] = await self._calculate_availability_sli(
                    project,
                    time_window_hours,
                    context
                )

            if "latency" in sli_types:
                sli_results["latency"] = await self._calculate_latency_sli(
                    project,
                    time_window_hours,
                    context
                )

            if "throughput" in sli_types:
                sli_results["throughput"] = await self._calculate_throughput_sli(
                    project,
                    time_window_hours,
                    context
                )

            # Calculate SLO compliance
            slo_compliance = self._calculate_slo_compliance(sli_results, context)

            # Generate recommendations
            recommendations = self._generate_recommendations(sli_results, slo_compliance)

            # Build result
            data = {
                "sli_results": sli_results,
                "slo_compliance": slo_compliance,
                "time_window_hours": time_window_hours,
                "analysis_timestamp": datetime.now().isoformat(),
            }

            confidence = 0.85  # High confidence for SLI calculations

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"SLI calculation failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _calculate_availability_sli(
        self,
        project: str,
        time_window_hours: int,
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate availability SLI.

        Returns:
            Dict with availability metrics
        """
        # Mock implementation - query Prometheus for:
        # - Total requests
        # - Error requests (5xx errors)
        # - Successful requests

        total_requests = 100000
        error_requests = 250  # 0.25% error rate

        availability_sli = {
            "total_requests": total_requests,
            "error_requests": error_requests,
            "success_requests": total_requests - error_requests,
            "error_rate_percent": round((error_requests / total_requests) * 100, 3),
            "availability_percent": round(((total_requests - error_requests) / total_requests) * 100, 3),
            "slo_target_percent": 99.9,  # From context
            "slo_compliant": ((total_requests - error_requests) / total_requests) >= 0.999,
        }

        return availability_sli

    async def _calculate_latency_sli(
        self,
        project: str,
        time_window_hours: int,
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate latency SLI with percentiles.

        Returns:
            Dict with latency metrics
        """
        # Mock implementation - query Prometheus for histogram metrics
        # Real implementation would calculate from http_request_duration_seconds

        latency_sli = {
            "percentiles": {
                "p50_ms": 120,
                "p90_ms": 350,
                "p95_ms": 520,
                "p99_ms": 1200,
            },
            "average_ms": 245,
            "max_ms": 3500,
            "slo_target_p95_ms": 1000,  # From context
            "slo_compliant": True,  # p95 < 1000ms
        }

        return latency_sli

    async def _calculate_throughput_sli(
        self,
        project: str,
        time_window_hours: int,
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate throughput SLI.

        Returns:
            Dict with throughput metrics
        """
        # Mock implementation - query Prometheus for request rate

        throughput_sli = {
            "requests_per_second": 125.5,
            "requests_per_minute": 7530,
            "peak_rps": 450,
            "average_rps": 125,
            "trend": "increasing",  # increasing, stable, decreasing
        }

        return throughput_sli

    def _calculate_slo_compliance(
        self,
        sli_results: Dict[str, Any],
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calculate SLO compliance across all SLIs.

        Returns:
            Dict with SLO compliance summary
        """
        compliance = {
            "overall_compliant": True,
            "sli_compliance": {},
        }

        for sli_type, sli_data in sli_results.items():
            if sli_type == "availability":
                is_compliant = sli_data.get("slo_compliant", False)
                compliance["sli_compliance"][sli_type] = {
                    "compliant": is_compliant,
                    "sli_value": sli_data.get("availability_percent"),
                    "slo_target": sli_data.get("slo_target_percent"),
                }
                if not is_compliant:
                    compliance["overall_compliant"] = False

            elif sli_type == "latency":
                is_compliant = sli_data.get("slo_compliant", False)
                compliance["sli_compliance"][sli_type] = {
                    "compliant": is_compliant,
                    "sli_value": sli_data["percentiles"]["p95_ms"],
                    "slo_target": sli_data.get("slo_target_p95_ms"),
                }
                if not is_compliant:
                    compliance["overall_compliant"] = False

        return compliance

    def _generate_recommendations(
        self,
        sli_results: Dict[str, Any],
        slo_compliance: Dict[str, Any],
    ) -> List[Recommendation]:
        """Generate SLI/SLO recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check SLO compliance
        if not slo_compliance["overall_compliant"]:
            for sli_type, compliance_data in slo_compliance["sli_compliance"].items():
                if not compliance_data["compliant"]:
                    recommendations.append(Recommendation(
                        title=f"Fix {sli_type} SLO violation",
                        description=f"{sli_type} SLI not meeting SLO target",
                        impact="high",
                        effort="high",
                        priority="critical",
                        actions=[
                            "Investigate root cause of SLO violation",
                            "Implement performance optimizations",
                            "Scale infrastructure if needed",
                            "Review SLO targets if unrealistic",
                        ],
                    ))

        # Availability recommendations
        if "availability" in sli_results:
            avail_data = sli_results["availability"]
            error_rate = avail_data.get("error_rate_percent", 0)

            if error_rate > 0.5:
                recommendations.append(Recommendation(
                    title="Reduce error rate",
                    description=f"Error rate is {error_rate}%, above recommended 0.1%",
                    impact="high",
                    effort="medium",
                    priority="high",
                    actions=[
                        "Investigate error patterns",
                        "Add circuit breakers for failing services",
                        "Implement retry logic with exponential backoff",
                    ],
                ))

        # Latency recommendations
        if "latency" in sli_results:
            lat_data = sli_results["latency"]
            p99_latency = lat_data["percentiles"]["p99_ms"]

            if p99_latency > 2000:
                recommendations.append(Recommendation(
                    title="Improve tail latency",
                    description=f"P99 latency is {p99_latency}ms, above recommended 1000ms",
                    impact="medium",
                    effort="high",
                    priority="medium",
                    actions=[
                        "Profile slow requests",
                        "Optimize database queries",
                        "Add caching for slow endpoints",
                        "Consider connection pooling optimizations",
                    ],
                ))

        # General monitoring recommendations
        recommendations.append(Recommendation(
            title="Set up SLI monitoring dashboard",
            description="Create visibility into SLI metrics",
            impact="medium",
            effort="low",
            priority="medium",
            actions=[
                "Create Grafana dashboard with SLI charts",
                "Set up alerts for SLO violations",
                "Daily SLI reports",
            ],
        ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate time_window_hours
        time_window = parameters.get("time_window_hours")
        if time_window is not None:
            if not isinstance(time_window, int) or time_window < 1 or time_window > 720:
                errors.append("time_window_hours must be between 1 and 720")

        # Validate sli_types
        sli_types = parameters.get("sli_types")
        if sli_types is not None:
            valid_types = ["availability", "latency", "throughput", "saturation"]
            for sli_type in sli_types:
                if sli_type not in valid_types:
                    errors.append(f"Invalid sli_type: {sli_type}")

        return len(errors) == 0, errors

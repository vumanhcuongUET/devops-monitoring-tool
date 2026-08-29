"""Observability SLO Tracker Skill.

Tracks SLO (Service Level Objective) compliance and error budgets.
Calculates SLO status, error budget remaining, and breach probability.
"""

import logging
from typing import Any

from app.services.prometheus_client import PrometheusClient
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
    """Track SLO compliance and error budgets.

    This skill analyzes SLO compliance for:
    - Availability targets (e.g., 99.9% uptime)
    - Latency targets (e.g., p95 < 100ms)
    - Error rate targets (e.g., < 0.1%)
    - Error budget consumption and remaining

    Example usage:
        skill = SLOTrackerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "slo_type": "availability",
                "target": 99.9,
                "window_days": 30
            }
        )
    """

    skill_id = "observability_slo_tracker"
    name = "Observability SLO Tracker"
    description = (
        "Track SLO compliance, calculate error budgets, "
        "and assess breach probability for service level objectives."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Default SLO targets
    DEFAULT_SLOS = {
        "availability": 99.9,  # 99.9% uptime
        "latency_p95_ms": 100,  # p95 latency < 100ms
        "latency_p99_ms": 500,  # p99 latency < 500ms
        "error_rate": 0.1,  # < 0.1% error rate
    }

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the SLO tracker skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        self.prometheus_client = PrometheusClient()

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run SLO compliance analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - slo_type: Type of SLO (availability, latency, error_rate)
                - target: SLO target value
                - window_days: Rolling window in days (default: 30)
            context: Additional context from registry

        Returns:
            AnalysisResult with SLO compliance data
        """
        try:
            # Extract parameters
            slo_type = parameters.get("slo_type", "availability")
            window_days = parameters.get("window_days", 30)

            # Get target (use default if not specified)
            if slo_type in self.DEFAULT_SLOS and "target" not in parameters:
                target = self.DEFAULT_SLOS[slo_type]
            else:
                target = parameters.get("target", self.DEFAULT_SLOS.get(slo_type, 99.9))

            # Calculate SLO compliance
            compliance_data = await self._calculate_slo_compliance(
                project=project,
                slo_type=slo_type,
                target=target,
                window_days=window_days,
            )

            # Calculate error budget
            error_budget = self._calculate_error_budget(
                slo_type=slo_type,
                target=target,
                compliance_data=compliance_data,
                window_days=window_days,
            )

            # Assess breach probability
            breach_probability = self._assess_breach_probability(
                compliance_data=compliance_data,
                error_budget=error_budget,
            )

            # Generate status
            status = self._determine_status(
                compliance_data=compliance_data,
                error_budget=error_budget,
            )

            # Calculate confidence
            confidence = self._calculate_confidence(compliance_data)

            # Generate warnings
            warnings = self._generate_warnings(status, error_budget, breach_probability)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "slo_type": slo_type,
                    "target": target,
                    "window_days": window_days,
                    "compliance": compliance_data,
                    "error_budget": error_budget,
                    "breach_probability": breach_probability,
                    "status": status,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "slo_type": slo_type,
                    "window_days": window_days,
                },
            )

        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[str(e)],
                metadata={"project": project},
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate recommendations based on SLO analysis.

        Args:
            analysis_id: ID of previous analysis result
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
        status = data.get("status")
        error_budget = data.get("error_budget", {})
        breach_probability = data.get("breach_probability", {})

        # Critical: SLO breach or high breach probability
        if status in ("breached", "critical"):
            recommendations.append(
                Recommendation(
                    title="SLO Breach Detected - Immediate Action Required",
                    description=f"SLO breach detected with {breach_probability.get('probability', 0):.0%} "
                    f"probability of continued failure.",
                    priority=SkillPriority.CRITICAL,
                    action_type="urgent",
                    estimated_effort="4-8 hours",
                    risk_level="critical",
                    commands=[
                        "Declare incident",
                        "Review recent changes",
                        "Rollback if necessary",
                        "Implement mitigation",
                    ],
                    references=["https://sre.google/sre-book/implementing-slos/"],
                )
            )

        # High risk: Error budget exhausted
        elif error_budget.get("remaining_percent", 100) < 20:
            recommendations.append(
                Recommendation(
                    title="Error Budget Nearly Exhausted",
                    description=f"Only {error_budget.get('remaining_percent', 0):.1f}% error budget "
                    f"remaining. Burn rate: {error_budget.get('burn_rate_percent', 0):.1f}% per day.",
                    priority=SkillPriority.HIGH,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="high",
                    commands=[
                        "Investigate reliability issues",
                        "Prioritize reliability work",
                        "Consider traffic shedding",
                        "Increase capacity if needed",
                    ],
                )
            )

        # Medium risk: At risk of breach
        elif status == "at_risk":
            recommendations.append(
                Recommendation(
                    title="SLO At Risk - Preventive Action Recommended",
                    description=f"SLO compliance trending toward breach. "
                    f"Current: {data.get('compliance', {}).get('current_value', 0):.2f}%, "
                    f"Target: {data.get('target', 0)}%",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="2-4 hours",
                    risk_level="medium",
                    commands=[
                        "Review performance trends",
                        "Identify degradation sources",
                        "Implement optimizations",
                        "Increase monitoring",
                    ],
                )
            )

        # Warning: High burn rate
        if error_budget.get("burn_rate_percent", 0) > 5:
            recommendations.append(
                Recommendation(
                    title="High Error Budget Burn Rate",
                    description=f"Error budget burning at {error_budget.get('burn_rate_percent', 0):.1f}% "
                    f"per day. At current rate, budget will be exhausted in "
                    f"{error_budget.get('days_until_exhausted', 0)} days.",
                    priority=SkillPriority.MEDIUM,
                    action_type="monitor",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Investigate error causes",
                        "Review incident response",
                        "Improve error handling",
                        "Add circuit breakers",
                    ],
                )
            )

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate analysis parameters.

        Args:
            parameters: Parameters to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate slo_type
        slo_type = parameters.get("slo_type", "availability")
        valid_types = ["availability", "latency_p95_ms", "latency_p99_ms", "error_rate"]
        if slo_type not in valid_types:
            errors.append(f"slo_type must be one of: {', '.join(valid_types)}")

        # Validate target
        target = parameters.get("target")
        if target is not None:
            if not isinstance(target, (int, float)):
                errors.append("target must be a number")
            elif slo_type == "availability" and (target <= 0 or target > 100):
                errors.append("availability target must be between 0 and 100")

        # Validate window_days
        window_days = parameters.get("window_days", 30)
        if not isinstance(window_days, int) or window_days < 1:
            errors.append("window_days must be a positive integer")

        return len(errors) == 0, errors

    async def _calculate_slo_compliance(
        self,
        project: str,
        slo_type: str,
        target: float,
        window_days: int,
    ) -> dict[str, Any]:
        """Calculate current SLO compliance.

        Args:
            project: Project name
            slo_type: Type of SLO
            target: SLO target value
            window_days: Rolling window in days

        Returns:
            Dictionary with compliance data
        """
        try:
            if slo_type == "availability":
                return await self._calculate_availability_compliance(
                    project, target, window_days
                )
            elif slo_type.startswith("latency"):
                return await self._calculate_latency_compliance(
                    project, target, window_days, slo_type
                )
            elif slo_type == "error_rate":
                return await self._calculate_error_rate_compliance(
                    project, target, window_days
                )
            else:
                return {"error": f"Unknown SLO type: {slo_type}"}

        except Exception as e:
            logger.warning(f"SLO compliance calculation failed: {e}")
            return {"error": str(e), "current_value": 0, "target": target}

    async def _calculate_availability_compliance(
        self, project: str, target: float, window_days: int
    ) -> dict[str, Any]:
        """Calculate availability SLO compliance.

        Args:
            project: Project name
            target: Availability target percentage
            window_days: Rolling window in days

        Returns:
            Availability compliance data
        """
        # Query total requests and errors in the window
        # In real implementation, query Prometheus:
        # total_requests = increase(http_requests_total)
        # errors = increase(http_requests_total{status=~"5.."})

        # Mock implementation
        total_requests = 1000000
        errors = 1500  # 0.15% error rate

        availability = ((total_requests - errors) / total_requests) * 100

        return {
            "current_value": availability,
            "target": target,
            "gap": availability - target,
            "total_requests": total_requests,
            "errors": errors,
            "compliance": availability >= target,
        }

    async def _calculate_latency_compliance(
        self, project: str, target: float, window_days: int, slo_type: str
    ) -> dict[str, Any]:
        """Calculate latency SLO compliance.

        Args:
            project: Project name
            target: Latency target in milliseconds
            window_days: Rolling window in days
            slo_type: Type of latency (p95 or p99)

        Returns:
            Latency compliance data
        """
        # Extract percentile from slo_type
        percentile = 95 if "p95" in slo_type else 99

        # Query latency histogram from Prometheus
        # In real implementation:
        # latency = histogram_quantile(percentile/100, rate(http_request_duration_seconds_bucket))

        # Mock implementation
        current_latency = 145.0  # milliseconds

        return {
            "current_value": current_latency,
            "target": target,
            "gap": current_latency - target,
            "percentile": f"p{percentile}",
            "compliance": current_latency <= target,
        }

    async def _calculate_error_rate_compliance(
        self, project: str, target: float, window_days: int
    ) -> dict[str, Any]:
        """Calculate error rate SLO compliance.

        Args:
            project: Project name
            target: Error rate target percentage
            window_days: Rolling window in days

        Returns:
            Error rate compliance data
        """
        # Query error rate from Prometheus
        # In real implementation:
        # error_rate = rate(http_requests_total{status=~"5.."}) / rate(http_requests_total)

        # Mock implementation
        current_error_rate = 0.08  # 0.08%

        return {
            "current_value": current_error_rate,
            "target": target,
            "gap": current_error_rate - target,
            "compliance": current_error_rate <= target,
        }

    def _calculate_error_budget(
        self,
        slo_type: str,
        target: float,
        compliance_data: dict,
        window_days: int,
    ) -> dict[str, Any]:
        """Calculate error budget status.

        Args:
            slo_type: Type of SLO
            target: SLO target
            compliance_data: Compliance calculation results
            window_days: Rolling window in days

        Returns:
            Error budget status dictionary
        """
        # Calculate allowed errors/misses based on target
        if slo_type == "availability":
            total = compliance_data.get("total_requests", 1)
            allowed_errors = total * (1 - target / 100)
            actual_errors = compliance_data.get("errors", 0)
        elif slo_type.startswith("latency"):
            # For latency, error budget is about time
            total_requests = 100000  # Mock
            allowed_latency_violations = total_requests * (1 - target / 100)
            actual_violations = 5000  # Mock
            allowed_errors = allowed_latency_violations
            actual_errors = actual_violations
        else:  # error_rate
            allowed_errors = target
            actual_errors = compliance_data.get("current_value", target)

        # Calculate budget
        total_budget = allowed_errors
        burned = actual_errors
        remaining = total_budget - burned
        remaining_percent = (remaining / total_budget * 100) if total_budget > 0 else 0

        # Calculate burn rate
        burned_percent = (burned / total_budget * 100) if total_budget > 0 else 0
        burn_rate_per_day = burned_percent / window_days
        days_until_exhausted = (
            int(remaining_percent / burn_rate_per_day) if burn_rate_per_day > 0 else 999
        )

        return {
            "total": total_budget,
            "burned": burned,
            "remaining": remaining,
            "remaining_percent": remaining_percent,
            "burned_percent": burned_percent,
            "burn_rate_percent": burn_rate_per_day,
            "days_until_exhausted": days_until_exhausted,
            "status": "healthy" if remaining_percent > 50 else "warning" if remaining_percent > 20 else "critical",
        }

    def _assess_breach_probability(
        self, compliance_data: dict, error_budget: dict
    ) -> dict[str, Any]:
        """Assess probability of SLO breach.

        Args:
            compliance_data: Compliance calculation results
            error_budget: Error budget status

        Returns:
            Breach probability assessment
        """
        # Simple heuristic-based probability assessment
        remaining_budget = error_budget.get("remaining_percent", 100)
        burn_rate = error_budget.get("burn_rate_percent", 0)

        # Calculate probability based on remaining budget and burn rate
        if remaining_budget < 10:
            probability = 0.9  # Very high risk
        elif remaining_budget < 25:
            probability = 0.7  # High risk
        elif remaining_budget < 50:
            probability = 0.4  # Medium risk
        elif burn_rate > 5:
            probability = 0.5  # Elevated risk due to high burn rate
        else:
            probability = 0.1  # Low risk

        return {
            "probability": probability,
            "risk_level": "critical" if probability > 0.7 else "high" if probability > 0.4 else "medium" if probability > 0.2 else "low",
            "factors": [
                f"Remaining budget: {remaining_budget:.1f}%",
                f"Burn rate: {burn_rate:.1f}%/day",
            ],
        }

    def _determine_status(
        self, compliance_data: dict, error_budget: dict
    ) -> str:
        """Determine overall SLO status.

        Args:
            compliance_data: Compliance data
            error_budget: Error budget status

        Returns:
            Status string
        """
        # Check if already breached
        if not compliance_data.get("compliance", True):
            return "breached"

        # Check error budget status
        budget_status = error_budget.get("status", "healthy")
        if budget_status == "critical":
            return "critical"
        elif budget_status == "warning":
            return "at_risk"
        else:
            return "healthy"

    def _calculate_confidence(self, compliance_data: dict) -> float:
        """Calculate confidence in the analysis.

        Args:
            compliance_data: Compliance calculation results

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence if we have valid data
        if compliance_data.get("current_value") is not None:
            confidence += 0.3

        # Increase confidence if we have gap analysis
        if "gap" in compliance_data:
            confidence += 0.1

        # Increase confidence if we have compliance status
        if "compliance" in compliance_data:
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_warnings(
        self, status: str, error_budget: dict, breach_probability: dict
    ) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            status: SLO status
            error_budget: Error budget status
            breach_probability: Breach probability assessment

        Returns:
            List of warning messages
        """
        warnings = []

        if status == "breached":
            warnings.append("SLO breach detected - immediate action required")

        if status == "critical":
            warnings.append(f"Error budget critical: {error_budget.get('remaining_percent', 0):.1f}% remaining")

        if status == "at_risk":
            warnings.append("SLO at risk of breach - preventive action recommended")

        if breach_probability.get("probability", 0) > 0.5:
            warnings.append(f"High breach probability: {breach_probability.get('probability', 0):.0%}")

        return warnings

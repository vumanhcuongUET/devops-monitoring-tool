"""Performance Circuit Breaker Health Skill.

Monitors circuit breaker states, trip patterns, recovery times,
and configuration recommendations for resilience patterns.
"""

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


# Circuit breaker states
class CircuitState(str):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerHealthSkill(BaseSkill):
    """Monitor circuit breaker states and health for resilience.

    This skill analyzes circuit breaker metrics to:
    - Track circuit state changes over time
    - Analyze trip frequency and patterns
    - Calculate recovery time metrics (MTTR)
    - Identify misconfigured thresholds
    - Recommend configuration adjustments

    Example usage:
        skill = CircuitBreakerHealthSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "service_name": "backend-api",
                "time_range_hours": 24
            }
        )
    """

    skill_id = "performance_circuit_breaker_health"
    name = "Performance Circuit Breaker Health"
    description = (
        "Monitor circuit breaker states, trip patterns, "
        "recovery times, and configuration recommendations."
    )
    category = SkillCategory.PERFORMANCE
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Default circuit breaker thresholds for recommendations
    DEFAULT_THRESHOLDS = {
        "failure_threshold": 5,        # Failures before opening
        "failure_rate_threshold": 0.5,  # 50% failure rate
        "success_threshold": 2,       # Successes to close circuit
        "timeout_ms": 30000,          # 30 second timeout
        "half_open_max_calls": 3,     # Max calls in half-open state
        "reset_timeout_ms": 60000,    # 1 minute before attempting recovery
    }

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the circuit breaker health skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        # In real implementation, this would connect to metrics backend
        self.metrics_client = None

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run circuit breaker health analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - service_name: Specific service to analyze (optional)
                - time_range_hours: Time range for analysis (default: 24)
                - include_recommendations: Include config recommendations (default: True)
            context: Additional context from registry

        Returns:
            AnalysisResult with circuit breaker health data
        """
        try:
            # Extract parameters
            service_name = parameters.get("service_name", project)
            time_range_hours = parameters.get("time_range_hours", 24)
            include_recommendations = parameters.get("include_recommendations", True)

            # Query circuit breaker metrics
            cb_metrics = await self._query_circuit_breaker_metrics(
                project=project,
                service_name=service_name,
                time_range_hours=time_range_hours,
            )

            # Analyze circuit breaker health
            analysis = await self._analyze_circuit_breaker_health(
                metrics=cb_metrics,
                service_name=service_name,
                include_recommendations=include_recommendations,
            )

            # Calculate confidence based on data quality
            confidence = self._calculate_confidence(cb_metrics, analysis)

            # Generate warnings for critical issues
            warnings = self._generate_warnings(analysis)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=analysis,
                warnings=warnings,
                metadata={
                    "project": project,
                    "service_name": service_name,
                    "time_range_hours": time_range_hours,
                    "circuits_analyzed": len(cb_metrics.get("circuits", [])),
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
        """Generate recommendations based on circuit breaker analysis.

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

        # Check for frequently tripping circuits
        circuit_states = data.get("circuit_states", [])
        frequent_trippers = [
            c for c in circuit_states
            if c.get("trip_count", 0) > 5
        ]
        if frequent_trippers:
            for circuit in frequent_trippers:
                recommendations.append(
                    Recommendation(
                        title=f"Frequently Tripping Circuit: {circuit['name']}",
                        description=(
                            f"Circuit '{circuit['name']}' has tripped "
                            f"{circuit['trip_count']} times in the analysis period. "
                            f"This indicates downstream service instability."
                        ),
                        priority=SkillPriority.HIGH,
                        action_type="investigate",
                        estimated_effort="1-2 days",
                        risk_level="high",
                        commands=[
                            f"Check {circuit['service']} health",
                            "Review error logs",
                            "Consider increasing timeout thresholds",
                            "Add fallback mechanisms",
                        ],
                        references=[
                            "https://martinfowler.com/bliki/CircuitBreaker.html",
                            "https://resilience4j.readme.io/docs/circuitbreaker",
                        ],
                    )
                )

        # Check for stuck open circuits
        stuck_open = [
            c for c in circuit_states
            if c.get("current_state") == CircuitState.OPEN
            and c.get("time_in_current_state_minutes", 0) > 30
        ]
        if stuck_open:
            for circuit in stuck_open:
                recommendations.append(
                    Recommendation(
                        title=f"Circuit Stuck Open: {circuit['name']}",
                        description=(
                            f"Circuit '{circuit['name']}' has been open for "
                            f"{circuit['time_in_current_state_minutes']:.0f} minutes. "
                            f"Downstream service may be down or misconfigured."
                        ),
                        priority=SkillPriority.CRITICAL,
                        action_type="urgent",
                        estimated_effort="1-4 hours",
                        risk_level="critical",
                        commands=[
                            f"Check {circuit['service']} availability",
                            "Review downstream service logs",
                            "Verify network connectivity",
                            "Consider manual circuit reset if safe",
                        ],
                    )
                )

        # Check for configuration issues
        config_review = data.get("configuration_review", {})
        if config_review.get("issues"):
            for issue in config_review["issues"]:
                recommendations.append(
                    Recommendation(
                        title="Circuit Breaker Configuration Issue",
                        description=issue["description"],
                        priority=SkillPriority.MEDIUM,
                        action_type="configure",
                        estimated_effort="30 minutes",
                        risk_level="low",
                        commands=issue.get("suggested_commands", []),
                    )
                )

        # Check MTTR
        recovery_analysis = data.get("recovery_analysis", {})
        avg_mttr = recovery_analysis.get("avg_mttr_minutes", 0)
        if avg_mttr > 10:  # More than 10 minutes average recovery
            recommendations.append(
                Recommendation(
                    title="High Mean Time To Recovery (MTTR)",
                    description=(
                        f"Average recovery time is {avg_mttr:.1f} minutes. "
                        f"Consider improving recovery automation and alerting."
                    ),
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="medium",
                    commands=[
                        "Review alerting for circuit trips",
                        "Automate downstream service recovery",
                        "Improve monitoring and visibility",
                        "Consider adding health check endpoints",
                    ],
                )
            )

        # Check for circuits without proper half-open behavior
        half_open_issues = [
            c for c in circuit_states
            if not c.get("has_half_open_state", True)
        ]
        if half_open_issues:
            recommendations.append(
                Recommendation(
                    title="Circuit Breakers Missing Half-Open State",
                    description=(
                        f"{len(half_open_issues)} circuits lack proper half-open state, "
                        f"preventing graceful recovery testing."
                    ),
                    priority=SkillPriority.LOW,
                    action_type="implement",
                    estimated_effort="1-2 days",
                    risk_level="low",
                    commands=[
                        "Implement half-open state transition",
                        "Add success threshold for closing circuit",
                        "Test recovery behavior",
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

        # Validate time_range_hours
        time_range = parameters.get("time_range_hours", 24)
        if not isinstance(time_range, (int, float)) or time_range <= 0:
            errors.append("time_range_hours must be a positive number")

        return len(errors) == 0, errors

    async def _query_circuit_breaker_metrics(
        self,
        project: str,
        service_name: str,
        time_range_hours: int,
    ) -> dict[str, Any]:
        """Query circuit breaker metrics from monitoring system.

        Args:
            project: Project name
            service_name: Service name
            time_range_hours: Time range in hours

        Returns:
            Dictionary with circuit breaker metrics
        """
        # In real implementation, this would query Prometheus/metrics backend
        # For now, return mock data
        now = datetime.now(timezone.utc)

        return {
            "circuits": [
                {
                    "name": "backend-api-circuit",
                    "service": service_name,
                    "current_state": CircuitState.CLOSED,
                    "state_transitions": [
                        {
                            "from_state": CircuitState.CLOSED,
                            "to_state": CircuitState.OPEN,
                            "timestamp": now,
                            "reason": "failure_threshold_exceeded",
                        },
                        {
                            "from_state": CircuitState.OPEN,
                            "to_state": CircuitState.HALF_OPEN,
                            "timestamp": now,
                            "reason": "reset_timeout",
                        },
                        {
                            "from_state": CircuitState.HALF_OPEN,
                            "to_state": CircuitState.CLOSED,
                            "timestamp": now,
                            "reason": "success_threshold_met",
                        },
                    ],
                    "config": {
                        "failure_threshold": 5,
                        "failure_rate_threshold": 0.5,
                        "success_threshold": 2,
                        "timeout_ms": 30000,
                        "reset_timeout_ms": 60000,
                    },
                    "metrics": {
                        "total_requests": 10000,
                        "successful_requests": 9500,
                        "failed_requests": 500,
                        "rejected_requests": 25,
                        "current_failure_rate": 0.05,
                    },
                },
                {
                    "name": "database-circuit",
                    "service": f"{service_name}-db",
                    "current_state": CircuitState.OPEN,
                    "state_transitions": [
                        {
                            "from_state": CircuitState.CLOSED,
                            "to_state": CircuitState.OPEN,
                            "timestamp": now,
                            "reason": "failure_rate_exceeded",
                        },
                    ],
                    "config": {
                        "failure_threshold": 3,
                        "failure_rate_threshold": 0.6,
                        "success_threshold": 1,
                        "timeout_ms": 5000,
                        "reset_timeout_ms": 30000,
                    },
                    "metrics": {
                        "total_requests": 5000,
                        "successful_requests": 4000,
                        "failed_requests": 1000,
                        "rejected_requests": 150,
                        "current_failure_rate": 0.2,
                    },
                },
                {
                    "name": "external-api-circuit",
                    "service": "external-payment-api",
                    "current_state": CircuitState.CLOSED,
                    "state_transitions": [],
                    "config": {
                        "failure_threshold": 10,
                        "failure_rate_threshold": 0.3,
                        "success_threshold": 3,
                        "timeout_ms": 60000,
                        "reset_timeout_ms": 120000,
                    },
                    "metrics": {
                        "total_requests": 2000,
                        "successful_requests": 1950,
                        "failed_requests": 50,
                        "rejected_requests": 0,
                        "current_failure_rate": 0.025,
                    },
                },
            ],
            "queried_successfully": True,
        }

    async def _analyze_circuit_breaker_health(
        self,
        metrics: dict[str, Any],
        service_name: str,
        include_recommendations: bool,
    ) -> dict[str, Any]:
        """Analyze circuit breaker metrics for health insights.

        Args:
            metrics: Raw circuit breaker metrics
            service_name: Service being analyzed
            include_recommendations: Whether to include config recommendations

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "service_name": service_name,
            "queried_successfully": metrics.get("queried_successfully", False),
        }

        circuits = metrics.get("circuits", [])
        if not circuits:
            return analysis

        # Analyze circuit states
        analysis["circuit_states"] = self._analyze_circuit_states(circuits)

        # Analyze trip patterns
        analysis["trip_patterns"] = self._analyze_trip_patterns(circuits)

        # Analyze recovery metrics
        analysis["recovery_analysis"] = self._analyze_recovery(circuits)

        # Configuration review
        if include_recommendations:
            analysis["configuration_review"] = self._review_configurations(circuits)

        # Overall health score
        analysis["overall_health_score"] = self._calculate_health_score(circuits)

        return analysis

    def _analyze_circuit_states(self, circuits: list) -> list[dict]:
        """Analyze current circuit states.

        Args:
            circuits: List of circuit data

        Returns:
            List of circuit state analysis
        """
        state_analysis = []

        for circuit in circuits:
            current_state = circuit.get("current_state")
            transitions = circuit.get("state_transitions", [])

            # Count trips (transitions to OPEN state)
            trip_count = sum(
                1 for t in transitions
                if t.get("to_state") == CircuitState.OPEN
            )

            # Calculate time in current state
            now = datetime.now(timezone.utc)
            time_in_current_state = 0
            if transitions:
                # Find most recent transition
                latest_transition = max(
                    [t for t in transitions if t.get("timestamp")],
                    key=lambda t: t.get("timestamp", datetime.min),
                    default=None,
                )
                if latest_transition:
                    time_diff = now - latest_transition.get("timestamp", now)
                    time_in_current_state = time_diff.total_seconds() / 60  # minutes

            # Check if circuit has proper half-open behavior
            has_half_open = any(
                t.get("to_state") == CircuitState.HALF_OPEN
                for t in transitions
            )

            state_analysis.append({
                "name": circuit["name"],
                "service": circuit["service"],
                "current_state": current_state,
                "trip_count": trip_count,
                "time_in_current_state_minutes": time_in_current_state,
                "has_half_open_state": has_half_open,
                "health_status": self._get_circuit_health_status(current_state, trip_count),
            })

        return state_analysis

    def _get_circuit_health_status(self, state: str, trip_count: int) -> str:
        """Determine health status based on state and trip count.

        Args:
            state: Current circuit state
            trip_count: Number of trips

        Returns:
            Health status: healthy, degraded, unhealthy, or critical
        """
        if state == CircuitState.OPEN:
            return "critical"
        elif state == CircuitState.HALF_OPEN:
            return "degraded"
        elif trip_count > 5:
            return "unhealthy"
        elif trip_count > 2:
            return "degraded"
        return "healthy"

    def _analyze_trip_patterns(self, circuits: list) -> dict:
        """Analyze circuit trip patterns.

        Args:
            circuits: List of circuit data

        Returns:
            Trip pattern analysis
        """
        total_trips = 0
        trip_reasons = {}
        trip_frequencies = {}

        for circuit in circuits:
            transitions = circuit.get("state_transitions", [])
            circuit_trips = [
                t for t in transitions
                if t.get("to_state") == CircuitState.OPEN
            ]
            total_trips += len(circuit_trips)

            # Count by reason
            for trip in circuit_trips:
                reason = trip.get("reason", "unknown")
                trip_reasons[reason] = trip_reasons.get(reason, 0) + 1

            # Track frequency per circuit
            trip_frequencies[circuit["name"]] = len(circuit_trips)

        return {
            "total_trips": total_trips,
            "most_common_reason": max(trip_reasons, key=trip_reasons.get) if trip_reasons else None,
            "reason_distribution": trip_reasons,
            "trip_frequency_by_circuit": trip_frequencies,
        }

    def _analyze_recovery(self, circuits: list) -> dict:
        """Analyze recovery metrics.

        Args:
            circuits: List of circuit data

        Returns:
            Recovery analysis with MTTR metrics
        """
        recovery_times = []
        successful_recoveries = 0

        for circuit in circuits:
            transitions = circuit.get("state_transitions", [])
            i = 0
            while i < len(transitions):
                # Find OPEN -> HALF_OPEN -> CLOSED pattern
                if transitions[i].get("to_state") == CircuitState.OPEN:
                    open_time = transitions[i].get("timestamp")

                    # Look for subsequent recovery
                    for j in range(i + 1, len(transitions)):
                        if transitions[j].get("to_state") == CircuitState.CLOSED:
                            close_time = transitions[j].get("timestamp")
                            if open_time and close_time:
                                mttr_minutes = (close_time - open_time).total_seconds() / 60
                                recovery_times.append(mttr_minutes)
                                successful_recoveries += 1
                            break
                i += 1

        avg_mttr = sum(recovery_times) / len(recovery_times) if recovery_times else 0
        max_mttr = max(recovery_times) if recovery_times else 0
        min_mttr = min(recovery_times) if recovery_times else 0

        return {
            "total_recoveries": successful_recoveries,
            "avg_mttr_minutes": avg_mttr,
            "max_mttr_minutes": max_mttr,
            "min_mttr_minutes": min_mttr,
            "recovery_rate": successful_recoveries / len(circuits) if circuits else 1.0,
        }

    def _review_configurations(self, circuits: list) -> dict:
        """Review circuit breaker configurations.

        Args:
            circuits: List of circuit data

        Returns:
            Configuration review with issues and recommendations
        """
        issues = []

        for circuit in circuits:
            config = circuit.get("config", {})
            _metrics = circuit.get("metrics", {})

            # Check failure threshold
            failure_threshold = config.get("failure_threshold", self.DEFAULT_THRESHOLDS["failure_threshold"])
            if failure_threshold < 3:
                issues.append({
                    "circuit": circuit["name"],
                    "severity": "low",
                    "type": "too_sensitive",
                    "description": (
                        f"Failure threshold of {failure_threshold} may be too low, "
                        f"causing unnecessary trips during temporary issues."
                    ),
                    "suggested_commands": [
                        f"Consider increasing failure_threshold to 5-10 for {circuit['name']}",
                    ],
                })
            elif failure_threshold > 20:
                issues.append({
                    "circuit": circuit["name"],
                    "severity": "medium",
                    "type": "too_lenient",
                    "description": (
                        f"Failure threshold of {failure_threshold} may be too high, "
                        f"allowing too many failures before tripping."
                    ),
                    "suggested_commands": [
                        f"Consider reducing failure_threshold to 5-10 for {circuit['name']}",
                    ],
                })

            # Check timeout
            timeout_ms = config.get("timeout_ms", self.DEFAULT_THRESHOLDS["timeout_ms"])
            if timeout_ms < 5000:
                issues.append({
                    "circuit": circuit["name"],
                    "severity": "medium",
                    "type": "timeout_too_low",
                    "description": (
                        f"Timeout of {timeout_ms}ms may be too short for {circuit['service']}, "
                        f"causing premature failures."
                    ),
                    "suggested_commands": [
                        f"Review and potentially increase timeout for {circuit['name']}",
                    ],
                })

            # Check reset timeout
            reset_timeout = config.get("reset_timeout_ms", self.DEFAULT_THRESHOLDS["reset_timeout_ms"])
            if reset_timeout < 30000:
                issues.append({
                    "circuit": circuit["name"],
                    "severity": "low",
                    "type": "reset_too_fast",
                    "description": (
                        f"Reset timeout of {reset_timeout}ms may be too short, "
                        f"not allowing enough time for service recovery."
                    ),
                    "suggested_commands": [
                        f"Consider increasing reset_timeout_ms to 60000+ for {circuit['name']}",
                    ],
                })

            # Check if failure rate threshold is appropriate
            failure_rate = config.get("failure_rate_threshold", self.DEFAULT_THRESHOLDS["failure_rate_threshold"])
            if failure_rate > 0.8:
                issues.append({
                    "circuit": circuit["name"],
                    "severity": "medium",
                    "type": "failure_rate_too_high",
                    "description": (
                        f"Failure rate threshold of {failure_rate:.0%} allows too many failures "
                        f"before tripping the circuit."
                    ),
                    "suggested_commands": [
                        f"Consider reducing failure_rate_threshold to 30-50% for {circuit['name']}",
                    ],
                })

        return {
            "total_issues": len(issues),
            "issues": issues,
        }

    def _calculate_health_score(self, circuits: list) -> dict:
        """Calculate overall circuit breaker health score.

        Args:
            circuits: List of circuit data

        Returns:
            Health score with breakdown
        """
        if not circuits:
            return {"score": 0, "status": "unknown"}

        total_circuits = len(circuits)
        healthy_circuits = sum(
            1 for c in circuits
            if c.get("current_state") == CircuitState.CLOSED
        )
        open_circuits = total_circuits - healthy_circuits

        # Calculate score (0-100)
        base_score = 100
        deduction_per_open = 25
        score = max(0, base_score - (open_circuits * deduction_per_open))

        # Determine status
        if score >= 80:
            status = "healthy"
        elif score >= 50:
            status = "degraded"
        elif score >= 25:
            status = "unhealthy"
        else:
            status = "critical"

        return {
            "score": score,
            "status": status,
            "total_circuits": total_circuits,
            "healthy_circuits": healthy_circuits,
            "open_circuits": open_circuits,
        }

    def _calculate_confidence(self, metrics: dict, analysis: dict) -> float:
        """Calculate confidence score based on data quality.

        Args:
            metrics: Raw metrics data
            analysis: Processed analysis

        Returns:
            Confidence score between 0 and 1
        """
        base_confidence = 0.5

        # Increase confidence if query was successful
        if metrics.get("queried_successfully"):
            base_confidence += 0.3

        # Increase confidence based on number of circuits
        circuit_count = len(metrics.get("circuits", []))
        if circuit_count >= 3:
            base_confidence += 0.2
        elif circuit_count >= 1:
            base_confidence += 0.1

        return min(base_confidence, 1.0)

    def _generate_warnings(self, analysis: dict) -> list[str]:
        """Generate warnings based on analysis results.

        Args:
            analysis: Analysis results

        Returns:
            List of warning messages
        """
        warnings = []

        # Check circuit states
        circuit_states = analysis.get("circuit_states", [])
        open_circuits = [c for c in circuit_states if c.get("current_state") == CircuitState.OPEN]
        if open_circuits:
            warnings.append(
                f"{len(open_circuits)} circuit(s) currently OPEN: "
                f"{', '.join([c['name'] for c in open_circuits])}"
            )

        # Check trip patterns
        trip_patterns = analysis.get("trip_patterns", {})
        total_trips = trip_patterns.get("total_trips", 0)
        if total_trips > 10:
            warnings.append(f"High trip count: {total_trips} trips in analysis period")

        # Check health score
        health_score = analysis.get("overall_health_score", {})
        if health_score.get("score", 100) < 50:
            warnings.append(f"Low health score: {health_score['score']}/100")

        # Check configuration issues
        config_review = analysis.get("configuration_review", {})
        if config_review.get("total_issues", 0) > 3:
            warnings.append(
                f"Multiple configuration issues: {config_review['total_issues']} found"
            )

        return warnings

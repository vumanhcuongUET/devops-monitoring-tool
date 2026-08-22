"""Reliability Scaling Analyzer Skill.

Analyzes HPA and scaling effectiveness, under/over-provisioning,
and provides cost optimization recommendations.
"""

import logging
from typing import Any, Optional

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


class ScalingAnalyzerSkill(BaseSkill):
    """Analyze HPA and scaling effectiveness.

    This skill analyzes:
    - Scaling event timeline
    - HPA effectiveness score
    - Under/over-provisioning analysis
    - Cost optimization recommendations

    Example usage:
        skill = ScalingAnalyzerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "deployment": "backend",
                "namespace": "production",
                "time_range_days": 7
            }
        )
    """

    skill_id = "reliability_scaling_analyzer"
    name = "Reliability Scaling Analyzer"
    description = (
        "Analyze HPA effectiveness, scaling patterns, and cost optimization "
        "for Kubernetes deployments."
    )
    category = SkillCategory.RELIABILITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the scaling analyzer skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        self.prometheus_client = PrometheusClient()

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run scaling analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - deployment: Deployment name (required)
                - namespace: Kubernetes namespace (default: default)
                - time_range_days: Time range for analysis (default: 7)
            context: Additional context from registry

        Returns:
            AnalysisResult with scaling analysis data
        """
        try:
            # Extract parameters
            deployment = parameters.get("deployment")
            if not deployment:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Parameter 'deployment' is required"],
                    metadata={"project": project},
                )

            namespace = parameters.get("namespace", "default")
            time_range_days = parameters.get("time_range_days", 7)

            # Get HPA configuration
            hpa_config = await self._get_hpa_config(deployment, namespace)

            # Get scaling events
            scaling_events = await self._get_scaling_events(
                deployment, namespace, time_range_days
            )

            # Analyze utilization
            utilization = await self._analyze_utilization(deployment, namespace)

            # Calculate effectiveness score
            effectiveness = self._calculate_effectiveness(
                hpa_config, scaling_events, utilization
            )

            # Analyze provisioning
            provisioning = self._analyze_provisioning(
                hpa_config, scaling_events, utilization
            )

            # Cost optimization
            cost_analysis = self._calculate_cost_savings(provisioning)

            # Calculate confidence
            confidence = self._calculate_confidence(
                hpa_config, scaling_events, utilization
            )

            # Generate warnings
            warnings = self._generate_warnings(effectiveness, provisioning)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "deployment": deployment,
                    "namespace": namespace,
                    "time_range_days": time_range_days,
                    "hpa_config": hpa_config,
                    "scaling_events": scaling_events,
                    "utilization": utilization,
                    "effectiveness": effectiveness,
                    "provisioning": provisioning,
                    "cost_analysis": cost_analysis,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "deployment": deployment,
                    "namespace": namespace,
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
        """Generate recommendations based on scaling analysis.

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
        effectiveness = data.get("effectiveness", {})
        provisioning = data.get("provisioning", {})
        cost_analysis = data.get("cost_analysis", {})
        hpa_config = data.get("hpa_config", {})

        # Critical: Hit max replicas frequently
        if provisioning.get("at_max_percent", 0) > 20:
            recommendations.append(
                Recommendation(
                    title="Increase HPA Max Replicas",
                    description=f"Deployment hit max replicas {provisioning.get('at_max_percent', 0)}% "
                    f"of the time. Current max: {hpa_config.get('max_replicas', 10)}",
                    priority=SkillPriority.HIGH,
                    action_type="scale",
                    estimated_effort="5 minutes",
                    risk_level="medium",
                    commands=[
                        f"kubectl edit hpa {data.get('deployment')} -n {data.get('namespace')}",
                        "Increase max_replicas to handle peak load",
                        "Consider adding custom metrics for scaling",
                    ],
                )
            )

        # High: At min replicas most of the time
        if provisioning.get("at_min_percent", 0) > 70:
            recommendations.append(
                Recommendation(
                    title="Decrease HPA Min Replicas",
                    description=f"Deployment runs at min replicas {provisioning.get('at_min_percent', 0)}% "
                    f"of the time. Potential cost savings: ${cost_analysis.get('potential_savings', 0):.2f}/month",
                    priority=SkillPriority.MEDIUM,
                    action_type="optimize",
                    estimated_effort="5 minutes",
                    risk_level="low",
                    commands=[
                        f"kubectl edit hpa {data.get('deployment')} -n {data.get('namespace')}",
                        "Decrease min_replicas to save resources",
                        "Ensure burst capacity is adequate",
                    ],
                )
            )

        # Medium: Ineffective scaling
        if effectiveness.get("score", 100) < 60:
            recommendations.append(
                Recommendation(
                    title="Improve HPA Effectiveness",
                    description=f"HPA effectiveness score is {effectiveness.get('score', 0):.0f}/100. "
                    f"Scaling is not responding to demand properly.",
                    priority=SkillPriority.MEDIUM,
                    action_type="configure",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Review HPA metrics and thresholds",
                        "Adjust target utilization percentages",
                        "Consider adding custom metrics",
                        "Add stabilization windows if scaling too frequently",
                    ],
                )
            )

        # Medium: High scaling frequency
        scaling_events = data.get("scaling_events", {})
        if scaling_events.get("total_events", 0) > 50:
            recommendations.append(
                Recommendation(
                    title="Reduce HPA Scaling Frequency",
                    description=f"HPA scaled {scaling_events.get('total_events', 0)} times in "
                    f"{data.get('time_range_days', 7)} days. This may cause instability.",
                    priority=SkillPriority.MEDIUM,
                    action_type="configure",
                    estimated_effort="30 minutes",
                    risk_level="medium",
                    commands=[
                        "Add stabilization window (e.g., 300s)",
                        "Increase thresholds to avoid flapping",
                        "Review metric selection",
                    ],
                )
            )

        # Low: Resource optimization
        utilization = data.get("utilization", {})
        if utilization.get("cpu", 0) < 30 and utilization.get("memory", 0) < 50:
            recommendations.append(
                Recommendation(
                    title="Right-Size Deployment Resources",
                    description=f"Low resource utilization: CPU {utilization.get('cpu', 0)}%, "
                    f"Memory {utilization.get('memory', 0)}%. Consider reducing requests/limits.",
                    priority=SkillPriority.LOW,
                    action_type="optimize",
                    estimated_effort="1-2 hours",
                    risk_level="low",
                    commands=[
                        "Review resource requirements in deployment",
                        "Reduce CPU/memory requests based on actual usage",
                        "Test with lower limits in staging",
                    ],
                )
            )

        # Cost optimization
        if cost_analysis.get("potential_savings", 0) > 50:
            recommendations.append(
                Recommendation(
                    title="Optimize Cluster Resource Costs",
                    description=f"Potential monthly savings: ${cost_analysis.get('potential_savings', 0):.2f} "
                    f"through right-sizing and HPA optimization.",
                    priority=SkillPriority.MEDIUM,
                    action_type="optimize",
                    estimated_effort="2-4 hours",
                    risk_level="low",
                    commands=[
                        "Review all deployment resource requests",
                        "Implement recommended HPA changes",
                        "Consider using Cluster Autoscaler",
                        "Use spot/preemptible instances for workloads",
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

        # Validate deployment is required
        if not parameters.get("deployment"):
            errors.append("Parameter 'deployment' is required")

        # Validate namespace
        namespace = parameters.get("namespace", "default")
        if not isinstance(namespace, str) or not namespace:
            errors.append("namespace must be a non-empty string")

        # Validate time_range_days
        time_range = parameters.get("time_range_days", 7)
        if not isinstance(time_range, int) or time_range < 1:
            errors.append("time_range_days must be a positive integer")

        return len(errors) == 0, errors

    async def _get_hpa_config(
        self, deployment: str, namespace: str
    ) -> dict[str, Any]:
        """Get HPA configuration from Kubernetes.

        Args:
            deployment: Deployment name
            namespace: Kubernetes namespace

        Returns:
            HPA configuration dictionary
        """
        # In real implementation, query Kubernetes API:
        # hpa = await k8s_client.get_horizontal_pod_autoscaler(deployment, namespace)

        # Mock implementation
        return {
            "name": f"{deployment}-hpa",
            "deployment": deployment,
            "namespace": namespace,
            "min_replicas": 2,
            "max_replicas": 10,
            "target_cpu_utilization": 70,
            "target_memory_utilization": 80,
            "metrics": ["cpu", "memory"],
            "stabilization_window_seconds": 0,
        }

    async def _get_scaling_events(
        self, deployment: str, namespace: str, time_range_days: int
    ) -> dict[str, Any]:
        """Get scaling event history.

        Args:
            deployment: Deployment name
            namespace: Kubernetes namespace
            time_range_days: Time range in days

        Returns:
            Scaling events dictionary
        """
        # In real implementation, query Kubernetes HPA metrics:
        # events = await k8s_client.get_hpa_events(deployment, namespace, time_range_days)

        # Mock implementation
        return {
            "total_events": 48,
            "scale_up_events": 23,
            "scale_down_events": 25,
            "average_scale_time_seconds": 45,
            "events_by_day": [
                {"day": "2026-08-15", "up": 5, "down": 4},
                {"day": "2026-08-16", "up": 6, "down": 5},
                {"day": "2026-08-17", "up": 3, "down": 4},
            ],
        }

    async def _analyze_utilization(
        self, deployment: str, namespace: str
    ) -> dict[str, Any]:
        """Analyze current resource utilization.

        Args:
            deployment: Deployment name
            namespace: Kubernetes namespace

        Returns:
            Utilization analysis dictionary
        """
        try:
            cpu = await self.prometheus_client.get_cpu_percent()
            memory = await self.prometheus_client.get_memory_percent()

            return {
                "cpu": cpu,
                "memory": memory,
                "average_replicas": 5,
                "peak_replicas": 8,
                "min_replicas_seen": 2,
            }
        except Exception as e:
            logger.warning(f"Utilization analysis failed: {e}")
            return {"cpu": 0, "memory": 0, "average_replicas": 0}

    def _calculate_effectiveness(
        self, hpa_config: dict, scaling_events: dict, utilization: dict
    ) -> dict[str, Any]:
        """Calculate HPA effectiveness score.

        Args:
            hpa_config: HPA configuration
            scaling_events: Scaling events data
            utilization: Utilization data

        Returns:
            Effectiveness analysis dictionary
        """
        score = 100.0
        issues = []

        # Deduct for hitting limits too frequently
        at_max_count = 0
        at_min_count = 0

        # Calculate time at min/max (would be in real scaling events)
        for day_events in scaling_events.get("events_by_day", []):
            # Mock calculation
            pass

        # Mock logic for scoring
        total_events = scaling_events.get("total_events", 0)
        scale_up = scaling_events.get("scale_up_events", 0)
        scale_down = scaling_events.get("scale_down_events", 0)

        # Good: balanced scaling
        if abs(scale_up - scale_down) / max(total_events, 1) < 0.3:
            score += 10
        else:
            issues.append("Imbalanced scaling pattern")

        # Deduct for excessive scaling
        if total_events > 100:
            score -= 20
            issues.append("Excessive scaling events")

        # Deduct for no scaling
        if total_events == 0:
            score -= 50
            issues.append("No scaling events detected")

        # Deduct for low utilization
        if utilization.get("cpu", 0) < 30:
            score -= 15
            issues.append("Low CPU utilization")

        return {
            "score": max(0, min(100, score)),
            "issues": issues,
            "status": "effective" if score >= 70 else "ineffective" if score >= 40 else "poor",
        }

    def _analyze_provisioning(
        self, hpa_config: dict, scaling_events: dict, utilization: dict
    ) -> dict[str, Any]:
        """Analyze provisioning state.

        Args:
            hpa_config: HPA configuration
            scaling_events: Scaling events
            utilization: Utilization data

        Returns:
            Provisioning analysis dictionary
        """
        min_replicas = hpa_config.get("min_replicas", 1)
        max_replicas = hpa_config.get("max_replicas", 10)
        avg_replicas = utilization.get("average_replicas", min_replicas)
        peak_replicas = utilization.get("peak_replicas", min_replicas)

        # Calculate time at min/max (simplified)
        range_size = max_replicas - min_replicas
        if range_size > 0:
            at_min_percent = ((avg_replicas - min_replicas) / range_size) * 100
            at_max_percent = ((max_replicas - peak_replicas) / range_size) * 100
        else:
            at_min_percent = 0
            at_max_percent = 0

        return {
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
            "average_replicas": avg_replicas,
            "peak_replicas": peak_replicas,
            "at_min_percent": at_min_percent,
            "at_max_percent": at_max_percent,
            "status": "under_provisioned"
            if at_max_percent > 20
            else "over_provisioned"
            if at_min_percent > 70
            else "optimal",
        }

    def _calculate_cost_savings(self, provisioning: dict) -> dict[str, float]:
        """Calculate potential cost savings.

        Args:
            provisioning: Provisioning analysis

        Returns:
            Cost analysis dictionary
        """
        # Simplified cost calculation
        # In real implementation, would use actual instance costs

        monthly_cost_per_instance = 30  # Mock: $30/month per instance
        avg_replicas = provisioning.get("average_replicas", 1)

        # Potential savings from right-sizing
        if provisioning.get("status") == "over_provisioned":
            excess_replicas = avg_replicas - provisioning.get("min_replicas", 1)
            potential_savings = excess_replicas * monthly_cost_per_instance * 30
        else:
            potential_savings = 0

        return {
            "potential_savings": potential_savings,
            "monthly_cost": avg_replicas * monthly_cost_per_instance * 30,
            "savings_percent": (potential_savings / (avg_replicas * monthly_cost_per_instance * 30) * 100)
            if avg_replicas > 0
            else 0,
        }

    def _calculate_confidence(
        self, hpa_config: dict, scaling_events: dict, utilization: dict
    ) -> float:
        """Calculate confidence in the analysis.

        Args:
            hpa_config: HPA configuration
            scaling_events: Scaling events
            utilization: Utilization data

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with HPA config
        if hpa_config and hpa_config.get("name"):
            confidence += 0.2

        # Increase confidence with scaling events
        if scaling_events.get("total_events", 0) > 0:
            confidence += 0.2

        # Increase confidence with utilization data
        if utilization.get("cpu", 0) > 0 or utilization.get("memory", 0) > 0:
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_warnings(
        self, effectiveness: dict, provisioning: dict
    ) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            effectiveness: Effectiveness analysis
            provisioning: Provisioning analysis

        Returns:
            List of warning messages
        """
        warnings = []

        if effectiveness.get("score", 100) < 60:
            warnings.append(f"Low HPA effectiveness score: {effectiveness.get('score', 0):.0f}/100")

        if provisioning.get("status") == "under_provisioned":
            warnings.append(f"Deployment at max replicas {provisioning.get('at_max_percent', 0):.0f}% of time")

        if provisioning.get("status") == "over_provisioned":
            warnings.append(f"Deployment at min replicas {provisioning.get('at_min_percent', 0):.0f}% of time")

        return warnings

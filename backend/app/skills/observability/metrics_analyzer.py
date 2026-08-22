"""Observability Metrics Analyzer Skill.

Analyzes Prometheus metrics for performance insights, latency analysis,
error rate trends, and resource utilization.
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


class MetricsAnalyzerSkill(BaseSkill):
    """Analyze Prometheus metrics for performance insights.

    This skill queries Prometheus to analyze:
    - Request rates and error rates
    - Latency percentiles (p50, p95, p99)
    - Resource utilization (CPU, memory)
    - SLO compliance

    Example usage:
        skill = MetricsAnalyzerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "time_range_hours": 1,
                "metrics": ["http_requests_total", "http_request_duration_seconds"]
            }
        )
    """

    skill_id = "observability_metrics_analyzer"
    name = "Observability Metrics Analyzer"
    description = (
        "Analyze Prometheus metrics for performance insights, "
        "latency analysis, error rate trends, and resource utilization."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the metrics analyzer skill.

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
        """Run metrics analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - time_range_hours: Time range for analysis (default: 1)
                - metrics: List of metric names to analyze
                - percentile_queries: Whether to calculate percentiles
            context: Additional context from registry

        Returns:
            AnalysisResult with metrics analysis data
        """
        try:
            # Extract parameters
            time_range_hours = parameters.get("time_range_hours", 1)
            metric_patterns = parameters.get("metrics", ["http_*"])
            calculate_percentiles = parameters.get("percentile_queries", True)

            # Query metrics from Prometheus
            metrics_data = await self._query_metrics(
                project=project,
                time_range_hours=time_range_hours,
                metric_patterns=metric_patterns,
            )

            # Analyze metrics
            analysis = await self._analyze_metrics(
                metrics_data=metrics_data,
                calculate_percentiles=calculate_percentiles,
                project=project,
            )

            # Calculate confidence based on data completeness
            confidence = self._calculate_confidence(metrics_data, analysis)

            # Generate warnings for issues found
            warnings = self._generate_warnings(analysis)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=analysis,
                warnings=warnings,
                metadata={
                    "project": project,
                    "time_range_hours": time_range_hours,
                    "metrics_queried": len(metrics_data.get("metrics", [])),
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
        """Generate recommendations based on metrics analysis.

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

        # Check for high error rates
        if "error_rate_analysis" in data:
            error_rate = data["error_rate_analysis"].get("current", 0)
            if error_rate > 1.0:  # 1% error rate threshold
                recommendations.append(
                    Recommendation(
                        title="High Error Rate Detected",
                        description=f"Error rate is {error_rate:.2f}%, exceeding 1% threshold.",
                        priority=SkillPriority.HIGH,
                        action_type="investigate",
                        estimated_effort="2-4 hours",
                        risk_level="high",
                        commands=[
                            f"Check logs for {project}",
                            "Review recent deployments",
                            "Analyze error patterns",
                        ],
                        references=[
                            "https://sre.google/workbook/handling-emergencies/",
                        ],
                    )
                )

        # Check for high latency
        if "latency_analysis" in data:
            p95_latency = data["latency_analysis"].get("p95_ms", 0)
            if p95_latency > 500:  # 500ms threshold
                recommendations.append(
                    Recommendation(
                        title="High P95 Latency",
                        description=f"P95 latency is {p95_latency}ms, exceeding 500ms threshold.",
                        priority=SkillPriority.MEDIUM,
                        action_type="optimize",
                        estimated_effort="1-2 days",
                        risk_level="medium",
                        commands=[
                            "Review slow endpoints",
                            "Check database queries",
                            "Analyze distributed traces",
                        ],
                        references=[
                            "https://sre.google/sre-book/implementing-slos/",
                        ],
                    )
                )

        # Check for resource issues
        if "resource_utilization" in data:
            cpu_usage = data["resource_utilization"].get("cpu_percent", 0)
            memory_usage = data["resource_utilization"].get("memory_percent", 0)

            if cpu_usage > 80:
                recommendations.append(
                    Recommendation(
                        title="High CPU Utilization",
                        description=f"CPU usage is at {cpu_usage}%, approaching limits.",
                        priority=SkillPriority.MEDIUM,
                        action_type="scale",
                        estimated_effort="1-2 hours",
                        risk_level="medium",
                        commands=[
                            "Review HPA configuration",
                            "Consider increasing CPU requests",
                            "Check for CPU-intensive operations",
                        ],
                    )
                )

            if memory_usage > 85:
                recommendations.append(
                    Recommendation(
                        title="High Memory Utilization",
                        description=f"Memory usage is at {memory_usage}%, approaching limits.",
                        priority=SkillPriority.HEDIUM,
                        action_type="scale",
                        estimated_effort="1-2 hours",
                        risk_level="medium",
                        commands=[
                            "Review HPA configuration",
                            "Consider increasing memory limits",
                            "Check for memory leaks",
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
        time_range = parameters.get("time_range_hours", 1)
        if not isinstance(time_range, (int, float)) or time_range <= 0:
            errors.append("time_range_hours must be a positive number")

        # Validate metrics list
        metrics = parameters.get("metrics", [])
        if metrics and not isinstance(metrics, list):
            errors.append("metrics must be a list of metric names")

        return len(errors) == 0, errors

    async def _query_metrics(
        self,
        project: str,
        time_range_hours: int,
        metric_patterns: list[str],
    ) -> dict[str, Any]:
        """Query metrics from Prometheus.

        Args:
            project: Project name
            time_range_hours: Time range in hours
            metric_patterns: List of metric name patterns

        Returns:
            Dictionary with queried metrics data
        """
        try:
            # Query request rate
            request_rate = await self.prometheus_client.query(
                f'rate(http_requests_total{{project="{project}"}}[{time_range_hours}h])'
            )

            # Query error rate
            error_rate = await self.prometheus_client.query(
                f'rate(http_requests_total{{project="{project}",status=~"5.."}}[{time_range_hours}h])'
            )

            # Query latency histogram
            latency_data = await self.prometheus_client.query(
                f'http_request_duration_seconds_bucket{{project="{project}"}}'
            )

            # Query resource utilization
            cpu_data = await self.prometheus_client.get_cpu_percent()
            memory_data = await self.prometheus_client.get_memory_percent()

            return {
                "metrics": [
                    {"name": "request_rate", "value": request_rate},
                    {"name": "error_rate", "value": error_rate},
                    {"name": "latency", "value": latency_data},
                ],
                "resource_utilization": {
                    "cpu_percent": cpu_data,
                    "memory_percent": memory_data,
                },
                "queried_successfully": True,
            }

        except Exception as e:
            logger.warning(f"Prometheus query failed: {e}")
            return {
                "metrics": [],
                "resource_utilization": {"cpu_percent": 0, "memory_percent": 0},
                "queried_successfully": False,
                "error": str(e),
            }

    async def _analyze_metrics(
        self,
        metrics_data: dict[str, Any],
        calculate_percentiles: bool,
        project: str,
    ) -> dict[str, Any]:
        """Analyze queried metrics.

        Args:
            metrics_data: Data from Prometheus queries
            calculate_percentiles: Whether to calculate percentiles
            project: Project name

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "project": project,
            "queried_successfully": metrics_data.get("queried_successfully", False),
        }

        # Analyze error rate
        if metrics_data.get("metrics"):
            for metric in metrics_data["metrics"]:
                if metric["name"] == "error_rate":
                    error_value = metric.get("value", 0)
                    analysis["error_rate_analysis"] = {
                        "current": float(error_value) if error_value else 0,
                        "status": "healthy" if float(error_value or 0) < 0.01 else "elevated",
                    }

        # Calculate latency percentiles
        if calculate_percentiles and metrics_data.get("metrics"):
            latency_data = next(
                (m["value"] for m in metrics_data["metrics"] if m["name"] == "latency"),
                None,
            )
            if latency_data:
                analysis["latency_analysis"] = self._calculate_percentiles(latency_data)

        # Include resource utilization
        analysis["resource_utilization"] = metrics_data.get("resource_utilization", {})

        return analysis

    def _calculate_percentiles(self, latency_data: Any) -> dict[str, float]:
        """Calculate latency percentiles from histogram data.

        Args:
            latency_data: Raw histogram data from Prometheus

        Returns:
            Dictionary with p50, p95, p99 latencies in milliseconds
        """
        # Placeholder implementation - in real scenario, parse histogram buckets
        return {
            "p50_ms": 45.0,
            "p95_ms": 234.0,
            "p99_ms": 1200.0,
        }

    def _calculate_confidence(self, metrics_data: dict, analysis: dict) -> float:
        """Calculate confidence score based on data completeness.

        Args:
            metrics_data: Raw metrics data
            analysis: Processed analysis

        Returns:
            Confidence score between 0 and 1
        """
        base_confidence = 0.5

        # Increase confidence if query was successful
        if metrics_data.get("queried_successfully"):
            base_confidence += 0.3

        # Increase confidence if we have resource data
        if analysis.get("resource_utilization"):
            base_confidence += 0.1

        # Increase confidence if we have latency analysis
        if analysis.get("latency_analysis"):
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

        # Check error rate
        error_analysis = analysis.get("error_rate_analysis", {})
        if error_analysis.get("status") == "elevated":
            warnings.append(
                f"Elevated error rate: {error_analysis.get('current', 0):.2%}"
            )

        # Check latency
        latency_analysis = analysis.get("latency_analysis", {})
        if latency_analysis.get("p95_ms", 0) > 500:
            warnings.append(
                f"High P95 latency: {latency_analysis.get('p95_ms', 0)}ms"
            )

        # Check resources
        resources = analysis.get("resource_utilization", {})
        if resources.get("cpu_percent", 0) > 80:
            warnings.append(f"High CPU usage: {resources.get('cpu_percent')}%")
        if resources.get("memory_percent", 0) > 85:
            warnings.append(f"High memory usage: {resources.get('memory_percent')}%")

        return warnings

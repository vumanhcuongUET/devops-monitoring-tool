"""Observability Tracing Analyzer Skill.

Analyzes distributed traces to identify bottlenecks, slow services,
dependency health, and timeout issues in microservices architecture.
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


class TracingAnalyzerSkill(BaseSkill):
    """Analyze distributed traces for performance insights.

    This skill analyzes OpenTelemetry/Jaeger traces to:
    - Identify slow services and operations
    - Analyze critical paths and bottlenecks
    - Detect timeout issues and failed spans
    - Map service dependencies
    - Calculate span-level latencies

    Example usage:
        skill = TracingAnalyzerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "trace_id": "optional-trace-id",
                "service_name": "my-service",
                "time_range_hours": 1,
                "min_duration_ms": 100
            }
        )
    """

    skill_id = "observability_tracing_analyzer"
    name = "Observability Tracing Analyzer"
    description = (
        "Analyze distributed traces to identify bottlenecks, "
        "slow services, dependency health, and timeout issues."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the tracing analyzer skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        # In real implementation, this would connect to Jaeger/OTLP
        self.jaeger_client = None
        self.otlp_endpoint = None

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run trace analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - trace_id: Optional specific trace ID to analyze
                - service_name: Service name to filter traces
                - time_range_hours: Time range for trace search (default: 1)
                - min_duration_ms: Minimum duration filter (default: 100)
            context: Additional context from registry

        Returns:
            AnalysisResult with trace analysis data
        """
        try:
            # Extract parameters
            trace_id = parameters.get("trace_id")
            service_name = parameters.get("service_name", project)
            time_range_hours = parameters.get("time_range_hours", 1)
            min_duration_ms = parameters.get("min_duration_ms", 100)

            # Query traces
            traces_data = await self._query_traces(
                trace_id=trace_id,
                service_name=service_name,
                time_range_hours=time_range_hours,
                min_duration_ms=min_duration_ms,
            )

            # Analyze traces
            analysis = await self._analyze_traces(
                traces_data=traces_data,
                service_name=service_name,
            )

            # Calculate confidence based on trace data quality
            confidence = self._calculate_confidence(traces_data, analysis)

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
                    "service_name": service_name,
                    "time_range_hours": time_range_hours,
                    "traces_analyzed": len(traces_data.get("traces", [])),
                    "trace_id": trace_id,
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
        """Generate recommendations based on trace analysis.

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

        # Check for slow services
        slow_services = data.get("slow_services", [])
        if slow_services:
            slowest = slow_services[0]  # Already sorted by duration
            recommendations.append(
                Recommendation(
                    title="Slow Service Detected",
                    description=(
                        f"Service '{slowest['name']}' has average duration of "
                        f"{slowest['avg_duration_ms']:.1f}ms, making it the "
                        f"bottleneck in the request path."
                    ),
                    priority=SkillPriority.HIGH,
                    action_type="optimize",
                    estimated_effort="2-5 days",
                    risk_level="high",
                    commands=[
                        f"Analyze {slowest['name']} performance",
                        "Review database queries",
                        "Check external service calls",
                        "Consider caching frequently accessed data",
                    ],
                    references=[
                        "https://opentelemetry.io/docs/concepts/signals/traces/",
                        "https://sre.google/sre-book/distributed-systems/",
                    ],
                )
            )

        # Check for timeout issues
        timeout_analysis = data.get("timeout_analysis", {})
        if timeout_analysis.get("timeout_rate", 0) > 0.05:  # 5% threshold
            recommendations.append(
                Recommendation(
                    title="High Timeout Rate",
                    description=(
                        f"{timeout_analysis['timeout_rate']:.1%} of traces "
                        f"contain timed-out spans. Consider increasing timeout "
                        f"thresholds or optimizing slow operations."
                    ),
                    priority=SkillPriority.CRITICAL,
                    action_type="investigate",
                    estimated_effort="1-2 days",
                    risk_level="critical",
                    commands=[
                        "Review timeout configurations",
                        "Analyze slow operations",
                        "Check downstream service health",
                    ],
                )
            )

        # Check for failed spans
        failed_spans = data.get("failed_spans_analysis", {})
        if failed_spans.get("total_failed", 0) > 0:
            recommendations.append(
                Recommendation(
                    title="Failed Spans Detected",
                    description=(
                        f"{failed_spans['total_failed']} failed spans found. "
                        f"Most common error: {failed_spans.get('most_common_error', 'Unknown')}"
                    ),
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="1-3 days",
                    risk_level="high",
                    commands=[
                        "Review error logs",
                        "Check service dependencies",
                        "Implement retry logic for transient errors",
                    ],
                )
            )

        # Check dependency health
        dependency_health = data.get("dependency_health", {})
        unhealthy_deps = [
            dep for dep in dependency_health
            if dep.get("health_status") != "healthy"
        ]
        if unhealthy_deps:
            dep_names = ", ".join([d["name"] for d in unhealthy_deps])
            recommendations.append(
                Recommendation(
                    title="Unhealthy Service Dependencies",
                    description=(
                        f"Service dependencies showing issues: {dep_names}. "
                        f"Review dependency health and consider fallback strategies."
                    ),
                    priority=SkillPriority.MEDIUM,
                    action_type="monitor",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Check dependency service health",
                        "Review circuit breaker configurations",
                        "Implement fallback mechanisms",
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

        # Validate min_duration_ms
        min_duration = parameters.get("min_duration_ms", 100)
        if not isinstance(min_duration, (int, float)) or min_duration < 0:
            errors.append("min_duration_ms must be a non-negative number")

        # Ensure either trace_id or service_name is provided
        trace_id = parameters.get("trace_id")
        service_name = parameters.get("service_name")
        if not trace_id and not service_name:
            errors.append("Either trace_id or service_name must be provided")

        return len(errors) == 0, errors

    async def _query_traces(
        self,
        trace_id: str | None,
        service_name: str,
        time_range_hours: int,
        min_duration_ms: int,
    ) -> dict[str, Any]:
        """Query traces from Jaeger/OTLP.

        Args:
            trace_id: Optional specific trace ID
            service_name: Service name to filter
            time_range_hours: Time range in hours
            min_duration_ms: Minimum duration filter

        Returns:
            Dictionary with trace data
        """
        # In real implementation, this would query Jaeger/OTLP
        # For now, return mock data
        return {
            "traces": [
                {
                    "trace_id": "trace-001",
                    "duration_ms": 245,
                    "start_time": datetime.now(timezone.utc) - timedelta(minutes=5),
                    "spans": [
                        {
                            "span_id": "span-001",
                            "operation_name": "GET /api/v1/overview",
                            "service_name": service_name,
                            "duration_ms": 45,
                            "parent_span_id": None,
                            "status": "ok",
                            "tags": {"http.method": "GET", "http.status_code": "200"},
                        },
                        {
                            "span_id": "span-002",
                            "operation_name": "GET /api/v1/metrics",
                            "service_name": f"{service_name}-backend",
                            "duration_ms": 180,
                            "parent_span_id": "span-001",
                            "status": "ok",
                            "tags": {"db.type": "elasticsearch"},
                        },
                        {
                            "span_id": "span-003",
                            "operation_name": "GET /api/v1/prometheus",
                            "service_name": f"{service_name}-backend",
                            "duration_ms": 15,
                            "parent_span_id": "span-001",
                            "status": "ok",
                        },
                    ],
                },
                {
                    "trace_id": "trace-002",
                    "duration_ms": 1250,
                    "start_time": datetime.now(timezone.utc) - timedelta(minutes=10),
                    "spans": [
                        {
                            "span_id": "span-004",
                            "operation_name": "POST /api/v1/triage",
                            "service_name": service_name,
                            "duration_ms": 1200,
                            "parent_span_id": None,
                            "status": "timeout",
                            "tags": {"timeout": "30s", "retry_count": "0"},
                        },
                    ],
                },
            ],
            "total_count": 2,
            "queried_successfully": True,
        }

    async def _analyze_traces(
        self,
        traces_data: dict[str, Any],
        service_name: str,
    ) -> dict[str, Any]:
        """Analyze trace data for insights.

        Args:
            traces_data: Raw trace data
            service_name: Service being analyzed

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "service_name": service_name,
            "queried_successfully": traces_data.get("queried_successfully", False),
        }

        traces = traces_data.get("traces", [])
        if not traces:
            return analysis

        # Analyze slow services
        analysis["slow_services"] = self._analyze_slow_services(traces)

        # Analyze critical path
        analysis["critical_path_analysis"] = self._analyze_critical_path(traces)

        # Analyze timeouts
        analysis["timeout_analysis"] = self._analyze_timeouts(traces)

        # Analyze failed spans
        analysis["failed_spans_analysis"] = self._analyze_failed_spans(traces)

        # Analyze dependency health
        analysis["dependency_health"] = self._analyze_dependency_health(traces)

        return analysis

    def _analyze_slow_services(self, traces: list) -> list[dict]:
        """Identify slow services from traces.

        Args:
            traces: List of trace data

        Returns:
            List of slow services sorted by avg duration
        """
        service_durations = {}

        for trace in traces:
            for span in trace.get("spans", []):
                service = span.get("service_name", "unknown")
                duration = span.get("duration_ms", 0)

                if service not in service_durations:
                    service_durations[service] = {"total": 0, "count": 0}

                service_durations[service]["total"] += duration
                service_durations[service]["count"] += 1

        # Calculate averages and sort
        slow_services = []
        for service, data in service_durations.items():
            avg_duration = data["total"] / data["count"] if data["count"] > 0 else 0
            slow_services.append({
                "name": service,
                "avg_duration_ms": avg_duration,
                "span_count": data["count"],
            })

        return sorted(slow_services, key=lambda x: x["avg_duration_ms"], reverse=True)

    def _analyze_critical_path(self, traces: list) -> dict:
        """Analyze critical path in traces.

        Args:
            traces: List of trace data

        Returns:
            Critical path analysis
        """
        # Find longest trace
        longest_trace = max(traces, key=lambda t: t.get("duration_ms", 0), default=None)

        if not longest_trace:
            return {"critical_path_duration_ms": 0, "critical_path_spans": []}

        # Build critical path from root to leaf
        spans_by_id = {s["span_id"]: s for s in longest_trace.get("spans", [])}
        root_spans = [s for s in longest_trace["spans"] if s.get("parent_span_id") is None]

        critical_spans = []
        if root_spans:
            # Start from root span
            current_span = root_spans[0]
            while current_span:
                critical_spans.append(current_span)
                # Find child with max duration
                children = [
                    s for s in longest_trace["spans"]
                    if s.get("parent_span_id") == current_span.get("span_id")
                ]
                if children:
                    current_span = max(children, key=lambda s: s.get("duration_ms", 0))
                else:
                    current_span = None

        return {
            "critical_path_duration_ms": longest_trace.get("duration_ms", 0),
            "critical_path_spans": [
                {
                    "service": s.get("service_name"),
                    "operation": s.get("operation_name"),
                    "duration_ms": s.get("duration_ms"),
                }
                for s in critical_spans
            ],
        }

    def _analyze_timeouts(self, traces: list) -> dict:
        """Analyze timeout patterns.

        Args:
            traces: List of trace data

        Returns:
            Timeout analysis
        """
        timeout_count = 0
        timeout_operations = []

        for trace in traces:
            for span in trace.get("spans", []):
                if span.get("status") == "timeout":
                    timeout_count += 1
                    timeout_operations.append({
                        "service": span.get("service_name"),
                        "operation": span.get("operation_name"),
                        "duration_ms": span.get("duration_ms"),
                    })

        return {
            "timeout_count": timeout_count,
            "timeout_rate": timeout_count / len(traces) if traces else 0,
            "common_timeout_operations": timeout_operations[:5],
        }

    def _analyze_failed_spans(self, traces: list) -> dict:
        """Analyze failed spans.

        Args:
            traces: List of trace data

        Returns:
            Failed spans analysis
        """
        failed_spans = []
        error_counts = {}

        for trace in traces:
            for span in trace.get("spans", []):
                status = span.get("status", "").lower()
                if status in ("error", "failed", "timeout"):
                    failed_spans.append(span)
                    # Count by error type
                    error = span.get("tags", {}).get("error.type", "unknown")
                    error_counts[error] = error_counts.get(error, 0) + 1

        most_common_error = max(error_counts, key=error_counts.get) if error_counts else None

        return {
            "total_failed": len(failed_spans),
            "failure_rate": len(failed_spans) / sum(len(t.get("spans", [])) for t in traces) if traces else 0,
            "most_common_error": most_common_error,
            "error_distribution": error_counts,
        }

    def _analyze_dependency_health(self, traces: list) -> list[dict]:
        """Analyze health of service dependencies.

        Args:
            traces: List of trace data

        Returns:
            List of dependency health status
        """
        dependencies = {}

        for trace in traces:
            for span in trace.get("spans", []):
                service = span.get("service_name")
                status = span.get("status", "ok")

                if service not in dependencies:
                    dependencies[service] = {"ok": 0, "error": 0, "timeout": 0}

                if status == "ok":
                    dependencies[service]["ok"] += 1
                elif status == "timeout":
                    dependencies[service]["timeout"] += 1
                else:
                    dependencies[service]["error"] += 1

        # Calculate health status
        health_results = []
        for service, counts in dependencies.items():
            total = counts["ok"] + counts["error"] + counts["timeout"]
            error_rate = (counts["error"] + counts["timeout"]) / total if total > 0 else 0

            health_status = "healthy"
            if error_rate > 0.1:
                health_status = "unhealthy"
            elif error_rate > 0.05:
                health_status = "degraded"

            health_results.append({
                "name": service,
                "health_status": health_status,
                "error_rate": error_rate,
                "total_calls": total,
                "successful_calls": counts["ok"],
            })

        return health_results

    def _calculate_confidence(self, traces_data: dict, analysis: dict) -> float:
        """Calculate confidence score based on trace data quality.

        Args:
            traces_data: Raw trace data
            analysis: Processed analysis

        Returns:
            Confidence score between 0 and 1
        """
        base_confidence = 0.5

        # Increase confidence if query was successful
        if traces_data.get("queried_successfully"):
            base_confidence += 0.2

        # Increase confidence based on number of traces
        trace_count = len(traces_data.get("traces", []))
        if trace_count >= 10:
            base_confidence += 0.2
        elif trace_count >= 5:
            base_confidence += 0.1

        # Increase confidence if we have dependency health data
        if analysis.get("dependency_health"):
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

        # Check for slow services
        slow_services = analysis.get("slow_services", [])
        if slow_services:
            slowest = slow_services[0]
            if slowest.get("avg_duration_ms", 0) > 500:
                warnings.append(
                    f"Very slow service: {slowest['name']} "
                    f"({slowest['avg_duration_ms']:.0f}ms avg)"
                )

        # Check for high timeout rate
        timeout_analysis = analysis.get("timeout_analysis", {})
        if timeout_analysis.get("timeout_rate", 0) > 0.05:
            warnings.append(
                f"High timeout rate: {timeout_analysis['timeout_rate']:.1%}"
            )

        # Check for unhealthy dependencies
        dependency_health = analysis.get("dependency_health", [])
        unhealthy = [d for d in dependency_health if d.get("health_status") == "unhealthy"]
        if unhealthy:
            warnings.append(
                f"Unhealthy dependencies: {', '.join([d['name'] for d in unhealthy])}"
            )

        return warnings

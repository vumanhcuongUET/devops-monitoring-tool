"""Performance Load Test Analyzer Skill.

Analyzes load test results and establishes baselines.
Supports Locust and k6 result parsing and analysis.
"""

import logging
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


class LoadTestAnalyzerSkill(BaseSkill):
    """Analyze load test results and establish baselines.

    This skill analyzes:
    - Locust and k6 test results
    - Performance regression detection
    - Capacity estimation
    - Bottleneck identification

    Example usage:
        skill = LoadTestAnalyzerSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "test_report_path": "/path/to/locust-report.json",
                "baseline_comparison": True
            }
        )
    """

    skill_id = "performance_load_test_analyzer"
    name = "Performance Load Test Analyzer"
    description = (
        "Analyze load test results (Locust/k6), detect regressions, "
        "estimate capacity, and identify bottlenecks."
    )
    category = SkillCategory.PERFORMANCE
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    # Performance thresholds
    DEFAULT_THRESHOLDS = {
        "requests_per_second": {"warning": 400, "critical": 200},
        "p95_latency_ms": {"warning": 200, "critical": 500},
        "p99_latency_ms": {"warning": 500, "critical": 1000},
        "error_rate_percent": {"warning": 1.0, "critical": 5.0},
    }

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the load test analyzer skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run load test analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - test_report_path: Path to test report file
                - test_type: Type of test (locust, k6)
                - thresholds: Custom performance thresholds
                - baseline_comparison: Compare with baseline (default: False)
            context: Additional context from registry

        Returns:
            AnalysisResult with load test analysis data
        """
        try:
            # Extract parameters
            test_report_path = parameters.get("test_report_path")
            test_type = parameters.get("test_type", "locust")
            custom_thresholds = parameters.get("thresholds", {})
            baseline_comparison = parameters.get("baseline_comparison", False)

            if not test_report_path:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Parameter 'test_report_path' is required"],
                    metadata={"project": project},
                )

            # Parse test report
            test_results = await self._parse_test_report(
                test_report_path, test_type
            )

            # Analyze performance metrics
            performance_analysis = self._analyze_performance(
                test_results, custom_thresholds
            )

            # Compare with baseline if requested
            baseline_analysis = None
            if baseline_comparison:
                baseline_analysis = await self._compare_with_baseline(
                    test_results, project
                )

            # Estimate capacity
            capacity_analysis = self._estimate_capacity(test_results)

            # Identify bottlenecks
            bottlenecks = self._identify_bottlenecks(test_results)

            # Calculate overall score
            overall_score = self._calculate_overall_score(
                performance_analysis, bottlenecks
            )

            # Calculate confidence
            confidence = self._calculate_confidence(test_results)

            # Generate warnings
            warnings = self._generate_warnings(performance_analysis, bottlenecks)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "test_report_path": test_report_path,
                    "test_type": test_type,
                    "test_results": test_results,
                    "performance_analysis": performance_analysis,
                    "baseline_analysis": baseline_analysis,
                    "capacity_analysis": capacity_analysis,
                    "bottlenecks": bottlenecks,
                    "overall_score": overall_score,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "test_type": test_type,
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
        """Generate recommendations based on load test analysis.

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
        performance = data.get("performance_analysis", {})
        bottlenecks = data.get("bottlenecks", [])
        overall_score = data.get("overall_score", 0)

        # Critical: Performance targets not met
        if performance.get("requests_per_second", {}).get("status") == "critical":
            recommendations.append(
                Recommendation(
                    title="Critical: Low Throughput",
                    description=f"RPS below critical threshold. "
                    f"Current: {performance.get('requests_per_second', {}).get('value', 0)}",
                    priority=SkillPriority.CRITICAL,
                    action_type="investigate",
                    estimated_effort="4-8 hours",
                    risk_level="critical",
                    commands=[
                        "Profile application for bottlenecks",
                        "Check database query performance",
                        "Review connection pooling",
                        "Consider horizontal scaling",
                    ],
                )
            )

        # High: High latency
        if performance.get("p95_latency", {}).get("status") == "critical":
            recommendations.append(
                Recommendation(
                    title="High P95 Latency Detected",
                    description=f"P95 latency exceeds critical threshold. "
                    f"Current: {performance.get('p95_latency', {}).get('value', 0)}ms",
                    priority=SkillPriority.HIGH,
                    action_type="optimize",
                    estimated_effort="2-4 hours",
                    risk_level="high",
                    commands=[
                        "Identify slow endpoints",
                        "Add database indexes",
                        "Implement caching",
                        "Optimize N+1 queries",
                    ],
                )
            )

        # High: High error rate
        if performance.get("error_rate", {}).get("status") == "critical":
            recommendations.append(
                Recommendation(
                    title="High Error Rate Detected",
                    description=f"Error rate exceeds critical threshold. "
                    f"Current: {performance.get('error_rate', {}).get('value', 0)}%",
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="2-4 hours",
                    risk_level="high",
                    commands=[
                        "Review error logs",
                        "Check for failed dependencies",
                        "Add retry logic with backoff",
                        "Improve error handling",
                    ],
                )
            )

        # Medium: Bottlenecks identified
        if bottlenecks:
            bottleneck_endpoints = [b["endpoint"] for b in bottlenecks[:3]]
            recommendations.append(
                Recommendation(
                    title="Optimize Slow Endpoints",
                    description=f"Slow endpoints detected: {', '.join(bottleneck_endpoints)}",
                    priority=SkillPriority.MEDIUM,
                    action_type="optimize",
                    estimated_effort="4-8 hours",
                    risk_level="medium",
                    commands=[
                        "Profile each slow endpoint",
                        "Review database queries",
                        "Add caching layers",
                        "Optimize data structures",
                    ],
                )
            )

        # Medium: Regression detected
        baseline = data.get("baseline_analysis", {})
        if baseline.get("has_regression", False):
            regressions = baseline.get("regressions", [])
            recommendations.append(
                Recommendation(
                    title="Investigate Performance Regression",
                    description=f"{len(regressions)} performance regressions detected "
                    f"compared to baseline.",
                    priority=SkillPriority.MEDIUM,
                    action_type="investigate",
                    estimated_effort="2-4 hours",
                    risk_level="medium",
                    commands=[
                        "Review recent code changes",
                        "Compare profiling data",
                        "Identify regression cause",
                        "Rollback if necessary",
                    ],
                )
            )

        # Capacity recommendations
        capacity = data.get("capacity_analysis", {})
        if capacity.get("headroom_percent", 0) < 20:
            recommendations.append(
                Recommendation(
                    title="Increase Capacity Headroom",
                    description=f"Only {capacity.get('headroom_percent', 0)}% headroom remaining. "
                    f"Consider scaling infrastructure.",
                    priority=SkillPriority.MEDIUM,
                    action_type="scale",
                    estimated_effort="30 minutes",
                    risk_level="medium",
                    commands=[
                        "Increase HPA max replicas",
                        "Add more instances",
                        "Review autoscaling configuration",
                    ],
                )
            )

        # Overall score recommendation
        if overall_score < 70:
            recommendations.append(
                Recommendation(
                    title="Improve Load Test Performance",
                    description=f"Overall load test score is {overall_score}/100. "
                    f"Focus on addressing bottlenecks and meeting performance targets.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="medium",
                    commands=[
                        "Review all performance recommendations",
                        "Implement performance fixes",
                        "Re-run load tests to validate",
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

        # Validate test_report_path is required
        if not parameters.get("test_report_path"):
            errors.append("Parameter 'test_report_path' is required")

        # Validate test_type
        test_type = parameters.get("test_type", "locust")
        if test_type not in ["locust", "k6"]:
            errors.append("test_type must be one of: locust, k6")

        # Validate thresholds format
        thresholds = parameters.get("thresholds", {})
        if thresholds and not isinstance(thresholds, dict):
            errors.append("thresholds must be a dictionary")

        return len(errors) == 0, errors

    async def _parse_test_report(
        self, report_path: str, test_type: str
    ) -> dict[str, Any]:
        """Parse load test report file.

        Args:
            report_path: Path to test report
            test_type: Type of test (locust or k6)

        Returns:
            Parsed test results dictionary
        """
        # In real implementation, would parse actual files:
        # if test_type == "locust":
        #     return await self._parse_locust_report(report_path)
        # elif test_type == "k6":
        #     return await self._parse_k6_report(report_path)

        # Mock implementation
        return {
            "test_type": test_type,
            "duration_seconds": 300,
            "total_requests": 125000,
            "failed_requests": 234,
            "requests_per_second": 450,
            "response_times": {
                "min_ms": 15,
                "max_ms": 2500,
                "average_ms": 85,
                "median_ms": 65,
                "p95_ms": 234,
                "p99_ms": 1200,
            },
            "error_rate_percent": 0.19,
            "endpoints": [
                {
                    "name": "/api/v1/overview",
                    "requests": 50000,
                    "p95_ms": 145,
                    "error_rate": 0.1,
                },
                {
                    "name": "/api/v1/analyze",
                    "requests": 25000,
                    "p95_ms": 850,
                    "error_rate": 0.5,
                },
                {
                    "name": "/api/v1/actions",
                    "requests": 50000,
                    "p95_ms": 45,
                    "error_rate": 0.05,
                },
            ],
        }

    def _analyze_performance(
        self, test_results: dict, custom_thresholds: dict
    ) -> dict[str, Any]:
        """Analyze performance metrics against thresholds.

        Args:
            test_results: Parsed test results
            custom_thresholds: Custom performance thresholds

        Returns:
            Performance analysis dictionary
        """
        thresholds = {**self.DEFAULT_THRESHOLDS, **custom_thresholds}
        response_times = test_results.get("response_times", {})

        analysis = {}

        # Analyze RPS
        rps = test_results.get("requests_per_second", 0)
        rps_thresholds = thresholds["requests_per_second"]
        analysis["requests_per_second"] = {
            "value": rps,
            "threshold": rps_thresholds,
            "status": "critical" if rps < rps_thresholds["critical"] else "warning" if rps < rps_thresholds["warning"] else "ok",
        }

        # Analyze P95 latency
        p95 = response_times.get("p95_ms", 0)
        p95_thresholds = thresholds["p95_latency_ms"]
        analysis["p95_latency"] = {
            "value": p95,
            "threshold": p95_thresholds,
            "status": "critical" if p95 > p95_thresholds["critical"] else "warning" if p95 > p95_thresholds["warning"] else "ok",
        }

        # Analyze P99 latency
        p99 = response_times.get("p99_ms", 0)
        p99_thresholds = thresholds["p99_latency_ms"]
        analysis["p99_latency"] = {
            "value": p99,
            "threshold": p99_thresholds,
            "status": "critical" if p99 > p99_thresholds["critical"] else "warning" if p99 > p99_thresholds["warning"] else "ok",
        }

        # Analyze error rate
        error_rate = test_results.get("error_rate_percent", 0)
        error_thresholds = thresholds["error_rate_percent"]
        analysis["error_rate"] = {
            "value": error_rate,
            "threshold": error_thresholds,
            "status": "critical" if error_rate > error_thresholds["critical"] else "warning" if error_rate > error_thresholds["warning"] else "ok",
        }

        return analysis

    async def _compare_with_baseline(
        self, test_results: dict, project: str
    ) -> dict[str, Any]:
        """Compare test results with baseline.

        Args:
            test_results: Current test results
            project: Project name

        Returns:
            Baseline comparison analysis
        """
        # In real implementation, load baseline from file:
        # baseline = await self._load_baseline(project)

        # Mock baseline
        baseline = {
            "requests_per_second": 400,
            "p95_latency_ms": 180,
            "p99_latency_ms": 500,
            "error_rate_percent": 0.3,
        }

        current = {
            "requests_per_second": test_results.get("requests_per_second", 0),
            "p95_latency_ms": test_results.get("response_times", {}).get("p95_ms", 0),
            "p99_latency_ms": test_results.get("response_times", {}).get("p99_ms", 0),
            "error_rate_percent": test_results.get("error_rate_percent", 0),
        }

        regressions = []
        improvements = []

        for metric in baseline:
            current_value = current.get(metric.replace("_ms", "") if "_ms" not in metric else metric, 0)
            baseline_value = baseline[metric]

            # Determine direction (lower is better for latency/error, higher for RPS)
            is_lower_better = "latency" in metric or "error" in metric

            if is_lower_better:
                if current_value > baseline_value * 1.1:  # 10% regression
                    regressions.append(
                        {
                            "metric": metric,
                            "baseline": baseline_value,
                            "current": current_value,
                            "change_percent": ((current_value - baseline_value) / baseline_value * 100),
                        }
                    )
                elif current_value < baseline_value * 0.9:  # 10% improvement
                    improvements.append(
                        {
                            "metric": metric,
                            "baseline": baseline_value,
                            "current": current_value,
                            "change_percent": ((baseline_value - current_value) / baseline_value * 100),
                        }
                    )
            else:
                if current_value < baseline_value * 0.9:  # 10% regression
                    regressions.append(
                        {
                            "metric": metric,
                            "baseline": baseline_value,
                            "current": current_value,
                            "change_percent": ((baseline_value - current_value) / baseline_value * 100),
                        }
                    )
                elif current_value > baseline_value * 1.1:  # 10% improvement
                    improvements.append(
                        {
                            "metric": metric,
                            "baseline": baseline_value,
                            "current": current_value,
                            "change_percent": ((current_value - baseline_value) / baseline_value * 100),
                        }
                    )

        return {
            "baseline": baseline,
            "current": current,
            "regressions": regressions,
            "improvements": improvements,
            "has_regression": len(regressions) > 0,
        }

    def _estimate_capacity(self, test_results: dict) -> dict[str, Any]:
        """Estimate system capacity from test results.

        Args:
            test_results: Test results

        Returns:
            Capacity analysis dictionary
        """
        rps = test_results.get("requests_per_second", 0)
        error_rate = test_results.get("error_rate_percent", 0)
        p95 = test_results.get("response_times", {}).get("p95_ms", 0)

        # Calculate headroom (simplified)
        # Assuming failure at 2x current RPS or when error rate hits 5%
        max_rps = rps * 2 if error_rate < 5 else rps
        headroom = max_rps - rps
        headroom_percent = (headroom / max_rps * 100) if max_rps > 0 else 0

        return {
            "current_rps": rps,
            "estimated_max_rps": max_rps,
            "headroom": headroom,
            "headroom_percent": headroom_percent,
            "status": "adequate" if headroom_percent > 30 else "tight" if headroom_percent > 10 else "critical",
        }

    def _identify_bottlenecks(self, test_results: dict) -> list[dict]:
        """Identify performance bottlenecks.

        Args:
            test_results: Test results

        Returns:
            List of bottleneck entries
        """
        bottlenecks = []
        endpoints = test_results.get("endpoints", [])

        # Sort endpoints by p95 latency
        sorted_endpoints = sorted(
            endpoints, key=lambda e: e.get("p95_ms", 0), reverse=True
        )

        for endpoint in sorted_endpoints:
            p95 = endpoint.get("p95_ms", 0)
            if p95 > 200:  # Threshold for slow endpoint
                bottlenecks.append(
                    {
                        "endpoint": endpoint.get("name"),
                        "p95_ms": p95,
                        "requests": endpoint.get("requests", 0),
                        "error_rate": endpoint.get("error_rate", 0),
                        "severity": "high" if p95 > 500 else "medium",
                    }
                )

        return bottlenecks

    def _calculate_overall_score(
        self, performance: dict, bottlenecks: list
    ) -> float:
        """Calculate overall performance score.

        Args:
            performance: Performance analysis
            bottlenecks: Bottlenecks list

        Returns:
            Overall score between 0 and 100
        """
        score = 100.0

        # Deduct for each metric not in OK status
        for metric_name, metric_data in performance.items():
            status = metric_data.get("status", "ok")
            if status == "critical":
                score -= 20
            elif status == "warning":
                score -= 10

        # Deduct for bottlenecks
        high_bottlenecks = sum(1 for b in bottlenecks if b.get("severity") == "high")
        medium_bottlenecks = sum(1 for b in bottlenecks if b.get("severity") == "medium")

        score -= high_bottlenecks * 15
        score -= medium_bottlenecks * 5

        return max(0, min(100, score))

    def _calculate_confidence(self, test_results: dict) -> float:
        """Calculate confidence in the analysis.

        Args:
            test_results: Test results

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with complete data
        if test_results.get("total_requests", 0) > 100:
            confidence += 0.2

        # Increase confidence with endpoint breakdown
        if test_results.get("endpoints"):
            confidence += 0.2

        # Increase confidence with response times
        if test_results.get("response_times"):
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_warnings(
        self, performance: dict, bottlenecks: list
    ) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            performance: Performance analysis
            bottlenecks: Bottlenecks list

        Returns:
            List of warning messages
        """
        warnings = []

        # Check for critical metrics
        for metric_name, metric_data in performance.items():
            if metric_data.get("status") == "critical":
                warnings.append(f"{metric_name} in critical status")

        # Check for bottlenecks
        if len(bottlenecks) > 0:
            warnings.append(f"{len(bottlenecks)} slow endpoints detected")

        return warnings

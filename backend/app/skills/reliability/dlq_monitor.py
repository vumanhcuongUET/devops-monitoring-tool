"""Reliability Dead Letter Queue Monitor Skill.

Monitors and analyzes Dead Letter Queue (DLQ) for failed autonomous actions,
failure patterns, retry strategies, and prevention recommendations.
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


class DLQMonitorSkill(BaseSkill):
    """Monitor Dead Letter Queue health and failed autonomous actions.

    This skill analyzes DLQ entries to:
    - Identify failure patterns and root causes
    - Analyze retry success rates
    - Track DLQ size trends over time
    - Recommend prevention strategies
    - Generate actionable remediation steps

    Example usage:
        skill = DLQMonitorSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "time_range_hours": 24,
                "action_type_filter": "remediation"
            }
        )
    """

    skill_id = "reliability_dlq_monitor"
    name = "Reliability DLQ Monitor"
    description = (
        "Monitor and analyze Dead Letter Queue for failed actions, "
        "failure patterns, and retry strategies."
    )
    category = SkillCategory.RELIABILITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Action categories in autonomous system
    ACTION_CATEGORIES = [
        "remediation",
        "scaling",
        "rollback",
        "restart",
        "config_update",
        "security_patch",
    ]

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the DLQ monitor skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        # In real implementation, this would connect to DLQ storage
        self.dlq_client = None

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Run DLQ analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - time_range_hours: Time range for DLQ analysis (default: 24)
                - action_type_filter: Filter by action type (optional)
                - include_retries: Include retry history (default: True)
            context: Additional context from registry

        Returns:
            AnalysisResult with DLQ analysis data
        """
        try:
            # Extract parameters
            time_range_hours = parameters.get("time_range_hours", 24)
            action_type_filter = parameters.get("action_type_filter")
            include_retries = parameters.get("include_retries", True)

            # Query DLQ entries
            dlq_data = await self._query_dlq(
                project=project,
                time_range_hours=time_range_hours,
                action_type_filter=action_type_filter,
            )

            # Analyze DLQ
            analysis = await self._analyze_dlq(
                dlq_data=dlq_data,
                include_retries=include_retries,
            )

            # Calculate confidence based on data quality
            confidence = self._calculate_confidence(dlq_data, analysis)

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
                    "time_range_hours": time_range_hours,
                    "dlq_entries_analyzed": len(dlq_data.get("entries", [])),
                    "action_type_filter": action_type_filter,
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
        """Generate recommendations based on DLQ analysis.

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

        # Check for high DLQ size
        size_trend = data.get("size_trend", {})
        current_size = size_trend.get("current_size", 0)
        if current_size > 100:  # Threshold for concerning DLQ size
            recommendations.append(
                Recommendation(
                    title="Large DLQ Detected",
                    description=(
                        f"DLQ contains {current_size} failed actions. "
                        f"This indicates systemic issues with autonomous actions."
                    ),
                    priority=SkillPriority.CRITICAL,
                    action_type="investigate",
                    estimated_effort="1-2 days",
                    risk_level="critical",
                    commands=[
                        "Review failed action logs",
                        "Analyze common failure patterns",
                        "Consider increasing retry limits",
                        "Review action validation logic",
                    ],
                    references=[
                        "https://www.enterpriseintegrationpatterns.com/patterns/messaging/DeadLetterChannel.html",
                    ],
                )
            )

        # Check for specific failure patterns
        failure_patterns = data.get("failure_patterns", {})
        common_failures = failure_patterns.get("common_failures", [])
        if common_failures:
            top_failure = common_failures[0]
            recommendations.append(
                Recommendation(
                    title="Common Failure Pattern Detected",
                    description=(
                        f"Most common failure: '{top_failure['error_type']}' "
                        f"({top_failure['count']} occurrences, {top_failure['percentage']:.1%}). "
                        f"Address root cause to reduce DLQ growth."
                    ),
                    priority=SkillPriority.HIGH,
                    action_type="fix",
                    estimated_effort="2-4 hours",
                    risk_level="high",
                    commands=[
                        f"Review {top_failure['error_type']} errors",
                        "Check API endpoint availability",
                        "Verify authentication credentials",
                        "Review rate limiting configurations",
                    ],
                )
            )

        # Check for low retry success rate
        retry_analysis = data.get("retry_analysis", {})
        retry_success_rate = retry_analysis.get("success_rate", 1.0)
        if retry_success_rate < 0.5:  # Less than 50% success rate
            recommendations.append(
                Recommendation(
                    title="Low Retry Success Rate",
                    description=(
                        f"Only {retry_success_rate:.1%} of retry attempts succeed. "
                        f"Current retry strategy may be ineffective."
                    ),
                    priority=SkillPriority.MEDIUM,
                    action_type="optimize",
                    estimated_effort="1-2 hours",
                    risk_level="medium",
                    commands=[
                        "Review retry backoff strategy",
                        "Check retry delays are appropriate",
                        "Consider adding circuit breakers",
                        "Review idempotency of actions",
                    ],
                )
            )

        # Check for action-specific issues
        action_breakdown = data.get("action_type_breakdown", {})
        problematic_actions = [
            (action, stats)
            for action, stats in action_breakdown.items()
            if stats.get("failure_rate", 0) > 0.2
        ]
        if problematic_actions:
            action_names = ", ".join([a[0] for a in problematic_actions[:3]])
            recommendations.append(
                Recommendation(
                    title="High Failure Rate for Specific Actions",
                    description=(
                        f"Actions with high failure rate: {action_names}. "
                        f"Review implementation and add better error handling."
                    ),
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="3-5 days",
                    risk_level="medium",
                    commands=[
                        "Review action implementations",
                        "Add better error handling",
                        "Improve validation logic",
                        "Add circuit breakers for external calls",
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

        # Validate action_type_filter if provided
        action_filter = parameters.get("action_type_filter")
        if action_filter and action_filter not in self.ACTION_CATEGORIES:
            errors.append(
                f"action_type_filter must be one of: {', '.join(self.ACTION_CATEGORIES)}"
            )

        return len(errors) == 0, errors

    async def _query_dlq(
        self,
        project: str,
        time_range_hours: int,
        action_type_filter: str | None,
    ) -> dict[str, Any]:
        """Query DLQ entries from storage.

        Args:
            project: Project name
            time_range_hours: Time range in hours
            action_type_filter: Optional action type filter

        Returns:
            Dictionary with DLQ data
        """
        # In real implementation, this would query actual DLQ storage
        # For now, return mock data
        entries = [
            {
                "id": "dlq-001",
                "action_type": "remediation",
                "action_id": "act-001",
                "failed_at": datetime.now(timezone.utc),
                "error_type": "TimeoutError",
                "error_message": "API call timed out after 30s",
                "retry_count": 3,
                "last_retry_at": datetime.now(timezone.utc),
                "payload": {"service": "backend", "issue": "high-cpu"},
            },
            {
                "id": "dlq-002",
                "action_type": "scaling",
                "action_id": "act-002",
                "failed_at": datetime.now(timezone.utc),
                "error_type": "InsufficientResources",
                "error_message": "Cluster has no available nodes",
                "retry_count": 0,
                "last_retry_at": None,
                "payload": {"deployment": "backend", "replicas": 5},
            },
            {
                "id": "dlq-003",
                "action_type": "remediation",
                "action_id": "act-003",
                "failed_at": datetime.now(timezone.utc),
                "error_type": "AuthenticationError",
                "error_message": "Invalid API token",
                "retry_count": 1,
                "last_retry_at": datetime.now(timezone.utc),
                "payload": {"service": "frontend", "issue": "pod-crash"},
            },
            {
                "id": "dlq-004",
                "action_type": "rollback",
                "action_id": "act-004",
                "failed_at": datetime.now(timezone.utc),
                "error_type": "ValidationError",
                "error_message": "Invalid rollback target version",
                "retry_count": 0,
                "last_retry_at": None,
                "payload": {"deployment": "backend", "target": "v2.3.1"},
            },
        ]

        # Filter by action type if specified
        if action_type_filter:
            entries = [e for e in entries if e["action_type"] == action_type_filter]

        return {
            "entries": entries,
            "total_count": len(entries),
            "queried_successfully": True,
        }

    async def _analyze_dlq(
        self,
        dlq_data: dict[str, Any],
        include_retries: bool,
    ) -> dict[str, Any]:
        """Analyze DLQ data for insights.

        Args:
            dlq_data: Raw DLQ data
            include_retries: Whether to include retry analysis

        Returns:
            Analysis results dictionary
        """
        analysis = {
            "queried_successfully": dlq_data.get("queried_successfully", False),
        }

        entries = dlq_data.get("entries", [])
        if not entries:
            analysis["size_trend"] = {"current_size": 0, "trend": "stable"}
            return analysis

        # Analyze size trend
        analysis["size_trend"] = {
            "current_size": len(entries),
            "trend": self._calculate_trend(entries),
        }

        # Analyze failure patterns
        analysis["failure_patterns"] = self._analyze_failure_patterns(entries)

        # Analyze by action type
        analysis["action_type_breakdown"] = self._analyze_by_action_type(entries)

        # Analyze retry success rate
        if include_retries:
            analysis["retry_analysis"] = self._analyze_retries(entries)

        # Analyze age of entries
        analysis["age_analysis"] = self._analyze_entry_age(entries)

        return analysis

    def _calculate_trend(self, entries: list) -> str:
        """Calculate trend direction based on entry timestamps.

        Args:
            entries: List of DLQ entries

        Returns:
            Trend direction: "increasing", "decreasing", or "stable"
        """
        if len(entries) < 2:
            return "stable"

        # Sort by failed_at
        sorted_entries = sorted(
            entries,
            key=lambda e: e.get("failed_at", datetime.min),
        )

        # Check if newer entries are more frequent
        now = datetime.now(timezone.utc)
        recent_count = sum(
            1 for e in sorted_entries
            if (now - e.get("failed_at", now)).total_seconds() < 3600
        )

        if recent_count > len(entries) / 2:
            return "increasing"
        elif recent_count < len(entries) / 4:
            return "decreasing"
        return "stable"

    def _analyze_failure_patterns(self, entries: list) -> dict:
        """Analyze common failure patterns.

        Args:
            entries: List of DLQ entries

        Returns:
            Failure pattern analysis
        """
        error_counts = {}
        for entry in entries:
            error_type = entry.get("error_type", "Unknown")
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

        total = len(entries)
        common_failures = [
            {
                "error_type": error_type,
                "count": count,
                "percentage": count / total if total > 0 else 0,
            }
            for error_type, count in sorted(
                error_counts.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
        ]

        return {
            "total_unique_errors": len(error_counts),
            "common_failures": common_failures,
        }

    def _analyze_by_action_type(self, entries: list) -> dict:
        """Analyze failures by action type.

        Args:
            entries: List of DLQ entries

        Returns:
            Action type breakdown
        """
        action_stats = {}

        for entry in entries:
            action_type = entry.get("action_type", "unknown")
            if action_type not in action_stats:
                action_stats[action_type] = {"failed": 0, "total": 0}

            action_stats[action_type]["failed"] += 1
            action_stats[action_type]["total"] += 1

        # Calculate failure rates
        for action_type, stats in action_stats.items():
            stats["failure_rate"] = stats["failed"] / stats["total"] if stats["total"] > 0 else 0

        return action_stats

    def _analyze_retries(self, entries: list) -> dict:
        """Analyze retry patterns and success rates.

        Args:
            entries: List of DLQ entries

        Returns:
            Retry analysis
        """
        retried_entries = [e for e in entries if e.get("retry_count", 0) > 0]
        successful_retries = [
            e for e in retried_entries
            if e.get("last_retry_at") and "success" in str(e.get("error_message", "")).lower()
        ]

        # Calculate average retry count
        avg_retries = (
            sum(e.get("retry_count", 0) for e in entries) / len(entries)
            if entries else 0
        )

        return {
            "total_retries": sum(e.get("retry_count", 0) for e in entries),
            "entries_retried": len(retried_entries),
            "successful_retries": len(successful_retries),
            "success_rate": len(successful_retries) / len(retried_entries) if retried_entries else 1.0,
            "avg_retry_count": avg_retries,
            "retry_distribution": self._get_retry_distribution(entries),
        }

    def _get_retry_distribution(self, entries: list) -> dict:
        """Get distribution of retry counts.

        Args:
            entries: List of DLQ entries

        Returns:
            Retry count distribution
        """
        distribution = {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0}

        for entry in entries:
            retry_count = entry.get("retry_count", 0)
            if retry_count == 0:
                distribution["0"] += 1
            elif retry_count == 1:
                distribution["1"] += 1
            elif retry_count == 2:
                distribution["2"] += 1
            elif retry_count == 3:
                distribution["3"] += 1
            else:
                distribution["4+"] += 1

        return distribution

    def _analyze_entry_age(self, entries: list) -> dict:
        """Analyze age distribution of DLQ entries.

        Args:
            entries: List of DLQ entries

        Returns:
            Age analysis
        """
        now = datetime.now(timezone.utc)
        ages = []

        for entry in entries:
            failed_at = entry.get("failed_at")
            if failed_at:
                age_hours = (now - failed_at).total_seconds() / 3600
                ages.append(age_hours)

        if not ages:
            return {"avg_age_hours": 0, "oldest_hours": 0, "newest_hours": 0}

        return {
            "avg_age_hours": sum(ages) / len(ages),
            "oldest_hours": max(ages),
            "newest_hours": min(ages),
            "age_distribution": {
                "<1h": sum(1 for a in ages if a < 1),
                "1-6h": sum(1 for a in ages if 1 <= a < 6),
                "6-24h": sum(1 for a in ages if 6 <= a < 24),
                ">24h": sum(1 for a in ages if a >= 24),
            },
        }

    def _calculate_confidence(self, dlq_data: dict, analysis: dict) -> float:
        """Calculate confidence score based on data quality.

        Args:
            dlq_data: Raw DLQ data
            analysis: Processed analysis

        Returns:
            Confidence score between 0 and 1
        """
        base_confidence = 0.5

        # Increase confidence if query was successful
        if dlq_data.get("queried_successfully"):
            base_confidence += 0.3

        # Increase confidence based on number of entries
        entry_count = len(dlq_data.get("entries", []))
        if entry_count >= 20:
            base_confidence += 0.2
        elif entry_count >= 5:
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

        # Check DLQ size
        size_trend = analysis.get("size_trend", {})
        current_size = size_trend.get("current_size", 0)
        if current_size > 50:
            warnings.append(f"Large DLQ size: {current_size} entries")

        # Check trend
        trend = size_trend.get("trend", "stable")
        if trend == "increasing":
            warnings.append("DLQ is growing - failure rate increasing")

        # Check retry success rate
        retry_analysis = analysis.get("retry_analysis", {})
        success_rate = retry_analysis.get("success_rate", 1.0)
        if success_rate < 0.3:
            warnings.append(f"Very low retry success rate: {success_rate:.1%}")

        # Check for stale entries
        age_analysis = analysis.get("age_analysis", {})
        stale_count = age_analysis.get("age_distribution", {}).get(">24h", 0)
        if stale_count > 10:
            warnings.append(f"Many stale entries: {stale_count} older than 24h")

        return warnings

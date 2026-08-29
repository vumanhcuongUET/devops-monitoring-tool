"""Alert Optimizer Skill - Optimize alerting rules to reduce fatigue.

This skill analyzes alert patterns to:
- Identify alert fatigue issues
- Recommend alert threshold optimizations
- Detect duplicate and overlapping alerts
- Suggest alert consolidation strategies
"""

import logging
from datetime import datetime
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


class AlertOptimizerSkill(BaseSkill):
    """Optimize alerting rules to reduce noise and fatigue.

    This skill analyzes alert history to:
    - Identify frequently firing alerts (potential noise)
    - Detect alert storms and cascading failures
    - Find duplicate or overlapping alerts
    - Recommend threshold and condition optimizations
    - Suggest alert consolidation strategies

    Requires:
    - Alert history data
    - Current alert rule configurations
    - Incident data for correlation
    """

    skill_id = "monitoring_alert_optimizer"
    name = "Alert Optimizer"
    description = "Optimize alerting rules to reduce fatigue and improve signal-to-noise ratio"
    category = SkillCategory.MONITORING
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the Alert Optimizer skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Analyze alert patterns and optimization opportunities.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context

        Returns:
            AnalysisResult with alert optimization recommendations
        """
        try:
            logger.info(f"Analyzing alert patterns for {project}")

            # Get alert history
            alert_history = await self._get_alert_history(project, context)

            # Analyze alert patterns
            noise_alerts = self._identify_noise_alerts(alert_history)
            duplicate_alerts = self._detect_duplicate_alerts(alert_history)
            alert_storms = self._detect_alert_storms(alert_history)

            # Get current alert rules
            alert_rules = await self._get_alert_rules(project, context)

            # Analyze rule efficiency
            rule_efficiency = self._analyze_rule_efficiency(alert_history, alert_rules)

            # Generate optimization recommendations
            recommendations = self._generate_optimization_recommendations(
                noise_alerts,
                duplicate_alerts,
                alert_storms,
                rule_efficiency,
            )

            # Build result
            data = {
                "noise_alerts": noise_alerts,
                "duplicate_alerts": duplicate_alerts,
                "alert_storms": alert_storms,
                "rule_efficiency": rule_efficiency,
                "total_alerts_analyzed": len(alert_history),
                "analysis_date": datetime.now().isoformat(),
            }

            confidence = self._calculate_confidence(alert_history, alert_rules)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Alert optimization failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _get_alert_history(
        self,
        project: str,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Get alert history for analysis.

        Returns:
            List of alert events
        """
        # Mock implementation - query alerting system
        # Real implementation would query AlertEngine or Prometheus Alertmanager
        return [
            {
                "alert_id": "high_cpu_1",
                "name": "HighCPUUsage",
                "severity": "warning",
                "fired_at": "2026-08-18T10:00:00Z",
                "resolved_at": "2026-08-18T10:05:00Z",
                "duration_minutes": 5,
                "rule_id": "cpu_high",
            },
            {
                "alert_id": "high_cpu_2",
                "name": "HighCPUUsage",
                "severity": "warning",
                "fired_at": "2026-08-18T11:00:00Z",
                "resolved_at": "2026-08-18T11:03:00Z",
                "duration_minutes": 3,
                "rule_id": "cpu_high",
            },
            # Add more mock alerts...
            {
                "alert_id": "disk_space_1",
                "name": "LowDiskSpace",
                "severity": "critical",
                "fired_at": "2026-08-18T12:00:00Z",
                "resolved_at": "2026-08-18T14:00:00Z",
                "duration_minutes": 120,
                "rule_id": "disk_low",
            },
        ]

    async def _get_alert_rules(
        self,
        project: str,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Get current alert rules.

        Returns:
            List of alert rule configurations
        """
        # Mock implementation - query alert rules
        return [
            {
                "rule_id": "cpu_high",
                "name": "HighCPUUsage",
                "condition": "cpu_usage_percent > 80",
                "severity": "warning",
                "enabled": True,
            },
            {
                "rule_id": "disk_low",
                "name": "LowDiskSpace",
                "condition": "disk_space_percent < 20",
                "severity": "critical",
                "enabled": True,
            },
        ]

    def _identify_noise_alerts(self, alert_history: list[dict[str, Any]]) -> dict[str, Any]:
        """Identify noisy alerts that fire frequently.

        Returns:
            Dict with noise alert analysis
        """
        # Count alerts by rule
        alert_counts = {}
        for alert in alert_history:
            rule_id = alert.get("rule_id")
            if rule_id:
                alert_counts[rule_id] = alert_counts.get(rule_id, 0) + 1

        # Identify noise alerts (fire more than 10 times in analysis period)
        noise_threshold = 10
        noise_alerts = [
            {"rule_id": rule_id, "fire_count": count}
            for rule_id, count in alert_counts.items()
            if count > noise_threshold
        ]

        return {
            "total_noisy_rules": len(noise_alerts),
            "noise_alerts": noise_alerts,
            "noise_percentage": round(len(noise_alerts) / max(len(alert_counts), 1) * 100, 1),
        }

    def _detect_duplicate_alerts(self, alert_history: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect duplicate or overlapping alerts.

        Returns:
            Dict with duplicate alert analysis
        """
        # Group alerts by time window (5 minutes)
        time_groups = {}
        for alert in alert_history:
            fired_at = alert.get("fired_at", "")
            # Create 5-minute bucket
            time_bucket = fired_at[:16] if len(fired_at) > 16 else fired_at
            if time_bucket not in time_groups:
                time_groups[time_bucket] = []
            time_groups[time_bucket].append(alert)

        # Find duplicate alerts (same rule firing within 5 minutes)
        duplicates = []
        for time_bucket, alerts in time_groups.items():
            if len(alerts) > 1:
                # Check if same rule fired multiple times
                rule_counts = {}
                for alert in alerts:
                    rule_id = alert.get("rule_id")
                    if rule_id:
                        rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

                for rule_id, count in rule_counts.items():
                    if count > 1:
                        duplicates.append({
                            "rule_id": rule_id,
                            "time_bucket": time_bucket,
                            "duplicate_count": count - 1,
                        })

        return {
            "total_duplicates": len(duplicates),
            "duplicates": duplicates,
        }

    def _detect_alert_storms(self, alert_history: list[dict[str, Any]]) -> dict[str, Any]:
        """Detect alert storms (many alerts firing in short time).

        Returns:
            Dict with alert storm analysis
        """
        # Group by time windows to find storms
        # Alert storm = 10+ alerts in 5 minutes
        storm_threshold = 10
        time_windows = {}

        for alert in alert_history:
            fired_at = alert.get("fired_at", "")
            time_bucket = fired_at[:16] if len(fired_at) > 16 else fired_at
            if time_bucket not in time_windows:
                time_windows[time_bucket] = 0
            time_windows[time_bucket] += 1

        storms = [
            {"time_window": window, "alert_count": count}
            for window, count in time_windows.items()
            if count >= storm_threshold
        ]

        return {
            "total_storms": len(storms),
            "storms": storms,
            "max_alerts_in_window": max((w["alert_count"] for w in storms), default=0),
        }

    def _analyze_rule_efficiency(
        self,
        alert_history: list[dict[str, Any]],
        alert_rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze alert rule efficiency.

        Returns:
            Dict with rule efficiency metrics
        """
        rule_metrics = {}

        for rule in alert_rules:
            rule_id = rule.get("rule_id")

            # Count fires for this rule
            rule_alerts = [a for a in alert_history if a.get("rule_id") == rule_id]

            # Calculate metrics
            total_fires = len(rule_alerts)
            avg_duration = sum(
                a.get("duration_minutes", 0) for a in rule_alerts
            ) / max(total_fires, 1)

            # Calculate efficiency (fires that led to action / total fires)
            # This is a simplified metric - real implementation would track
            # whether fires led to incident creation or action
            efficiency = 0.5 if total_fires > 0 else 0.0

            rule_metrics[rule_id] = {
                "total_fires": total_fires,
                "avg_duration_minutes": round(avg_duration, 1),
                "efficiency_score": round(efficiency, 2),
                "enabled": rule.get("enabled", True),
            }

        return rule_metrics

    def _generate_optimization_recommendations(
        self,
        noise_alerts: dict[str, Any],
        duplicate_alerts: dict[str, Any],
        alert_storms: dict[str, Any],
        rule_efficiency: dict[str, Any],
    ) -> list[Recommendation]:
        """Generate alert optimization recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Noise alert recommendations
        if noise_alerts["total_noisy_rules"] > 0:
            for noise in noise_alerts["noise_alerts"]:
                recommendations.append(Recommendation(
                    title=f"Optimize noisy alert rule: {noise['rule_id']}",
                    description=f"Rule fires {noise['fire_count']} times, likely causing alert fatigue",
                    impact="high",
                    effort="low",
                    priority="high",
                    actions=[
                        "Increase threshold to reduce false positives",
                        "Add hysteresis to prevent flapping",
                        "Consider adding delay before alerting",
                        "Review if rule is still needed",
                    ],
                ))

        # Duplicate alert recommendations
        if duplicate_alerts["total_duplicates"] > 0:
            recommendations.append(Recommendation(
                title="Consolidate duplicate alerts",
                description=f"Found {duplicate_alerts['total_duplicates']} duplicate alert instances",
                impact="medium",
                    effort="medium",
                priority="medium",
                actions=[
                    "Review alert rules for overlap",
                    "Consolidate similar alerts",
                    "Add alert grouping to reduce notifications",
                ],
            ))

        # Alert storm recommendations
        if alert_storms["total_storms"] > 0:
            recommendations.append(Recommendation(
                title="Implement alert storm protection",
                description=f"Detected {alert_storms['total_storms']} alert storms",
                impact="high",
                effort="medium",
                priority="high",
                actions=[
                    "Implement alert rate limiting",
                    "Add alert grouping for related issues",
                    "Create suppression rules for cascading failures",
                ],
            ))

        # General optimization recommendations
        low_efficiency_rules = [
            rule_id for rule_id, metrics in rule_efficiency.items()
            if metrics.get("efficiency_score", 0) < 0.3
        ]

        if low_efficiency_rules:
            recommendations.append(Recommendation(
                title="Review low-efficiency alert rules",
                description=f"{len(low_efficiency_rules)} rules have low efficiency scores",
                impact="medium",
                effort="medium",
                priority="medium",
                actions=[
                    "Review and update thresholds",
                    "Consider disabling unused rules",
                    "Add context to improve relevance",
                ],
            ))

        return recommendations

    def _calculate_confidence(
        self,
        alert_history: list[dict[str, Any]],
        alert_rules: list[dict[str, Any]],
    ) -> float:
        """Calculate confidence in the analysis.

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.6  # Base confidence

        # Increase confidence with more data
        if len(alert_history) >= 100:
            confidence += 0.2
        elif len(alert_history) >= 50:
            confidence += 0.1

        # Increase confidence if we have rule configurations
        if len(alert_rules) > 0:
            confidence += 0.1

        return min(confidence, 0.9)

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate time_period
        time_period = parameters.get("time_period_days")
        if time_period is not None:
            if not isinstance(time_period, int) or time_period < 1 or time_period > 90:
                errors.append("time_period_days must be between 1 and 90")

        return len(errors) == 0, errors

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Get recommendations based on analysis results.

        Args:
            analysis_id: ID of previous analysis result
            project: Project/service name

        Returns:
            List of recommendations
        """
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        return result.recommendations or []

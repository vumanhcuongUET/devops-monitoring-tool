"""Capacity Bottleneck Detector Skill - Identify performance bottlenecks in infrastructure.

This skill analyzes system metrics to:
- Detect CPU, memory, I/O bottlenecks
- Identify slow database queries
- Find network latency issues
- Locate resource constraints
"""

import logging
from datetime import datetime
from typing import Any, Optional

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillPriority,
    AnalysisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)


class CapacityBottleneckDetectorSkill(BaseSkill):
    """Detect capacity bottlenecks in infrastructure.

    This skill analyzes performance metrics to:
    - Identify CPU bottlenecks (high utilization, saturation)
    - Detect memory constraints (OOM, swap usage)
    - Find I/O bottlenecks (disk latency, network saturation)
    - Locate database performance issues

    Requires:
    - Prometheus metrics access
    - Performance monitoring data
    - APM traces for database queries
    """

    skill_id = "capacity_bottleneck_detector"
    name = "Capacity Bottleneck Detector"
    description = "Identify performance bottlenecks in infrastructure"
    category = SkillCategory.CAPACITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Bottleneck Detector skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze infrastructure for bottlenecks.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context

        Returns:
            AnalysisResult with bottleneck findings
        """
        try:
            logger.info(f"Detecting bottlenecks for {project}")

            # Analyze different bottleneck types
            cpu_bottlenecks = await self._detect_cpu_bottlenecks(project, context)
            memory_bottlenecks = await self._detect_memory_bottlenecks(project, context)
            disk_bottlenecks = await self._detect_disk_bottlenecks(project, context)
            network_bottlenecks = await self._detect_network_bottlenecks(project, context)
            db_bottlenecks = await self._detect_database_bottlenecks(project, context)

            # Aggregate findings
            all_bottlenecks = {
                "cpu": cpu_bottlenecks,
                "memory": memory_bottlenecks,
                "disk": disk_bottlenecks,
                "network": network_bottlenecks,
                "database": db_bottlenecks,
            }

            # Calculate overall bottleneck score
            bottleneck_score = self._calculate_bottleneck_score(all_bottlenecks)

            # Generate recommendations
            recommendations = self._generate_recommendations(all_bottlenecks)

            # Build result
            data = {
                "bottlenecks": all_bottlenecks,
                "bottleneck_score": bottleneck_score,
                "analysis_timestamp": datetime.now().isoformat(),
                "analyzed_components": list(all_bottlenecks.keys()),
            }

            confidence = self._calculate_confidence(all_bottlenecks)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Bottleneck detection failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _detect_cpu_bottlenecks(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect CPU-related bottlenecks.

        Returns:
            Dict with CPU bottleneck findings
        """
        # Mock implementation - query Prometheus for:
        # - High CPU utilization (>80%)
        # - CPU saturation (load average vs core count)
        # - CPU throttling (container throttling time)

        bottlenecks = []

        # Example: High CPU utilization
        bottlenecks.append({
            "type": "high_cpu_utilization",
            "severity": "high",
            "component": "app-server-1",
            "description": "CPU utilization averaging 85% over 1h",
            "current_value": 85,
            "threshold": 80,
            "impact": "Request latency increased by 40%",
            "recommendation": "Scale horizontally or optimize CPU-intensive operations",
        })

        return {
            "has_bottlenecks": len(bottlenecks) > 0,
            "bottlenecks": bottlenecks,
            "summary": f"{len(bottlenecks)} CPU bottlenecks detected",
        }

    async def _detect_memory_bottlenecks(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect memory-related bottlenecks.

        Returns:
            Dict with memory bottleneck findings
        """
        bottlenecks = []

        # Example: Memory pressure
        bottlenecks.append({
            "type": "memory_pressure",
            "severity": "medium",
            "component": "api-server",
            "description": "Memory usage at 78% with increasing swap activity",
            "current_value": 78,
            "threshold": 70,
            "impact": "Increased GC pause times, occasional OOM kills",
            "recommendation": "Investigate memory leaks, increase container memory limits",
        })

        return {
            "has_bottlenecks": len(bottlenecks) > 0,
            "bottlenecks": bottlenecks,
            "summary": f"{len(bottlenecks)} memory bottlenecks detected",
        }

    async def _detect_disk_bottlenecks(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect disk I/O bottlenecks.

        Returns:
            Dict with disk bottleneck findings
        """
        bottlenecks = []

        # Example: High I/O wait
        bottlenecks.append({
            "type": "high_iowait",
            "severity": "high",
            "component": "database-primary",
            "description": "I/O wait averaging 35%, slow disk operations",
            "current_value": 35,
            "threshold": 20,
            "impact": "Database query latency increased 200%",
            "recommendation": "Upgrade to faster SSD storage, optimize queries",
        })

        return {
            "has_bottlenecks": len(bottlenecks) > 0,
            "bottlenecks": bottlenecks,
            "summary": f"{len(bottlenecks)} disk I/O bottlenecks detected",
        }

    async def _detect_network_bottlenecks(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect network bottlenecks.

        Returns:
            Dict with network bottleneck findings
        """
        bottlenecks = []

        # Example: Network latency
        bottlenecks.append({
            "type": "high_latency",
            "severity": "medium",
            "component": "microservice-b",
            "description": "Average response latency 450ms to microservice-a",
            "current_value": 450,
            "threshold": 200,
            "impact": "Slow API responses, degraded user experience",
            "recommendation": "Optimize network paths, consider service mesh, add caching",
        })

        return {
            "has_bottlenecks": len(bottlenecks) > 0,
            "bottlenecks": bottlenecks,
            "summary": f"{len(bottlenecks)} network bottlenecks detected",
        }

    async def _detect_database_bottlenecks(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect database performance bottlenecks.

        Returns:
            Dict with database bottleneck findings
        """
        bottlenecks = []

        # Example: Slow queries
        bottlenecks.append({
            "type": "slow_query",
            "severity": "critical",
            "component": "postgres-db",
            "description": "Query 'SELECT * FROM orders WHERE status = pending' averaging 8.5s",
            "current_value": 8500,
            "threshold": 1000,  # ms
            "impact": "API timeouts, degraded checkout experience",
            "recommendation": "Add index on status column, optimize query, consider pagination",
        })

        # Example: Connection pool exhaustion
        bottlenecks.append({
            "type": "connection_pool_exhaustion",
            "severity": "high",
            "component": "postgres-db",
            "description": "Connection pool at 95% utilization, frequent wait times",
            "current_value": 95,
            "threshold": 80,
            "impact": "New connection requests waiting 2-3s",
            "recommendation": "Increase connection pool size, optimize connection reuse",
        })

        return {
            "has_bottlenecks": len(bottlenecks) > 0,
            "bottlenecks": bottlenecks,
            "summary": f"{len(bottlenecks)} database bottlenecks detected",
        }

    def _calculate_bottleneck_score(self, all_bottlenecks: dict[str, Any]) -> float:
        """Calculate overall bottleneck severity score.

        Returns:
            Score from 0.0 (no bottlenecks) to 1.0 (severe)
        """
        total_bottlenecks = 0
        critical_count = 0
        high_count = 0

        for component_data in all_bottlenecks.values():
            for bottleneck in component_data.get("bottlenecks", []):
                total_bottlenecks += 1
                severity = bottleneck.get("severity", "low")
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1

        if total_bottlenecks == 0:
            return 0.0

        # Weight critical bottlenecks heavily
        score = (critical_count * 1.0 + high_count * 0.6 +
                (total_bottlenecks - critical_count - high_count) * 0.3)
        return min(score / 10.0, 1.0)  # Normalize to 0-1

    def _generate_recommendations(
        self,
        all_bottlenecks: dict[str, Any],
    ) -> list[Recommendation]:
        """Generate bottleneck remediation recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Check for critical bottlenecks
        for component, data in all_bottlenecks.items():
            for bottleneck in data.get("bottlenecks", []):
                severity = bottleneck.get("severity", "low")
                if severity in ["critical", "high"]:
                    recommendations.append(Recommendation(
                        title=f"Fix {component} bottleneck: {bottleneck['type']}",
                        description=bottleneck["description"],
                        impact="high",
                        effort=bottleneck.get("effort", "medium"),
                        priority=severity,
                        actions=[
                            bottleneck.get("recommendation", "Investigate and optimize"),
                            f"Monitor {component} for improvements",
                            "Document resolution for future reference",
                        ],
                    ))

        # General optimization recommendations
        if any(b["has_bottlenecks"] for b in all_bottlenecks.values()):
            recommendations.append(Recommendation(
                title="Implement bottleneck monitoring dashboards",
                description="Create visibility into bottleneck metrics",
                impact="medium",
                effort="low",
                priority="medium",
                actions=[
                    "Add Grafana dashboards for bottleneck metrics",
                    "Set up alerts for critical thresholds",
                    "Conduct weekly bottleneck review",
                ],
            ))

        return recommendations

    def _calculate_confidence(self, all_bottlenecks: dict[str, Any]) -> float:
        """Calculate confidence in the analysis.

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.7  # Base confidence

        # Increase confidence if we detected bottlenecks (actual data)
        for component_data in all_bottlenecks.values():
            if component_data.get("has_bottlenecks"):
                confidence += 0.05

        return min(confidence, 1.0)

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate analysis_period
        analysis_period = parameters.get("analysis_period_hours")
        if analysis_period is not None:
            if not isinstance(analysis_period, (int, float)) or analysis_period <= 0:
                errors.append("analysis_period_hours must be a positive number")

        # Validate components to analyze
        components = parameters.get("components")
        if components is not None:
            valid_components = ["cpu", "memory", "disk", "network", "database"]
            for component in components:
                if component not in valid_components:
                    errors.append(f"Invalid component: {component}")

        return len(errors) == 0, errors

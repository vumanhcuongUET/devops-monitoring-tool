"""Dashboard Auditor Skill - Audit monitoring dashboard coverage.

This skill analyzes monitoring coverage to:
- Identify gaps in dashboard coverage
- Detect missing critical metrics
- Review alert rule coverage
- Suggest dashboard improvements
"""

import logging
from datetime import datetime
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


class DashboardAuditorSkill(BaseSkill):
    """Audit monitoring dashboard coverage and completeness.

    This skill analyzes:
    - Dashboard coverage for all services
    - Essential metrics tracking
    - Alert-to-dashboard ratio
    - Visualization gaps
    - SLO/SLI dashboard coverage

    Requires:
    - Dashboard metadata
    - Service inventory
    - Metric catalog
    """

    skill_id = "monitoring_dashboard_auditor"
    name = "Dashboard Auditor"
    description = "Audit monitoring dashboard coverage and identify gaps"
    category = SkillCategory.MONITORING
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Dashboard Auditor skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Audit dashboard coverage for the project.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context

        Returns:
            AnalysisResult with coverage gaps and recommendations
        """
        try:
            logger.info(f"Auditing dashboard coverage for {project}")

            # Get service inventory
            services = await self._get_services(project, context)

            # Get existing dashboards
            dashboards = await self._get_dashboards(project, context)

            # Analyze coverage
            coverage_analysis = self._analyze_coverage(services, dashboards)

            # Identify critical metrics gaps
            metrics_gaps = self._identify_metrics_gaps(services, dashboards)

            # Review SLO dashboard coverage
            slo_coverage = self._review_slo_coverage(project, dashboards)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                coverage_analysis,
                metrics_gaps,
                slo_coverage,
            )

            # Build result
            data = {
                "services": services,
                "dashboards": dashboards,
                "coverage_analysis": coverage_analysis,
                "metrics_gaps": metrics_gaps,
                "slo_coverage": slo_coverage,
                "analysis_date": datetime.now().isoformat(),
            }

            confidence = self._calculate_confidence(services, dashboards)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Dashboard audit failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _get_services(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Get service inventory for the project.

        Returns:
            List of services
        """
        # Mock implementation - query service registry
        return [
            {
                "service_id": "api-service",
                "name": "API Service",
                "type": "backend",
                "critical": True,
            },
            {
                "service_id": "frontend-app",
                "name": "Frontend Application",
                "type": "frontend",
                "critical": True,
            },
            {
                "service_id": "database",
                "name": "PostgreSQL Database",
                "type": "database",
                "critical": True,
            },
            {
                "service_id": "cache",
                "name": "Redis Cache",
                "type": "cache",
                "critical": False,
            },
        ]

    async def _get_dashboards(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Get existing dashboards for the project.

        Returns:
            List of dashboards
        """
        # Mock implementation - query Grafana API
        return [
            {
                "dashboard_id": "api-overview",
                "name": "API Service Overview",
                "services": ["api-service"],
                "metrics": ["requests", "errors", "latency"],
            },
            {
                "dashboard_id": "frontend-stats",
                "name": "Frontend Stats",
                "services": ["frontend-app"],
                "metrics": ["page_views", "load_time"],
            },
        ]

    def _analyze_coverage(
        self,
        services: List[Dict[str, Any]],
        dashboards: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze dashboard coverage across services.

        Returns:
            Dict with coverage analysis
        """
        # Track which services have dashboards
        covered_services = set()
        for dashboard in dashboards:
            covered_services.update(dashboard.get("services", []))

        # Find uncovered services
        uncovered_services = [
            service for service in services
            if service["service_id"] not in covered_services
        ]

        # Find critical services without dashboards
        uncovered_critical = [
            service for service in uncovered_services
            if service.get("critical", False)
        ]

        return {
            "total_services": len(services),
            "covered_services": len(covered_services),
            "coverage_percent": round(len(covered_services) / max(len(services), 1) * 100, 1),
            "uncovered_services": [s["service_id"] for s in uncovered_services],
            "uncovered_critical": [s["service_id"] for s in uncovered_critical],
        }

    def _identify_metrics_gaps(
        self,
        services: List[Dict[str, Any]],
        dashboards: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Identify missing essential metrics.

        Returns:
            Dict with metrics gap analysis
        """
        # Define essential metrics by service type
        essential_metrics = {
            "backend": ["requests", "errors", "latency", "cpu", "memory"],
            "frontend": ["page_views", "load_time", "errors", "js_errors"],
            "database": ["connections", "query_time", "deadlocks", "replication_lag"],
            "cache": ["hit_rate", "memory_usage", "evictions", "connections"],
        }

        gaps = []

        for service in services:
            service_type = service.get("type")
            required_metrics = essential_metrics.get(service_type, [])

            # Find dashboards for this service
            service_dashboards = [
                d for d in dashboards
                if service["service_id"] in d.get("services", [])
            ]

            # Collect tracked metrics
            tracked_metrics = set()
            for dashboard in service_dashboards:
                tracked_metrics.update(dashboard.get("metrics", []))

            # Find missing metrics
            missing_metrics = [m for m in required_metrics if m not in tracked_metrics]

            if missing_metrics:
                gaps.append({
                    "service_id": service["service_id"],
                    "service_name": service["name"],
                    "missing_metrics": missing_metrics,
                    "severity": "high" if service.get("critical") else "medium",
                })

        return {
            "total_gaps": len(gaps),
            "gaps": gaps,
        }

    def _review_slo_coverage(
        self,
        project: str,
        dashboards: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Review SLO dashboard coverage.

        Returns:
            Dict with SLO coverage analysis
        """
        # Check for SLO-specific dashboards
        slo_dashboards = [
            d for d in dashboards
            if "slo" in d["dashboard_id"].lower() or "sli" in d["dashboard_id"].lower()
        ]

        # Essential SLO metrics
        essential_slo_metrics = ["availability", "latency", "error_budget"]

        # Check if SLO dashboards cover essential metrics
        covered_slo_metrics = set()
        for dashboard in slo_dashboards:
            covered_slo_metrics.update(dashboard.get("metrics", []))

        missing_slo_metrics = [
            m for m in essential_slo_metrics
            if m not in covered_slo_metrics
        ]

        return {
            "has_slo_dashboard": len(slo_dashboards) > 0,
            "slo_dashboard_count": len(slo_dashboards),
            "covered_slo_metrics": list(covered_slo_metrics),
            "missing_slo_metrics": missing_slo_metrics,
        }

    def _generate_recommendations(
        self,
        coverage_analysis: Dict[str, Any],
        metrics_gaps: Dict[str, Any],
        slo_coverage: Dict[str, Any],
    ) -> List[Recommendation]:
        """Generate dashboard improvement recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Critical service coverage recommendations
        if coverage_analysis["uncovered_critical"]:
            for service_id in coverage_analysis["uncovered_critical"]:
                recommendations.append(Recommendation(
                    title=f"Create dashboard for critical service: {service_id}",
                    description=f"Critical service has no monitoring dashboard",
                    impact="high",
                    effort="medium",
                    priority="high",
                    actions=[
                        f"Create dashboard for {service_id}",
                        "Include essential metrics (requests, errors, latency)",
                        "Set up alerts for critical thresholds",
                    ],
                ))

        # Metrics gap recommendations
        for gap in metrics_gaps["gaps"]:
            service_name = gap["service_name"]
            missing = gap["missing_metrics"]
            recommendations.append(Recommendation(
                title=f"Add missing metrics to {service_name} dashboard",
                description=f"Missing metrics: {', '.join(missing)}",
                impact="medium",
                effort="low",
                priority=gap["severity"],
                actions=[
                    f"Add panels for: {', '.join(missing)}",
                    "Ensure consistent time ranges across dashboards",
                    "Add annotations for deployments",
                ],
            ))

        # SLO coverage recommendations
        if not slo_coverage["has_slo_dashboard"]:
            recommendations.append(Recommendation(
                title="Create SLO dashboard",
                description="No SLO/SLI dashboard found",
                impact="high",
                effort="medium",
                priority="high",
                actions=[
                    "Create SLO overview dashboard",
                    "Include availability, latency, error budget",
                    "Add SLO trend charts",
                    "Link to service-level details",
                ],
            ))
        elif slo_coverage["missing_slo_metrics"]:
            recommendations.append(Recommendation(
                title="Add missing SLO metrics",
                description=f"Missing SLO metrics: {slo_coverage['missing_slo_metrics']}",
                impact="medium",
                effort="low",
                priority="medium",
                actions=[
                    f"Add panels for: {', '.join(slo_coverage['missing_slo_metrics'])}",
                    "Include error budget calculations",
                    "Add burn rate alerts",
                ],
            ))

        return recommendations

    def _calculate_confidence(
        self,
        services: List[Dict[str, Any]],
        dashboards: List[Dict[str, Any]],
    ) -> float:
        """Calculate confidence in the analysis.

        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.7  # Base confidence

        # Increase confidence with more data
        if len(services) >= 5 and len(dashboards) >= 3:
            confidence += 0.1

        return min(confidence, 0.9)

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        # No specific validation required for this skill
        return True, []


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
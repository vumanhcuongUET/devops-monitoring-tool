"""Observability Dashboard Auditor Skill.

Audits Grafana dashboards for coverage, quality, and compliance.
Identifies missing dashboards, duplicate detection, and health checks.
"""

import logging
from typing import Any, Optional

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)


class DashboardAuditorSkill(BaseSkill):
    """Audit Grafana dashboards for coverage and quality.

    This skill analyzes:
    - Dashboard coverage for all services and components
    - Duplicate dashboard detection
    - Dashboard health (data source connectivity, query validity)
    - Stale dashboard identification (no queries in 30d)
    - Standard dashboard template recommendations

    Example usage:
        skill = DashboardAuditorSkill()
        result = await skill.analyze(
            project="my-service",
            parameters={
                "namespace": "production",
                "check_stale": True,
                "stale_days": 30
            }
        )
    """

    skill_id = "observability_dashboard_auditor"
    name = "Observability Dashboard Auditor"
    description = (
        "Audit Grafana dashboards for coverage, quality, and compliance. "
        "Identifies missing dashboards, duplicates, and health issues."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    # Standard dashboard templates
    STANDARD_TEMPLATES = {
        "service_overview": {
            "required_panels": [
                "Request Rate",
                "Error Rate",
                "Latency (p50, p95, p99)",
                "Resource Usage",
                "Alert Status",
            ]
        },
        "slo_dashboard": {
            "required_panels": ["SLO Status", "Error Budget", "Burn Rate", "Breach Probability"]
        },
        "resource_usage": {
            "required_panels": ["CPU", "Memory", "Network", "Disk"]
        },
    }

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the dashboard auditor skill.

        Args:
            config: Optional skill configuration
        """
        super().__init__(config)
        # Grafana client would be initialized here
        # self.grafana_client = GrafanaClient()

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run dashboard audit analysis.

        Args:
            project: Project/service name to analyze
            parameters: Analysis parameters including:
                - namespace: Namespace to scope audit (default: all)
                - check_stale: Check for stale dashboards (default: True)
                - stale_days: Days before considering stale (default: 30)
                - check_duplicates: Check for duplicates (default: True)
            context: Additional context from registry

        Returns:
            AnalysisResult with dashboard audit data
        """
        try:
            # Extract parameters
            namespace = parameters.get("namespace")
            check_stale = parameters.get("check_stale", True)
            stale_days = parameters.get("stale_days", 30)
            check_duplicates = parameters.get("check_duplicates", True)

            # Get list of dashboards from Grafana
            dashboards = await self._get_dashboards(namespace)

            # Perform audit checks
            coverage_analysis = self._analyze_coverage(dashboards, project)

            health_analysis = await self._analyze_health(dashboards)

            duplicate_analysis = []
            if check_duplicates:
                duplicate_analysis = self._detect_duplicates(dashboards)

            stale_analysis = []
            if check_stale:
                stale_analysis = self._detect_stale(dashboards, stale_days)

            # Calculate overall score
            overall_score = self._calculate_overall_score(
                coverage_analysis, health_analysis, duplicate_analysis, stale_analysis
            )

            # Generate grade
            grade = self._calculate_grade(overall_score)

            # Calculate confidence
            confidence = self._calculate_confidence(dashboards)

            # Generate warnings
            warnings = self._generate_warnings(
                coverage_analysis, health_analysis, stale_analysis
            )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data={
                    "project": project,
                    "namespace": namespace,
                    "total_dashboards": len(dashboards),
                    "coverage_analysis": coverage_analysis,
                    "health_analysis": health_analysis,
                    "duplicate_analysis": duplicate_analysis,
                    "stale_analysis": stale_analysis,
                    "overall_score": overall_score,
                    "grade": grade,
                },
                warnings=warnings,
                metadata={
                    "project": project,
                    "namespace": namespace,
                    "stale_days": stale_days,
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
        """Generate recommendations based on dashboard audit.

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
        coverage = data.get("coverage_analysis", {})
        health = data.get("health_analysis", {})
        stale = data.get("stale_analysis", [])
        duplicates = data.get("duplicate_analysis", [])

        # Check for missing dashboards
        missing = coverage.get("missing_dashboards", [])
        if missing:
            recommendations.append(
                Recommendation(
                    title="Missing Required Dashboards",
                    description=f"{len(missing)} required dashboards are missing: "
                    f"{', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
                    priority=SkillPriority.HIGH,
                    action_type="create",
                    estimated_effort="2-4 hours per dashboard",
                    risk_level="medium",
                    commands=[
                        "Use standard dashboard templates",
                        "Import from dashboard library",
                        "Customize for service needs",
                    ],
                    references=["https://grafana.com/grafana/dashboards/"],
                )
            )

        # Check for unhealthy dashboards
        unhealthy_count = len(
            [d for d in health.get("dashboards", []) if not d.get("healthy", True)]
        )
        if unhealthy_count > 0:
            recommendations.append(
                Recommendation(
                    title="Unhealthy Dashboards Detected",
                    description=f"{unhealthy_count} dashboards have health issues: "
                    f"broken queries, missing data sources, or invalid panels.",
                    priority=SkillPriority.MEDIUM,
                    action_type="fix",
                    estimated_effort="1-2 hours",
                    risk_level="low",
                    commands=[
                        "Review data source connections",
                        "Fix broken queries",
                        "Update panel configurations",
                    ],
                )
            )

        # Check for stale dashboards
        if stale:
            recommendations.append(
                Recommendation(
                    title="Stale Dashboards Found",
                    description=f"{len(stale)} dashboards haven't been queried in "
                    f"{data.get('metadata', {}).get('stale_days', 30)} days. "
                    f"Consider archiving or updating.",
                    priority=SkillPriority.LOW,
                    action_type="review",
                    estimated_effort="30 minutes per dashboard",
                    risk_level="low",
                    commands=[
                        "Review dashboard usage",
                        "Archive if unused",
                        "Update if still relevant",
                    ],
                )
            )

        # Check for duplicate dashboards
        if duplicates:
            recommendations.append(
                Recommendation(
                    title="Duplicate Dashboards Detected",
                    description=f"{len(duplicates)} duplicate or overlapping dashboards found. "
                    f"Consolidate to reduce maintenance overhead.",
                    priority=SkillPriority.LOW,
                    action_type="consolidate",
                    estimated_effort="1-2 hours",
                    risk_level="low",
                    commands=[
                        "Review duplicate dashboards",
                        "Merge where appropriate",
                        "Archive redundant versions",
                    ],
                )
            )

        # Overall score recommendation
        overall_score = data.get("overall_score", 0)
        if overall_score < 70:
            recommendations.append(
                Recommendation(
                    title="Improve Dashboard Coverage",
                    description=f"Overall dashboard score is {overall_score}/100. "
                    f"Focus on creating missing dashboards and fixing health issues.",
                    priority=SkillPriority.MEDIUM,
                    action_type="improve",
                    estimated_effort="1-2 days",
                    risk_level="medium",
                    commands=[
                        "Create missing dashboards",
                        "Fix health issues",
                        "Archive stale dashboards",
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

        # Validate stale_days
        stale_days = parameters.get("stale_days", 30)
        if not isinstance(stale_days, int) or stale_days < 1:
            errors.append("stale_days must be a positive integer")

        # Validate boolean parameters
        for param in ["check_stale", "check_duplicates"]:
            value = parameters.get(param)
            if value is not None and not isinstance(value, bool):
                errors.append(f"{param} must be a boolean")

        return len(errors) == 0, errors

    async def _get_dashboards(self, namespace: Optional[str]) -> list[dict[str, Any]]:
        """Get list of dashboards from Grafana.

        Args:
            namespace: Optional namespace filter

        Returns:
            List of dashboard metadata
        """
        # In real implementation, query Grafana API:
        # dashboards = await self.grafana_client.list_dashboards(folder=namespace)

        # Mock implementation
        return [
            {
                "uid": "abc123",
                "title": "Backend API Overview",
                "folder": "Services",
                "url": "/d/abc123/backend-api-overview",
                "created_at": "2026-07-01T00:00:00Z",
                "updated_at": "2026-08-20T10:30:00Z",
                "healthy": True,
                "panels": ["Request Rate", "Error Rate", "Latency"],
            },
            {
                "uid": "def456",
                "title": "Database Metrics",
                "folder": "Infrastructure",
                "url": "/d/def456/database-metrics",
                "created_at": "2026-06-15T00:00:00Z",
                "updated_at": "2026-08-01T15:45:00Z",
                "healthy": False,
                "panels": ["Connections", "Query Latency", "Slow Queries"],
            },
            {
                "uid": "ghi789",
                "title": "Frontend Performance",
                "folder": "Services",
                "url": "/d/ghi789/frontend-performance",
                "created_at": "2026-07-10T00:00:00Z",
                "updated_at": "2026-07-10T12:00:00Z",
                "healthy": True,
                "panels": ["Page Load Time", "API Calls"],
            },
            {
                "uid": "jkl012",
                "title": "SLO Dashboard",
                "folder": "SLO",
                "url": "/d/jkl012/slo-dashboard",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-22T09:00:00Z",
                "healthy": True,
                "panels": ["SLO Status", "Error Budget"],
            },
        ]

    def _analyze_coverage(
        self, dashboards: list[dict], project: str
    ) -> dict[str, Any]:
        """Analyze dashboard coverage for services.

        Args:
            dashboards: List of dashboards
            project: Project name

        Returns:
            Coverage analysis dictionary
        """
        # Expected dashboards for a typical service
        expected_dashboards = [
            f"{project} Overview",
            f"{project} SLO",
            f"{project} Resources",
            "Infrastructure Overview",
        ]

        existing_titles = [d.get("title", "") for d in dashboards]
        missing = [d for d in expected_dashboards if d not in existing_titles]

        # Calculate coverage percentage
        coverage_percent = (len(dashboards) / len(expected_dashboards) * 100) if expected_dashboards else 100

        # Analyze by service
        services = {}
        for dashboard in dashboards:
            folder = dashboard.get("folder", "General")
            if folder not in services:
                services[folder] = []
            services[folder].append(dashboard.get("title"))

        return {
            "expected_count": len(expected_dashboards),
            "existing_count": len(dashboards),
            "missing_dashboards": missing,
            "coverage_percent": coverage_percent,
            "by_service": services,
        }

    async def _analyze_health(
        self, dashboards: list[dict]
    ) -> dict[str, Any]:
        """Analyze dashboard health.

        Args:
            dashboards: List of dashboards

        Returns:
            Health analysis dictionary
        """
        healthy_dashboards = []
        unhealthy_dashboards = []

        for dashboard in dashboards:
            is_healthy = dashboard.get("healthy", True)

            # Check for common health issues
            issues = []
            if not is_healthy:
                issues.append("Data source connection failed")

            # Check if dashboard has minimal required panels
            panels = dashboard.get("panels", [])
            if len(panels) < 2:
                issues.append("Insufficient panels")
                is_healthy = False

            dashboard_info = {
                "uid": dashboard.get("uid"),
                "title": dashboard.get("title"),
                "healthy": is_healthy,
                "issues": issues,
            }

            if is_healthy:
                healthy_dashboards.append(dashboard_info)
            else:
                unhealthy_dashboards.append(dashboard_info)

        return {
            "total": len(dashboards),
            "healthy": len(healthy_dashboards),
            "unhealthy": len(unhealthy_dashboards),
            "dashboards": healthy_dashboards + unhealthy_dashboards,
        }

    def _detect_duplicates(self, dashboards: list[dict]) -> list[dict[str, Any]]:
        """Detect duplicate or overlapping dashboards.

        Args:
            dashboards: List of dashboards

        Returns:
            List of duplicate groups
        """
        duplicates = []
        seen = {}

        for dashboard in dashboards:
            title = dashboard.get("title", "").lower()

            # Check for similar titles
            for existing_title in seen.keys():
                similarity = self._calculate_similarity(title, existing_title)
                if similarity > 0.8:  # 80% similarity threshold
                    duplicates.append(
                        {
                            "dashboard_1": seen[existing_title],
                            "dashboard_2": dashboard,
                            "similarity": similarity,
                        }
                    )

            seen[title] = dashboard

        return duplicates

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score between 0 and 1
        """
        # Simple implementation using word overlap
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _detect_stale(
        self, dashboards: list[dict], stale_days: int
    ) -> list[dict[str, Any]]:
        """Detect stale dashboards.

        Args:
            dashboards: List of dashboards
            stale_days: Days before considering stale

        Returns:
            List of stale dashboards
        """
        from datetime import datetime, timezone

        stale = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=stale_days)

        for dashboard in dashboards:
            updated_str = dashboard.get("updated_at")
            if not updated_str:
                continue

            try:
                updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                if updated_at < cutoff_date:
                    days_stale = (datetime.now(timezone.utc) - updated_at).days
                    stale.append(
                        {
                            "uid": dashboard.get("uid"),
                            "title": dashboard.get("title"),
                            "last_updated": updated_str,
                            "days_stale": days_stale,
                        }
                    )
            except (ValueError, AttributeError):
                continue

        return stale

    def _calculate_overall_score(
        self,
        coverage: dict,
        health: dict,
        duplicates: list,
        stale: list,
    ) -> float:
        """Calculate overall dashboard score.

        Args:
            coverage: Coverage analysis
            health: Health analysis
            duplicates: Duplicate analysis
            stale: Stale analysis

        Returns:
            Overall score between 0 and 100
        """
        score = 100.0

        # Deduct for missing dashboards
        missing_count = len(coverage.get("missing_dashboards", []))
        score -= missing_count * 10

        # Deduct for unhealthy dashboards
        unhealthy_count = health.get("unhealthy", 0)
        score -= unhealthy_count * 5

        # Deduct for duplicates
        score -= len(duplicates) * 5

        # Deduct for stale dashboards
        score -= len(stale) * 2

        # Add bonus for high coverage
        if coverage.get("coverage_percent", 0) >= 100:
            score += 5

        return max(0, min(100, score))

    def _calculate_grade(self, score: float) -> str:
        """Calculate letter grade from score.

        Args:
            score: Overall score

        Returns:
            Letter grade
        """
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _calculate_confidence(self, dashboards: list) -> float:
        """Calculate confidence in the analysis.

        Args:
            dashboards: List of dashboards

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5

        # Increase confidence with more dashboards
        if len(dashboards) > 10:
            confidence += 0.3
        elif len(dashboards) > 5:
            confidence += 0.2

        # Increase confidence if we have health data
        if any(d.get("healthy") is not None for d in dashboards):
            confidence += 0.1

        # Increase confidence if we have update timestamps
        if any(d.get("updated_at") for d in dashboards):
            confidence += 0.1

        return min(confidence, 1.0)

    def _generate_warnings(
        self, coverage: dict, health: dict, stale: list
    ) -> list[str]:
        """Generate warnings based on analysis.

        Args:
            coverage: Coverage analysis
            health: Health analysis
            stale: Stale dashboards

        Returns:
            List of warning messages
        """
        warnings = []

        missing = coverage.get("missing_dashboards", [])
        if missing:
            warnings.append(f"{len(missing)} required dashboards are missing")

        unhealthy = health.get("unhealthy", 0)
        if unhealthy > 0:
            warnings.append(f"{unhealthy} dashboards have health issues")

        if stale:
            warnings.append(f"{len(stale)} dashboards are stale")

        return warnings

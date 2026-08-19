"""Dependency Health Skill - Monitor health of service dependencies.

This skill analyzes dependency health to:
- Check upstream service health
- Monitor downstream service availability
- Identify dependency bottlenecks
- Track cascading failure risks
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import settings
from app.skills.base import (
    BaseSkill,
    SkillConfig,
    SkillCategory,
    SkillPriority,
    AnalysisResult,
    Recommendation,
)

logger = logging.getLogger(__name__)


class DependencyHealthSkill(BaseSkill):
    """Monitor health of service dependencies.

    This skill analyzes:
    - Upstream service health
    - Downstream service availability
    - Database connection health
    - External API dependencies
    - Network latency between services

    Requires:
    - Service dependency graph
    - Health check endpoints
    - Network metrics
    - External dependency monitoring
    """

    skill_id = "reliability_dependency_health"
    name = "Dependency Health Monitor"
    description = "Monitor health of service dependencies and identify risks"
    category = SkillCategory.RELIABILITY
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        """Initialize the Dependency Health skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze dependency health.

        Args:
            project: Project/service name
            parameters: Analysis parameters
            context: Additional context

        Returns:
            AnalysisResult with dependency health data
        """
        try:
            logger.info(f"Analyzing dependency health for {project}")

            # Get service dependencies
            dependencies = await self._get_dependencies(project, context)

            # Check upstream services
            upstream_health = await self._check_upstream_health(
                dependencies["upstream"],
                context
            )

            # Check downstream services
            downstream_health = await self._check_downstream_health(
                dependencies["downstream"],
                context
            )

            # Check database connections
            database_health = await self._check_database_health(
                dependencies["databases"],
                context
            )

            # Check external APIs
            external_health = await self._check_external_apis(
                dependencies["external_apis"],
                context
            )

            # Calculate overall health score
            health_score = self._calculate_health_score(
                upstream_health,
                downstream_health,
                database_health,
                external_health,
            )

            # Identify critical issues
            critical_issues = self._identify_critical_issues(
                upstream_health,
                downstream_health,
                database_health,
                external_health,
            )

            # Generate recommendations
            recommendations = self._generate_recommendations(
                health_score,
                critical_issues,
                dependencies,
            )

            # Build result
            data = {
                "dependencies": dependencies,
                "upstream_health": upstream_health,
                "downstream_health": downstream_health,
                "database_health": database_health,
                "external_health": external_health,
                "health_score": health_score,
                "critical_issues": critical_issues,
                "analysis_timestamp": datetime.now().isoformat(),
            }

            confidence = 0.75

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=confidence,
                data=data,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Dependency health analysis failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                confidence=0.0,
                data={"error": str(e)},
                recommendations=[],
            )

    async def _get_dependencies(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get service dependency graph from configuration.

        Returns:
            Dict with dependency lists organized by type
        """
        # Build dependency list from configuration
        dependencies = {
            "upstream": [],
            "downstream": [],
            "databases": [],
            "external_apis": [],
        }

        # Process internal services
        for service_id, base_url in settings.INTERNAL_SERVICES.items():
            service_info = {
                "service_id": service_id,
                "name": service_id.replace("-", " ").replace("_", " ").title(),
                "type": "internal",
                "critical": service_id in ["auth-service", "postgres-primary"],
                "endpoint": f"{base_url}/health",
            }
            # Categorize based on service type
            if "postgres" in service_id or "mysql" in service_id or "mongo" in service_id:
                service_info["connection_string"] = base_url.replace("http://", "").replace("https://", "")
                dependencies["databases"].append(service_info)
            elif "redis" in service_id:
                service_info["connection_string"] = base_url.replace("http://", "").replace("https://", "")
                dependencies["databases"].append(service_info)
            elif "auth" in service_id:
                dependencies["upstream"].append(service_info)
            else:
                dependencies["downstream"].append(service_info)

        # Process external endpoints
        for service_id, base_url in settings.EXTERNAL_ENDPOINTS.items():
            dependencies["external_apis"].append({
                "service_id": f"{service_id}-api",
                "name": service_id.replace("-", " ").replace("_", " ").title() + " API",
                "type": "external",
                "critical": True,
                "endpoint": base_url,
            })

        return dependencies

    async def _check_upstream_health(
        self,
        upstream_services: List[Dict[str, Any]],
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check health of upstream services.

        Returns:
            Dict with upstream health data
        """
        health_results = []

        for service in upstream_services:
            # Mock health check - real implementation would call health endpoint
            is_healthy = service["service_id"] != "auth-service"  # Mock issue
            latency_ms = 50 if is_healthy else 5000

            health_results.append({
                "service_id": service["service_id"],
                "name": service["name"],
                "healthy": is_healthy,
                "latency_ms": latency_ms,
                "status": "down" if not is_healthy else "healthy",
                "critical": service.get("critical", False),
            })

        return {
            "total_services": len(upstream_services),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [r for r in health_results if not r["healthy"] and r["critical"]],
            "results": health_results,
        }

    async def _check_downstream_health(
        self,
        downstream_services: List[Dict[str, Any]],
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check health of downstream services.

        Returns:
            Dict with downstream health data
        """
        health_results = []

        for service in downstream_services:
            # Mock health check
            is_healthy = True
            latency_ms = 75

            health_results.append({
                "service_id": service["service_id"],
                "name": service["name"],
                "healthy": is_healthy,
                "latency_ms": latency_ms,
                "status": "healthy",
                "critical": service.get("critical", False),
            })

        return {
            "total_services": len(downstream_services),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [],
            "results": health_results,
        }

    async def _check_database_health(
        self,
        databases: List[Dict[str, Any]],
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check database connection health.

        Returns:
            Dict with database health data
        """
        health_results = []

        for db in databases:
            # Mock health check
            is_healthy = db["service_id"] != "postgres-primary"  # Mock issue
            latency_ms = 10 if is_healthy else 100
            connection_count = 50 if is_healthy else 0

            health_results.append({
                "service_id": db["service_id"],
                "name": db["name"],
                "healthy": is_healthy,
                "latency_ms": latency_ms,
                "connection_count": connection_count,
                "status": "down" if not is_healthy else "healthy",
                "critical": db.get("critical", False),
            })

        return {
            "total_databases": len(databases),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [r for r in health_results if not r["healthy"] and r["critical"]],
            "results": health_results,
        }

    async def _check_external_apis(
        self,
        external_apis: List[Dict[str, Any]],
        context: Optional[dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check external API availability.

        Returns:
            Dict with external API health data
        """
        health_results = []

        for api in external_apis:
            # Mock health check - check if API is reachable
            is_healthy = True
            latency_ms = 200

            health_results.append({
                "service_id": api["service_id"],
                "name": api["name"],
                "healthy": is_healthy,
                "latency_ms": latency_ms,
                "status": "healthy",
                "critical": api.get("critical", False),
            })

        return {
            "total_apis": len(external_apis),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [],
            "results": health_results,
        }

    def _calculate_health_score(
        self,
        upstream_health: Dict[str, Any],
        downstream_health: Dict[str, Any],
        database_health: Dict[str, Any],
        external_health: Dict[str, Any],
    ) -> float:
        """Calculate overall dependency health score.

        Returns:
            Health score (0.0 to 1.0)
        """
        total_dependencies = (
            upstream_health["total_services"] +
            downstream_health["total_services"] +
            database_health["total_databases"] +
            external_health["total_apis"]
        )

        total_healthy = (
            upstream_health["healthy_count"] +
            downstream_health["healthy_count"] +
            database_health["healthy_count"] +
            external_health["healthy_count"]
        )

        if total_dependencies == 0:
            return 1.0

        return total_healthy / total_dependencies

    def _identify_critical_issues(
        self,
        upstream_health: Dict[str, Any],
        downstream_health: Dict[str, Any],
        database_health: Dict[str, Any],
        external_health: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Identify critical dependency issues.

        Returns:
            List of critical issues
        """
        critical_issues = []

        # Check unhealthy critical dependencies
        for health_data in [upstream_health, database_health, external_health]:
            for issue in health_data.get("unhealthy_critical", []):
                critical_issues.append({
                    "service_id": issue["service_id"],
                    "name": issue["name"],
                    "severity": "critical",
                    "description": f"Critical dependency '{issue['name']}' is unhealthy",
                })

        # Check high latency
        for health_data in [upstream_health, downstream_health]:
            for result in health_data.get("results", []):
                if result.get("latency_ms", 0) > 1000:
                    critical_issues.append({
                        "service_id": result["service_id"],
                        "name": result["name"],
                        "severity": "warning",
                        "description": f"High latency to '{result['name']}': {result['latency_ms']}ms",
                    })

        return critical_issues

    def _generate_recommendations(
        self,
        health_score: float,
        critical_issues: List[Dict[str, Any]],
        dependencies: Dict[str, Any],
    ) -> List[Recommendation]:
        """Generate dependency health recommendations.

        Returns:
            List of recommendations
        """
        recommendations = []

        # Critical issue recommendations
        for issue in critical_issues:
            if issue["severity"] == "critical":
                recommendations.append(Recommendation(
                    title=f"Fix critical dependency: {issue['name']}",
                    description=issue["description"],
                    impact="critical",
                    effort="high",
                    priority="critical",
                    actions=[
                        "Check service logs for errors",
                        "Verify network connectivity",
                        "Restart service if needed",
                        "Escalate to service owner",
                    ],
                ))

        # Low overall health score
        if health_score < 0.8:
            recommendations.append(Recommendation(
                title="Improve dependency health",
                description=f"Overall dependency health is {health_score:.1%}",
                impact="high",
                effort="medium",
                priority="high",
                actions=[
                    "Review all unhealthy dependencies",
                    "Implement circuit breakers",
                    "Add fallback mechanisms",
                    "Increase monitoring coverage",
                ],
            ))

        # General monitoring recommendations
        recommendations.append(Recommendation(
            title="Set up dependency health monitoring",
            description="Create visibility into dependency health",
            impact="medium",
            effort="low",
            priority="medium",
            actions=[
                "Create dependency health dashboard",
                "Set up alerts for unhealthy dependencies",
                "Implement synthetic health checks",
            ],
        ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate skill parameters.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        # No specific validation required
        return True, []

"""Dependency Health Skill - Monitor health of service dependencies.

This skill analyzes dependency health to:
- Check upstream service health
- Monitor downstream service availability
- Identify dependency bottlenecks
- Track cascading failure risks
"""

import logging
from datetime import datetime
from typing import Any

from app.config import settings
from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
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

    def __init__(self, config: SkillConfig | None = None):
        """Initialize the Dependency Health skill."""
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
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
        context: dict[str, Any] | None,
    ) -> dict[str, list[dict[str, Any]]]:
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
            if "postgres" in service_id or "mysql" in service_id or "mongo" in service_id or "redis" in service_id:
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

    async def _probe(self, endpoint: str) -> dict[str, Any]:
        """Real HTTP health probe (Phase 13): GET the endpoint, report
        reachability + latency. Any error degrades to unhealthy with the
        reason — never a fabricated healthy state."""
        import time as time_module

        import httpx

        start = time_module.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(endpoint)
            latency_ms = int((time_module.monotonic() - start) * 1000)
            healthy = resp.status_code < 500
            return {
                "healthy": healthy,
                "latency_ms": latency_ms,
                "detail": f"HTTP {resp.status_code}",
            }
        except Exception as e:
            latency_ms = int((time_module.monotonic() - start) * 1000)
            return {"healthy": False, "latency_ms": latency_ms, "detail": str(e)[:120]}

    async def _check_upstream_health(
        self,
        upstream_services: list[dict[str, Any]],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Probe upstream services' health endpoints."""
        health_results = []
        for service in upstream_services:
            probe = await self._probe(service["endpoint"])
            health_results.append({
                "service_id": service["service_id"],
                "name": service["name"],
                "healthy": probe["healthy"],
                "latency_ms": probe["latency_ms"],
                "status": "healthy" if probe["healthy"] else "down",
                "detail": probe["detail"],
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
        downstream_services: list[dict[str, Any]],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Probe downstream services' health endpoints."""
        health_results = []
        for service in downstream_services:
            probe = await self._probe(service["endpoint"])
            health_results.append({
                "service_id": service["service_id"],
                "name": service["name"],
                "healthy": probe["healthy"],
                "latency_ms": probe["latency_ms"],
                "status": "healthy" if probe["healthy"] else "down",
                "detail": probe["detail"],
                "critical": service.get("critical", False),
            })
        return {
            "total_services": len(downstream_services),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [r for r in health_results if not r["healthy"] and r["critical"]],
            "results": health_results,
        }

    async def _check_database_health(
        self,
        databases: list[dict[str, Any]],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Probe database service health endpoints (HTTP surface only —
        deep connection-pool metrics need an exporter, not fabricated here)."""
        health_results = []
        for db in databases:
            probe = await self._probe(db["endpoint"])
            health_results.append({
                "service_id": db["service_id"],
                "name": db["name"],
                "healthy": probe["healthy"],
                "latency_ms": probe["latency_ms"],
                "detail": probe["detail"],
                "status": "healthy" if probe["healthy"] else "down",
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
        external_apis: list[dict[str, Any]],
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Probe external API availability."""
        health_results = []
        for api in external_apis:
            probe = await self._probe(api["endpoint"])
            health_results.append({
                "service_id": api["service_id"],
                "name": api["name"],
                "healthy": probe["healthy"],
                "latency_ms": probe["latency_ms"],
                "status": "healthy" if probe["healthy"] else "unreachable",
                "detail": probe["detail"],
                "critical": api.get("critical", False),
            })
        return {
            "total_apis": len(external_apis),
            "healthy_count": sum(1 for r in health_results if r["healthy"]),
            "unhealthy_critical": [r for r in health_results if not r["healthy"] and r["critical"]],
            "results": health_results,
        }

    def _calculate_health_score(
        self,
        upstream_health: dict[str, Any],
        downstream_health: dict[str, Any],
        database_health: dict[str, Any],
        external_health: dict[str, Any],
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
        upstream_health: dict[str, Any],
        downstream_health: dict[str, Any],
        database_health: dict[str, Any],
        external_health: dict[str, Any],
    ) -> list[dict[str, Any]]:
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
        critical_issues: list[dict[str, Any]],
        dependencies: dict[str, Any],
    ) -> list[Recommendation]:
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
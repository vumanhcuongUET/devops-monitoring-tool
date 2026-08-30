"""Deployment Health Check Skill - Check health status of deployments."""

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


class DeploymentHealthCheckSkill(BaseSkill):
    """Check health status of Kubernetes deployments.

    This skill analyzes:
    - Deployment availability
    - Pod health and restarts
    - Rolling deployment status
    - Rollback readiness
    """

    skill_id = "devops_deployment_health_check"
    name = "Deployment Health Check"
    description = "Check health status of Kubernetes deployments and provide rollback recommendations"
    category = SkillCategory.DEVOPS
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Check deployment health.

        Args:
            project: Project name
            parameters: Check parameters
                - namespace: Namespace to check (default: all)
                - deployment: Specific deployment (optional)
            context: Registry context

        Returns:
            AnalysisResult with health status
        """
        try:
            namespace = parameters.get("namespace")
            deployment = parameters.get("deployment")

            # Fetch deployment status
            deployments = await self._fetch_deployment_status(
                project, namespace, deployment, context
            )

            # Analyze health
            health_status = self._analyze_health(deployments)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "deployments": deployments,
                    "health_status": health_status,
                    "project": project,
                },
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Deployment health check failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate health recommendations.

        Args:
            analysis_id: Analysis ID
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

        for deployment in data["deployments"]:
            if deployment["health"] == "unhealthy":
                recommendations.append(Recommendation(
                    title=f"Fix unhealthy deployment: {deployment['name']}",
                    description=deployment["reason"],
                    priority=SkillPriority.HIGH,
                    action_type="manual",
                    estimated_effort="30 minutes",
                    risk_level="medium",
                    commands=[
                        "# Check deployment status",
                        f"kubectl get deployment {deployment['name']} -n {deployment['namespace']}",
                        "# View pod logs",
                        f"kubectl logs -l app={deployment['name']} -n {deployment['namespace']}",
                    ],
                ))

        return recommendations

    async def _fetch_deployment_status(
        self,
        project: str,
        namespace: str | None,
        deployment: str | None,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Fetch deployment status from Kubernetes.

        Phase 13: real data via the k8s client injected by the skills API as
        context["clients"]["k8s"].
        """
        clients = (context or {}).get("clients") or {}
        k8s = clients.get("k8s")
        if k8s is None:
            raise RuntimeError(
                "No Kubernetes client in context['clients']['k8s'] — skill requires a live K8s connection"
            )
        deployments = await k8s.list_deployments(namespace)
        if deployment:
            deployments = [d for d in deployments if d["name"] == deployment]
        return deployments

    def _analyze_health(self, deployments: list) -> dict[str, Any]:
        """Stamp health + reason per deployment; return summary counts."""
        healthy = degraded = unhealthy = 0
        for d in deployments:
            available, replicas = d.get("available", 0), d.get("replicas", 0)
            if replicas == 0:
                d["health"], d["reason"] = "pending", "scaled to zero"
                degraded += 1
            elif available >= replicas:
                d["health"], d["reason"] = "healthy", "all replicas available"
                healthy += 1
            elif available > 0:
                d["health"] = "unhealthy"
                d["reason"] = f"{available}/{replicas} replicas available"
                unhealthy += 1
            else:
                d["health"] = "unhealthy"
                d["reason"] = f"0 of {replicas} replicas available"
                unhealthy += 1
        return {"healthy": healthy, "unhealthy": unhealthy, "pending": degraded}

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []

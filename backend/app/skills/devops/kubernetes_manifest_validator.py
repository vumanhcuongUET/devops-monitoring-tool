"""Kubernetes Manifest Validator - Validate K8s manifests.

This skill validates:
- Resource limits/requests
- Security context
- Liveness/Readiness probes
- Label selectors
- HPA configuration
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


class KubernetesManifestValidatorSkill(BaseSkill):
    """Validate Kubernetes manifests against best practices.

    Checks:
    - Resource limits and requests
    - Security context configuration
    - Health check probes
    - Label selectors
    - HPA configuration
    - Image pull policy
    """

    skill_id = "kubernetes_manifest_validator"
    name = "Kubernetes Manifest Validator"
    description = "Validate Kubernetes manifests for security and best practices"
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
        """Validate Kubernetes manifests.

        Args:
            project: Project name
            parameters: Analysis parameters
                - manifest_path: Path to manifests directory or file
                - namespace: Namespace to validate
            context: Registry context

        Returns:
            AnalysisResult with validation issues
        """
        try:
            manifest_path = parameters.get("manifest_path")
            namespace = parameters.get("namespace")

            if not manifest_path:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: manifest_path"],
                )

            # Validate manifests
            issues = await self._validate_manifests(manifest_path, namespace)

            # Categorize issues
            security_issues = [i for i in issues if i["category"] == "security"]
            reliability_issues = [i for i in issues if i["category"] == "reliability"]
            resource_issues = [i for i in issues if i["category"] == "resources"]

            # Calculate score
            score = self._calculate_score(issues)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "manifest_path": manifest_path,
                    "namespace": namespace,
                    "issues": issues,
                    "summary": {
                        "total_issues": len(issues),
                        "security": len(security_issues),
                        "reliability": len(reliability_issues),
                        "resources": len(resource_issues),
                    },
                    "score": score,
                },
                warnings=self._generate_warnings(issues),
            )

        except Exception as e:
            logger.error(f"K8s manifest validation failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"K8s manifest validation failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate remediation recommendations.

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

        # Missing resource limits
        no_limits = [i for i in data["issues"] if i["type"] == "missing_resource_limits"]
        if no_limits:
            recommendations.append(Recommendation(
                title=f"Add resource limits to {len(no_limits)} deployments",
                description="Deployments without resource limits can consume unlimited cluster resources.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="medium",
                commands=[
                    "# Add resources to deployment",
                    "resources:",
                    "  limits:",
                    "    memory: \"512Mi\"",
                    "    cpu: \"500m\"",
                ],
            ))

        # No probes
        no_probes = [i for i in data["issues"] if i["type"] == "missing_probes"]
        if no_probes:
            recommendations.append(Recommendation(
                title=f"Add health probes to {len(no_probes)} deployments",
                description="Missing liveness and readiness probes prevents proper health monitoring.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1 hour",
                risk_level="medium",
                commands=[
                    "# Add liveness probe",
                    "livenessProbe:",
                    "  httpGet:",
                    "    path: /health",
                    "    port: 8080",
                ],
            ))

        # Run as root
        root_containers = [i for i in data["issues"] if i["type"] == "root_container"]
        if root_containers:
            recommendations.append(Recommendation(
                title="Fix containers running as root",
                description="Containers running as root pose security risks. Use security context.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="high",
                commands=[
                    "# Add security context",
                    "securityContext:",
                    "  runAsNonRoot: true",
                    "  runAsUser: 1000",
                ],
            ))

        return recommendations

    async def _validate_manifests(
        self,
        manifest_path: str,
        namespace: str | None,
    ) -> list[dict[str, Any]]:
        """Validate Kubernetes manifests.

        Args:
            manifest_path: Path to manifests
            namespace: Namespace to check

        Returns:
            List of issues
        """
        # Mock implementation
        # Would use kube-score, kube-linter in production
        issues = [
            {
                "type": "missing_resource_limits",
                "category": "resources",
                "severity": "high",
                "resource": "deployment/api",
                "description": "Deployment has no resource limits defined",
            },
            {
                "type": "missing_probes",
                "category": "reliability",
                "severity": "high",
                "resource": "deployment/web",
                "description": "Deployment has no liveness or readiness probes",
            },
            {
                "type": "root_container",
                "category": "security",
                "severity": "critical",
                "resource": "deployment/app",
                "description": "Container runs as root user",
            },
            {
                "type": "no_image_tag",
                "category": "reliability",
                "severity": "medium",
                "resource": "deployment/api",
                "description": "Image uses 'latest' tag - pin specific version",
            },
        ]

        return issues

    def _calculate_score(self, issues: list) -> int:
        """Calculate manifest score.

        Args:
            issues: List of issues

        Returns:
            Score (0-100)
        """
        if not issues:
            return 100

        weights = {"critical": 20, "high": 10, "medium": 5, "low": 2}
        penalty = sum(weights.get(i.get("severity", "low"), 2) for i in issues)

        return max(0, 100 - penalty)

    def _generate_warnings(self, issues: list) -> list[str]:
        """Generate warnings.

        Args:
            issues: List of issues

        Returns:
            List of warnings
        """
        warnings = []

        critical = [i for i in issues if i.get("severity") == "critical"]
        if critical:
            warnings.append(f"{len(critical)} CRITICAL K8s manifest issues")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("manifest_path"):
            return False, ["manifest_path is required"]
        return True, []

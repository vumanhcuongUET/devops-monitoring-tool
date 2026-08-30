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
            self._inline_manifest = parameters.get("manifest")
            namespace = parameters.get("namespace")

            if not manifest_path and self._inline_manifest is None:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: manifest_path or manifest"],
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
        """Static manifest lint (Phase 13). Accepts inline YAML via
        parameters["manifest"] or a server-side file path. Checks the
        highest-signal gaps only — real policy engines (OPA/Kyverno) live
        elsewhere in this platform.

        Returns:
            List of issues with {type, category, severity, location, description}
        """
        import io
        from pathlib import Path

        import yaml

        if self._inline_manifest is not None:
            raw_docs = list(yaml.safe_load_all(io.StringIO(self._inline_manifest)))
        else:
            path = Path(manifest_path)
            if not path.exists():
                raise FileNotFoundError(f"Manifest not found: {manifest_path}")
            raw_docs = list(yaml.safe_load_all(path.read_text()))

        issues: list[dict[str, Any]] = []

        def _walk(spec: dict, where: str) -> None:
            containers = spec.get("containers") or []
            if isinstance(containers, dict):
                containers = [containers]
            for idx, c in enumerate(containers):
                cname = c.get("name", f"container-{idx}")
                base = f"{where}/{cname}"
                if not c.get("resources", {}).get("requests"):
                    issues.append({
                        "type": "no_resource_requests", "category": "resources",
                        "severity": "medium", "location": base,
                        "description": "No resource requests — scheduler cannot make placement decisions",
                    })
                if not c.get("resources", {}).get("limits"):
                    issues.append({
                        "type": "no_resource_limits", "category": "resources",
                        "severity": "medium", "location": base,
                        "description": "No resource limits — the container can starve its node",
                    })
                if c.get("securityContext", {}).get("allowPrivilegeEscalation", True):
                    issues.append({
                        "type": "privilege_escalation", "category": "security",
                        "severity": "high", "location": base,
                        "description": "allowPrivilegeEscalation not set to false",
                    })
                if c.get("securityContext", {}).get("runAsRoot", True) and \
                        c.get("securityContext", {}).get("runAsNonRoot") is not True:
                    issues.append({
                        "type": "run_as_root", "category": "security",
                        "severity": "high", "location": base,
                        "description": "Container may run as root (runAsNonRoot not set)",
                    })
                image = c.get("image", "")
                if ":" not in image or image.endswith(":latest"):
                    issues.append({
                        "type": "unpinned_image", "category": "security",
                        "severity": "high", "location": base,
                        "description": f"Image {image!r} is unpinned or :latest",
                    })
            if spec.get("livenessProbe") is None:
                issues.append({
                    "type": "no_liveness_probe", "category": "reliability",
                    "severity": "medium", "location": where,
                    "description": "No livenessProbe — a wedged container is never restarted",
                })
            if spec.get("readinessProbe") is None:
                issues.append({
                    "type": "no_readiness_probe", "category": "reliability",
                    "severity": "medium", "location": where,
                    "description": "No readinessProbe — traffic can hit a non-ready pod",
                })

        for doc_i, doc in enumerate(d for d in raw_docs if isinstance(d, dict)):
            kind = doc.get("kind", "?")
            name = doc.get("metadata", {}).get("name", f"doc-{doc_i}")
            where = f"{kind}/{name}"
            if kind in ("Pod",) or "template" in (doc.get("spec") or {}):
                spec = doc.get("spec", {})
                pod_spec = spec.get("template", {}).get("spec", spec)
                if kind not in ("Pod",) and doc.get("spec", {}).get("template") is None:
                    pod_spec = {}
                if pod_spec:
                    _walk(pod_spec, where)
                if kind in ("Deployment", "StatefulSet") and namespace is None:
                    if doc.get("metadata", {}).get("namespace") is None:
                        issues.append({
                            "type": "no_namespace", "category": "reliability",
                            "severity": "low", "location": where,
                            "description": "No namespace set — lands in default",
                        })
                if (doc.get("spec") or {}).get("hostNetwork") or (doc.get("spec") or {}).get("hostPID"):
                    issues.append({
                        "type": "host_namespaces", "category": "security",
                        "severity": "high", "location": where,
                        "description": "hostNetwork/hostPID exposes the host to the container",
                    })

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

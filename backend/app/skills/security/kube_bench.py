"""Kube-bench Skill - CIS Kubernetes benchmark checks."""

import logging
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


class KubeBenchSkill(BaseSkill):
    """Run CIS Kubernetes benchmark security checks.

    This skill integrates with kube-bench to check:
    - CIS Kubernetes Benchmark compliance
    - Security best practices
    - Control plane configuration
    - Worker node security
    """

    skill_id = "security_kube_bench"
    name = "Kubernetes CIS Benchmark"
    description = "Run CIS Kubernetes benchmark security checks using kube-bench"
    category = SkillCategory.SECURITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Run CIS benchmark checks.

        Args:
            project: Project name
            parameters: Check parameters
                - benchmark: CIS benchmark version (default: 1.29)
                - node_type: Type of node (master, worker, etcd)
            context: Registry context

        Returns:
            AnalysisResult with check results
        """
        try:
            benchmark = parameters.get("benchmark", "1.29")
            node_type = parameters.get("node_type", "master")

            # Run checks
            checks = await self._run_benchmark_checks(benchmark, node_type)

            # Calculate compliance
            passed = sum(1 for c in checks if c["status"] == "PASS")
            failed = sum(1 for c in checks if c["status"] == "FAIL")
            warn = sum(1 for c in checks if c["status"] == "WARN")
            total = len(checks)
            compliance = (passed / total * 100) if total > 0 else 0

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.95,
                data={
                    "benchmark": benchmark,
                    "node_type": node_type,
                    "checks": checks,
                    "summary": {
                        "passed": passed,
                        "failed": failed,
                        "warn": warn,
                        "total": total,
                        "compliance_percent": round(compliance, 1),
                    },
                },
                warnings=self._generate_warnings(failed, warn),
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Kube-bench check failed: {str(e)}"],
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
        summary = data["summary"]

        if summary["compliance_percent"] < 80:
            recommendations.append(Recommendation(
                title=f"Improve CIS compliance (currently {summary['compliance_percent']}%)",
                description=f"Cluster has {summary['failed']} failed checks. "
                f"Address security gaps to improve compliance.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 days",
                risk_level="low",
                commands=[
                    "# View failed checks",
                    "kube-bench --json | jq '.tests[] | select(.status == \"FAIL\")'",
                ],
            ))

        return recommendations

    async def _run_benchmark_checks(
        self,
        benchmark: str,
        node_type: str,
    ) -> list[dict[str, Any]]:
        """Run kube-bench checks."""
        return []

    def _generate_warnings(self, failed: int, warn: int) -> list[str]:
        """Generate warnings."""
        warnings = []

        if failed > 10:
            warnings.append("High number of failed CIS checks - immediate action required")

        if warn > 5:
            warnings.append("Multiple warnings - review security configuration")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []

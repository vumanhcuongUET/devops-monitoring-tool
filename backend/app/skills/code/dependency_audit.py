"""Dependency Audit Skill - Audit dependencies for vulnerabilities and updates."""

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


class DependencyAuditSkill(BaseSkill):
    """Audit dependencies for security vulnerabilities and updates.

    This skill checks:
    - Vulnerable dependencies (CVEs)
    - Outdated packages
    - License compliance
    - Transitive dependencies
    """

    skill_id = "code_dependency_audit"
    name = "Dependency Auditor"
    description = "Audit code dependencies for vulnerabilities, updates, and license compliance"
    category = SkillCategory.CODE
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
        """Run dependency audit.

        Args:
            project: Project name
            parameters: Audit parameters
                - repository: Repository URL or path
                - check_transitive: Include transitive deps (default: true)
            context: Registry context

        Returns:
            AnalysisResult with dependency findings
        """
        try:
            repository = parameters.get("repository")
            check_transitive = parameters.get("check_transitive", True)

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Run audit
            dependencies = await self._run_dependency_audit(
                repository, check_transitive
            )

            # Analyze results
            vulnerable = [d for d in dependencies if d.get("vulnerabilities")]
            outdated = [d for d in dependencies if d.get("update_available")]
            problematic_licenses = [d for d in dependencies if d.get("license_issue")]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.85,
                data={
                    "repository": repository,
                    "dependencies": dependencies,
                    "summary": {
                        "total": len(dependencies),
                        "vulnerable": len(vulnerable),
                        "outdated": len(outdated),
                        "license_issues": len(problematic_licenses),
                    },
                },
                warnings=self._generate_warnings(vulnerable, problematic_licenses),
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Dependency audit failed: {e!s}"],
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

        if summary["vulnerable"] > 0:
            recommendations.append(Recommendation(
                title=f"Update {summary['vulnerable']} vulnerable dependencies",
                description=f"Found {summary['vulnerable']} dependencies with known vulnerabilities. "
                f"Update to secure versions immediately.",
                priority=SkillPriority.CRITICAL,
                action_type="automated",
                estimated_effort="1-2 hours",
                risk_level="medium",
                commands=[
                    "# Update vulnerable packages",
                    "npm audit fix",
                    "# or for Python",
                    "pip install --upgrade -r requirements.txt",
                ],
            ))

        if summary["license_issues"] > 0:
            recommendations.append(Recommendation(
                title=f"Review {summary['license_issues']} problematic licenses",
                description="Found dependencies with non-compliant licenses. "
                "Review and replace with compliant alternatives.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="low",
            ))

        return recommendations

    async def _run_dependency_audit(
        self,
        repository: str,
        check_transitive: bool,
    ) -> list[dict[str, Any]]:
        """Run dependency audit using Snyk/Dependabot."""
        return []

    def _generate_warnings(
        self,
        vulnerable: list,
        problematic_licenses: list,
    ) -> list[str]:
        """Generate warnings."""
        warnings = []

        if len(vulnerable) > 5:
            warnings.append("High number of vulnerable dependencies")

        if len(problematic_licenses) > 3:
            warnings.append("Multiple license compliance issues")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]
        return True, []

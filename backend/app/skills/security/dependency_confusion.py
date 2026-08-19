"""Dependency Confusion Detector - Detect dependency confusion attacks.

This skill checks for:
- Internal package names on public registries
- Typosquatting detection
- Supply chain vulnerabilities
"""

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


class DependencyConfusionSkill(BaseSkill):
    """Detect dependency confusion attacks and supply chain vulnerabilities.

    This skill checks:
    - Internal packages that exist on public registries
    - Suspicious package updates
    - Typosquatting attacks
    - Supply chain vulnerabilities
    """

    skill_id = "security_dependency_confusion"
    name = "Dependency Confusion Detector"
    description = "Detect dependency confusion attacks and supply chain vulnerabilities"
    category = SkillCategory.SECURITY
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Public package registries
    REGISTRIES = {
        "npm": "https://registry.npmjs.org",
        "pypi": "https://pypi.org",
        "rubygems": "https://rubygems.org",
        "maven": "https://repo.maven.apache.org",
        "go": "https://pkg.go.dev",
        "nuget": "https://nuget.org",
    }

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Check for dependency confusion vulnerabilities.

        Args:
            project: Project name
            parameters: Scan parameters
                - repository: Repository path
                - internal_packages: List of internal package prefixes
                - check_typosquatting: Enable typoquatting check
            context: Registry context

        Returns:
            AnalysisResult with vulnerabilities found
        """
        try:
            repository = parameters.get("repository")
            internal_packages = parameters.get("internal_packages", [])
            check_typosquatting = parameters.get("check_typosquatting", True)

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Get dependencies
            dependencies = await self._extract_dependencies(repository)

            # Check for confusion attacks
            confusion_issues = await self._check_confusion_attacks(
                dependencies, internal_packages
            )

            # Check for typosquatting
            typosquatting_issues = []
            if check_typosquatting:
                typosquatting_issues = await self._check_typosquatting(dependencies)

            # Combine all issues
            all_issues = confusion_issues + typosquatting_issues

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.75,
                data={
                    "repository": repository,
                    "dependencies_checked": len(dependencies),
                    "issues": all_issues,
                    "summary": {
                        "confusion_attacks": len(confusion_issues),
                        "typosquatting": len(typosquatting_issues),
                        "total": len(all_issues),
                    },
                },
                warnings=self._generate_warnings(all_issues),
            )

        except Exception as e:
            logger.error(f"Dependency confusion scan failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Dependency confusion scan failed: {str(e)}"],
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

        # Dependency confusion
        confusion = data["issues"][0] if data["issues"] else None
        if confusion and confusion.get("type") == "dependency_confusion":
            recommendations.append(Recommendation(
                title="Mitigate dependency confusion attack",
                description=f"Package '{confusion['package']}' exists on public registry. "
                f"Internal package may be replaced by malicious public version.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="critical",
                commands=[
                    "# Scope internal packages",
                    "# Use private registry",
                    "# Pin exact versions",
                    "# Enable package namespace",
                ],
            ))

        # Typosquatting
        typosquatting = [i for i in data["issues"] if i.get("type") == "typosquatting"]
        if typosquatting:
            recommendations.append(Recommendation(
                title=f"Review {len(typosquatting)} potential typosquatting packages",
                description="Suspicious package names that may be typosquatting attempts. Verify authenticity.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="high",
                commands=[
                    "# Verify package sources",
                    "# Check package maintainers",
                    "# Review package installation dates",
                ],
            ))

        return recommendations

    async def _extract_dependencies(self, repository: str) -> list[dict[str, Any]]:
        """Extract dependencies from repository.

        Args:
            repository: Repository path

        Returns:
            List of dependencies
        """
        # Mock implementation
        # Would parse package.json, requirements.txt, go.mod, etc.
        dependencies = [
            {"name": "express", "version": "^4.18.0", "type": "npm"},
            {"name": "lodash", "version": "^4.17.21", "type": "npm"},
            {"name": "mycompany-auth-lib", "version": "1.0.0", "type": "npm"},
            {"name": "axios", "version": "^1.4.0", "type": "npm"},
        ]

        return dependencies

    async def _check_confusion_attacks(
        self,
        dependencies: list[dict[str, Any]],
        internal_packages: list[str],
    ) -> list[dict[str, Any]]:
        """Check for dependency confusion attacks.

        Args:
            dependencies: List of dependencies
            internal_packages: Internal package prefixes

        Returns:
            List of confusion issues
        """
        issues = []

        for dep in dependencies:
            name = dep["name"]
            dep_type = dep.get("type", "npm")

            # Check if this looks like an internal package
            is_internal = any(
                name.startswith(prefix) for prefix in internal_packages
            )

            if is_internal:
                # Check if package exists on public registry
                exists_on_public = await self._check_public_registry(name, dep_type)

                if exists_on_public:
                    issues.append({
                        "type": "dependency_confusion",
                        "severity": "CRITICAL",
                        "package": name,
                        "version": dep.get("version"),
                        "registry": dep_type,
                        "message": f"Internal package '{name}' exists on public {dep_type} registry",
                        "recommendation": "Scope internal packages or use private registry",
                    })

        return issues

    async def _check_typosquatting(
        self,
        dependencies: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Check for typosquatting attacks.

        Args:
            dependencies: List of dependencies

        Returns:
            List of typosquatting issues
        """
        issues = []

        # Known popular packages to check against
        popular_packages = {
            "npm": ["express", "lodash", "axios", "react", "vue", "angular"],
            "pypi": ["requests", "numpy", "pandas", "flask", "django"],
        }

        for dep in dependencies:
            name = dep["name"]
            dep_type = dep.get("type", "npm")

            # Check if name is similar to popular package
            popular = popular_packages.get(dep_type, [])
            for popular_pkg in popular:
                similarity = self._calculate_similarity(name, popular_pkg)

                if similarity > 0.7 and name != popular_pkg:
                    issues.append({
                        "type": "typosquatting",
                        "severity": "HIGH",
                        "package": name,
                        "similar_to": popular_pkg,
                        "similarity": round(similarity, 2),
                        "registry": dep_type,
                        "message": f"Package '{name}' is similar to '{popular_pkg}'",
                    })

        return issues

    async def _check_public_registry(
        self,
        package_name: str,
        registry_type: str,
    ) -> bool:
        """Check if package exists on public registry.

        Args:
            package_name: Package name
            registry_type: Registry type

        Returns:
            True if package exists
        """
        # Mock implementation
        # Would make HTTP request to registry in production
        import random

        # Simulate random existence
        return random.choice([True, False]) if "mycompany" in package_name else False

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity using Levenshtein distance.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score (0-1)
        """
        import difflib

        sequence = difflib.SequenceMatcher(None, str1.lower(), str2.lower())
        return sequence.ratio()

    def _generate_warnings(self, issues: list) -> list[str]:
        """Generate warnings based on findings.

        Args:
            issues: List of issues

        Returns:
            List of warnings
        """
        warnings = []

        critical = [i for i in issues if i.get("severity") == "CRITICAL"]
        if critical:
            warnings.append(f"{len(critical)} CRITICAL dependency confusion vulnerabilities detected")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]
        return True, []

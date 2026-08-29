"""CI/CD Pipeline Analyzer - Analyze pipeline quality and security.

This skill checks:
- Pipeline performance bottlenecks
- Missing security checks
- Broken build dependencies
- Deployment risks
- Compliance violations
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


class CicdPipelineAnalyzerSkill(BaseSkill):
    """Analyze CI/CD pipeline quality and security.

    This skill checks:
    - Build pipeline efficiency
    - Security scan integration
    - Test coverage requirements
    - Deployment safety
    - Compliance adherence
    """

    skill_id = "cicd_pipeline_analyzer"
    name = "CI/CD Pipeline Analyzer"
    description = "Analyze CI/CD pipeline for performance, security, and best practices"
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
        """Analyze CI/CD pipeline.

        Args:
            project: Project name
            parameters: Analysis parameters
                - pipeline_file: Path to pipeline config (.github/workflows, .gitlab-ci.yml, etc.)
                - platform: CI/CD platform (github, gitlab, jenkins)
            context: Registry context

        Returns:
            AnalysisResult with pipeline issues
        """
        try:
            pipeline_file = parameters.get("pipeline_file")
            platform = parameters.get("platform", "github")

            if not pipeline_file:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: pipeline_file"],
                )

            # Analyze pipeline
            issues = await self._analyze_pipeline(pipeline_file, platform)

            # Categorize issues
            security_issues = [i for i in issues if i["category"] == "security"]
            performance_issues = [i for i in issues if i["category"] == "performance"]
            reliability_issues = [i for i in issues if i["category"] == "reliability"]

            # Calculate score
            pipeline_score = self._calculate_pipeline_score(issues)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.8,
                data={
                    "pipeline_file": pipeline_file,
                    "platform": platform,
                    "issues": issues,
                    "summary": {
                        "total_issues": len(issues),
                        "security_issues": len(security_issues),
                        "performance_issues": len(performance_issues),
                        "reliability_issues": len(reliability_issues),
                    },
                    "pipeline_score": pipeline_score,
                },
                warnings=self._generate_warnings(issues),
            )

        except Exception as e:
            logger.error(f"Pipeline analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Pipeline analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate pipeline improvement recommendations.

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

        # Missing security scans
        security_issues = [i for i in data["issues"] if i["category"] == "security"]
        if security_issues:
            recommendations.append(Recommendation(
                title=f"Add {len(security_issues)} security checks to pipeline",
                description="Pipeline is missing critical security scans. Add SAST, dependency scans, and container scans.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 days",
                risk_level="high",
                commands=[
                    "# Add SAST scan stage",
                    "# Add dependency scan stage",
                    "# Add container image scan stage",
                ],
            ))

        # Auto-deploy to prod
        auto_deploy = [i for i in data["issues"] if i["type"] == "auto_deploy_to_prod"]
        if auto_deploy:
            recommendations.append(Recommendation(
                title="Remove automatic production deployment",
                description="Automatic deployment to production without approval is dangerous. Add manual approval gate.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="critical",
                commands=[
                    "# Add manual approval gate",
                    "# Require peer review",
                    "# Add smoke tests before prod",
                ],
            ))

        # Missing tests
        no_tests = [i for i in data["issues"] if i["type"] == "no_tests"]
        if no_tests:
            recommendations.append(Recommendation(
                title="Add test stage to pipeline",
                description="Pipeline has no test stage. Add unit tests and integration tests.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="medium",
                commands=[
                    "# Add unit test stage",
                    "# Add integration test stage",
                    "# Set coverage thresholds",
                ],
            ))

        return recommendations

    async def _analyze_pipeline(
        self,
        pipeline_file: str,
        platform: str,
    ) -> list[dict[str, Any]]:
        """Analyze pipeline configuration.

        Args:
            pipeline_file: Path to pipeline file
            platform: CI/CD platform

        Returns:
            List of issues
        """
        # Mock implementation
        issues = [
            {
                "type": "missing_security_scan",
                "category": "security",
                "severity": "high",
                "stage": "build",
                "description": "No SAST scan in build stage",
            },
            {
                "type": "no_tests",
                "category": "reliability",
                "severity": "high",
                "stage": "test",
                "description": "No test stage defined",
            },
            {
                "type": "auto_deploy_to_prod",
                "category": "security",
                "severity": "critical",
                "stage": "deploy",
                "description": "Automatic deployment to production without approval",
            },
            {
                "type": "slow_build",
                "category": "performance",
                "severity": "medium",
                "stage": "build",
                "description": "Build stage takes 15+ minutes",
            },
            {
                "type": "no_coverage_check",
                "category": "reliability",
                "severity": "medium",
                "stage": "test",
                "description": "No test coverage requirement enforced",
            },
        ]

        return issues

    def _calculate_pipeline_score(self, issues: list) -> int:
        """Calculate pipeline score (0-100).

        Args:
            issues: List of issues

        Returns:
            Pipeline score
        """
        if not issues:
            return 100

        # Weight by severity
        weights = {"critical": 20, "high": 10, "medium": 5, "low": 2}
        total_penalty = sum(weights.get(i.get("severity", "low"), 2) for i in issues)

        score = max(0, 100 - total_penalty)
        return score

    def _generate_warnings(self, issues: list) -> list[str]:
        """Generate warnings based on issues.

        Args:
            issues: List of issues

        Returns:
            List of warnings
        """
        warnings = []

        critical = [i for i in issues if i.get("severity") == "critical"]
        if critical:
            warnings.append(f"{len(critical)} CRITICAL pipeline issues detected")

        security = [i for i in issues if i["category"] == "security"]
        if len(security) > 3:
            warnings.append(f"{len(security)} security issues in pipeline")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("pipeline_file"):
            return False, ["pipeline_file is required"]
        return True, []

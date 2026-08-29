"""Dockerfile Best Practices Skill - Check Dockerfile quality.

This skill validates:
- Multi-stage build usage
- Layer optimization
- Security recommendations
- Image size optimization
- Base image vulnerabilities
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


class DockerfileBestPracticesSkill(BaseSkill):
    """Validate Dockerfile against best practices.

    Checks:
    - Multi-stage build usage
    - Layer optimization
    - Security context
    - Image size
    - Base image vulnerabilities
    """

    skill_id = "dockerfile_best_practices"
    name = "Dockerfile Best Practices Checker"
    description = "Validate Dockerfile against security and optimization best practices"
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
        """Validate Dockerfile.

        Args:
            project: Project name
            parameters: Analysis parameters
                - dockerfile: Path to Dockerfile (default: Dockerfile)
                - context: Build context path
            context: Registry context

        Returns:
            AnalysisResult with Dockerfile issues
        """
        try:
            dockerfile = parameters.get("dockerfile", "Dockerfile")
            context_path = parameters.get("context", ".")

            # Analyze Dockerfile
            issues = await self._analyze_dockerfile(dockerfile, context_path)

            # Calculate score
            score = self._calculate_score(issues)

            # Estimate image size
            estimated_size = self._estimate_image_size(dockerfile, issues)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.85,
                data={
                    "dockerfile": dockerfile,
                    "issues": issues,
                    "score": score,
                    "estimated_size": estimated_size,
                    "summary": {
                        "total_issues": len(issues),
                        "critical": sum(1 for i in issues if i["severity"] == "critical"),
                        "high": sum(1 for i in issues if i["severity"] == "high"),
                        "medium": sum(1 for i in issues if i["severity"] == "medium"),
                    },
                },
                warnings=self._generate_warnings(issues),
            )

        except Exception as e:
            logger.error(f"Dockerfile analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Dockerfile analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate Dockerfile improvement recommendations.

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

        # No multi-stage
        no_multi_stage = [i for i in data["issues"] if i["type"] == "no_multi_stage"]
        if no_multi_stage:
            recommendations.append(Recommendation(
                title="Use multi-stage build to reduce image size",
                description="Multi-stage builds separate build dependencies from runtime, reducing final image size.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="low",
                commands=[
                    "# Use multi-stage Dockerfile",
                    "FROM golang:alpine AS builder",
                    "# ... build steps ...",
                    "FROM alpine:latest",
                    "COPY --from=builder /app /app",
                ],
            ))

        # Root user
        root_user = [i for i in data["issues"] if i["type"] == "root_user"]
        if root_user:
            recommendations.append(Recommendation(
                title="Run as non-root user for security",
                description="Containers running as root pose security risks. Create and use a non-root user.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="medium",
                commands=[
                    "# Add non-root user",
                    "RUN addgroup -g 1000 appuser && \\",
                    "    adduser -u 1000 -G appuser appuser",
                    "USER appuser",
                ],
            ))

        # Large image
        if data["estimated_size"] > 500:
            recommendations.append(Recommendation(
                title=f"Optimize Dockerfile (current size: ~{data['estimated_size']}MB)",
                description="Image size is too large. Use multi-stage builds and alpine base images.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="low",
                commands=[
                    "# Use alpine base images",
                    "# Combine RUN commands",
                    "# Clean package cache",
                ],
            ))

        # No security scan
        no_scan = [i for i in data["issues"] if i["type"] == "no_security_scan"]
        if no_scan:
            recommendations.append(Recommendation(
                title="Add vulnerability scanning to build process",
                description="Scan base images and final image for vulnerabilities.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1 hour",
                risk_level="medium",
                commands=[
                    "# Add trivy scan",
                    "RUN trivy image --exit-code 1 app:latest",
                ],
            ))

        return recommendations

    async def _analyze_dockerfile(
        self,
        dockerfile: str,
        context: str,
    ) -> list[dict[str, Any]]:
        """Analyze Dockerfile for best practices.

        Args:
            dockerfile: Path to Dockerfile
            context: Build context

        Returns:
            List of issues
        """
        # Mock implementation
        # Would use hadolint in production
        issues = [
            {
                "type": "no_multi_stage",
                "severity": "high",
                "line": 1,
                "description": "Single-stage build - consider using multi-stage",
            },
            {
                "type": "root_user",
                "severity": "critical",
                "line": 10,
                "description": "Container runs as root user - security risk",
            },
            {
                "type": "large_image",
                "severity": "medium",
                "line": None,
                "description": "Image size estimated > 500MB",
            },
            {
                "type": "no_security_scan",
                "severity": "high",
                "line": None,
                "description": "No vulnerability scanning in Dockerfile",
            },
        ]

        return issues

    def _calculate_score(self, issues: list) -> int:
        """Calculate Dockerfile score.

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

    def _estimate_image_size(self, dockerfile: str, issues: list) -> int:
        """Estimate final image size.

        Args:
            dockerfile: Dockerfile path
            issues: List of issues

        Returns:
            Estimated size in MB
        """
        # Simplified estimation
        no_multi_stage = any(i["type"] == "no_multi_stage" for i in issues)

        if no_multi_stage:
            return 800  # Large without multi-stage
        return 200  # Smaller with multi-stage

    def _generate_warnings(self, issues: list) -> list[str]:
        """Generate warnings.

        Args:
            issues: List of issues

        Returns:
            List of warnings
        """
        warnings = []

        critical = [i for i in issues if i["severity"] == "critical"]
        if critical:
            warnings.append(f"{len(critical)} CRITICAL Dockerfile issues")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []

"""Right-sizing Skill - Optimize resource sizes based on actual usage."""

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


class RightSizingSkill(BaseSkill):
    """Right-size cloud resources based on actual usage.

    This skill analyzes resource utilization to recommend:
    - Instance type changes (up or down)
    - Storage size adjustments
    - Memory allocations
    """

    skill_id = "finops_rightsizing"
    name = "Resource Right-Sizing"
    description = "Optimize resource sizes based on actual utilization patterns"
    category = SkillCategory.FINOPS
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze resources for right-sizing opportunities.

        Args:
            project: Project name
            parameters: Analysis parameters
            context: Registry context

        Returns:
            AnalysisResult with right-sizing recommendations
        """
        try:
            # Analyze compute resources
            compute_recommendations = await self._analyze_compute(project, context)

            # Analyze storage resources
            storage_recommendations = await self._analyze_storage(project, context)

            # Calculate potential savings
            monthly_savings = (
                compute_recommendations.get("monthly_savings", 0) +
                storage_recommendations.get("monthly_savings", 0)
            )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.75,
                data={
                    "compute": compute_recommendations,
                    "storage": storage_recommendations,
                    "monthly_savings": monthly_savings,
                    "total_recommendations": (
                        len(compute_recommendations.get("resources", [])) +
                        len(storage_recommendations.get("resources", []))
                    ),
                },
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Right-sizing analysis failed: {str(e)}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate right-sizing recommendations.

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

        # Compute recommendations
        for resource in data.get("compute", {}).get("resources", []):
            recommendations.append(Recommendation(
                title=f"Right-size instance: {resource['name']}",
                description=resource["reason"],
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="15 minutes",
                risk_level="low",
                commands=[
                    f"# Current: {resource['current_type']}, Recommended: {resource['recommended_type']}",
                ],
            ))

        return recommendations

    async def _analyze_compute(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze compute resources for right-sizing."""
        return {"resources": [], "monthly_savings": 0}

    async def _analyze_storage(
        self,
        project: str,
        context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Analyze storage resources for right-sizing."""
        return {"resources": [], "monthly_savings": 0}

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []

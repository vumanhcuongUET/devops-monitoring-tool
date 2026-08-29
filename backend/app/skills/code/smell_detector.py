"""Code Smell Detector - Detect code smells and anti-patterns.

This skill identifies:
- God class, Long method, Feature envy
- Duplicate code, Dead code
- Global variables, Magic numbers
- Inappropriate intimacy
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


class CodeSmellDetectorSkill(BaseSkill):
    """Detect code smells and anti-patterns.

    Code smells detected:
    - God Class/Method
    - Feature Envy
    - Inappropriate Intimacy
    - Duplicated Code
    - Magic Numbers
    - Global Variables
    - Long Parameter List
    """

    skill_id = "code_smell_detector"
    name = "Code Smell Detector"
    description = "Detect code smells and anti-patterns that impact maintainability"
    category = SkillCategory.CODE
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Smell thresholds
    THRESHOLDS = {
        "god_class_lines": 500,
        "long_method_lines": 50,
        "long_parameter_list": 7,
        "max_nesting": 5,
    }

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Detect code smells.

        Args:
            project: Project name
            parameters: Analysis parameters
                - repository: Repository path
                - check_types: Types of smells to check (default: all)
            context: Registry context

        Returns:
            AnalysisResult with smells found
        """
        try:
            repository = parameters.get("repository")
            check_types = parameters.get("check_types", ["all"])

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Detect smells
            smells = await self._detect_smells(repository, check_types)

            # Categorize by type
            smell_types = {}
            for smell in smells:
                smell_type = smell["type"]
                if smell_type not in smell_types:
                    smell_types[smell_type] = []
                smell_types[smell_type].append(smell)

            # Calculate severity
            severity_counts = self._count_by_severity(smells)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.85,
                data={
                    "repository": repository,
                    "smells": smells,
                    "smell_types": smell_types,
                    "summary": {
                        "total_smells": len(smells),
                        "by_severity": severity_counts,
                        "by_type": {k: len(v) for k, v in smell_types.items()},
                    },
                },
                warnings=self._generate_warnings(severity_counts),
            )

        except Exception as e:
            logger.error(f"Code smell detection failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Code smell detection failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate refactoring recommendations.

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
        smell_types = data["smell_types"]

        # God class
        god_classes = smell_types.get("god_class", [])
        if god_classes:
            recommendations.append(Recommendation(
                title=f"Refactor {len(god_classes)} God Classes",
                description="Classes with too many responsibilities. Apply Single Responsibility Principle.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="3-5 days",
                risk_level="medium",
                commands=[
                    "# Split into smaller classes",
                    "# Extract related methods",
                    "# Use composition over inheritance",
                ],
            ))

        # Long methods
        long_methods = smell_types.get("long_method", [])
        if long_methods:
            recommendations.append(Recommendation(
                title=f"Break down {len(long_methods)} long methods",
                description="Methods that are too long and complex. Extract smaller functions.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="2-4 hours per method",
                risk_level="low",
                commands=[
                    "# Extract Method refactoring",
                    "# Identify logical blocks",
                    "# Give descriptive names to extracted functions",
                ],
            ))

        # Magic numbers
        magic_numbers = smell_types.get("magic_numbers", [])
        if magic_numbers:
            recommendations.append(Recommendation(
                title=f"Extract {len(magic_numbers)} magic numbers to constants",
                description="Replace magic numbers with named constants for better readability.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="30 minutes",
                risk_level="low",
                commands=[
                    "# Create constants file",
                    "# Use meaningful names",
                    "# Document constants with units",
                ],
            ))

        # Global variables
        globals_smell = smell_types.get("global_variables", [])
        if globals_smell:
            recommendations.append(Recommendation(
                title=f"Eliminate {len(globals_smell)} global variables",
                description="Global variables create hidden dependencies. Use dependency injection.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="1-2 hours",
                risk_level="medium",
                commands=[
                    "# Pass globals as parameters",
                    "# Use dependency injection",
                    "# Create state objects",
                ],
            ))

        return recommendations

    async def _detect_smells(
        self,
        repository: str,
        check_types: list[str],
    ) -> list[dict[str, Any]]:
        """Detect code smells.

        Args:
            repository: Repository path
            check_types: Types of smells to check

        Returns:
            List of smells
        """
        # Mock implementation
        # Would use tools like SonarQube, CodeClimate in production
        smells = [
            {
                "type": "god_class",
                "severity": "high",
                "file": "app/services/order_manager.py",
                "line": 1,
                "description": "OrderManager class has 2000 lines and 50 methods",
            },
            {
                "type": "long_method",
                "severity": "medium",
                "file": "app/services/api.py",
                "line": 100,
                "description": "process_request method is 250 lines long",
            },
            {
                "type": "magic_numbers",
                "severity": "low",
                "file": "app/utils/calculator.py",
                "line": 45,
                "description": "Magic number 86400 used without constant",
            },
            {
                "type": "global_variables",
                "severity": "medium",
                "file": "app/config.py",
                "line": 10,
                "description": "Global variable CONFIG_STATE used across modules",
            },
            {
                "type": "feature_envy",
                "severity": "medium",
                "file": "app/handlers/api.py",
                "line": 78,
                "description": "Method accesses data from Order class excessively",
            },
        ]

        return smells

    def _count_by_severity(self, smells: list) -> dict[str, int]:
        """Count smells by severity.

        Args:
            smells: List of smells

        Returns:
            Counts by severity
        """
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for smell in smells:
            severity = smell.get("severity", "low")
            if severity in counts:
                counts[severity] += 1

        return counts

    def _generate_warnings(self, severity_counts: dict) -> list[str]:
        """Generate warnings based on severity counts.

        Args:
            severity_counts: Counts by severity

        Returns:
            List of warnings
        """
        warnings = []

        if severity_counts.get("critical", 0) > 0:
            warnings.append("Critical code smells detected - immediate refactoring needed")

        if severity_counts.get("high", 0) > 5:
            warnings.append("Many high-severity code smells - prioritized refactoring recommended")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]
        return True, []

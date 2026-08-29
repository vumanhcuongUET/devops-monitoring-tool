"""Code Complexity Analyzer - Measure code complexity.

This skill analyzes:
- Cyclomatic complexity
- Cognitive complexity
- Nesting depth
- Function length
- Class size
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


class ComplexityAnalyzerSkill(BaseSkill):
    """Analyze code complexity to identify maintainability risks.

    This skill measures:
    - Cyclomatic complexity (McCabe)
    - Cognitive complexity
    - Maximum nesting depth
    - Function/class length
    - Maintainability index

    Complexity thresholds:
    - 1-10: Simple (low risk)
    - 11-20: Moderate (medium risk)
    - 21-50: Complex (high risk)
    - 50+: Very Complex (critical risk)
    """

    skill_id = "code_complexity_analyzer"
    name = "Code Complexity Analyzer"
    description = "Measure code complexity to identify maintainability risks"
    category = SkillCategory.CODE
    priority = SkillPriority.CRITICAL
    version = "1.0.0"

    # Complexity thresholds
    THRESHOLDS = {
        "simple": 10,
        "moderate": 20,
        "complex": 50,
    }

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Analyze code complexity.

        Args:
            project: Project name
            parameters: Analysis parameters
                - repository: Repository path
                - language: Programming language
                - max_complexity: Maximum allowed complexity (default: 20)
            context: Registry context

        Returns:
            AnalysisResult with complexity metrics
        """
        try:
            repository = parameters.get("repository")
            language = parameters.get("language", "python")
            max_complexity = parameters.get("max_complexity", 20)

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Analyze files
            files = await self._analyze_repository(repository, language, max_complexity)

            # Calculate overall metrics
            overall_metrics = self._calculate_overall_metrics(files)

            # Identify problematic functions
            complex_functions = []
            for file_data in files:
                complex_functions.extend(file_data.get("complex_functions", []))

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "repository": repository,
                    "language": language,
                    "files_analyzed": len(files),
                    "files": files,
                    "overall_metrics": overall_metrics,
                    "complex_functions": complex_functions,
                    "summary": {
                        "total_functions": overall_metrics.get("total_functions", 0),
                        "simple_functions": overall_metrics.get("simple", 0),
                        "moderate_functions": overall_metrics.get("moderate", 0),
                        "complex_functions": overall_metrics.get("complex", 0),
                        "very_complex_functions": overall_metrics.get("very_complex", 0),
                    },
                },
                warnings=self._generate_warnings(overall_metrics),
            )

        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Complexity analysis failed: {e!s}"],
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
        summary = data["summary"]
        overall = data["overall_metrics"]

        # Very complex functions
        if summary["very_complex_functions"] > 0:
            recommendations.append(Recommendation(
                title=f"Refactor {summary['very_complex_functions']} very complex functions",
                description=f"Found {summary['very_complex_functions']} functions with complexity >50. "
                f"These are extremely difficult to maintain and test.",
                priority=SkillPriority.CRITICAL,
                action_type="manual",
                estimated_effort="2-5 days",
                risk_level="high",
                commands=[
                    "# Break down into smaller functions",
                    "# Extract helper methods",
                    "# Use early returns to reduce nesting",
                ],
            ))

        # Complex functions
        if summary["complex_functions"] > 0:
            recommendations.append(Recommendation(
                title=f"Simplify {summary['complex_functions']} complex functions",
                description=f"Found {summary['complex_functions']} functions with complexity 21-50. "
                f"Consider refactoring to improve maintainability.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="3-7 days",
                risk_level="medium",
                commands=[
                    "# Apply Extract Method refactoring",
                    "# Reduce nesting levels",
                    "# Simplify conditional logic",
                ],
            ))

        # High average complexity
        avg_complexity = overall.get("average_complexity", 0)
        if avg_complexity > 15:
            recommendations.append(Recommendation(
                title=f"Reduce average code complexity (current: {avg_complexity:.1f})",
                description="The average code complexity is high. Review codebase for simplification opportunities.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="1-2 weeks",
                risk_level="low",
                commands=[
                    "# Review all moderate functions",
                    "# Apply refactoring patterns",
                    "# Consider design patterns to simplify",
                ],
            ))

        # Deep nesting
        max_nesting = overall.get("max_nesting_depth", 0)
        if max_nesting > 4:
            recommendations.append(Recommendation(
                title=f"Reduce nesting depth (max: {max_nesting})",
                description=f"Maximum nesting depth of {max_nesting} is too high. "
                f"Deep nesting makes code hard to read and maintain.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="low",
                commands=[
                    "# Use early returns (guard clauses)",
                    "# Extract nested conditions into functions",
                    "# Use strategy pattern for complex conditions",
                ],
            ))

        return recommendations

    async def _analyze_repository(
        self,
        repository: str,
        language: str,
        max_complexity: int,
    ) -> list[dict[str, Any]]:
        """Analyze all files in repository.

        Args:
            repository: Repository path
            language: Programming language
            max_complexity: Maximum allowed complexity

        Returns:
            List of file analyses
        """
        # Mock implementation
        # Would use radon, lizard, or similar tools in production
        files = [
            {
                "path": "app/services/api.py",
                "functions": [
                    {
                        "name": "process_data",
                        "line": 45,
                        "end_line": 95,
                        "cyclomatic_complexity": 8,
                        "cognitive_complexity": 12,
                        "nesting_depth": 3,
                    },
                    {
                        "name": "handle_request",
                        "line": 100,
                        "end_line": 250,
                        "cyclomatic_complexity": 35,  # COMPLEX
                        "cognitive_complexity": 45,
                        "nesting_depth": 6,
                    },
                ],
                "classes": [
                    {
                        "name": "APIHandler",
                        "line": 20,
                        "end_line": 300,
                        "methods": 8,
                        "total_complexity": 120,
                    }
                ],
                "metrics": {
                    "average_complexity": 21.5,
                    "max_complexity": 35,
                    "max_nesting": 6,
                },
                "complex_functions": [
                    {
                        "name": "handle_request",
                        "line": 100,
                        "complexity": 35,
                        "type": "complex",
                    }
                ]
            },
            {
                "path": "app/utils/helpers.py",
                "functions": [
                    {
                        "name": "format_date",
                        "line": 10,
                        "end_line": 15,
                        "cyclomatic_complexity": 2,
                        "cognitive_complexity": 1,
                        "nesting_depth": 1,
                    },
                ],
                "classes": [],
                "metrics": {
                    "average_complexity": 2.0,
                    "max_complexity": 2,
                    "max_nesting": 1,
                },
                "complex_functions": []
            }
        ]

        return files

    def _calculate_overall_metrics(self, files: list) -> dict[str, Any]:
        """Calculate overall complexity metrics.

        Args:
            files: List of file analyses

        Returns:
            Overall metrics
        """
        total_functions = 0
        simple = moderate = complex = very_complex = 0
        total_complexity = 0
        max_nesting = 0

        for file_data in files:
            for func in file_data.get("functions", []):
                total_functions += 1
                complexity = func.get("cyclomatic_complexity", 1)
                total_complexity += complexity

                if complexity <= self.THRESHOLDS["simple"]:
                    simple += 1
                elif complexity <= self.THRESHOLDS["moderate"]:
                    moderate += 1
                elif complexity <= self.THRESHOLDS["complex"]:
                    complex += 1
                else:
                    very_complex += 1

                max_nesting = max(max_nesting, func.get("nesting_depth", 0))

        avg_complexity = total_complexity / total_functions if total_functions > 0 else 0

        return {
            "total_functions": total_functions,
            "simple": simple,
            "moderate": moderate,
            "complex": complex,
            "very_complex": very_complex,
            "average_complexity": round(avg_complexity, 1),
            "max_complexity": max(
                (f.get("cyclomatic_complexity", 0)
                 for file in files
                 for f in file.get("functions", [])),
                default=0
            ),
            "max_nesting_depth": max_nesting,
            "maintainability_index": self._calculate_maintainability_index(avg_complexity, max_nesting),
        }

    def _calculate_maintainability_index(
        self,
        avg_complexity: float,
        max_nesting: int,
    ) -> int:
        """Calculate maintainability index (0-100).

        Args:
            avg_complexity: Average cyclomatic complexity
            max_nesting: Maximum nesting depth

        Returns:
            Maintainability index
        """
        # Simplified MI calculation
        mi = 100 - (avg_complexity * 2) - (max_nesting * 3)
        return max(0, min(100, int(mi)))

    def _generate_warnings(self, metrics: dict) -> list[str]:
        """Generate warnings based on metrics.

        Args:
            metrics: Overall metrics

        Returns:
            List of warnings
        """
        warnings = []

        if metrics.get("very_complex", 0) > 2:
            warnings.append(f"{metrics['very_complex']} very complex functions detected")

        if metrics.get("max_nesting_depth", 0) > 5:
            warnings.append(f"Deep nesting detected (max: {metrics['max_nesting_depth']})")

        if metrics.get("maintainability_index", 100) < 50:
            warnings.append("Low maintainability index - significant refactoring needed")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]

        max_complexity = parameters.get("max_complexity", 20)
        if not isinstance(max_complexity, int) or max_complexity < 1:
            return False, ["max_complexity must be a positive integer"]

        return True, []

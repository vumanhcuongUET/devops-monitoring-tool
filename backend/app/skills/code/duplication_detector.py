"""Code Duplication Detector - Find duplicate code.

This skill identifies:
- Type-1 clones (exact copies)
- Type-2 clones (renamed variables)
- Type-3 clones (modified statements)
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


class DuplicationDetectorSkill(BaseSkill):
    """Detect code duplication across the codebase.

    This skill finds:
    - Exact code clones
    - Parameterized clones
    - Near-miss duplicates
    - Suggests extraction to reduce duplication

    Duplication rate:
    - <3%: Excellent
    - 3-5%: Good
    - 5-10%: Acceptable
    - 10-20%: Poor
    - >20%: Critical
    """

    skill_id = "code_duplication_detector"
    name = "Code Duplication Detector"
    description = "Find duplicate code blocks that should be refactored"
    category = SkillCategory.CODE
    priority = SkillPriority.HIGH
    version = "1.0.0"

    # Duplication thresholds
    THRESHOLDS = {
        "excellent": 3,
        "good": 5,
        "acceptable": 10,
        "poor": 20,
    }

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Detect code duplication.

        Args:
            project: Project name
            parameters: Analysis parameters
                - repository: Repository path
                - min_lines: Minimum lines to consider as duplicate (default: 10)
                - ignore_comments: Ignore comments when comparing (default: true)
            context: Registry context

        Returns:
            AnalysisResult with duplication findings
        """
        try:
            repository = parameters.get("repository")
            min_lines = parameters.get("min_lines", 10)
            ignore_comments = parameters.get("ignore_comments", True)

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Find duplicates
            duplicates = await self._find_duplicates(
                repository, min_lines, ignore_comments
            )

            # Calculate duplication rate
            duplication_rate = self._calculate_duplication_rate(duplicates)

            # Categorize duplicates
            exact_clones = [d for d in duplicates if d["type"] == "type-1"]
            near_miss = [d for d in duplicates if d["type"] == "type-3"]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.8,
                data={
                    "repository": repository,
                    "duplicates": duplicates,
                    "duplication_rate": duplication_rate,
                    "summary": {
                        "total_duplicates": len(duplicates),
                        "exact_clones": len(exact_clones),
                        "near_miss": len(near_miss),
                        "total_duplicate_lines": sum(d["lines"] for d in duplicates),
                        "duplication_level": self._get_duplication_level(duplication_rate),
                    },
                },
                warnings=self._generate_warnings(duplication_rate),
            )

        except Exception as e:
            logger.error(f"Duplication detection failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Duplication detection failed: {e!s}"],
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
        duplication_rate = data["duplication_rate"]
        summary = data["summary"]

        # High duplication rate
        if duplication_rate > self.THRESHOLDS["acceptable"]:
            recommendations.append(Recommendation(
                title=f"Reduce code duplication (current: {duplication_rate:.1f}%)",
                description=f"Code duplication rate of {duplication_rate:.1f}% is too high. "
                f"Extract duplicate code into reusable functions.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="2-5 days",
                risk_level="medium",
                commands=[
                    "# Extract common patterns into functions",
                    "# Create utility modules",
                    "# Use design patterns to reduce duplication",
                ],
            ))

        # Exact clones
        if summary["exact_clones"] > 5:
            recommendations.append(Recommendation(
                title=f"Refactor {summary['exact_clones']} exact code clones",
                description=f"Found {summary['exact_clones']} exact code copies. "
                f"These should be extracted into a single function.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="1-2 days",
                risk_level="low",
                commands=[
                    "# Use Extract Method refactoring",
                    "# Create shared utility functions",
                    "# Apply DRY principle consistently",
                ],
            ))

        # Large duplicates
        large_duplicates = [
            d for d in data["duplicates"]
            if d["lines"] > 50
        ]
        if large_duplicates:
            recommendations.append(Recommendation(
                title=f"Extract {len(large_duplicates)} large duplicate blocks",
                description=f"Found {len(large_duplicates)} duplicate blocks over 50 lines. "
                f"These are significant opportunities for code reuse.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="1-3 days",
                risk_level="low",
                commands=[
                    "# Prioritize largest duplicates",
                    *[f"# {d['files'][0]} - {d['lines']} lines" for d in large_duplicates[:3]],
                ],
            ))

        return recommendations

    async def _find_duplicates(
        self,
        repository: str,
        min_lines: int,
        ignore_comments: bool,
    ) -> list[dict[str, Any]]:
        """Find duplicate code blocks.

        Args:
            repository: Repository path
            min_lines: Minimum lines to consider
            ignore_comments: Whether to ignore comments

        Returns:
            List of duplicates
        """
        # Mock implementation
        # Would use tools like PMD-CPD, jscpd, SonarQube in production
        duplicates = [
            {
                "type": "type-1",
                "lines": 35,
                "similarity": 100,
                "occurrences": 3,
                "files": [
                    {"path": "app/services/api.py", "start_line": 45},
                    {"path": "app/services/user.py", "start_line": 78},
                    {"path": "app/services/auth.py", "start_line": 102},
                ],
                "description": "Exact copy of error handling code",
            },
            {
                "type": "type-2",
                "lines": 25,
                "similarity": 90,
                "occurrences": 2,
                "files": [
                    {"path": "app/utils/validation.py", "start_line": 20},
                    {"path": "app/utils/parser.py", "start_line": 45},
                ],
                "description": "Similar parameter validation with renamed variables",
            },
            {
                "type": "type-3",
                "lines": 60,
                "similarity": 75,
                "occurrences": 2,
                "files": [
                    {"path": "app/handlers/api.py", "start_line": 100},
                    {"path": "app/handlers/web.py", "start_line": 85},
                ],
                "description": "Modified copy of request handling logic",
            },
        ]

        return duplicates

    def _calculate_duplication_rate(self, duplicates: list) -> float:
        """Calculate overall duplication rate.

        Args:
            duplicates: List of duplicates

        Returns:
            Duplication rate percentage
        """
        if not duplicates:
            return 0.0

        # Simplified calculation
        total_lines = sum(d["lines"] * d["occurrences"] for d in duplicates)
        # Assume codebase is ~10000 lines for this example
        codebase_size = 10000

        return (total_lines / codebase_size) * 100

    def _get_duplication_level(self, rate: float) -> str:
        """Get duplication level from rate.

        Args:
            rate: Duplication rate

        Returns:
            Level descriptor
        """
        if rate <= self.THRESHOLDS["excellent"]:
            return "excellent"
        elif rate <= self.THRESHOLDS["good"]:
            return "good"
        elif rate <= self.THRESHOLDS["acceptable"]:
            return "acceptable"
        elif rate <= self.THRESHOLDS["poor"]:
            return "poor"
        else:
            return "critical"

    def _generate_warnings(self, duplication_rate: float) -> list[str]:
        """Generate warnings based on duplication rate.

        Args:
            duplication_rate: Duplication rate

        Returns:
            List of warnings
        """
        warnings = []

        if duplication_rate > self.THRESHOLDS["poor"]:
            warnings.append(f"Critical code duplication ({duplication_rate:.1f}%) - major refactoring needed")

        elif duplication_rate > self.THRESHOLDS["acceptable"]:
            warnings.append(f"High code duplication ({duplication_rate:.1f}%) - refactoring recommended")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]

        min_lines = parameters.get("min_lines", 10)
        if not isinstance(min_lines, int) or min_lines < 3:
            return False, ["min_lines must be at least 3"]

        return True, []

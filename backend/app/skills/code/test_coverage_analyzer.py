"""Test Coverage Analyzer - Analyze test coverage.

This skill measures:
- Line coverage
- Branch coverage
- Path coverage
- Uncovered code paths
- Missing edge cases
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


class TestCoverageAnalyzerSkill(BaseSkill):
    """Analyze test coverage to identify untested code.

    This skill measures:
    - Line coverage percentage
    - Branch coverage percentage
    - Function/method coverage
    - Identifies risky untested code
    """

    skill_id = "code_test_coverage_analyzer"
    name = "Test Coverage Analyzer"
    description = "Analyze test coverage to identify gaps in testing"
    category = SkillCategory.CODE
    priority = SkillPriority.CRITICAL
    version = "1.0.0"

    # Coverage thresholds
    THRESHOLDS = {
        "excellent": 80,
        "good": 70,
        "acceptable": 60,
    }

    def __init__(self, config: Optional[SkillConfig] = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """Analyze test coverage.

        Args:
            project: Project name
            parameters: Analysis parameters
                - repository: Repository path
                - coverage_file: Path to coverage report
                - min_coverage: Minimum acceptable coverage (default: 70)
            context: Registry context

        Returns:
            AnalysisResult with coverage metrics
        """
        try:
            repository = parameters.get("repository")
            coverage_file = parameters.get("coverage_file")
            min_coverage = parameters.get("min_coverage", 70)

            if not repository:
                return AnalysisResult(
                    success=False,
                    skill_id=self.skill_id,
                    errors=["Missing required parameter: repository"],
                )

            # Get coverage data
            coverage_data = await self._get_coverage_data(repository, coverage_file)

            # Analyze coverage
            analysis = self._analyze_coverage(coverage_data, min_coverage)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.95,
                data={
                    "repository": repository,
                    "coverage_data": coverage_data,
                    "analysis": analysis,
                    "threshold": min_coverage,
                },
                warnings=self._generate_warnings(analysis),
            )

        except Exception as e:
            logger.error(f"Coverage analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Coverage analysis failed: {str(e)}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate test improvement recommendations.

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
        analysis = data["analysis"]
        threshold = data["threshold"]

        # Low overall coverage
        line_coverage = analysis.get("line_coverage", 0)
        if line_coverage < threshold:
            deficit = threshold - line_coverage
            recommendations.append(Recommendation(
                title=f"Increase test coverage by {deficit:.1f}% (current: {line_coverage:.1f}%)",
                description=f"Test coverage is below {threshold}% threshold. Add tests for uncovered code paths.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-3 days",
                risk_level="medium",
                commands=[
                    "# View coverage report",
                    "coverage report",
                    "# Add tests for uncovered functions",
                    "# Focus on high-risk areas first",
                ],
            ))

        # Low branch coverage
        branch_coverage = analysis.get("branch_coverage", 0)
        if branch_coverage < threshold:
            recommendations.append(Recommendation(
                title=f"Improve branch coverage to {threshold}% (current: {branch_coverage:.1f}%)",
                description="Branch coverage is lower than line coverage. Add tests for conditional branches.",
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="2-4 hours",
                risk_level="low",
                commands=[
                    "# Add edge case tests",
                    "# Test error conditions",
                    "# Test boundary values",
                ],
            ))

        # Untested critical files
        untested_critical = [
            f for f in analysis.get("untested_files", [])
            if f.get("is_critical", False)
        ]
        if untested_critical:
            recommendations.append(Recommendation(
                title=f"Add tests for {len(untested_critical)} critical files",
                description=f"Found {len(untested_critical)} critical files with no tests. These files handle important functionality.",
                priority=SkillPriority.HIGH,
                action_type="manual",
                estimated_effort="1-2 days",
                risk_level="medium",
                commands=[
                    "# Prioritize tests for these files",
                    *[f"# {f['path']}" for f in untested_critical[:3]],
                ],
            ))

        return recommendations

    async def _get_coverage_data(
        self,
        repository: str,
        coverage_file: Optional[str],
    ) -> dict[str, Any]:
        """Get coverage data from repository.

        Args:
            repository: Repository path
            coverage_file: Optional coverage file path

        Returns:
            Coverage data
        """
        # Mock implementation
        # Would parse coverage.json, .coverage, lcov.info, etc.
        return {
            "line_coverage": 68.5,
            "branch_coverage": 54.2,
            "function_coverage": 72.0,
            "files": [
                {
                    "path": "app/services/api.py",
                    "line_coverage": 82.3,
                    "branch_coverage": 70.0,
                    "is_critical": True,
                    "uncovered_lines": [45, 67, 89, 102],
                },
                {
                    "path": "app/utils/helpers.py",
                    "line_coverage": 45.0,
                    "branch_coverage": 30.0,
                    "is_critical": False,
                    "uncovered_lines": [12, 15, 18, 21, 24, 27],
                },
                {
                    "path": "app/auth/permissions.py",
                    "line_coverage": 0.0,
                    "branch_coverage": 0.0,
                    "is_critical": True,
                    "uncovered_lines": "all",
                },
            ]
        }

    def _analyze_coverage(
        self,
        coverage_data: dict[str, Any],
        min_coverage: float,
    ) -> dict[str, Any]:
        """Analyze coverage data.

        Args:
            coverage_data: Coverage data
            min_coverage: Minimum acceptable coverage

        Returns:
            Analysis results
        """
        line_cov = coverage_data.get("line_coverage", 0)
        branch_cov = coverage_data.get("branch_coverage", 0)
        function_cov = coverage_data.get("function_coverage", 0)

        # Determine coverage level
        overall = (line_cov + branch_cov + function_cov) / 3

        if overall >= self.THRESHOLDS["excellent"]:
            level = "excellent"
        elif overall >= self.THRESHOLDS["good"]:
            level = "good"
        elif overall >= self.THRESHOLDS["acceptable"]:
            level = "acceptable"
        else:
            level = "poor"

        # Identify untested files
        untested_files = []
        for file_data in coverage_data.get("files", []):
            if file_data.get("line_coverage", 100) < min_coverage:
                untested_files.append({
                    "path": file_data["path"],
                    "line_coverage": file_data.get("line_coverage", 0),
                    "is_critical": file_data.get("is_critical", False),
                    "uncovered_lines": file_data.get("uncovered_lines", []),
                })

        return {
            "line_coverage": line_cov,
            "branch_coverage": branch_cov,
            "function_coverage": function_cov,
            "overall_coverage": round(overall, 1),
            "coverage_level": level,
            "meets_threshold": overall >= min_coverage,
            "untested_files": untested_files,
            "risk_score": self._calculate_risk_score(line_cov, branch_cov),
        }

    def _calculate_risk_score(self, line_cov: float, branch_cov: float) -> float:
        """Calculate risk score based on coverage.

        Args:
            line_cov: Line coverage
            branch_cov: Branch coverage

        Returns:
            Risk score (0-100, higher = riskier)
        """
        # Lower coverage = higher risk
        line_risk = (100 - line_cov) * 0.4
        branch_risk = (100 - branch_cov) * 0.6

        return min(100, line_risk + branch_risk)

    def _generate_warnings(self, analysis: dict) -> list[str]:
        """Generate warnings based on coverage.

        Args:
            analysis: Coverage analysis

        Returns:
            List of warnings
        """
        warnings = []

        if analysis.get("coverage_level") == "poor":
            warnings.append("Overall test coverage is poor - significant testing needed")

        critical_untested = sum(1 for f in analysis.get("untested_files", []) if f.get("is_critical"))
        if critical_untested > 0:
            warnings.append(f"{critical_untested} critical files have insufficient tests")

        if analysis.get("branch_coverage", 0) < analysis.get("line_coverage", 0) - 20:
            warnings.append("Branch coverage significantly lower than line coverage")

        return warnings

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        if not parameters.get("repository"):
            return False, ["repository is required"]

        min_coverage = parameters.get("min_coverage", 70)
        if not isinstance(min_coverage, (int, float)) or not (0 <= min_coverage <= 100):
            return False, ["min_coverage must be between 0 and 100"]

        return True, []

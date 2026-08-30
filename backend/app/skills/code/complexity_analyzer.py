"""Code Complexity Analyzer Skill — static AST analysis (Phase 13).

Was a stub returning fabricated complexity numbers. Now it parses uploaded
Python source with the stdlib `ast` module and measures real cyclomatic
complexity per function (decision points + 1), flagging hotspots.
"""

from __future__ import annotations

import ast
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

COMPLEXITY_WARNING = 10
COMPLEXITY_CRITICAL = 20

# Each of these adds one independent path through a function.
_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.comprehension,
)


class ComplexityAnalyzerSkill(BaseSkill):
    """Measure cyclomatic complexity of uploaded Python source."""

    skill_id = "code_complexity_analyzer"
    name = "Code Complexity Analyzer"
    description = (
        "Measure cyclomatic complexity of uploaded Python source and flag "
        "function hotspots (warning > 10, critical > 20)."
    )
    category = SkillCategory.CODE
    priority = SkillPriority.MEDIUM
    version = "2.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        try:
            files = self._input_files(parameters)
            if not files:
                raise ValueError(
                    "No source provided — pass {'files': {name: content}} or "
                    "{'filename': ..., 'content': ...}"
                )

            functions = []
            unparsable = []
            for name, content in files.items():
                try:
                    tree = ast.parse(content)
                except SyntaxError as e:
                    unparsable.append({"file": name, "error": str(e)})
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append({
                            "file": name,
                            "function": node.name,
                            "line": node.lineno,
                            "complexity": self._complexity(node),
                            "lines": (getattr(node, "end_lineno", node.lineno) or node.lineno)
                            - node.lineno
                            + 1,
                        })

            if not functions and not unparsable:
                raise ValueError("No functions found in the provided source")

            hotspots = sorted(
                (f for f in functions if f["complexity"] > COMPLEXITY_WARNING),
                key=lambda f: f["complexity"],
                reverse=True,
            )
            complexities = [f["complexity"] for f in functions]

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.95,
                data={
                    "files_analyzed": len(files),
                    "functions_analyzed": len(functions),
                    "unparsable_files": unparsable,
                    "summary": {
                        "avg_complexity": round(sum(complexities) / len(complexities), 2)
                        if complexities
                        else 0,
                        "max_complexity": max(complexities) if complexities else 0,
                        "hotspot_count": len(hotspots),
                        "critical_count": sum(
                            1 for f in hotspots if f["complexity"] > COMPLEXITY_CRITICAL
                        ),
                    },
                    "hotspots": hotspots[:20],
                },
                warnings=[f"{len(hotspots)} functions exceed complexity {COMPLEXITY_WARNING}"]
                if hotspots
                else [],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Complexity analysis failed: {e!s}"],
            )

    def _complexity(self, func: ast.AST) -> int:
        """Cyclomatic complexity: 1 + decision points (boolops count n-1)."""
        complexity = 1
        for node in ast.walk(func):
            if isinstance(node, _DECISION_NODES):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
        return complexity

    def _input_files(self, parameters: dict[str, Any]) -> dict[str, str]:
        files = parameters.get("files")
        if isinstance(files, dict) and files:
            return {str(k): str(v) for k, v in files.items()}
        if parameters.get("filename") and parameters.get("content") is not None:
            return {str(parameters["filename"]): str(parameters["content"])}
        return {}

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        for hotspot in result.data.get("hotspots", [])[:5]:
            recommendations.append(Recommendation(
                title=f"Refactor {hotspot['function']} (complexity {hotspot['complexity']})",
                description=(
                    f"{hotspot['file']}:{hotspot['line']} — split the decision "
                    "paths into smaller functions or use lookup tables."
                ),
                priority=SkillPriority.HIGH
                if hotspot["complexity"] > COMPLEXITY_CRITICAL
                else SkillPriority.MEDIUM,
                action_type="manual",
                risk_level="low",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        return True, []

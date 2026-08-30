"""Code Smell Detector Skill — static AST/line lint (Phase 13).

Was a stub reporting fabricated smell counts. Now it lints uploaded Python
source with real, line-accurate rules: long functions, too many arguments,
bare excepts, mutable default arguments, deep nesting, debug prints,
TODO/FIXME markers and god files.
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

LONG_FUNCTION_LINES = 50
MAX_ARGUMENTS = 6
MAX_NESTING = 4
GOD_FILE_LINES = 500

_RULES = {
    "long_function": "high",
    "too_many_arguments": "medium",
    "bare_except": "high",
    "mutable_default_argument": "high",
    "deep_nesting": "medium",
    "print_debug": "low",
    "todo_comment": "low",
    "god_file": "medium",
}


class CodeSmellDetectorSkill(BaseSkill):
    """Detect common code smells in uploaded Python source."""

    skill_id = "code_smell_detector"
    name = "Code Smell Detector"
    description = (
        "Detect code smells in uploaded Python source: long functions, too "
        "many arguments, bare excepts, mutable defaults, deep nesting, debug "
        "prints, TODO markers and god files."
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
            files = parameters.get("files")
            if isinstance(files, dict) and files:
                files = {str(k): str(v) for k, v in files.items()}
            elif parameters.get("filename") and parameters.get("content") is not None:
                files = {str(parameters["filename"]): str(parameters["content"])}
            else:
                raise ValueError(
                    "No source provided — pass {'files': {name: content}} or "
                    "{'filename': ..., 'content': ...}"
                )

            issues: list[dict[str, Any]] = []
            for name, content in files.items():
                issues.extend(self._lint_file(name, content))

            counts: dict[str, int] = {}
            for issue in issues:
                counts[issue["type"]] = counts.get(issue["type"], 0) + 1

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "files_analyzed": len(files),
                    "issues": issues[:100],
                    "counts": counts,
                    "summary": {
                        "total_issues": len(issues),
                        "high": sum(
                            1 for i in issues if i["severity"] == "high"
                        ),
                        "files_with_issues": len({i["file"] for i in issues}),
                    },
                },
                warnings=[f"{sum(1 for i in issues if i['severity'] == 'high')} high-severity smells"]
                if any(i["severity"] == "high" for i in issues)
                else [],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Smell detection failed: {e!s}"],
            )

    def _lint_file(self, name: str, content: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []

        def add(rule: str, line: int | None, detail: str) -> None:
            issues.append({
                "file": name,
                "type": rule,
                "severity": _RULES[rule],
                "line": line,
                "description": detail,
            })

        lines = content.splitlines()
        if len(lines) > GOD_FILE_LINES:
            add("god_file", None, f"{len(lines)} lines — split the module")

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            add("syntax_error", e.lineno, f"Cannot parse: {e.msg}")
            return issues

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                length = end - node.lineno + 1
                if length > LONG_FUNCTION_LINES:
                    add(
                        "long_function",
                        node.lineno,
                        f"{node.name} is {length} lines (>{LONG_FUNCTION_LINES})",
                    )
                if len(node.args.args) + len(node.args.kwonlyargs) > MAX_ARGUMENTS:
                    add(
                        "too_many_arguments",
                        node.lineno,
                        f"{node.name} takes {len(node.args.args) + len(node.args.kwonlyargs)} arguments",
                    )
                for default in list(node.args.defaults) + [
                    d for d in node.args.kw_defaults if d is not None
                ]:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        add(
                            "mutable_default_argument",
                            node.lineno,
                            f"{node.name} uses a mutable default argument",
                        )
                        break
                if self._max_nesting(node) > MAX_NESTING:
                    add(
                        "deep_nesting",
                        node.lineno,
                        f"{node.name} nests deeper than {MAX_NESTING} levels",
                    )
                if any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)
                    and n.func.id == "print"
                    for n in ast.walk(node)
                ):
                    add("print_debug", node.lineno, f"{node.name} uses print()")

            elif isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    add(
                        "bare_except",
                        node.lineno,
                        "Bare except swallows every error — catch specific exceptions",
                    )

        for n, raw in enumerate(lines, 1):
            if "TODO" in raw or "FIXME" in raw:
                add("todo_comment", n, "Unresolved TODO/FIXME marker")

        return issues

    def _max_nesting(self, func: ast.AST) -> int:
        """Deepest nesting of control-flow blocks inside a function."""
        branch = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)

        def depth(node: ast.AST, current: int) -> int:
            worst = current
            for child in ast.iter_child_nodes(node):
                if isinstance(child, branch):
                    worst = max(worst, depth(child, current + 1))
                elif not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    worst = max(worst, depth(child, current))
            return worst

        return depth(func, 0)

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        recommendations = []
        counts = result.data.get("counts", {})
        if counts.get("bare_except"):
            recommendations.append(Recommendation(
                title=f"Fix {counts['bare_except']} bare except(s)",
                description=(
                    "Bare excepts hide real failures — catch specific exception "
                    "types and re-raise what is unexpected."
                ),
                priority=SkillPriority.HIGH,
                action_type="manual",
                risk_level="medium",
            ))
        if counts.get("long_function"):
            recommendations.append(Recommendation(
                title=f"Split {counts['long_function']} long function(s)",
                description=(
                    f"Functions over {LONG_FUNCTION_LINES} lines are hard to "
                    "test and review — extract cohesive blocks."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                risk_level="low",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        return True, []

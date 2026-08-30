"""Code Duplication Detector Skill — static clone detection (Phase 13).

Was a stub reporting fabricated clone percentages. Now it finds real Type-1
clones in uploaded source: identical normalized line windows (default 6
lines, whitespace/comments stripped) that appear more than once, across
files or within one.
"""

from __future__ import annotations

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

WINDOW_SIZE = 6
DUPLICATION_WARN_PERCENT = 10.0


def _normalized_lines(content: str) -> list[tuple[int, str]]:
    """(line_number, stripped) pairs with blanks and comment-only lines dropped."""
    lines = []
    for n, raw in enumerate(content.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        lines.append((n, stripped))
    return lines


class DuplicationDetectorSkill(BaseSkill):
    """Detect duplicated code blocks in uploaded source files."""

    skill_id = "code_duplication_detector"
    name = "Code Duplication Detector"
    description = (
        "Detect duplicated code blocks (identical normalized line windows) "
        "in uploaded source files, within and across files."
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
            window = max(int(parameters.get("window_size", WINDOW_SIZE)), 2)

            # Map each normalized window hash to everywhere it occurs.
            occurrences: dict[str, list[dict[str, Any]]] = {}
            total_windows = 0
            for name, content in files.items():
                lines = _normalized_lines(content)
                total_windows += max(len(lines) - window + 1, 0)
                for i in range(len(lines) - window + 1):
                    chunk = "\n".join(line for _, line in lines[i : i + window])
                    key = hash(chunk)
                    occurrences.setdefault(key, []).append(
                        {"file": name, "start_line": lines[i][0], "chunk": chunk}
                    )

            # A window is duplicated when it occurs 2+ times and the
            # occurrences are not part of an already-reported larger block.
            duplicates = []
            duplicated_windows = 0
            reported: set[tuple] = set()
            for chunks in occurrences.values():
                if len(chunks) < 2:
                    continue
                duplicated_windows += 1
                signature = tuple(sorted((c["file"], c["start_line"]) for c in chunks))
                # Skip windows that only restate a neighboring reported block
                # (same file pairs one line apart).
                if any(
                    (c1[0], c1[1] - 1) in reported or (c1[0], c1[1] + 1) in reported
                    for c1 in signature
                ):
                    continue
                reported.update(signature)
                duplicates.append({
                    "occurrences": [
                        {"file": c["file"], "line": c["start_line"]} for c in chunks[:4]
                    ],
                    "preview": chunks[0]["chunk"].splitlines()[0][:120],
                })

            duplicate_percent = (
                round(100 * duplicated_windows / total_windows, 1) if total_windows else 0.0
            )

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "files_analyzed": len(files),
                    "window_size": window,
                    "total_windows": total_windows,
                    "duplicated_windows": duplicated_windows,
                    "duplicate_percent": duplicate_percent,
                    "duplicate_blocks": duplicates[:20],
                    "summary": {
                        "duplicate_percent": duplicate_percent,
                        "blocks": len(duplicates),
                        "level": "high"
                        if duplicate_percent > DUPLICATION_WARN_PERCENT
                        else "acceptable",
                    },
                },
                warnings=[
                    f"Code duplication at {duplicate_percent}% (threshold {DUPLICATION_WARN_PERCENT}%)"
                ]
                if duplicate_percent > DUPLICATION_WARN_PERCENT
                else [],
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Duplication detection failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        data = result.data
        recommendations = []
        if data["summary"]["level"] == "high":
            recommendations.append(Recommendation(
                title=f"Reduce duplication ({data['duplicate_percent']}%)",
                description=(
                    f"{data['duplicated_windows']} duplicated {data['window_size']}-line "
                    "blocks — extract shared helpers for the biggest offenders."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                risk_level="low",
            ))
        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        return True, []

"""Observability SLO Tracker Skill — real SloClient data (Phase 13).

Was a stub with fabricated compliance numbers. The reliability category
already ships a real SLO tracker over the shared SLO configs; this skill is
the observability-flavored view of the same live computation (identical
data source, different category/packaging), so it subclasses rather than
duplicating the analysis.
"""

from __future__ import annotations

from app.skills.base import SkillCategory, SkillPriority
from app.skills.reliability.slo_tracker import SLOTrackerSkill as ReliabilitySLOTracker


class SLOTrackerSkill(ReliabilitySLOTracker):
    """Track SLO compliance and error budget from real APM data."""

    skill_id = "observability_slo_tracker"
    name = "Observability SLO Tracker"
    description = (
        "Track Service Level Objective compliance and error budget from live "
        "APM data (observability view of the reliability SLO tracker)."
    )
    category = SkillCategory.OBSERVABILITY
    priority = SkillPriority.HIGH
    version = "2.0.0"

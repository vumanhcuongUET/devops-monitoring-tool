"""Compliance Skills."""

from app.skills.compliance.gdpr_auditor import GDPRAuditorSkill
from app.skills.compliance.soc2_auditor import SOC2AuditorSkill

__all__ = [
    "GDPRAuditorSkill",
    "SOC2AuditorSkill",
]

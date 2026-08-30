"""Unit tests for skill registry init hardening.

Regression for the old single try/except that let one broken group
(e.g. optional-dep ImportError) silently drop every group after it.
"""

import app.skills.registry as registry_module
from app.skills.registry import (
    EXPECTED_SKILL_COUNT,
    SkillRegistry,
    _initialize_registry,
)


def test_all_builtin_skills_register():
    """All builtin skills register on a fresh registry."""
    registry = SkillRegistry()
    _initialize_registry(registry)
    assert len(registry._skills) == EXPECTED_SKILL_COUNT


def test_group_failure_does_not_block_rest(monkeypatch):
    """A raising group must not prevent later groups from registering."""
    def _boom(_registry):
        raise RuntimeError("simulated group failure")

    monkeypatch.setattr(
        registry_module,
        "_SKILL_GROUPS",
        (_boom, *registry_module._SKILL_GROUPS[1:]),
    )
    registry = SkillRegistry()
    _initialize_registry(registry)
    # Only the 3 finops skills (first group) are missing.
    assert len(registry._skills) == EXPECTED_SKILL_COUNT - 3


def test_duplicate_free_registration_is_idempotent_error_visible(caplog):
    """Re-running init on a populated registry must not raise: the duplicate
    registrations are logged (registry reports the mismatch), not fatal."""
    registry = SkillRegistry()
    _initialize_registry(registry)
    with caplog.at_level("ERROR"):
        _initialize_registry(registry)  # every group now fails: already registered
    assert len(registry._skills) == EXPECTED_SKILL_COUNT
    assert any("PARTIALLY initialized" in r.message for r in caplog.records)

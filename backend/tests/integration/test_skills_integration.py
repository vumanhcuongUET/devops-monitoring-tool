"""Integration tests for the Skills registry contract.

All 44 registered skills are catalog stubs (STUB_SKILLS): execute() must
refuse so mock data is never returned as analysis. These tests pin that
contract — if a new skill lands unflagged, or a stub starts returning
fabricated data, they fail.
"""

import pytest

from app.skills.base import SkillConfig
from app.skills.registry import STUB_SKILLS, SkillCategory, get_skill_registry


@pytest.fixture
def registry():
    """Registry singleton, initialized with built-ins at module import."""
    return get_skill_registry()


class TestSkillCatalog:
    def test_all_builtin_skills_registered(self, registry):
        assert len(registry._skills) == 44

    def test_stub_flags_match_stub_set(self, registry):
        """Every registered skill flagged unimplemented is in STUB_SKILLS, and vice versa."""
        listed = registry.list_skills()
        unimplemented = {m["skill_id"] for m in listed if not m["implemented"]}
        assert unimplemented == set(STUB_SKILLS)

    def test_no_orphan_stub_entries(self, registry):
        """STUB_SKILLS contains no names that are not registered."""
        assert set(STUB_SKILLS) <= set(registry._skills)

    def test_skill_ids_unique(self, registry):
        ids = list(registry._skills)
        assert len(ids) == len(set(ids))

    def test_metadata_complete(self, registry):
        skills = registry.list_skills()
        assert skills, "registry must not be empty"
        for meta in skills:
            for field in ("skill_id", "name", "description", "category", "version", "implemented"):
                assert field in meta, f"skill {meta.get('skill_id')} missing {field}"

    def test_list_skills_by_category(self, registry):
        finops = registry.list_skills(category=SkillCategory.FINOPS)
        assert finops
        assert all(m["category"] == SkillCategory.FINOPS for m in finops)

    def test_implemented_only_filter_drops_stubs(self, registry):
        """The honest catalog view: implemented_only returns nothing while all are stubs."""
        assert registry.list_skills(implemented_only=True) == []


class TestStubRefusal:
    @pytest.mark.asyncio
    async def test_stub_execute_refused(self, registry):
        with pytest.raises(ValueError, match="not implemented yet"):
            await registry.execute("finops_cost_analyzer", "test-project", {})

    @pytest.mark.asyncio
    async def test_unknown_skill_refused(self, registry):
        with pytest.raises(ValueError, match="not found"):
            await registry.execute("no_such_skill", "test-project", {})

    @pytest.mark.asyncio
    async def test_disabled_skill_refused(self, registry):
        sid = "finops_cost_analyzer"
        registry.update_skill_config(sid, SkillConfig(enabled=False))
        try:
            with pytest.raises(ValueError, match="disabled"):
                await registry.execute(sid, "test-project", {})
        finally:
            registry.update_skill_config(sid, SkillConfig())

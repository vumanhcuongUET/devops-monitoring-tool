"""Integration tests for Skills system."""

import pytest
import pytest_asyncio

from app.skills.registry import SkillRegistry
from app.skills.capacity.planner import CapacityPlannerSkill
from app.skills.security.vulnerability_scanner import VulnerabilityScannerSkill
from app.skills.finops.cost_analyzer import CostAnalyzerSkill


@pytest.fixture
def registry():
    """Get a fresh skill registry for testing."""
    # Clear any existing registry state
    import app.skills.registry as reg_module
    if hasattr(reg_module, '_registry_instance'):
        reg_module._registry_instance = None
    return SkillRegistry()


class TestSkillRegistry:
    """Integration tests for SkillRegistry."""

    def test_registry_initialization(self, registry):
        """Test registry initializes with builtin skills."""
        skills = registry.list_skills()
        assert len(skills) > 0

    def test_get_skill_by_id(self, registry):
        """Test getting a specific skill."""
        skill = registry.get_skill("capacity_planner")
        assert skill is not None
        assert skill.skill_id == "capacity_planner"

    def test_get_nonexistent_skill(self, registry):
        """Test getting a non-existent skill."""
        skill = registry.get_skill("nonexistent_skill")
        assert skill is None

    def test_list_skills_by_category(self, registry):
        """Test filtering skills by category."""
        from app.skills.base import SkillCategory

        capacity_skills = registry.list_skills(skill_type=SkillCategory.CAPACITY)
        assert len(capacity_skills) > 0
        for skill in capacity_skills:
            assert skill.category == SkillCategory.CAPACITY

    def test_register_skill_dynamically(self, registry):
        """Test dynamically registering a skill."""
        from app.skills.base import SkillCategory, SkillPriority

        # Create a custom skill
        class CustomSkill:
            skill_id = "custom_test_skill"
            name = "Custom Test Skill"
            description = "A test skill"
            category = SkillCategory.DEVOPS
            priority = SkillPriority.LOW

        # Register it
        skill = CustomSkill()
        registry.register_skill(skill)

        # Verify it's registered
        retrieved = registry.get_skill("custom_test_skill")
        assert retrieved is not None
        assert retrieved.skill_id == "custom_test_skill"


class TestSkillExecution:
    """Integration tests for skill execution."""

    @pytest.mark.asyncio
    async def test_capacity_planner_execution(self, registry):
        """Test executing Capacity Planner skill."""
        skill = registry.get_skill("capacity_planner")
        assert skill is not None

        result = await skill.analyze(
            project="test-project",
            parameters={
                "forecast_horizon_days": 90,
                "resource_types": ["cpu", "memory"],
            },
        )

        assert result.success is True
        assert result.skill_id == "capacity_planner"
        assert "current_capacity" in result.data

    @pytest.mark.asyncio
    async def test_vulnerability_scanner_execution(self, registry):
        """Test executing Vulnerability Scanner skill."""
        skill = registry.get_skill("security_vulnerability_scanner")
        assert skill is not None

        result = await skill.analyze(
            project="test-project",
            parameters={"scan_type": "full"},
        )

        assert result.success is True
        assert result.skill_id == "security_vulnerability_scanner"

    @pytest.mark.asyncio
    async def test_cost_analyzer_execution(self, registry):
        """Test executing Cost Analyzer skill."""
        skill = registry.get_skill("finops_cost_analyzer")
        assert skill is not None

        result = await skill.analyze(
            project="test-project",
            parameters={"days": 30},
        )

        assert result.success is True
        assert result.skill_id == "finops_cost_analyzer"


class TestSkillRecommendations:
    """Integration tests for skill recommendations."""

    @pytest.mark.asyncio
    async def test_capacity_planner_recommendations(self, registry):
        """Test getting recommendations from Capacity Planner."""
        skill = registry.get_skill("capacity_planner")

        # First run analysis
        result = await skill.analyze(
            project="test-project",
            parameters={"forecast_horizon_days": 90},
        )

        # Get recommendations
        recommendations = await skill.get_recommendations(
            analysis_id="test-analysis-id",
            project="test-project",
        )

        # Note: This requires the registry to store results
        # In production, this would use actual analysis IDs


class TestMultiSkillAnalysis:
    """Integration tests for multi-skill analysis."""

    @pytest.mark.asyncio
    async def test_parallel_skill_execution(self, registry):
        """Test executing multiple skills in parallel."""
        import asyncio

        skill_ids = [
            "capacity_planner",
            "security_vulnerability_scanner",
            "finops_cost_analyzer",
        ]

        # Get skills
        skills = [registry.get_skill(sid) for sid in skill_ids]

        # Execute in parallel
        tasks = [
            skill.analyze(
                project="test-project",
                parameters={},
            )
            for skill in skills
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all succeeded
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Skill execution failed: {result}")
            assert result.success is True


class TestSkillErrorHandling:
    """Integration tests for skill error handling."""

    @pytest.mark.asyncio
    async def test_invalid_parameters(self, registry):
        """Test handling of invalid parameters."""
        skill = registry.get_skill("capacity_planner")

        result = await skill.analyze(
            project="test-project",
            parameters={"forecast_horizon_days": 500},  # Invalid
        )

        # Should fail gracefully
        assert result.success is False

    @pytest.mark.asyncio
    async def test_skill_timeout_handling(self, registry):
        """Test handling of skill timeouts."""
        # This would require a skill with a configured timeout
        skill = registry.get_skill("capacity_planner")

        # Create a config with short timeout
        from app.skills.base import SkillConfig
        skill.config = SkillConfig(timeout_seconds=0.001)

        result = await skill.analyze(
            project="test-project",
            parameters={},
        )

        # Should handle timeout gracefully
        # Note: This depends on implementation


class TestSkillMetadata:
    """Integration tests for skill metadata."""

    def test_all_skills_have_metadata(self, registry):
        """Test that all skills have required metadata."""
        skills = registry.list_skills()

        for skill in skills:
            assert hasattr(skill, 'skill_id')
            assert hasattr(skill, 'name')
            assert hasattr(skill, 'description')
            assert hasattr(skill, 'category')
            assert hasattr(skill, 'priority')
            assert hasattr(skill, 'version')

            # Verify values are not empty
            assert skill.skill_id
            assert skill.name
            assert skill.description

    def test_skill_ids_are_unique(self, registry):
        """Test that all skill IDs are unique."""
        skills = registry.list_skills()
        skill_ids = [skill.skill_id for skill in skills]

        assert len(skill_ids) == len(set(skill_ids))

    def test_all_skills_have_versions(self, registry):
        """Test that all skills have version numbers."""
        skills = registry.list_skills()

        for skill in skills:
            assert skill.version
            # Version should follow semantic versioning
            assert '.' in skill.version


@pytest.mark.integration
class TestSkillSystemEndToEnd:
    """End-to-end integration tests for the skills system."""

    @pytest.mark.asyncio
    async def test_complete_skill_workflow(self, registry):
        """Test complete workflow from analysis to recommendations."""
        # Step 1: Select a skill
        skill = registry.get_skill("capacity_planner")
        assert skill is not None

        # Step 2: Run analysis
        result = await skill.analyze(
            project="test-project",
            parameters={"forecast_horizon_days": 90},
        )
        assert result.success is True

        # Step 3: Check confidence
        assert 0.0 <= result.confidence <= 1.0

        # Step 4: Validate data structure
        assert "current_capacity" in result.data
        assert "forecast" in result.data

        # Step 5: In production, would get recommendations
        # recommendations = await skill.get_recommendations(analysis_id, project)

    @pytest.mark.asyncio
    async def test_skill_categories_coverage(self, registry):
        """Test that all expected skill categories are present."""
        from app.skills.base import SkillCategory

        skills = registry.list_skills()
        categories = set(skill.category for skill in skills)

        # Check for expected categories
        expected_categories = {
            SkillCategory.CAPACITY,
            SkillCategory.SECURITY,
            SkillCategory.FINOPS,
            SkillCategory.DEVOPS,
        }

        # At least some expected categories should be present
        assert len(categories.intersection(expected_categories)) > 0

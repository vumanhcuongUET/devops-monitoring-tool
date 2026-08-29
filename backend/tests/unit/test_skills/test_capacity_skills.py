"""Unit tests for the capacity skills (live implementations in planner.py /
bottleneck_detector.py / growth_predictor.py) and the registry stub flag."""

import pytest

from app.skills.base import SkillConfig
from app.skills.capacity.planner import CapacityPlannerSkill
from app.skills.capacity.bottleneck_detector import BottleneckDetectorSkill
from app.skills.capacity.growth_predictor import GrowthPredictorSkill
from app.skills.registry import SkillRegistry, STUB_SKILLS


@pytest.mark.asyncio
class TestCapacityPlannerSkill:
    """Tests for the registered CapacityPlannerSkill (capacity/planner.py)."""

    def test_initialization(self):
        # implemented flag is applied by SkillRegistry, not on direct instantiation
        skill = CapacityPlannerSkill()
        assert skill.skill_id == "capacity_planner"
        assert skill.name == "Capacity Planner"
        assert skill.category.value == "capacity"

    @pytest.mark.asyncio
    async def test_analyze_success(self):
        skill = CapacityPlannerSkill()
        result = await skill.analyze(
            project="test-project",
            parameters={"forecast_days": 30, "threshold_percent": 80},
        )
        assert result.success is True
        assert result.skill_id == "capacity_planner"
        assert "cpu" in result.data
        assert "memory" in result.data
        assert "disk" in result.data
        assert "capacity_needs" in result.data
        assert result.data["forecast_days"] == 30

    @pytest.mark.asyncio
    async def test_analyze_default_parameters(self):
        skill = CapacityPlannerSkill()
        result = await skill.analyze(project="test-project", parameters={})
        assert result.success is True
        assert result.data["forecast_days"] == 30
        assert result.data["threshold_percent"] == 80

    def test_validate_parameters_valid(self):
        skill = CapacityPlannerSkill()
        is_valid, errors = skill.validate_parameters(
            {"forecast_days": 90, "threshold_percent": 85}
        )
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_invalid_forecast_days(self):
        skill = CapacityPlannerSkill()
        is_valid, errors = skill.validate_parameters({"forecast_days": 0})
        assert is_valid is False
        assert any("forecast_days" in e for e in errors)

    def test_validate_parameters_invalid_threshold(self):
        skill = CapacityPlannerSkill()
        is_valid, errors = skill.validate_parameters({"threshold_percent": 101})
        assert is_valid is False
        assert any("threshold_percent" in e for e in errors)


@pytest.mark.asyncio
class TestBottleneckDetectorSkill:
    """Tests for the registered BottleneckDetectorSkill."""

    def test_initialization(self):
        skill = BottleneckDetectorSkill()
        assert skill.skill_id == "capacity_bottleneck_detector"
        assert skill.name == "Bottleneck Detector"

    @pytest.mark.asyncio
    async def test_analyze_success(self):
        skill = BottleneckDetectorSkill()
        result = await skill.analyze(
            project="test-project", parameters={"time_range_minutes": 60}
        )
        assert result.success is True
        assert result.skill_id == "capacity_bottleneck_detector"
        assert "bottlenecks" in result.data
        assert result.data["summary"]["total"] == len(result.data["bottlenecks"])

    def test_validate_parameters_accepts_anything(self):
        skill = BottleneckDetectorSkill()
        is_valid, errors = skill.validate_parameters({"anything": "goes"})
        assert is_valid is True
        assert errors == []


@pytest.mark.asyncio
class TestGrowthPredictorSkill:
    """Tests for the registered GrowthPredictorSkill."""

    def test_initialization(self):
        skill = GrowthPredictorSkill()
        assert skill.skill_id == "capacity_growth_predictor"
        assert skill.name == "Growth Predictor"

    @pytest.mark.asyncio
    async def test_analyze_success(self):
        skill = GrowthPredictorSkill()
        result = await skill.analyze(
            project="test-project",
            parameters={"forecast_months": 6, "lookback_days": 90},
        )
        assert result.success is True
        assert result.skill_id == "capacity_growth_predictor"
        assert "predictions" in result.data
        assert result.data["forecast_months"] == 6

    def test_validate_parameters_valid(self):
        skill = GrowthPredictorSkill()
        is_valid, errors = skill.validate_parameters(
            {"forecast_months": 3, "lookback_days": 90}
        )
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_invalid_forecast_months(self):
        skill = GrowthPredictorSkill()
        is_valid, errors = skill.validate_parameters({"forecast_months": 0})
        assert is_valid is False
        assert any("forecast_months" in e for e in errors)

    def test_validate_parameters_invalid_lookback_days(self):
        skill = GrowthPredictorSkill()
        is_valid, errors = skill.validate_parameters({"lookback_days": 3})
        assert is_valid is False
        assert any("lookback_days" in e for e in errors)


class TestStubFlag:
    """The registry must flag stub skills and refuse to execute them."""

    def test_stub_set_contains_registered_skills(self):
        assert "capacity_planner" in STUB_SKILLS
        assert "finops_cost_analyzer" in STUB_SKILLS

    def test_registry_marks_stubs(self):
        registry = SkillRegistry()
        registry.register(CapacityPlannerSkill)
        assert registry.get_skill("capacity_planner").implemented is False
        assert registry.get_skill("capacity_planner").get_metadata()["implemented"] is False

    @pytest.mark.asyncio
    async def test_registry_refuses_stub_execution(self):
        registry = SkillRegistry()
        registry.register(CapacityPlannerSkill)
        with pytest.raises(ValueError, match="not implemented"):
            await registry.execute(
                skill_id="capacity_planner",
                project="test",
                parameters={},
            )

    def test_list_skills_implemented_only_filter(self):
        registry = SkillRegistry()
        registry.register(CapacityPlannerSkill)
        all_skills = registry.list_skills()
        assert len(all_skills) == 1
        assert all_skills[0]["implemented"] is False
        filtered = registry.list_skills(implemented_only=True)
        assert filtered == []

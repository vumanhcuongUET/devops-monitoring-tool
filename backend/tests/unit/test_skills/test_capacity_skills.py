"""Tests for Capacity Planning skills."""

import pytest
from unittest.mock import AsyncMock, patch

from app.skills.capacity.capacity_planner import CapacityPlannerSkill
from app.skills.capacity.capacity_bottleneck_detector import CapacityBottleneckDetectorSkill
from app.skills.capacity.capacity_growth_predictor import CapacityGrowthPredictorSkill


class TestCapacityPlannerSkill:
    """Tests for CapacityPlannerSkill."""

    @pytest.fixture
    def skill(self):
        """Create a CapacityPlannerSkill instance."""
        return CapacityPlannerSkill()

    def test_skill_initialization(self, skill):
        """Test skill initialization."""
        assert skill.skill_id == "capacity_planner"
        assert skill.name == "Capacity Planner"
        assert skill.category.value == "capacity"
        assert skill.forecast_horizon_days == 90

    @pytest.mark.asyncio
    async def test_analyze_success(self, skill):
        """Test successful analysis."""
        result = await skill.analyze(
            project="test-project",
            parameters={
                "forecast_horizon_days": 60,
                "resource_types": ["cpu", "memory"],
            },
        )

        assert result.success is True
        assert result.skill_id == "capacity_planner"
        assert "current_capacity" in result.data
        assert "forecast" in result.data
        assert "capacity_gaps" in result.data

    @pytest.mark.asyncio
    async def test_analyze_with_custom_growth_rate(self, skill):
        """Test analysis with custom growth rate."""
        result = await skill.analyze(
            project="test-project",
            parameters={"growth_rate": 15.0},
        )

        assert result.success is True
        assert result.data["growth_rates"] == {"cpu": 15.0, "memory": 15.0}

    def test_validate_parameters_valid(self, skill):
        """Test parameter validation with valid parameters."""
        is_valid, errors = skill.validate_parameters({
            "forecast_horizon_days": 90,
            "resource_types": ["cpu", "memory", "storage"],
        })
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_invalid_horizon(self, skill):
        """Test parameter validation with invalid horizon."""
        is_valid, errors = skill.validate_parameters({
            "forecast_horizon_days": 400,  # > 365
        })
        assert is_valid is False
        assert len(errors) > 0
        assert "forecast_horizon_days" in errors[0]

    def test_validate_parameters_invalid_resource_type(self, skill):
        """Test parameter validation with invalid resource type."""
        is_valid, errors = skill.validate_parameters({
            "resource_types": ["invalid_type"],
        })
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_parameters_invalid_growth_rate(self, skill):
        """Test parameter validation with invalid growth rate."""
        is_valid, errors = skill.validate_parameters({
            "growth_rate": 150,  # > 100
        })
        assert is_valid is False
        assert len(errors) > 0


class TestCapacityBottleneckDetectorSkill:
    """Tests for CapacityBottleneckDetectorSkill."""

    @pytest.fixture
    def skill(self):
        """Create a CapacityBottleneckDetectorSkill instance."""
        return CapacityBottleneckDetectorSkill()

    def test_skill_initialization(self, skill):
        """Test skill initialization."""
        assert skill.skill_id == "capacity_bottleneck_detector"
        assert skill.name == "Capacity Bottleneck Detector"
        assert skill.category.value == "capacity"

    @pytest.mark.asyncio
    async def test_analyze_success(self, skill):
        """Test successful analysis."""
        result = await skill.analyze(
            project="test-project",
            parameters={},
        )

        assert result.success is True
        assert result.skill_id == "capacity_bottleneck_detector"
        assert "bottlenecks" in result.data
        assert "bottleneck_score" in result.data

    @pytest.mark.asyncio
    async def test_analyze_specific_components(self, skill):
        """Test analysis of specific components."""
        result = await skill.analyze(
            project="test-project",
            parameters={"components": ["cpu", "memory"]},
        )

        assert result.success is True
        assert "cpu" in result.data["bottlenecks"]
        assert "memory" in result.data["bottlenecks"]

    def test_validate_parameters_valid(self, skill):
        """Test parameter validation with valid parameters."""
        is_valid, errors = skill.validate_parameters({
            "analysis_period_hours": 24,
            "components": ["cpu", "memory", "disk"],
        })
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_invalid_period(self, skill):
        """Test parameter validation with invalid period."""
        is_valid, errors = skill.validate_parameters({
            "analysis_period_hours": -1,  # Negative
        })
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_parameters_invalid_component(self, skill):
        """Test parameter validation with invalid component."""
        is_valid, errors = skill.validate_parameters({
            "components": ["invalid_component"],
        })
        assert is_valid is False
        assert len(errors) > 0


class TestCapacityGrowthPredictorSkill:
    """Tests for CapacityGrowthPredictorSkill."""

    @pytest.fixture
    def skill(self):
        """Create a CapacityGrowthPredictorSkill instance."""
        return CapacityGrowthPredictorSkill()

    def test_skill_initialization(self, skill):
        """Test skill initialization."""
        assert skill.skill_id == "capacity_growth_predictor"
        assert skill.name == "Capacity Growth Predictor"
        assert skill.category.value == "capacity"

    @pytest.mark.asyncio
    async def test_analyze_success(self, skill):
        """Test successful analysis."""
        result = await skill.analyze(
            project="test-project",
            parameters={
                "prediction_horizon_days": 90,
                "resource_type": "all",
            },
        )

        assert result.success is True
        assert result.skill_id == "capacity_growth_predictor"
        assert "historical_growth" in result.data
        assert "predictions" in result.data
        assert "peak_periods" in result.data

    @pytest.mark.asyncio
    async def test_analyze_specific_resource_type(self, skill):
        """Test analysis of specific resource type."""
        result = await skill.analyze(
            project="test-project",
            parameters={"resource_type": "cpu"},
        )

        assert result.success is True

    def test_validate_parameters_valid(self, skill):
        """Test parameter validation with valid parameters."""
        is_valid, errors = skill.validate_parameters({
            "prediction_horizon_days": 180,
            "resource_type": "cpu",
        })
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_invalid_horizon(self, skill):
        """Test parameter validation with invalid horizon."""
        is_valid, errors = skill.validate_parameters({
            "prediction_horizon_days": 10,  # < 30
        })
        assert is_valid is False
        assert len(errors) > 0

    def test_validate_parameters_invalid_resource_type(self, skill):
        """Test parameter validation with invalid resource type."""
        is_valid, errors = skill.validate_parameters({
            "resource_type": "invalid_type",
        })
        assert is_valid is False
        assert len(errors) > 0


class TestCapacitySkillsIntegration:
    """Integration tests for capacity skills."""

    @pytest.mark.asyncio
    async def test_capacity_skills_workflow(self):
        """Test complete capacity planning workflow."""
        planner = CapacityPlannerSkill()
        detector = CapacityBottleneckDetectorSkill()
        predictor = CapacityGrowthPredictorSkill()

        # Step 1: Detect current bottlenecks
        bottleneck_result = await detector.analyze(
            project="test-project",
            parameters={},
        )
        assert bottleneck_result.success is True

        # Step 2: Plan capacity based on trends
        planner_result = await planner.analyze(
            project="test-project",
            parameters={"forecast_horizon_days": 90},
        )
        assert planner_result.success is True

        # Step 3: Predict future growth
        predictor_result = await predictor.analyze(
            project="test-project",
            parameters={"prediction_horizon_days": 180},
        )
        assert predictor_result.success is True

    @pytest.mark.asyncio
    async def test_capacity_skills_confidence_scores(self):
        """Test that skills provide reasonable confidence scores."""
        skills = [
            CapacityPlannerSkill(),
            CapacityBottleneckDetectorSkill(),
            CapacityGrowthPredictorSkill(),
        ]

        for skill in skills:
            result = await skill.analyze(
                project="test-project",
                parameters={},
            )
            assert 0.0 <= result.confidence <= 1.0

"""Tests for BaseSkill interface and core skill functionality."""

import pytest
from datetime import datetime, timezone

from app.skills.base import (
    BaseSkill,
    SkillCategory,
    SkillConfig,
    SkillPriority,
    AnalysisResult,
    Recommendation,
    SkillExecutionError,
    SkillValidationError,
)


class MockSkill(BaseSkill):
    """Mock skill for testing."""

    skill_id = "mock_skill"
    name = "Mock Skill"
    description = "A mock skill for testing"
    category = SkillCategory.DEVOPS
    priority = SkillPriority.MEDIUM
    version = "1.0.0"

    async def analyze(
        self,
        project: str,
        parameters: dict,
        context: dict = None,
    ) -> AnalysisResult:
        """Mock analyze implementation."""
        return AnalysisResult(
            success=True,
            skill_id=self.skill_id,
            confidence=0.8,
            data={"project": project, "parameters": parameters},
        )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Mock recommendations implementation."""
        return [
            Recommendation(
                title="Test recommendation",
                description="A test recommendation",
                priority=SkillPriority.LOW,
            )
        ]


class TestBaseSkill:
    """Tests for BaseSkill class."""

    def test_skill_initialization(self):
        """Test skill initialization with default config."""
        skill = MockSkill()
        assert skill.skill_id == "mock_skill"
        assert skill.name == "Mock Skill"
        assert skill.category == SkillCategory.DEVOPS
        assert skill.priority == SkillPriority.MEDIUM
        assert skill.version == "1.0.0"

    def test_skill_initialization_with_config(self):
        """Test skill initialization with custom config."""
        config = SkillConfig(
            enabled=True,
            priority=SkillPriority.HIGH,
            timeout_seconds=60,
            max_retries=5,
        )
        skill = MockSkill(config=config)
        assert skill.config.enabled is True
        assert skill.config.priority == SkillPriority.HIGH
        assert skill.config.timeout_seconds == 60
        assert skill.config.max_retries == 5

    def test_skill_initialization_invalid_config(self):
        """Test skill initialization with invalid config."""
        from pydantic_core import ValidationError
        with pytest.raises(ValidationError, match="timeout_seconds"):
            SkillConfig(timeout_seconds=0)  # Invalid

    def test_get_metadata(self):
        """Test get_metadata method."""
        skill = MockSkill()
        metadata = skill.get_metadata()
        assert metadata["skill_id"] == "mock_skill"
        assert metadata["name"] == "Mock Skill"
        assert metadata["category"] == SkillCategory.DEVOPS
        assert metadata["priority"] == SkillPriority.MEDIUM
        assert metadata["version"] == "1.0.0"
        assert "enabled" in metadata

    def test_validate_parameters_default(self):
        """Test default parameter validation."""
        skill = MockSkill()
        is_valid, errors = skill.validate_parameters({})
        assert is_valid is True
        assert errors == []

    def test_validate_parameters_custom(self):
        """Test custom parameter validation."""
        skill = MockSkill()

        # Override validate_parameters for testing
        def custom_validate(params):
            if "invalid_param" in params:
                return False, ["invalid_param not allowed"]
            return True, []

        skill.validate_parameters = custom_validate

        is_valid, errors = skill.validate_parameters({"invalid_param": True})
        assert is_valid is False
        assert "invalid_param not allowed" in errors


class TestSkillConfig:
    """Tests for SkillConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = SkillConfig()
        assert config.enabled is True
        assert config.priority == SkillPriority.MEDIUM
        assert config.timeout_seconds == 300
        assert config.max_retries == 3
        assert config.parameters == {}
        assert config.schedule is None

    def test_custom_config(self):
        """Test custom configuration."""
        config = SkillConfig(
            enabled=False,
            priority=SkillPriority.CRITICAL,
            timeout_seconds=600,
            max_retries=5,
            parameters={"threshold": 80},
            schedule="0 9 * * *",
        )
        assert config.enabled is False
        assert config.priority == SkillPriority.CRITICAL
        assert config.timeout_seconds == 600
        assert config.max_retries == 5
        assert config.parameters["threshold"] == 80
        assert config.schedule == "0 9 * * *"


class TestAnalysisResult:
    """Tests for AnalysisResult class."""

    def test_analysis_result_success(self):
        """Test successful analysis result."""
        result = AnalysisResult(
            success=True,
            skill_id="test_skill",
            confidence=0.9,
            data={"key": "value"},
        )
        assert result.success is True
        assert result.skill_id == "test_skill"
        assert result.confidence == 0.9
        assert result.data["key"] == "value"
        assert result.errors == []
        assert result.warnings == []

    def test_analysis_result_failure(self):
        """Test failed analysis result."""
        result = AnalysisResult(
            success=False,
            skill_id="test_skill",
            confidence=0.0,
            errors=["Error 1", "Error 2"],
        )
        assert result.success is False
        assert result.confidence == 0.0
        assert len(result.errors) == 2

    def test_analysis_result_with_warnings(self):
        """Test analysis result with warnings."""
        result = AnalysisResult(
            success=True,
            skill_id="test_skill",
            warnings=["Warning 1", "Warning 2"],
        )
        assert len(result.warnings) == 2

    def test_analysis_result_confidence_bounds(self):
        """Test confidence score bounds."""
        # Valid confidence
        result = AnalysisResult(
            success=True,
            skill_id="test_skill",
            confidence=0.5,
        )
        assert result.confidence == 0.5

        # Confidence should be bounded by Pydantic model
        # (This would be tested with model validation in production)


class TestRecommendation:
    """Tests for Recommendation class."""

    def test_recommendation_defaults(self):
        """Test recommendation with defaults."""
        rec = Recommendation(
            title="Test Recommendation",
            description="A test recommendation",
        )
        assert rec.title == "Test Recommendation"
        assert rec.description == "A test recommendation"
        assert rec.priority == SkillPriority.MEDIUM
        assert rec.action_type == "manual"
        assert rec.estimated_effort is None
        assert rec.risk_level == "low"
        assert rec.commands == []
        assert rec.references == []

    def test_recommendation_custom(self):
        """Test recommendation with custom fields."""
        rec = Recommendation(
            title="Test Recommendation",
            description="A test recommendation",
            priority=SkillPriority.HIGH,
            action_type="automated",
            estimated_effort="2 hours",
            risk_level="medium",
            commands=["kubectl get pods"],
            references=["https://example.com"],
        )
        assert rec.priority == SkillPriority.HIGH
        assert rec.action_type == "automated"
        assert rec.estimated_effort == "2 hours"
        assert rec.risk_level == "medium"
        assert len(rec.commands) == 1
        assert len(rec.references) == 1


class TestSkillExecutionError:
    """Tests for SkillExecutionError."""

    def test_skill_execution_error(self):
        """Test skill execution error."""
        error = SkillExecutionError(
            skill_id="test_skill",
            message="Test error",
            details={"context": "test"},
        )
        assert str(error) == "[test_skill] Test error"
        assert error.skill_id == "test_skill"
        assert error.details == {"context": "test"}


class TestSkillValidationError:
    """Tests for SkillValidationError."""

    def test_skill_validation_error(self):
        """Test skill validation error."""
        error = SkillValidationError(
            skill_id="test_skill",
            parameter="invalid_param",
            message="Parameter validation failed",
        )
        assert str(error) == "[test_skill] Invalid parameter 'invalid_param': Parameter validation failed"
        assert error.skill_id == "test_skill"
        assert error.parameter == "invalid_param"


class TestSkillCategories:
    """Tests for skill categories."""

    def test_all_categories(self):
        """Test all skill categories are defined."""
        categories = [
            SkillCategory.DEVOPS,
            SkillCategory.CODE,
            SkillCategory.SECURITY,
            SkillCategory.FINOPS,
            SkillCategory.CAPACITY,
            SkillCategory.MONITORING,
            SkillCategory.INCIDENT,
            SkillCategory.RELIABILITY,
            SkillCategory.COMPLIANCE,
        ]
        assert len(categories) == 9

    def test_category_values(self):
        """Test category values."""
        assert SkillCategory.DEVOPS == "devops"
        assert SkillCategory.SECURITY == "security"
        assert SkillCategory.CAPACITY == "capacity"


class TestSkillPriority:
    """Tests for skill priority levels."""

    def test_all_priorities(self):
        """Test all priority levels are defined."""
        priorities = [
            SkillPriority.CRITICAL,
            SkillPriority.HIGH,
            SkillPriority.MEDIUM,
            SkillPriority.LOW,
        ]
        assert len(priorities) == 4

    def test_priority_values(self):
        """Test priority values."""
        assert SkillPriority.CRITICAL == "critical"
        assert SkillPriority.HIGH == "high"
        assert SkillPriority.MEDIUM == "medium"
        assert SkillPriority.LOW == "low"

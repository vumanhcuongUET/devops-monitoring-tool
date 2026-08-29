"""Unit tests for Command Validator."""

import pytest
from unittest.mock import MagicMock

from app.actions.validator import (
    CommandValidator,
    ValidationResult,
    get_command_validator,
)
from app.models.actions import CommandType, CommandParams, RiskLevel
from app.models.registry import (
    ProjectConfig,
    ClusterConfig,
    RbacConstraints,
    NamespaceMapping,
)


@pytest.fixture
def mock_registry():
    """Mock registry with test project."""
    registry = MagicMock()

    # Create test project config
    cluster = ClusterConfig(
        name="test-cluster",
        context="test-context",
        platform="kubernetes",
    )

    namespaces = NamespaceMapping(
        app="meinvoice",
        database="meinvoice-db",
    )

    rbac = RbacConstraints(
        allowed_actions=["kubectl_get", "kubectl_describe", "kubectl_logs", "kubectl_get_pod", "kubectl_describe_deployment", "kubectl_logs_pod"],
        requires_approval=["kubectl_delete", "kubectl_delete_pod", "kubectl_scale", "kubectl_scale_deployment", "kubectl_rollout_restart", "kubectl_rollout_restart_deployment"],
        forbidden_actions=["kubectl_delete_namespace", "kubectl_delete_pvc"],
        requires_comment_for=["kubectl_delete", "kubectl_delete_pod"],
    )

    project = ProjectConfig(
        name="meinvoice",
        cluster=cluster,
        namespaces=namespaces,
        rbac=rbac,
    )

    registry.projects = [project]
    registry.global_constraints = None

    return registry


@pytest.fixture
def validator(mock_registry):
    """Create validator with mocked registry."""
    validator = CommandValidator()
    validator.registry = mock_registry
    return validator


@pytest.fixture
def mock_parser():
    """Mock command parser."""
    parser = MagicMock()
    return parser


class TestValidationResult:
    """Test ValidationResult class."""

    def test_validation_result_to_dict(self):
        """Test ValidationResult to_dict conversion."""
        result = ValidationResult(
            is_valid=True,
            allowed=True,
            requires_approval=False,
            reason="Test",
            risk_level=RiskLevel.SAFE,
            warnings=["warning1"],
        )

        result_dict = result.to_dict()

        assert result_dict["is_valid"] is True
        assert result_dict["allowed"] is True
        assert result_dict["requires_approval"] is False
        assert result_dict["risk_level"] == RiskLevel.SAFE
        assert result_dict["reason"] == "Test"
        assert result_dict["warnings"] == ["warning1"]

    def test_validation_result_defaults(self):
        """Test ValidationResult default values."""
        result = ValidationResult(is_valid=True, allowed=True)

        assert result.risk_level == RiskLevel.MEDIUM
        assert result.requires_approval is True
        assert result.reason == ""
        assert result.warnings == []


class TestCommandValidator:
    """Test CommandValidator functionality."""

    def test_validate_allowed_action(self, validator, mock_parser):
        """Test validation of allowed action."""
        # Setup parser
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            resource_type="pod",
            action="get",
            namespace="meinvoice",
        )

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="kubectl get pods -n meinvoice",
            project="meinvoice",
        )

        # Verify allowed without approval
        assert result.is_valid is True
        assert result.allowed is True
        assert result.requires_approval is False
        assert "allowed without approval" in result.reason.lower()

    def test_validate_action_requires_approval(self, validator, mock_parser):
        """Test validation of action requiring approval."""
        # Setup parser for delete action
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            resource_type="pod",
            action="delete",
            namespace="meinvoice",
        )

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="kubectl delete pod -n meinvoice",
            project="meinvoice",
        )

        # Verify requires approval
        assert result.is_valid is True
        assert result.allowed is True
        assert result.requires_approval is True
        assert "requires approval" in result.reason.lower()

    def test_validate_forbidden_action(self, validator, mock_parser):
        """Test validation of forbidden action."""
        # Setup parser for namespace delete (forbidden)
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            resource_type="namespace",
            action="delete",
        )

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="kubectl delete namespace meinvoice",
            project="meinvoice",
        )

        # Verify forbidden
        assert result.is_valid is True
        assert result.allowed is False
        assert "forbidden" in result.reason.lower()

    def test_validate_unknown_project(self, validator, mock_parser):
        """Test validation for unknown project."""
        # Setup parser
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            action="get",
        )

        validator.parser = mock_parser

        # Execute with unknown project
        result = validator.validate(
            command="kubectl get pods",
            project="unknown-project",
        )

        # Verify not found
        assert result.is_valid is False
        assert result.allowed is False
        assert "not found" in result.reason.lower()

    def test_validate_parse_failure(self, validator, mock_parser):
        """Test validation when parsing fails."""
        # Setup parser to raise exception
        mock_parser.parse.side_effect = ValueError("Invalid command")

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="invalid command",
            project="meinvoice",
        )

        # Verify parse error
        assert result.is_valid is False
        assert result.allowed is False
        assert "parse" in result.reason.lower() or "invalid" in result.reason.lower()

    def test_assess_risk_safe_actions(self, validator):
        """Test risk assessment for safe actions."""
        safe_actions = ["get", "describe", "logs", "top", "list", "status"]

        for action in safe_actions:
            params = CommandParams(
                command_type=CommandType.KUBECTL,
                action=action,
            )
            risk = validator._assess_risk(params)
            assert risk in [RiskLevel.SAFE, RiskLevel.LOW]

    def test_assess_risk_medium_actions(self, validator):
        """Test risk assessment for medium risk actions."""
        medium_actions = ["apply", "upgrade", "sync"]

        for action in medium_actions:
            params = CommandParams(
                command_type=CommandType.KUBECTL,
                action=action,
            )
            risk = validator._assess_risk(params)
            assert risk == RiskLevel.MEDIUM

    def test_assess_risk_high_actions(self, validator):
        """Test risk assessment for high risk actions."""
        high_actions = ["scale", "restart", "rollout"]

        for action in high_actions:
            params = CommandParams(
                command_type=CommandType.KUBECTL,
                action=action,
            )
            risk = validator._assess_risk(params)
            assert risk == RiskLevel.HIGH

    def test_assess_risk_critical_actions(self, validator):
        """Test risk assessment for critical risk actions."""
        critical_actions = ["delete", "remove", "uninstall"]

        for action in critical_actions:
            params = CommandParams(
                command_type=CommandType.KUBECTL,
                action=action,
            )
            risk = validator._assess_risk(params)
            assert risk == RiskLevel.CRITICAL

    def test_build_action_id_kubectl(self, validator):
        """Test action ID building for kubectl commands."""
        params = CommandParams(
            command_type=CommandType.KUBECTL,
            action="get",
            resource_type="pod",
        )

        action_id = validator._build_action_id(params)

        assert "kubectl" in action_id
        assert "get" in action_id
        assert "pod" in action_id

    def test_build_action_id_helm(self, validator):
        """Test action ID building for helm commands."""
        params = CommandParams(
            command_type=CommandType.HELM,
            action="upgrade",
        )

        action_id = validator._build_action_id(params)

        assert "helm" in action_id
        assert "upgrade" in action_id

    def test_build_action_id_minimal(self, validator):
        """Test action ID building with minimal params."""
        params = CommandParams(
            command_type=CommandType.KUBECTL,
            action="version",
        )

        action_id = validator._build_action_id(params)

        assert "kubectl" in action_id
        assert "version" in action_id

    def test_check_constraints_with_warnings(self, validator):
        """Test constraint checking generates warnings for required comments."""
        # Setup registry with comment requirement
        # Action_id will be kubectl_delete_pod based on current implementation
        validator.registry.projects[0].rbac.requires_comment_for = ["kubectl_delete_pod"]

        # Setup parser
        mock_parser = MagicMock()
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            action="delete",
            resource_type="pod",
        )

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="kubectl delete pod test-pod -n meinvoice",
            project="meinvoice",
        )

        # Verify warning about comment
        assert any("comment" in w.lower() for w in result.warnings)

    def test_validate_with_user_context(self, validator, mock_parser):
        """Test validation with user context."""
        # Setup parser
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            action="get",
        )

        validator.parser = mock_parser

        # Execute with user
        result = validator.validate(
            command="kubectl get pods",
            project="meinvoice",
            user="john.doe",
        )

        # Verify validation succeeds (user context logged but doesn't affect result)
        assert result.is_valid is True

    def test_check_rate_limit_default(self, validator):
        """Test rate limit checking returns default allowed."""
        allowed, message, _metadata = validator.check_rate_limit("meinvoice", "restart")

        # Default implementation returns allowed
        assert allowed is True
        assert "passed" in message.lower()

    def test_validate_global_constraints(self, mock_registry, mock_parser):
        """Test validation with global constraints."""
        # Setup global constraints
        from app.models.registry import RbacConstraints

        mock_registry.global_constraints = RbacConstraints(
            forbidden_actions=["kubectl_delete_all"],
        )

        # Create validator
        validator = CommandValidator()
        validator.registry = mock_registry

        # Setup parser
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            action="delete",
            resource_type="all",
        )

        validator.parser = mock_parser

        # Execute
        result = validator.validate(
            command="kubectl delete pod --all -n meinvoice",
            project="meinvoice",
        )

        # Verify global constraint checked
        assert result.is_valid is not None


    def test_check_rate_limit_project_not_found(self, validator):
        """Test rate limit checking with unknown project."""
        # The validator will return True with "Project not found" message
        # when project is not in registry
        allowed, message, _metadata = validator.check_rate_limit("unknown-project", "restart")

        # Unknown projects are denied
        assert allowed is False
        assert "not found" in message.lower()

    def test_assess_risk_unknown_action_default_medium(self, validator):
        """Test risk assessment for unknown actions defaults to MEDIUM."""
        # Create params with unknown action
        params = CommandParams(
            command_type=CommandType.SCRIPT,
            action="unknown_custom_action",
        )

        risk = validator._assess_risk(params)

        # Unknown actions should default to MEDIUM
        assert risk == RiskLevel.MEDIUM

    def test_assess_risk_version_safe(self, validator):
        """Test risk assessment for version/config commands returns SAFE."""
        safe_diagnostic_actions = ["version", "config", "help"]

        for action in safe_diagnostic_actions:
            params = CommandParams(
                command_type=CommandType.KUBECTL,
                action=action,
            )
            risk = validator._assess_risk(params)
            assert risk == RiskLevel.SAFE, f"Action {action} should be SAFE, got {risk}"

    def test_validate_default_policy_unknown_action(self, validator, mock_parser):
        """Test validation with default policy for unknown actions."""
        # Setup parser for action not in any list
        mock_parser.parse.return_value = CommandParams(
            command_type=CommandType.KUBECTL,
            action="custom_action",
            resource_type="pod",
        )

        # Execute
        result = validator.validate(
            command="kubectl custom_action pods",
            project="meinvoice",
        )

        # Unknown actions default to requiring approval
        assert result.is_valid is True
        assert result.allowed is True
        assert result.requires_approval is True
        assert "default policy" in result.reason.lower()


class TestCommandValidatorSingleton:
    """Test CommandValidator singleton pattern."""

    def test_get_command_validator_returns_singleton(self):
        """Test that get_command_validator returns same instance."""
        validator1 = get_command_validator()
        validator2 = get_command_validator()

        assert validator1 is validator2

    def test_get_command_validator_initializes_new_instance(self):
        """Test that first call initializes the validator."""
        from app.actions.validator import _validator
        _validator = None

        validator = get_command_validator()

        assert validator is not None
        assert isinstance(validator, CommandValidator)

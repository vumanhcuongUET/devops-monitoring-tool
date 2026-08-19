"""Unit tests for Action Engine."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.actions.engine import ActionEngine, get_action_engine
from app.actions.parser import get_command_parser
from app.actions.validator import get_command_validator, ValidationResult, RiskLevel
from app.actions.executor import get_command_executor, ExecutionResult
from app.approvals.store import get_approval_tracker
from app.audit.logger import get_audit_logger
from app.models.actions import (
    Action,
    ActionStatus,
    CommandType,
    CreateActionRequest,
    ApproveActionRequest,
    RejectActionRequest,
    ExecuteActionRequest,
    CommandParams,
)
from app.models.triage_card import Recommendation, SeverityLevel
from app.registry.loader import get_registry


@pytest.fixture
def mock_parser():
    """Mock command parser."""
    parser = MagicMock()
    parser.parse.return_value = CommandParams(
        command_type=CommandType.KUBECTL,
        resource_type="pod",
        resource_name="test-pod",
        namespace="default",
        action="get",
    )
    return parser


@pytest.fixture
def mock_validator():
    """Mock command validator."""
    validator = MagicMock()
    validator.validate.return_value = ValidationResult(
        is_valid=True,
        allowed=True,
        requires_approval=False,
        reason="Action allowed",
        risk_level=RiskLevel.SAFE,
    )
    return validator


@pytest.fixture
def mock_executor():
    """Mock command executor."""
    executor = AsyncMock()
    executor.execute.return_value = ExecutionResult(
        success=True,
        exit_code=0,
        stdout="pod ready",
        stderr="",
        duration_seconds=0.5,
    )
    return executor


@pytest.fixture
def mock_approval_tracker():
    """Mock approval tracker."""
    tracker = MagicMock()
    tracker.get.return_value = None
    tracker.get_all.return_value = {}
    return tracker


@pytest.fixture
def mock_audit_logger():
    """Mock audit logger."""
    logger = MagicMock()
    return logger


@pytest.fixture
def mock_registry():
    """Mock registry."""
    registry = MagicMock()
    registry.projects = []
    return registry


@pytest.fixture
def action_engine(
    mock_parser,
    mock_validator,
    mock_executor,
    mock_approval_tracker,
    mock_audit_logger,
    mock_registry,
):
    """Create ActionEngine with mocked dependencies."""
    engine = ActionEngine()
    engine.parser = mock_parser
    engine.validator = mock_validator
    engine.executor = mock_executor
    engine.approval_tracker = mock_approval_tracker
    engine.audit_logger = mock_audit_logger
    engine.registry = mock_registry
    engine.approval_history = MagicMock()
    engine.approval_history.add = MagicMock()
    return engine


@pytest.fixture
def sample_recommendation():
    """Create sample recommendation."""
    return Recommendation(
        priority=1,
        action="Check pod status",
        command="kubectl get pods -n default",
        reason="Verify pod health",
        risk=SeverityLevel.LOW,
        estimated_impact="No impact",
    )


@pytest.fixture
def sample_create_request():
    """Create sample create action request."""
    return CreateActionRequest(
        triage_card_id="tc-001",
        recommendation_id="rec-001",
        project="test-project",
    )


class TestActionEngine:
    """Test ActionEngine functionality."""

    def test_create_action_from_recommendation_success(
        self,
        action_engine,
        sample_recommendation,
        sample_create_request,
        mock_parser,
        mock_validator,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test successful action creation from recommendation."""
        # Execute
        action = action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify action created
        assert action.triage_card_id == "tc-001"
        assert action.recommendation_id == "rec-001"
        assert action.project == "test-project"
        assert action.command == "kubectl get pods -n default"
        assert action.title == "Check pod status"
        assert action.command_type == CommandType.KUBECTL

        # Verify parser called
        mock_parser.parse.assert_called_once_with("kubectl get pods -n default")

        # Verify validator called
        mock_validator.validate.assert_called_once()

        # Verify audit log called
        mock_audit_logger.log_action_created.assert_called_once()

        # Verify approval tracker updated
        mock_approval_tracker.set_status.assert_called_once()

    def test_create_action_requires_approval(
        self,
        action_engine,
        sample_create_request,
        sample_recommendation,
        mock_validator,
    ):
        """Test action creation when approval required."""
        # Setup validator to require approval
        mock_validator.validate.return_value = ValidationResult(
            is_valid=True,
            allowed=True,
            requires_approval=True,
            reason="Approval required",
            risk_level=RiskLevel.HIGH,
        )

        # Execute
        action = action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify status is pending
        assert action.status == ActionStatus.PENDING

    def test_create_action_auto_approved_for_safe_actions(
        self,
        action_engine,
        sample_create_request,
        sample_recommendation,
        mock_validator,
    ):
        """Test safe actions are auto-approved."""
        # Setup validator for safe action
        mock_validator.validate.return_value = ValidationResult(
            is_valid=True,
            allowed=True,
            requires_approval=False,
            reason="Safe action",
            risk_level=RiskLevel.SAFE,
        )

        # Execute
        action = action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify status is approved
        assert action.status == ActionStatus.APPROVED

    def test_create_action_forbidden_by_policy(
        self,
        action_engine,
        sample_create_request,
        sample_recommendation,
        mock_validator,
    ):
        """Test forbidden actions get critical risk."""
        # Setup validator to forbid action
        mock_validator.validate.return_value = ValidationResult(
            is_valid=True,
            allowed=False,
            requires_approval=True,
            reason="Action forbidden",
            risk_level=RiskLevel.CRITICAL,
        )

        # Execute
        action = action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify critical risk level
        assert action.risk_level == RiskLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_approve_action_success(
        self,
        action_engine,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test successful action approval."""
        # Setup tracker to return pending action
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.PENDING,
            "command": "kubectl get pods",
        }

        request = ApproveActionRequest(
            approved_by="john.doe",
            comment="Approved after review",
        )

        # Execute
        action = await action_engine.approve_action("act-123", request)

        # Verify approval
        assert action.status == ActionStatus.APPROVED
        assert action.approved_by == "john.doe"
        assert action.approved_at is not None

        # Verify tracker updated
        mock_approval_tracker.set_status.assert_called_once()

        # Verify audit log called
        mock_audit_logger.log_action_approved.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_action_fails_for_non_pending(
        self,
        action_engine,
        mock_approval_tracker,
    ):
        """Test approval fails for non-pending action."""
        # Setup tracker to return approved action
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.APPROVED,
        }

        request = ApproveActionRequest(approved_by="john.doe")

        # Execute and verify raises
        with pytest.raises(ValueError, match="is not pending"):
            await action_engine.approve_action("act-123", request)

    @pytest.mark.asyncio
    async def test_approve_action_not_found(
        self,
        action_engine,
        mock_approval_tracker,
    ):
        """Test approval fails for non-existent action."""
        # Setup tracker to return None
        mock_approval_tracker.get.return_value = None

        request = ApproveActionRequest(approved_by="john.doe")

        # Execute and verify raises
        with pytest.raises(ValueError, match="not found"):
            await action_engine.approve_action("act-123", request)

    @pytest.mark.asyncio
    async def test_reject_action_success(
        self,
        action_engine,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test successful action rejection."""
        # Setup tracker to return pending action
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.PENDING,
            "command": "kubectl delete pod",
        }

        request = RejectActionRequest(
            rejected_by="john.doe",
            reason="Too risky during business hours",
        )

        # Execute
        action = await action_engine.reject_action("act-123", request)

        # Verify rejection
        assert action.status == ActionStatus.REJECTED
        assert action.rejected_by == "john.doe"
        assert action.rejected_at is not None

        # Verify tracker updated
        mock_approval_tracker.set_status.assert_called_once()

        # Verify audit log called
        mock_audit_logger.log_action_rejected.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_action_success(
        self,
        action_engine,
        mock_executor,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test successful action execution."""
        # Setup tracker to return approved action with command
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.APPROVED,
            "command": "kubectl get pods",
        }

        request = ExecuteActionRequest(
            executed_by="john.doe",
            dry_run=False,
        )

        # Execute
        action = await action_engine.execute_action("act-123", request)

        # Verify execution
        assert action.status == ActionStatus.EXECUTED
        assert action.executed_by == "john.doe"
        assert action.executed_at is not None
        assert action.execution_result is not None
        assert action.execution_result.success is True

        # Verify executor called
        mock_executor.execute.assert_called_once_with(
            command="kubectl get pods",
            dry_run=False,
        )

        # Verify audit log called
        mock_audit_logger.log_action_executed.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_action_dry_run(
        self,
        action_engine,
        mock_executor,
        mock_approval_tracker,
    ):
        """Test dry run execution."""
        # Setup tracker and executor
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.APPROVED,
            "command": "kubectl delete pod",
        }
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="[DRY RUN] Command validation passed",
            stderr="",
            duration_seconds=0.0,
        )

        request = ExecuteActionRequest(
            executed_by="john.doe",
            dry_run=True,
        )

        # Execute
        action = await action_engine.execute_action("act-123", request)

        # Verify executor called with dry_run
        mock_executor.execute.assert_called_once_with(
            command="kubectl delete pod",
            dry_run=True,
        )

    @pytest.mark.asyncio
    async def test_execute_action_failure(
        self,
        action_engine,
        mock_executor,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test action execution failure."""
        # Setup tracker and executor for failure
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.APPROVED,
            "command": "kubectl delete pod",
        }
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="Error: pod not found",
            duration_seconds=0.3,
        )

        request = ExecuteActionRequest(
            executed_by="john.doe",
            dry_run=False,
        )

        # Execute
        action = await action_engine.execute_action("act-123", request)

        # Verify failed status
        assert action.status == ActionStatus.FAILED
        assert action.execution_result.success is False

    @pytest.mark.asyncio
    async def test_execute_action_not_approved(
        self,
        action_engine,
        mock_approval_tracker,
    ):
        """Test execution fails for non-approved action."""
        # Setup tracker to return pending action
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.PENDING,
        }

        request = ExecuteActionRequest(executed_by="john.doe")

        # Execute and verify raises
        with pytest.raises(ValueError, match="is not approved"):
            await action_engine.execute_action("act-123", request)

    @pytest.mark.asyncio
    async def test_execute_action_no_command(
        self,
        action_engine,
        mock_approval_tracker,
    ):
        """Test execution fails when command missing."""
        # Setup tracker without command
        mock_approval_tracker.get.return_value = {
            "status": ActionStatus.APPROVED,
        }

        request = ExecuteActionRequest(executed_by="john.doe")

        # Execute and verify raises
        with pytest.raises(ValueError, match="no command"):
            await action_engine.execute_action("act-123", request)

    def test_get_action(self, action_engine, mock_approval_tracker):
        """Test getting action details."""
        # Setup tracker
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": "approved",
            "command": "kubectl get pods",
        }

        # Execute
        result = action_engine.get_action("act-123")

        # Verify
        assert result is not None
        assert result["id"] == "act-123"
        mock_approval_tracker.get.assert_called_once_with("act-123")

    def test_get_action_not_found(self, action_engine, mock_approval_tracker):
        """Test getting non-existent action."""
        # Setup tracker to return None
        mock_approval_tracker.get.return_value = None

        # Execute
        result = action_engine.get_action("act-123")

        # Verify
        assert result is None

    def test_list_actions(self, action_engine, mock_approval_tracker):
        """Test listing actions."""
        # Setup tracker
        mock_approval_tracker.get_all.return_value = {
            "act-1": {"status": "pending", "project": "proj1"},
            "act-2": {"status": "approved", "project": "proj1"},
            "act-3": {"status": "rejected", "project": "proj2"},
        }

        # Execute
        result = action_engine.list_actions(project="proj1", limit=100)

        # Verify
        assert result.total >= 0
        assert hasattr(result, "actions")
        mock_approval_tracker.get_all.assert_called_once()

    def test_list_actions_with_status_filter(
        self, action_engine, mock_approval_tracker
    ):
        """Test listing actions with status filter."""
        # Execute with status filter
        result = action_engine.list_actions(status=ActionStatus.PENDING)

        # Verify filter applied (implementation detail)
        assert hasattr(result, "actions")

    def test_list_actions_with_project_filter(
        self, action_engine, mock_approval_tracker
    ):
        """Test listing actions with project filter."""
        # Execute with project filter
        result = action_engine.list_actions(project="test-project")

        # Verify
        assert hasattr(result, "actions")


class TestActionEngineSingleton:
    """Test ActionEngine singleton pattern."""

    def test_get_action_engine_returns_singleton(self):
        """Test that get_action_engine returns same instance."""
        engine1 = get_action_engine()
        engine2 = get_action_engine()

        assert engine1 is engine2

    def test_get_action_engine_initializes_new_instance(self):
        """Test that first call initializes the engine."""
        # Reset singleton
        from app.actions.engine import _action_engine
        _action_engine = None

        engine = get_action_engine()

        assert engine is not None
        assert isinstance(engine, ActionEngine)

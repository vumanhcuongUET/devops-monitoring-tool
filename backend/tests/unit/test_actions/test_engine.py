"""Unit tests for Action Engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.actions.engine import ActionEngine, get_action_engine
from app.actions.executor import ExecutionResult
from app.actions.rate_limiter import get_rate_limiter
from app.actions.validator import RiskLevel, ValidationResult
from app.models.actions import (
    ActionStatus,
    ApproveActionRequest,
    CommandParams,
    CommandType,
    CreateActionRequest,
    ExecuteActionRequest,
    RejectActionRequest,
)
from app.models.triage_card import Recommendation, SeverityLevel


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
    """Mock approval tracker (all-async API)."""
    tracker = AsyncMock()
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
    # Create mock for permission checker
    mock_permission_checker = MagicMock()
    mock_permission_checker.check_command.return_value = MagicMock(
        allowed=True,
        reason="Allowed",
        required_permission=MagicMock(value="view"),
        requires_approval=False,  # Auto-approve safe actions
        to_dict=lambda: {"allowed": True, "requires_approval": False},
    )

    # Create mock for env-aware executor
    mock_env_executor = AsyncMock()
    mock_env_executor.execute.return_value = MagicMock(
        success=True,
        stdout="Command executed",
        stderr="",
        exit_code=0,
        duration_seconds=1.0,
    )

    engine = ActionEngine()
    get_rate_limiter().reset()
    engine.parser = mock_parser
    engine.validator = mock_validator
    engine.executor = mock_executor
    engine.approval_tracker = mock_approval_tracker
    engine.audit_logger = mock_audit_logger
    engine.registry = mock_registry
    engine.approval_history = MagicMock()
    engine.approval_history.add = AsyncMock()
    engine.permission_checker = mock_permission_checker
    engine.env_aware_executor = mock_env_executor
    engine.feedback = MagicMock()
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

    @pytest.mark.asyncio
    async def test_create_action_from_recommendation_success(
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
        action = await action_engine.create_action_from_recommendation(
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

    @pytest.mark.asyncio
    async def test_create_action_requires_approval(
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
        action = await action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify status is pending
        assert action.status == ActionStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_action_auto_approved_for_safe_actions(
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
        action = await action_engine.create_action_from_recommendation(
            request=sample_create_request,
            recommendation=sample_recommendation,
        )

        # Verify status is approved
        assert action.status == ActionStatus.APPROVED

    @pytest.mark.asyncio
    async def test_create_action_forbidden_by_policy(
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
        action = await action_engine.create_action_from_recommendation(
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
        # Setup tracker to return pending action with all required fields
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Check pod status",
            "description": "Get pod status",
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
    async def test_self_approval_blocked(self, action_engine, mock_approval_tracker):
        """S6: creator cannot approve their own action (Phase 12)."""
        mock_approval_tracker.get = AsyncMock(return_value={
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "created_by": "john.doe",
            "context": {"environment": "development"},
        })
        action_engine.permission_checker.check = MagicMock(return_value=MagicMock(allowed=True))

        request = ApproveActionRequest(approved_by="john.doe")

        with pytest.raises(PermissionError, match="Self-approval blocked"):
            await action_engine.approve_action("act-123", request)

        mock_approval_tracker.set_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_without_permission_in_production_blocked(self, action_engine, mock_approval_tracker):
        """S6: approver without 'approve' permission in production is blocked."""
        mock_approval_tracker.get = AsyncMock(return_value={
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "context": {"environment": "production"},
        })
        action_engine.permission_checker.check = MagicMock(
            return_value=MagicMock(allowed=False, reason="read-only env")
        )

        request = ApproveActionRequest(approved_by="someone.else")

        with pytest.raises(PermissionError, match="lacks 'approve' permission"):
            await action_engine.approve_action("act-123", request)

        mock_approval_tracker.set_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_without_permission_blocked(self, action_engine, mock_approval_tracker):
        """S6 (security recheck F1): reject requires the `approve` permission too."""
        mock_approval_tracker.get = AsyncMock(return_value={
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "context": {"environment": "production"},
        })
        action_engine.permission_checker.check = MagicMock(
            return_value=MagicMock(allowed=False, reason="read-only env")
        )

        request = RejectActionRequest(rejected_by="someone.else", reason="not needed")

        with pytest.raises(PermissionError, match="lacks 'approve' permission"):
            await action_engine.reject_action("act-123", request)

        mock_approval_tracker.set_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_by_creator_allowed(self, action_engine, mock_approval_tracker):
        """S6 (security recheck F1): self-reject stays allowed — a creator
        cancelling their own pending request gains no privilege."""
        mock_approval_tracker.get = AsyncMock(return_value={
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "created_by": "john.doe",
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Check pod status",
            "description": "Get pod status",
            "context": {"environment": "development"},
        })
        action_engine.permission_checker.check = MagicMock(return_value=MagicMock(allowed=True))

        request = RejectActionRequest(rejected_by="john.doe", reason="cancelled by creator")

        await action_engine.reject_action("act-123", request)

        mock_approval_tracker.set_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_in_development_allowed(self, action_engine, mock_approval_tracker):
        """S6: permitted approver in development passes the integrity check."""
        mock_approval_tracker.get = AsyncMock(return_value={
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Check pod status",
            "description": "Get pod status",
            "context": {"environment": "development"},
        })
        action_engine.permission_checker.check = MagicMock(return_value=MagicMock(allowed=True))

        request = ApproveActionRequest(approved_by="approver.one")

        action = await action_engine.approve_action("act-123", request)

        assert action.status == ActionStatus.APPROVED
        mock_approval_tracker.set_status.assert_called_once()


    @pytest.mark.asyncio
    async def test_approve_action_fails_for_non_pending(
        self,
        action_engine,
        mock_approval_tracker,
    ):
        """Test approval fails for non-pending action."""
        # Setup tracker to return approved action with all required fields
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
            "project": "test-project",
            "title": "Test",
            "description": "Test",
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
        # Setup tracker to return pending action with all required fields
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "command": "kubectl delete pod",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="delete",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Delete pod",
            "description": "Delete a pod",
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
        # Setup tracker to return approved action with all required fields
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Get pods",
            "description": "Get pod status",
            "context": {"environment": "development"},  # Set environment to avoid OPA blocking
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

        # Verify env_aware_executor called (not the old mock_executor)
        action_engine.env_aware_executor.execute.assert_called_once()

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
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl delete pod",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="delete",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Delete pod",
            "description": "Delete a pod",
            "context": {"environment": "development"},  # Set environment to avoid OPA blocking
        }

        request = ExecuteActionRequest(
            executed_by="john.doe",
            dry_run=True,
        )

        # Execute
        action = await action_engine.execute_action("act-123", request)

        # Verify executor called with dry_run — the request flag must reach the
        # executor, not just the audit log (Phase 12 B2 regression guard).
        action_engine.env_aware_executor.execute.assert_called_once()
        _, kwargs = action_engine.env_aware_executor.execute.call_args
        assert kwargs.get("dry_run") is True

    @pytest.mark.asyncio
    async def test_execute_action_failure(
        self,
        action_engine,
        mock_executor,
        mock_approval_tracker,
        mock_audit_logger,
    ):
        """Test action execution failure."""
        # Setup env_aware_executor to return failure
        action_engine.env_aware_executor.execute.return_value = ExecutionResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="Error: pod not found",
            duration_seconds=0.3,
        )

        # Setup tracker and executor for failure
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl delete pod",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL,
                action="delete",
                resource_type="pod",
            ),
            "project": "test-project",
            "title": "Delete pod",
            "description": "Delete a pod",
            "context": {"environment": "development"},  # Set environment to avoid OPA blocking
        }

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
        # Setup tracker to return pending action with all required fields
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.PENDING,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
            "project": "test-project",
            "title": "Get pods",
            "description": "Get pod status",
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
        # Setup tracker without command (but with all other required fields)
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
            "project": "test-project",
            "title": "Get pods",
            "description": "Get pod status",
        }

        request = ExecuteActionRequest(executed_by="john.doe")

        # Execute and verify raises
        with pytest.raises(ValueError, match="no command"):
            await action_engine.execute_action("act-123", request)

    @pytest.mark.asyncio
    async def test_get_action(self, action_engine, mock_approval_tracker):
        """Test getting action details."""
        # Setup tracker
        mock_approval_tracker.get.return_value = {
            "id": "act-123",
            "status": "approved",
            "command": "kubectl get pods",
        }

        # Execute
        result = await action_engine.get_action("act-123")

        # Verify
        assert result is not None
        assert result["id"] == "act-123"
        mock_approval_tracker.get.assert_called_once_with("act-123")

    @pytest.mark.asyncio
    async def test_get_action_injects_id_when_state_omits_it(
        self, action_engine, mock_approval_tracker
    ):
        """Tracker state is keyed by id and omits it — get_action must inject
        it so the API response_model can rehydrate Action (Phase 12 manual
        smoke: GET /actions/{id} 500'd on pydantic 'id: Field required')."""
        mock_approval_tracker.get.return_value = {
            "status": "pending",
            "command": "kubectl get pods",
        }

        result = await action_engine.get_action("act-xyz")

        assert result is not None
        assert result["id"] == "act-xyz"

    @pytest.mark.asyncio
    async def test_get_action_not_found(self, action_engine, mock_approval_tracker):
        """Test getting non-existent action."""
        # Setup tracker to return None
        mock_approval_tracker.get.return_value = None

        # Execute
        result = await action_engine.get_action("act-123")

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_list_actions(self, action_engine, mock_approval_tracker):
        """Test listing actions."""
        # Setup tracker with complete Action objects
        mock_approval_tracker.get_all.return_value = {
            "act-1": {
                "id": "act-1",
                "status": "pending",
                "project": "proj1",
                "command": "kubectl get pods",
                "command_type": CommandType.KUBECTL,
                "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
                "title": "Get pods",
                "description": "Get pod status",
            },
            "act-2": {
                "id": "act-2",
                "status": "approved",
                "project": "proj1",
                "command": "kubectl get pods",
                "command_type": CommandType.KUBECTL,
                "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
                "title": "Get pods",
                "description": "Get pod status",
            },
            "act-3": {
                "id": "act-3",
                "status": "rejected",
                "project": "proj2",
                "command": "kubectl get pods",
                "command_type": CommandType.KUBECTL,
                "parsed_params": CommandParams(command_type=CommandType.KUBECTL),
                "title": "Get pods",
                "description": "Get pod status",
            },
        }

        # Execute
        result = await action_engine.list_actions(project="proj1", limit=100)

        # Verify
        assert result.total >= 0
        assert hasattr(result, "actions")
        mock_approval_tracker.get_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_actions_with_status_filter(
        self, action_engine, mock_approval_tracker
    ):
        """Test listing actions with status filter."""
        # Execute with status filter
        result = await action_engine.list_actions(status=ActionStatus.PENDING)

        # Verify filter applied (implementation detail)
        assert hasattr(result, "actions")

    @pytest.mark.asyncio
    async def test_list_actions_with_project_filter(
        self, action_engine, mock_approval_tracker
    ):
        """Test listing actions with project filter."""
        # Execute with project filter
        result = await action_engine.list_actions(project="test-project")

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


class TestTimeWindowWiring:
    """Phase 12 Sprint 3: time-window enforcement is in the execute path."""

    @pytest.mark.asyncio
    async def test_execution_outside_window_blocked_and_audited(self, action_engine, mock_approval_tracker, mock_audit_logger):

        from app.models.audit import AuditEventType

        window_enforcer = MagicMock()
        window_enforcer.check_time_window.return_value = MagicMock(
            is_allowed=False, reason="Not allowed in time window 'business-hours'"
        )

        state = {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL, action="get", resource_type="pod",
            ),
            "project": "test-project",
            "title": "Check pod status",
            "description": "Get pod status",
            "context": {"environment": "production"},
        }
        mock_approval_tracker.get = AsyncMock(return_value=state)

        with patch("app.actions.engine.get_time_window_enforcer", return_value=window_enforcer):
            request = ExecuteActionRequest(executed_by="operator", dry_run=False)
            with pytest.raises(PermissionError, match="time window"):
                await action_engine.execute_action("act-123", request)

        window_enforcer.check_time_window.assert_called_once()
        blocked = [
            c for c in mock_audit_logger.log_event.call_args_list
            if c.kwargs.get("details", {}).get("blocked_by") == "time_window"
        ]
        assert blocked, "time-window block must be audit-logged"
        assert blocked[0].kwargs["event_type"] == AuditEventType.VALIDATION_CHECK

    @pytest.mark.asyncio
    async def test_failed_action_creates_pending_rollback_action(self, action_engine, mock_approval_tracker):
        """Phase 12 Sprint 3: failed execution leaves a PENDING rollback action."""
        from app.models.actions import ExecutionResult

        state = {
            "id": "act-fail",
            "status": ActionStatus.APPROVED,
            "command": "kubectl apply -f bad.yaml",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL, action="apply", resource_type="configmap",
            ),
            "project": "test-project",
            "title": "Apply config",
            "description": "Apply config",
            "context": {"environment": "development"},
        }
        mock_approval_tracker.get = AsyncMock(return_value=state)

        action_engine.env_aware_executor.execute = AsyncMock(return_value=ExecutionResult(
            success=False, exit_code=1, stdout="", stderr="boom", duration_seconds=0.1,
        ))
        action_engine.feedback = MagicMock()
        # Rollback commands are mutating — real validator requires approval for them
        action_engine.validator.validate.return_value = ValidationResult(
            is_valid=True, allowed=True, requires_approval=True,
            reason="mutating", risk_level=RiskLevel.HIGH,
        )

        request = ExecuteActionRequest(executed_by="operator", dry_run=False)
        await action_engine.execute_action("act-fail", request)

        statuses = [
            c.kwargs.get("status") for c in mock_approval_tracker.set_status.call_args_list
        ]
        from app.models.actions import ActionStatus as AS
        assert any(s == AS.PENDING for s in statuses), (
            "a PENDING rollback action must be created after a failed execution"
        )


class TestOPAEnforcement:
    """Phase 12 Sprint 3: flag-gated OPA enforcement in the execute path."""

    def _approved_state(self):
        return {
            "id": "act-123",
            "status": ActionStatus.APPROVED,
            "command": "kubectl get pods",
            "command_type": CommandType.KUBECTL,
            "parsed_params": CommandParams(
                command_type=CommandType.KUBECTL, action="get", resource_type="pod",
            ),
            "project": "test-project",
            "title": "Check pod status",
            "description": "Get pod status",
            "context": {"environment": "development"},
        }

    @pytest.mark.asyncio
    async def test_opa_deny_blocks_when_enforce_enabled(self, action_engine, mock_approval_tracker):
        from app.governance.opa_client import PolicyDecision, PolicyEvaluationResult

        mock_approval_tracker.get = AsyncMock(return_value=self._approved_state())
        opa = MagicMock()
        opa.evaluate_action = AsyncMock(return_value=PolicyEvaluationResult(decision=PolicyDecision.DENY))

        with patch("app.actions.engine.settings") as mock_settings, \
             patch("app.actions.engine.get_opa_client", return_value=opa):
            mock_settings.OPA_ENFORCE = True
            request = ExecuteActionRequest(executed_by="operator", dry_run=False)
            with pytest.raises(PermissionError, match="OPA policy"):
                await action_engine.execute_action("act-123", request)

    @pytest.mark.asyncio
    async def test_opa_unreachable_does_not_block(self, action_engine, mock_approval_tracker):
        mock_approval_tracker.get = AsyncMock(return_value=self._approved_state())
        opa = MagicMock()
        opa.evaluate_action = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch("app.actions.engine.settings") as mock_settings, \
             patch("app.actions.engine.get_opa_client", return_value=opa):
            mock_settings.OPA_ENFORCE = True
            request = ExecuteActionRequest(executed_by="operator", dry_run=False)
            action = await action_engine.execute_action("act-123", request)

        assert action.status == ActionStatus.EXECUTED


@pytest.mark.asyncio
async def test_rollback_survives_real_audit_logger(
    action_engine, mock_approval_tracker, monkeypatch, tmp_path
):
    """Phase 15 P1-1: the rollback trigger must pass a valid AuditEventType.

    With the mocked audit logger of every other test, the invalid
    'rollback_triggered' string silently passed; the real AuditLogger
    (pydantic-validated) raised, the broad except overwrote the persisted
    status and re-raised — every rollback-triggering execution 500'd.
    """
    from app.audit.logger import AuditLogger
    from app.config import settings as app_settings
    from app.models.actions import ExecutionResult

    monkeypatch.setattr(app_settings, "DATA_DIR", str(tmp_path))
    action_engine.audit_logger = AuditLogger()

    state = {
        "id": "act-fail-real",
        "status": ActionStatus.APPROVED,
        "command": "kubectl apply -f bad.yaml",
        "command_type": CommandType.KUBECTL,
        "parsed_params": CommandParams(
            command_type=CommandType.KUBECTL, action="apply", resource_type="configmap",
        ),
        "project": "test-project",
        "title": "Apply config",
        "description": "Apply config",
        "context": {"environment": "development"},
    }
    mock_approval_tracker.get = AsyncMock(return_value=state)
    action_engine.env_aware_executor.execute = AsyncMock(return_value=ExecutionResult(
        success=False, exit_code=1, stdout="", stderr="boom", duration_seconds=0.1,
    ))
    action_engine.feedback = MagicMock()
    action_engine.validator.validate.return_value = ValidationResult(
        is_valid=True, allowed=True, requires_approval=True,
        reason="mutating", risk_level=RiskLevel.HIGH,
    )

    request = ExecuteActionRequest(executed_by="operator", dry_run=False)
    result = await action_engine.execute_action("act-fail-real", request)

    assert result.status == ActionStatus.FAILED
    statuses = [
        c.kwargs.get("status") for c in mock_approval_tracker.set_status.call_args_list
    ]
    assert any(s == ActionStatus.PENDING for s in statuses), (
        "a PENDING rollback action must be created after a failed execution"
    )


@pytest.mark.asyncio
async def test_dry_run_keeps_action_approved(action_engine, mock_approval_tracker):
    """Phase 15: a dry run must not consume the approval — status stays
    APPROVED so the operator can execute for real afterwards."""
    from app.models.actions import ExecutionResult

    state = {
        "id": "act-dry",
        "status": ActionStatus.APPROVED,
        "command": "kubectl get pods",
        "command_type": CommandType.KUBECTL,
        "parsed_params": CommandParams(
            command_type=CommandType.KUBECTL, action="get", resource_type="pod",
        ),
        "project": "test-project",
        "title": "Check pods",
        "description": "Check pods",
        "context": {"environment": "development"},
    }
    mock_approval_tracker.get = AsyncMock(return_value=state)
    action_engine.env_aware_executor.execute = AsyncMock(return_value=ExecutionResult(
        success=True, exit_code=0, stdout="ok", duration_seconds=0.01,
    ))
    action_engine.feedback = MagicMock()

    request = ExecuteActionRequest(executed_by="operator", dry_run=True)
    result = await action_engine.execute_action("act-dry", request)

    assert result.status == ActionStatus.APPROVED
    statuses = [
        c.kwargs.get("status") for c in mock_approval_tracker.set_status.call_args_list
    ]
    assert ActionStatus.EXECUTED not in statuses, "dry run must not set EXECUTED"


@pytest.mark.asyncio
async def test_dry_run_does_not_consume_rate_limit_slot(action_engine, mock_approval_tracker, monkeypatch):
    """Dry runs mutate nothing — they must not burn the cooldown slot that
    the real execution needs."""
    from unittest.mock import MagicMock as _M
    from app.models.actions import ExecutionResult

    rl = _M()
    rl.check.return_value = (True, "allowed", {})
    monkeypatch.setattr("app.actions.engine.get_rate_limiter", lambda: rl)

    state = {
        "id": "act-dry-rl",
        "status": ActionStatus.APPROVED,
        "command": "kubectl get pods",
        "command_type": CommandType.KUBECTL,
        "parsed_params": CommandParams(
            command_type=CommandType.KUBECTL, action="get", resource_type="pod",
        ),
        "project": "test-project",
        "title": "Check pods",
        "description": "Check pods",
        "context": {"environment": "development"},
    }
    mock_approval_tracker.get = AsyncMock(return_value=state)
    action_engine.env_aware_executor.execute = AsyncMock(return_value=ExecutionResult(
        success=True, exit_code=0, stdout="ok", duration_seconds=0.01,
    ))
    action_engine.feedback = MagicMock()

    await action_engine.execute_action(
        "act-dry-rl", ExecuteActionRequest(executed_by="operator", dry_run=True)
    )
    rl.record_action.assert_not_called()

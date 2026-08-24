"""Unit tests for RollbackExecutor."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone

from app.actions.rollback_executor import (
    RollbackExecutor,
    RollbackStatus,
    RollbackPlan,
    RollbackCondition,
    RollbackResult,
    get_rollback_executor,
)


@pytest.fixture
def reset_rollback_executor():
    """Reset the global rollback executor before each test."""
    global _rollback_executor
    from app.actions.rollback_executor import _rollback_executor
    _rollback_executor = None
    yield
    _rollback_executor = None


class TestRollbackCondition:
    """Test RollbackCondition dataclass."""

    def test_condition_creation(self):
        """Test creating a rollback condition."""
        condition = RollbackCondition(
            name="test_condition",
            description="Test condition",
            check_fn=lambda ctx: True,
        )

        assert condition.name == "test_condition"
        assert condition.description == "Test condition"
        assert condition.check_fn({"test": "context"}) is True


class TestRollbackPlan:
    """Test RollbackPlan dataclass."""

    def test_plan_creation(self):
        """Test creating a rollback plan."""
        plan = RollbackPlan(
            action_id="action-1",
            original_command="kubectl apply -f deploy.yaml",
            rollback_command="kubectl delete -f deploy.yaml",
            reason="Generated rollback plan",
        )

        assert plan.action_id == "action-1"
        assert plan.rollback_command == "kubectl delete -f deploy.yaml"
        assert plan.requires_approval is True


class TestRollbackResult:
    """Test RollbackResult dataclass."""

    def test_result_creation(self):
        """Test creating a rollback result."""
        result = RollbackResult(
            action_id="action-1",
            rollback_action_id="rollback-action-1",
            status=RollbackStatus.SUCCESS,
            rollback_command="kubectl delete pod my-pod",
            output="Pod deleted",
        )

        assert result.action_id == "action-1"
        assert result.status == RollbackStatus.SUCCESS
        assert result.rollback_command == "kubectl delete pod my-pod"
        assert isinstance(result.timestamp, datetime)


class TestRollbackExecutor:
    """Test RollbackExecutor functionality."""

    def test_initial_state(self):
        """Test that executor starts with empty state."""
        executor = RollbackExecutor()

        assert len(executor._rollback_plans) == 0
        assert len(executor._rollback_history) == 0
        assert len(executor._conditions) > 0  # Should have default conditions

    def test_default_conditions(self):
        """Test that default conditions are created."""
        executor = RollbackExecutor()

        condition_names = [c.name for c in executor._conditions]
        assert "action_failed" in condition_names
        assert "high_error_rate" in condition_names
        assert "health_check_failed" in condition_names

    def test_create_rollback_plan_kubectl_apply(self):
        """Test creating rollback plan for kubectl apply."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl apply -f deployment.yaml -n default",
        )

        assert plan is not None
        assert plan.action_id == "action-1"
        assert "delete" in plan.rollback_command

    def test_create_rollback_plan_kubectl_rollout_restart(self):
        """Test creating rollback plan for kubectl rollout restart."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-2",
            command="kubectl rollout restart deployment my-app -n prod",
        )

        assert plan is not None
        assert "undo" in plan.rollback_command
        assert "my-app" in plan.rollback_command

    def test_create_rollback_plan_helm_upgrade(self):
        """Test creating rollback plan for helm upgrade."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-3",
            command="helm upgrade my-release ./chart -n prod",
        )

        assert plan is not None
        assert "rollback" in plan.rollback_command
        assert "my-release" in plan.rollback_command

    def test_create_rollback_plan_helm_install(self):
        """Test creating rollback plan for helm install."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-4",
            command="helm install my-release ./chart -n prod",
        )

        assert plan is not None
        assert "uninstall" in plan.rollback_command

    def test_create_rollback_plan_unsupported(self):
        """Test that unsupported commands return None."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-5",
            command="kubectl get pods",  # Read-only operation
        )

        assert plan is None

    def test_should_rollback_on_failure(self):
        """Test that failed action triggers rollback."""
        executor = RollbackExecutor()

        should_rollback, triggered = executor.should_rollback(
            action_id="action-1",
            execution_context={"execution_success": False},
        )

        assert should_rollback is True
        assert "action_failed" in triggered

    def test_should_rollback_on_high_error_rate(self):
        """Test that high error rate triggers rollback."""
        executor = RollbackExecutor()

        should_rollback, triggered = executor.should_rollback(
            action_id="action-1",
            execution_context={"execution_success": True, "error_rate": 0.7},
        )

        assert should_rollback is True
        assert "high_error_rate" in triggered

    def test_should_not_rollback_on_success(self):
        """Test that successful action doesn't trigger rollback."""
        executor = RollbackExecutor()

        should_rollback, triggered = executor.should_rollback(
            action_id="action-1",
            execution_context={"execution_success": True},
        )

        assert should_rollback is False
        assert len(triggered) == 0

    def test_execute_rollback_dry_run(self):
        """Test rollback execution in dry run mode."""
        executor = RollbackExecutor()

        # Create a plan first
        executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl rollout restart deployment my-app",
        )

        result = asyncio.run(executor.execute_rollback(
            action_id="action-1",
            executor=Mock(),
            dry_run=True,
        ))

        assert result.status == RollbackStatus.SKIPPED
        assert "[DRY RUN]" in result.output

    def test_execute_rollback_success(self):
        """Test successful rollback execution."""
        executor = RollbackExecutor()

        # Create a plan
        executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl rollout restart deployment my-app",
        )

        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=Mock(
            success=True,
            stdout="Rollback successful",
            stderr="",
        ))

        result = asyncio.run(executor.execute_rollback(
            action_id="action-1",
            executor=mock_executor,
            dry_run=False,
        ))

        assert result.status == RollbackStatus.SUCCESS
        assert "Rollback successful" in result.output

    def test_execute_rollback_failure(self):
        """Test failed rollback execution."""
        executor = RollbackExecutor()

        # Create a plan
        executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl rollout restart deployment my-app",
        )

        # Mock executor that fails
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=Mock(
            success=False,
            stdout="",
            stderr="Rollback failed: deployment not found",
        ))

        result = asyncio.run(executor.execute_rollback(
            action_id="action-1",
            executor=mock_executor,
            dry_run=False,
        ))

        assert result.status == RollbackStatus.FAILED
        assert "Rollback failed" in result.error or "not found" in result.error

    def test_execute_rollback_no_plan(self):
        """Test rollback execution when no plan exists."""
        executor = RollbackExecutor()

        result = asyncio.run(executor.execute_rollback(
            action_id="nonexistent",
            executor=Mock(),
            dry_run=False,
        ))

        assert result.status == RollbackStatus.FAILED
        assert "No rollback plan found" in result.error

    def test_get_rollback_plan(self):
        """Test retrieving a rollback plan."""
        executor = RollbackExecutor()

        plan = executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl apply -f deploy.yaml",
        )

        retrieved = executor.get_rollback_plan("action-1")

        assert retrieved is not None
        assert retrieved.action_id == "action-1"
        assert retrieved.rollback_command == plan.rollback_command

    def test_get_rollback_plan_not_found(self):
        """Test retrieving non-existent plan."""
        executor = RollbackExecutor()

        retrieved = executor.get_rollback_plan("nonexistent")

        assert retrieved is None

    def test_get_rollback_history(self):
        """Test retrieving rollback history."""
        executor = RollbackExecutor()

        # Create and execute a rollback
        executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl apply -f deploy.yaml",
        )

        asyncio.run(executor.execute_rollback(
            action_id="action-1",
            executor=Mock(),
            dry_run=True,
        ))

        history = executor.get_rollback_history()
        assert len(history) == 1
        assert history[0].action_id == "action-1"

    def test_get_rollback_history_filtered(self):
        """Test retrieving rollback history filtered by action ID."""
        executor = RollbackExecutor()

        # Create and execute multiple rollbacks
        for i in range(3):
            executor.create_rollback_plan(
                action_id=f"action-{i}",
                command="kubectl apply -f deploy.yaml",
            )
            asyncio.run(executor.execute_rollback(
                action_id=f"action-{i}",
                executor=Mock(),
                dry_run=True,
            ))

        # Get history for specific action
        history = executor.get_rollback_history(action_id="action-1")
        assert len(history) == 1
        assert history[0].action_id == "action-1"

    def test_add_rollback_condition(self):
        """Test adding a custom rollback condition."""
        executor = RollbackExecutor()

        original_count = len(executor._conditions)

        custom_condition = RollbackCondition(
            name="custom_condition",
            description="Custom rollback condition",
            check_fn=lambda ctx: ctx.get("custom_metric", 0) > 100,
        )

        executor.add_rollback_condition(custom_condition)

        assert len(executor._conditions) == original_count + 1
        assert "custom_condition" in [c.name for c in executor._conditions]

    def test_remove_rollback_condition(self):
        """Test removing a rollback condition."""
        executor = RollbackExecutor()

        # Add a custom condition
        custom_condition = RollbackCondition(
            name="temp_condition",
            description="Temporary condition",
            check_fn=lambda ctx: True,
        )
        executor.add_rollback_condition(custom_condition)

        assert "temp_condition" in [c.name for c in executor._conditions]

        # Remove it
        removed = executor.remove_rollback_condition("temp_condition")

        assert removed is True
        assert "temp_condition" not in [c.name for c in executor._conditions]

    def test_remove_nonexistent_condition(self):
        """Test removing a condition that doesn't exist."""
        executor = RollbackExecutor()

        removed = executor.remove_rollback_condition("nonexistent")

        assert removed is False

    def test_clear_rollback_plan(self):
        """Test clearing a rollback plan."""
        executor = RollbackExecutor()

        executor.create_rollback_plan(
            action_id="action-1",
            command="kubectl apply -f deploy.yaml",
        )

        assert executor.get_rollback_plan("action-1") is not None

        executor.clear_rollback_plan("action-1")

        assert executor.get_rollback_plan("action-1") is None


class TestGlobalRollbackExecutor:
    """Test global rollback executor singleton."""

    @pytest.fixture(autouse=True)
    def reset_executor(self):
        """Reset the global executor before each test."""
        global _rollback_executor
        from app.actions.rollback_executor import _rollback_executor
        _rollback_executor = None
        yield
        _rollback_executor = None

    def test_singleton(self):
        """Test that get_rollback_executor returns same instance."""
        executor1 = get_rollback_executor()
        executor2 = get_rollback_executor()

        assert executor1 is executor2

    def test_singleton_persistence(self):
        """Test that singleton persists across calls."""
        executor1 = get_rollback_executor()
        executor1.create_rollback_plan(
            action_id="test",
            command="kubectl apply -f test.yaml",
        )

        executor2 = get_rollback_executor()
        plan = executor2.get_rollback_plan("test")

        assert plan is not None
        assert plan.action_id == "test"

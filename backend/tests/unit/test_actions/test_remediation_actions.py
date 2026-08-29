"""Unit tests for Remediation Actions (Phase 4)."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.actions.remediation_actions import (
    DeleteCrashLoopPodAction,
    RemediationActionFactory,
    RemediationActionType,
    ScaleDeploymentAction,
)
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent, AlertSeverity


class TestDeleteCrashLoopPodAction:
    """Test CrashLoop pod deletion action."""

    @pytest.fixture
    def action(self):
        return DeleteCrashLoopPodAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="test-event-1",
            rule_id="crashloop-rule",
            rule_name="CrashLoop Detected",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=5.0,
            threshold=3.0,
            message="Pod has 5 restarts",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_execute_with_crashloop_pods(self, action, mock_event):
        """Test deletion of crashloop pods."""
        # Mock kubectl list response
        mock_pods_data = {
            "items": [
                {
                    "metadata": {"name": "crashloop-pod-1"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"restartCount": 10}]
                    }
                },
                {
                    "metadata": {"name": "crashloop-pod-2"},
                    "status": {
                        "phase": "Restarting",
                        "containerStatuses": [{"restartCount": 7}]
                    }
                },
            ]
        }

        mock_list_result = ExecutionResult(
            success=True,
            stdout="pods data",
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout='pod "crashloop-pod-1" deleted',
        )

        with patch("json.loads", return_value=mock_pods_data):
            with patch.object(action.executor, "execute_kubectl", return_value=mock_list_result):
                with patch.object(action.executor, "execute_kubectl", return_value=mock_delete_result):
                    result = await action.execute(
                        alert_event=mock_event,
                        parameters={"namespace": "default", "restart_threshold": 5},
                        dry_run=False,
                    )

        assert result.success is True
        assert "Deleted" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_no_crashloop_pods(self, action, mock_event):
        """Test when no crashloop pods found."""
        mock_pods_data = {"items": []}

        mock_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_result):
            with patch("json.loads", return_value=mock_pods_data):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={"namespace": "default", "restart_threshold": 5},
                    dry_run=False,
                )

        assert result.success is True
        assert "No crashloop pods found" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_dry_run(self, action, mock_event):
        """Test dry run mode."""
        mock_pods_data = {"items": []}

        mock_result = ExecutionResult(
            success=True,
            stdout='{"items": []}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_result):
            with patch("json.loads", return_value=mock_pods_data):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={"namespace": "default"},
                    dry_run=True,
                )

        assert result.success is True
        assert "No crashloop pods found" in result.stdout


class TestScaleDeploymentAction:
    """Test deployment scaling action."""

    @pytest.fixture
    def action(self):
        return ScaleDeploymentAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="scale-event-1",
            rule_id="high-cpu",
            rule_name="High CPU Usage",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=90.0,
            threshold=85.0,
            message="CPU at 90%",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_scale_up(self, action, mock_event):
        """Test scaling up deployment."""
        deploy_data = {"spec": {"replicas": 2}}

        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"spec": {"replicas": 2}}',
            exit_code=0,
        )

        mock_scale_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="deployment.apps/myapp scaled",
        )

        with patch("json.loads", return_value=deploy_data):
            with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
                with patch.object(action.executor, "execute_kubectl", return_value=mock_scale_result):
                    result = await action.execute(
                        alert_event=mock_event,
                        parameters={
                            "namespace": "default",
                            "deployment": "myapp",
                            "replicas": "+2",
                        },
                        dry_run=False,
                    )

        assert result.success is True
        assert "scaled" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_scale_with_limits(self, action, mock_event):
        """Test scaling respects min/max limits."""
        deploy_data = {"spec": {"replicas": 1}}

        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"spec": {"replicas": 1}}',
            exit_code=0,
        )

        with patch("json.loads", return_value=deploy_data):
            with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "default",
                        "deployment": "myapp",
                        "replicas": 100,  # Try to scale to 100
                        "max_replicas": 10,  # But limit is 10
                    },
                    dry_run=False,
                )

        # Should be limited to max_replicas
        assert result.success is True
        assert "10" in result.stdout


class TestRemediationActionFactory:
    """Test remediation action factory."""

    def test_create_all_action_types(self):
        """Test creating all action types."""
        for action_type in RemediationActionType:
            action = RemediationActionFactory.create(action_type)
            assert action is not None
            assert hasattr(action, "execute")

    def test_get_available_actions(self):
        """Test getting available action types."""
        actions = RemediationActionFactory.get_available_actions()
        assert len(actions) == 14  # 7 original + 7 added in Phase 4A
        # Original actions
        assert "delete_crashloop_pod" in actions
        assert "scale_deployment" in actions
        assert "rollback_deployment" in actions
        assert "restart_deployment" in actions
        # Phase 4A actions
        assert "clear_stuck_pods" in actions
        assert "cleanup_failed_jobs" in actions
        assert "adjust_hpa_min_replicas" in actions

    def test_create_invalid_action_type(self):
        """Test creating invalid action type raises error."""
        with pytest.raises(ValueError, match="Unknown remediation action type"):
            RemediationActionFactory.create("invalid_action")

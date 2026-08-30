"""Unit tests for Remediation Actions (Phase 4)."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.actions.remediation_actions import (
    DeleteCrashLoopPodAction,
    RemediationActionFactory,
    RemediationActionType,
    RestartDeploymentAction,
    RollbackDeploymentAction,
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


class TestDeleteCrashLoopPodTargeting:
    """Regression tests: pod_name must restrict deletion to the target pod."""

    @pytest.fixture
    def action(self):
        return DeleteCrashLoopPodAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="target-event-1",
            rule_id="crashloop-rule",
            rule_name="CrashLoop Detected",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=5.0,
            threshold=3.0,
            message="Pod has many restarts",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.fixture
    def crashloop_pods_json(self):
        """Two pods, both above the default restart threshold of 5."""
        return json.dumps(
            {
                "items": [
                    {
                        "metadata": {"name": "target-pod"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 10}],
                        },
                    },
                    {
                        "metadata": {"name": "other-pod"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 10}],
                        },
                    },
                ]
            }
        )

    @staticmethod
    def _recording_executor(action, list_stdout, deletes):
        """Fake executor: serves the pod list, records delete commands."""

        def fake_kubectl(args, namespace=None, dry_run=False):
            if args and args[0] == "pods":
                return ExecutionResult(success=True, exit_code=0, stdout=list_stdout)
            deletes.append(list(args))
            return ExecutionResult(success=True, exit_code=0, stdout="pod deleted")

        return patch.object(action.executor, "execute_kubectl", side_effect=fake_kubectl)

    @pytest.mark.asyncio
    async def test_pod_name_deletes_only_target_pod(
        self, action, mock_event, crashloop_pods_json
    ):
        """Regression: with pod_name set, only that pod is selected/deleted."""
        deletes: list[list[str]] = []

        with self._recording_executor(action, crashloop_pods_json, deletes):
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "pod_name": "target-pod"},
                dry_run=False,
            )

        assert result.success is True
        assert deletes == [["delete", "pod", "target-pod"]]
        assert "target-pod" in result.stdout
        assert "other-pod" not in result.stdout

    @pytest.mark.asyncio
    async def test_without_pod_name_deletes_all_crashloop_pods(
        self, action, mock_event, crashloop_pods_json
    ):
        """Without pod_name, every crashloop pod is deleted."""
        deletes: list[list[str]] = []

        with self._recording_executor(action, crashloop_pods_json, deletes):
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default"},
                dry_run=False,
            )

        assert result.success is True
        assert deletes == [
            ["delete", "pod", "target-pod"],
            ["delete", "pod", "other-pod"],
        ]

    @pytest.mark.asyncio
    async def test_pod_name_not_crashlooping_deletes_nothing(
        self, action, mock_event, crashloop_pods_json
    ):
        """A named pod below the threshold is not deleted."""
        low_restarts = json.dumps(
            {
                "items": [
                    {
                        "metadata": {"name": "target-pod"},
                        "status": {
                            "phase": "Running",
                            "containerStatuses": [{"restartCount": 1}],
                        },
                    }
                ]
            }
        )
        deletes: list[list[str]] = []

        with self._recording_executor(action, low_restarts, deletes):
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "pod_name": "target-pod"},
                dry_run=False,
            )

        assert result.success is True
        assert deletes == []
        assert "No crashloop pods found" in result.stdout


class TestRollbackDeploymentAction:
    """Characterization tests for RollbackDeploymentAction."""

    @pytest.fixture
    def action(self):
        return RollbackDeploymentAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="rollback-event-1",
            rule_id="deploy-fail",
            rule_name="Deployment Failing",
            severity=AlertSeverity.CRITICAL,
            status="firing",
            value=5.0,
            threshold=3.0,
            message="Deployment failing",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_rollback_success_without_revision(self, action, mock_event):
        """Rollback without revision uses 'rollout undo' (previous revision)."""
        history = ExecutionResult(success=True, exit_code=0, stdout="revisions...")
        undo = ExecutionResult(
            success=True, exit_code=0, stdout='deployment.apps/myapp rolled back'
        )

        with patch.object(
            action.executor, "execute_kubectl", side_effect=[history, undo]
        ) as mock_kubectl:
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=False,
            )

        assert result.success is True
        assert "Rollback initiated for myapp" in result.stdout
        assert [c.kwargs["args"] for c in mock_kubectl.call_args_list] == [
            ["rollout", "history", "deployment", "myapp"],
            ["rollout", "undo", "deployment", "myapp"],
        ]
        assert action.get_execution_history()[0]["action_type"] == "rollback_deployment"

    @pytest.mark.asyncio
    async def test_rollback_with_explicit_revision(self, action, mock_event):
        """Explicit revision is forwarded via --to-revision."""
        history = ExecutionResult(success=True, exit_code=0, stdout="revisions...")
        undo = ExecutionResult(success=True, exit_code=0, stdout="rolled back")

        with patch.object(
            action.executor, "execute_kubectl", side_effect=[history, undo]
        ) as mock_kubectl:
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "deployment": "myapp",
                    "revision": 3,
                },
                dry_run=False,
            )

        assert result.success is True
        assert [c.kwargs["args"] for c in mock_kubectl.call_args_list] == [
            ["rollout", "history", "deployment", "myapp"],
            [
                "rollout",
                "undo",
                "deployment",
                "myapp",
                "--to-revision=3",
            ],
        ]

    @pytest.mark.asyncio
    async def test_rollback_dry_run_still_queries_history(self, action, mock_event):
        """Dry run checks rollout history first, then reports without undo."""
        history = ExecutionResult(success=True, exit_code=0, stdout="revisions...")

        with patch.object(
            action.executor, "execute_kubectl", side_effect=[history]
        ) as mock_kubectl:
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=True,
            )

        assert result.success is True
        # Quirk (preserved): the final return overwrites the [DRY RUN] stdout
        # with the success message on success.
        assert result.stdout == "Rollback initiated for myapp"
        assert len(mock_kubectl.call_args_list) == 1

    @pytest.mark.asyncio
    async def test_rollback_missing_deployment(self, action, mock_event):
        """Missing deployment name fails validation."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={"namespace": "default"},
            dry_run=False,
        )

        assert result.success is False
        assert "Deployment name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_rollback_deployment_not_found(self, action, mock_event):
        """History lookup reporting 'not found' maps to a clear error."""
        history = ExecutionResult(
            success=False,
            exit_code=1,
            stderr='deployment "myapp" not found',
            error_message='Error from server (NotFound): deployment "myapp" not found',
        )

        with patch.object(
            action.executor, "execute_kubectl", side_effect=[history]
        ):
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=False,
            )

        assert result.success is False
        assert "Deployment 'myapp' not found" in result.error_message


class TestRestartDeploymentAction:
    """Characterization tests for RestartDeploymentAction."""

    @pytest.fixture
    def action(self):
        return RestartDeploymentAction()

    @pytest.fixture
    def mock_event(self):
        return AlertEvent(
            id="restart-event-1",
            rule_id="memory-leak",
            rule_name="Memory Leak Suspected",
            severity=AlertSeverity.WARNING,
            status="firing",
            value=90.0,
            threshold=85.0,
            message="Memory usage high",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.mark.asyncio
    async def test_restart_success(self, action, mock_event):
        """Restart issues 'rollout restart <deployment>'."""
        restart = ExecutionResult(
            success=True, exit_code=0, stdout='deployment.apps/myapp restarted'
        )

        with patch.object(
            action.executor, "execute_kubectl", return_value=restart
        ) as mock_kubectl:
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=False,
            )

        assert result.success is True
        assert "Rollout restart initiated for myapp" in result.stdout
        assert [c.kwargs["args"] for c in mock_kubectl.call_args_list] == [
            ["rollout", "restart", "myapp"]
        ]
        assert action.get_execution_history()[0]["action_type"] == "restart_deployment"

    @pytest.mark.asyncio
    async def test_restart_failure_passes_through(self, action, mock_event):
        """A failed kubectl restart yields a failed result with stdout passthrough."""
        restart = ExecutionResult(
            success=False,
            exit_code=1,
            stdout="partial output",
            stderr="boom",
            error_message="boom",
            duration_seconds=1.5,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=restart):
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=False,
            )

        assert result.success is False
        assert result.exit_code == 1
        assert result.stdout == "partial output"
        assert result.error_message == "boom"
        assert result.duration_seconds == 1.5

    @pytest.mark.asyncio
    async def test_restart_dry_run_does_not_execute(self, action, mock_event):
        """Dry run reports without touching the executor."""
        with patch.object(action.executor, "execute_kubectl") as mock_kubectl:
            result = await action.execute(
                alert_event=mock_event,
                parameters={"namespace": "default", "deployment": "myapp"},
                dry_run=True,
            )

        assert result.success is True
        # Quirk (preserved): the final return overwrites the [DRY RUN] stdout
        # with the success message on success.
        assert result.stdout == "Rollout restart initiated for myapp"
        mock_kubectl.assert_not_called()

    @pytest.mark.asyncio
    async def test_restart_missing_deployment(self, action, mock_event):
        """Missing deployment name fails validation."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={"namespace": "default"},
            dry_run=False,
        )

        assert result.success is False
        assert "Deployment name is required" in result.error_message


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

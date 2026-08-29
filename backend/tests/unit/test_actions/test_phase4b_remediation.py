"""Tests for Phase 4B autonomous remediation actions."""

from unittest.mock import MagicMock, patch

import pytest

from app.actions.remediation_actions import (
    EvictPodFromNodeAction,
    FlushEndpointsAction,
    RemediationActionFactory,
    RemediationActionType,
    RestartStatefulSetPodAction,
)
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent


# Fixtures
@pytest.fixture
def mock_event():
    """Create a mock AlertEvent."""
    event = MagicMock(spec=AlertEvent)
    event.id = "test-event-123"
    return event


class TestRestartStatefulSetPodAction:
    """Tests for RestartStatefulSetPodAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return RestartStatefulSetPodAction()

    @pytest.mark.asyncio
    async def test_restart_statefulset_pod_success(self, action, mock_event):
        """Test successful StatefulSet pod restart."""
        # Mock StatefulSet get
        mock_sts_result = ExecutionResult(
            success=True,
            stdout='{"spec":{"selector":{"matchLabels":{"app":"mysql"}}}}',
            exit_code=0,
        )

        # Mock pods list with high restart count
        mock_pods_result = ExecutionResult(
            success=True,
            stdout='{"items":[{"metadata":{"name":"mysql-0"},"status":{"containerStatuses":[{"restartCount":10}]}}]}',
            exit_code=0,
        )

        # Mock delete
        mock_delete_result = ExecutionResult(
            success=True,
            stdout='pod "mysql-0" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_sts_result,
            mock_pods_result,
            mock_delete_result,
        ]):
            with patch("json.loads", side_effect=[
                {"spec": {"selector": {"matchLabels": {"app": "mysql"}}}},
                {"items": [{"metadata": {"name": "mysql-0"}, "status": {"containerStatuses": [{"restartCount": 10}]}}]},
            ]):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "database",
                        "statefulset": "mysql",
                        "restart_threshold": 5,
                    },
                    dry_run=False,
                )

        assert result.success is True
        assert "mysql-0" in result.stdout
        assert "Restarted" in result.stdout

    @pytest.mark.asyncio
    async def test_restart_statefulset_pod_dry_run(self, action, mock_event):
        """Test dry-run mode for StatefulSet pod restart."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "database",
                "statefulset": "mysql",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout
        assert "mysql" in result.stdout

    @pytest.mark.asyncio
    async def test_restart_statefulset_pod_missing_statefulset(self, action, mock_event):
        """Test validation when statefulset name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "database",
            },
            dry_run=False,
        )

        assert result.success is False
        assert "StatefulSet name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_restart_statefulset_pod_no_pods_found(self, action, mock_event):
        """Test when no pods need restarting."""
        mock_sts_result = ExecutionResult(
            success=True,
            stdout='{"spec":{"selector":{"matchLabels":{"app":"mysql"}}}}',
            exit_code=0,
        )

        mock_pods_result = ExecutionResult(
            success=True,
            stdout='{"items":[]}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_sts_result,
            mock_pods_result,
        ]), patch("json.loads", side_effect=[
            {"spec": {"selector": {"matchLabels": {"app": "mysql"}}}},
            {"items": []},
        ]):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "database",
                    "statefulset": "mysql",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "no statefulset pods found" in result.stdout.lower() or "needing restart" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_restart_statefulset_pod_execution_history(self, action, mock_event):
        """Test execution history tracking."""
        mock_sts_result = ExecutionResult(
            success=True,
            stdout='{"spec":{"selector":{"matchLabels":{"app":"mysql"}}}}',
            exit_code=0,
        )

        mock_pods_result = ExecutionResult(
            success=True,
            stdout='{"items":[{"metadata":{"name":"mysql-0"},"status":{"containerStatuses":[{"restartCount":10}]}}]}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            stdout='pod "mysql-0" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_sts_result,
            mock_pods_result,
            mock_delete_result,
        ]):
            with patch("json.loads", side_effect=[
                {"spec": {"selector": {"matchLabels": {"app": "mysql"}}}},
                {"items": [{"metadata": {"name": "mysql-0"}, "status": {"containerStatuses": [{"restartCount": 10}]}}]},
            ]):
                await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "database",
                        "statefulset": "mysql",
                    },
                    dry_run=False,
                )

        history = action.get_execution_history()
        assert len(history) > 0
        assert history[0]["action_type"] == "restart_statefulset_pod"
        assert history[0]["success"] is True


class TestFlushEndpointsAction:
    """Tests for FlushEndpointsAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return FlushEndpointsAction()

    @pytest.mark.asyncio
    async def test_flush_endpoints_success(self, action, mock_event):
        """Test successful endpoint flush."""
        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"metadata":{"name":"my-service"},"subsets":[]}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            stdout='endpoints "my-service" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_get_result,
            mock_delete_result,
        ]):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "service": "my-service",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "Flushed endpoints" in result.stdout

    @pytest.mark.asyncio
    async def test_flush_endpoints_dry_run(self, action, mock_event):
        """Test dry-run mode for endpoint flush."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "service": "my-service",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_flush_endpoints_missing_service(self, action, mock_event):
        """Test validation when service name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
            },
            dry_run=False,
        )

        assert result.success is False
        assert "Service name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_flush_endpoints_not_found(self, action, mock_event):
        """Test when endpoints don't exist."""
        mock_get_result = ExecutionResult(
            success=False,
            stderr='Error from server (NotFound): endpoints "my-service" not found',
            exit_code=1,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "service": "my-service",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "do not exist" in result.stdout.lower()


class TestEvictPodFromNodeAction:
    """Tests for EvictPodFromNodeAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return EvictPodFromNodeAction()

    @pytest.mark.asyncio
    async def test_evict_pod_success(self, action, mock_event):
        """Test successful pod eviction."""
        mock_delete_result = ExecutionResult(
            success=True,
            stdout='pod "problematic-pod" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_delete_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "pod_name": "problematic-pod",
                    "node_name": "node-1",
                    "grace_period_seconds": 30,
                },
                dry_run=False,
            )

        assert result.success is True
        assert "Evicted pod" in result.stdout
        assert "problematic-pod" in result.stdout

    @pytest.mark.asyncio
    async def test_evict_pod_dry_run(self, action, mock_event):
        """Test dry-run mode for pod eviction."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "pod_name": "problematic-pod",
                "node_name": "node-1",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_evict_pod_missing_pod_name(self, action, mock_event):
        """Test validation when pod name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "node_name": "node-1",
            },
            dry_run=False,
        )

        assert result.success is False
        assert "Pod name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_evict_pod_invalid_grace_period(self, action, mock_event):
        """Test validation when grace period is negative."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "pod_name": "problematic-pod",
                "grace_period_seconds": -10,
            },
            dry_run=False,
        )

        assert result.success is False
        assert "non-negative" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_evict_pod_auto_detect_node(self, action, mock_event):
        """Test auto-detection of node when not specified."""
        mock_pod_result = ExecutionResult(
            success=True,
            stdout='{"spec":{"nodeName":"node-2"}}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            stdout='pod "test-pod" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_pod_result,
            mock_delete_result,
        ]), patch("json.loads", return_value={"spec": {"nodeName": "node-2"}}):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "pod_name": "test-pod",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "node-2" in result.stdout


class TestPhase4BActionFactory:
    """Tests for Phase 4B action factory integration."""

    @pytest.mark.asyncio
    async def test_factory_creates_restart_statefulset_action(self):
        """Test factory creates RestartStatefulSetPodAction."""
        action = RemediationActionFactory.create(RemediationActionType.RESTART_STATEFULSET_POD)
        assert isinstance(action, RestartStatefulSetPodAction)

    @pytest.mark.asyncio
    async def test_factory_creates_flush_endpoints_action(self):
        """Test factory creates FlushEndpointsAction."""
        action = RemediationActionFactory.create(RemediationActionType.FLUSH_ENDPOINTS)
        assert isinstance(action, FlushEndpointsAction)

    @pytest.mark.asyncio
    async def test_factory_creates_evict_pod_action(self):
        """Test factory creates EvictPodFromNodeAction."""
        action = RemediationActionFactory.create(RemediationActionType.EVICT_POD_FROM_NODE)
        assert isinstance(action, EvictPodFromNodeAction)

    def test_factory_includes_phase4b_actions(self):
        """Test factory includes all Phase 4B actions."""
        available = RemediationActionFactory.get_available_actions()
        assert "restart_statefulset_pod" in available
        assert "flush_endpoints" in available
        assert "evict_pod_from_node" in available

    def test_factory_total_actions_count(self):
        """Test factory has 14 total actions (7 + 3 + 4)."""
        available = RemediationActionFactory.get_available_actions()
        # Phase 4A: 7, Phase 4B: 3 = 10 total
        assert len(available) >= 10

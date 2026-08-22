"""Tests for Phase 4C autonomous remediation actions."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.actions.remediation_actions import (
    RemediationActionType,
    RotateServiceAccountTokenAction,
    RestartDaemonSetAction,
    TruncateNodeLogsAction,
    RestartIngressControllerAction,
    RemediationActionFactory,
)
from app.models.actions import ExecutionResult
from app.models.alerts import AlertEvent


# Fixtures
@pytest.fixture
def mock_event():
    """Create a mock AlertEvent."""
    event = MagicMock(spec=AlertEvent)
    event.id = "test-event-456"
    return event


class TestRotateServiceAccountTokenAction:
    """Tests for RotateServiceAccountTokenAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return RotateServiceAccountTokenAction()

    @pytest.mark.asyncio
    async def test_rotate_token_specific_secret(self, action, mock_event):
        """Test rotating specific service account token secret."""
        mock_delete_result = ExecutionResult(
            success=True,
            stdout='secret "my-service-account-token-xyz" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_delete_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "default",
                    "service_account": "my-service-account",
                    "secret_name": "my-service-account-token-xyz",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "Deleted token secret" in result.stdout

    @pytest.mark.asyncio
    async def test_rotate_token_all_secrets(self, action, mock_event):
        """Test rotating all service account token secrets."""
        mock_secrets_result = ExecutionResult(
            success=True,
            stdout='{"items":['
                   '{"metadata":{"name":"sa-token-1"},"type":"kubernetes.io/service-account-token",'
                   '"metadata":{"annotations":{"kubernetes.io/service-account.name":"my-sa"}}},'
                   '{"metadata":{"name":"sa-token-2"},"type":"kubernetes.io/service-account-token",'
                   '"metadata":{"annotations":{"kubernetes.io/service-account.name":"my-sa"}}}'
                   ']}',
            exit_code=0,
        )

        mock_delete_result = ExecutionResult(
            success=True,
            stdout='secret "sa-token-1" deleted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_secrets_result,
            mock_delete_result,
            mock_delete_result,
        ]):
            with patch("json.loads", return_value={
                "items": [
                    {
                        "metadata": {
                            "name": "sa-token-1",
                            "annotations": {"kubernetes.io/service-account.name": "my-sa"}
                        },
                        "type": "kubernetes.io/service-account-token",
                    },
                    {
                        "metadata": {
                            "name": "sa-token-2",
                            "annotations": {"kubernetes.io/service-account.name": "my-sa"}
                        },
                        "type": "kubernetes.io/service-account-token",
                    },
                ]
            }):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "default",
                        "service_account": "my-sa",
                    },
                    dry_run=False,
                )

        assert result.success is True
        assert "token secret" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_rotate_token_dry_run(self, action, mock_event):
        """Test dry-run mode for token rotation."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "service_account": "my-sa",
                "secret_name": "sa-token-1",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_rotate_token_missing_service_account(self, action, mock_event):
        """Test validation when service account is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "default",
                "secret_name": "sa-token-1",
            },
            dry_run=False,
        )

        assert result.success is False
        assert "Service account name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_rotate_token_no_tokens_found(self, action, mock_event):
        """Test when no token secrets found."""
        mock_secrets_result = ExecutionResult(
            success=True,
            stdout='{"items":[]}',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_secrets_result):
            with patch("json.loads", return_value={"items": []}):
                result = await action.execute(
                    alert_event=mock_event,
                    parameters={
                        "namespace": "default",
                        "service_account": "my-sa",
                    },
                    dry_run=False,
                )

        assert result.success is True
        assert "No token secrets found" in result.stdout


class TestRestartDaemonSetAction:
    """Tests for RestartDaemonSetAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return RestartDaemonSetAction()

    @pytest.mark.asyncio
    async def test_restart_daemonset_success(self, action, mock_event):
        """Test successful DaemonSet restart."""
        mock_result = ExecutionResult(
            success=True,
            stdout='daemonset.apps/monitoring-agent restarted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "monitoring",
                    "daemonset": "monitoring-agent",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "rolling restart" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_restart_daemonset_dry_run(self, action, mock_event):
        """Test dry-run mode for DaemonSet restart."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "monitoring",
                "daemonset": "monitoring-agent",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout

    @pytest.mark.asyncio
    async def test_restart_daemonset_missing_daemonset(self, action, mock_event):
        """Test validation when daemonset name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "monitoring",
            },
            dry_run=False,
        )

        assert result.success is False
        assert "DaemonSet name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_restart_daemonset_with_node_selector(self, action, mock_event):
        """Test DaemonSet restart with node selector."""
        mock_result = ExecutionResult(
            success=True,
            stdout='daemonset.apps/monitoring-agent restarted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "monitoring",
                    "daemonset": "monitoring-agent",
                    "node_selector": "role=worker",
                },
                dry_run=False,
            )

        assert result.success is True


class TestTruncateNodeLogsAction:
    """Tests for TruncateNodeLogsAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return TruncateNodeLogsAction()

    @pytest.mark.asyncio
    async def test_truncate_logs_success(self, action, mock_event):
        """Test successful log truncation."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "node_name": "worker-node-1",
                "log_paths": ["/var/log/*.log", "/var/log/app/*.log"],
                "max_size_mb": 100,
            },
            dry_run=False,
        )

        assert result.success is True
        assert "log-truncator" in result.stdout.lower()
        assert "worker-node-1" in result.stdout

    @pytest.mark.asyncio
    async def test_truncate_logs_dry_run(self, action, mock_event):
        """Test dry-run mode for log truncation."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "node_name": "worker-node-1",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout
        assert "worker-node-1" in result.stdout

    @pytest.mark.asyncio
    async def test_truncate_logs_missing_node(self, action, mock_event):
        """Test validation when node name is missing."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "log_paths": ["/var/log/*.log"],
            },
            dry_run=False,
        )

        assert result.success is False
        assert "Node name is required" in result.error_message

    @pytest.mark.asyncio
    async def test_truncate_logs_invalid_max_size(self, action, mock_event):
        """Test validation when max_size_mb is too small."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "node_name": "worker-node-1",
                "max_size_mb": 0,
            },
            dry_run=False,
        )

        assert result.success is False
        assert "at least 1" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_truncate_logs_default_values(self, action, mock_event):
        """Test log truncation with default values."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "node_name": "worker-node-1",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "/var/log/*.log" in result.stdout


class TestRestartIngressControllerAction:
    """Tests for RestartIngressControllerAction."""

    @pytest.fixture
    def action(self):
        """Create action instance."""
        return RestartIngressControllerAction()

    @pytest.mark.asyncio
    async def test_restart_ingress_success(self, action, mock_event):
        """Test successful ingress controller restart."""
        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"metadata":{"name":"ingress-nginx-controller"},"spec":{"replicas":2}}',
            exit_code=0,
        )

        mock_restart_result = ExecutionResult(
            success=True,
            stdout='deployment.apps/ingress-nginx-controller restarted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_get_result,
            mock_restart_result,
        ]):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "ingress-nginx",
                    "deployment": "ingress-nginx-controller",
                },
                dry_run=False,
            )

        assert result.success is True
        assert "rolling restart" in result.stdout.lower()

    @pytest.mark.asyncio
    async def test_restart_ingress_dry_run(self, action, mock_event):
        """Test dry-run mode for ingress restart."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "ingress-nginx",
                "deployment": "ingress-nginx-controller",
            },
            dry_run=True,
        )

        assert result.success is True
        assert "DRY RUN" in result.stdout
        assert "HIGH RISK" in result.stdout

    @pytest.mark.asyncio
    async def test_restart_ingress_deployment_not_found(self, action, mock_event):
        """Test when ingress deployment not found."""
        mock_get_result = ExecutionResult(
            success=False,
            stderr='Error from server (NotFound): deployments.apps "not-found" not found',
            exit_code=1,
        )

        with patch.object(action.executor, "execute_kubectl", return_value=mock_get_result):
            result = await action.execute(
                alert_event=mock_event,
                parameters={
                    "namespace": "ingress-nginx",
                    "deployment": "not-found",
                },
                dry_run=False,
            )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_restart_ingress_invalid_wait_seconds(self, action, mock_event):
        """Test validation when wait_seconds is negative."""
        result = await action.execute(
            alert_event=mock_event,
            parameters={
                "namespace": "ingress-nginx",
                "deployment": "ingress-nginx-controller",
                "wait_seconds": -10,
            },
            dry_run=False,
        )

        assert result.success is False
        assert "non-negative" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_restart_ingress_default_values(self, action, mock_event):
        """Test ingress restart with default namespace and deployment."""
        mock_get_result = ExecutionResult(
            success=True,
            stdout='{"metadata":{"name":"ingress-controller"},"spec":{"replicas":2}}',
            exit_code=0,
        )

        mock_restart_result = ExecutionResult(
            success=True,
            stdout='deployment.apps/ingress-controller restarted',
            exit_code=0,
        )

        with patch.object(action.executor, "execute_kubectl", side_effect=[
            mock_get_result,
            mock_restart_result,
        ]):
            result = await action.execute(
                alert_event=mock_event,
                parameters={},
                dry_run=False,
            )

        assert result.success is True
        assert "ingress-nginx" in result.stdout  # Default namespace


class TestPhase4CActionFactory:
    """Tests for Phase 4C action factory integration."""

    @pytest.mark.asyncio
    async def test_factory_creates_rotate_token_action(self):
        """Test factory creates RotateServiceAccountTokenAction."""
        action = RemediationActionFactory.create(RemediationActionType.ROTATE_SERVICE_ACCOUNT_TOKEN)
        assert isinstance(action, RotateServiceAccountTokenAction)

    @pytest.mark.asyncio
    async def test_factory_creates_restart_daemonset_action(self):
        """Test factory creates RestartDaemonSetAction."""
        action = RemediationActionFactory.create(RemediationActionType.RESTART_DAEMONSET)
        assert isinstance(action, RestartDaemonSetAction)

    @pytest.mark.asyncio
    async def test_factory_creates_truncate_logs_action(self):
        """Test factory creates TruncateNodeLogsAction."""
        action = RemediationActionFactory.create(RemediationActionType.TRUNCATE_NODE_LOGS)
        assert isinstance(action, TruncateNodeLogsAction)

    @pytest.mark.asyncio
    async def test_factory_creates_restart_ingress_action(self):
        """Test factory creates RestartIngressControllerAction."""
        action = RemediationActionFactory.create(RemediationActionType.RESTART_INGRESS_CONTROLLER)
        assert isinstance(action, RestartIngressControllerAction)

    def test_factory_includes_phase4c_actions(self):
        """Test factory includes all Phase 4C actions."""
        available = RemediationActionFactory.get_available_actions()
        assert "rotate_service_account_token" in available
        assert "restart_daemonset" in available
        assert "truncate_node_logs" in available
        assert "restart_ingress_controller" in available

    def test_factory_total_actions_count(self):
        """Test factory has 14 total actions (7 + 3 + 4)."""
        available = RemediationActionFactory.get_available_actions()
        # Phase 4A: 7, Phase 4B: 3, Phase 4C: 4 = 14 total
        assert len(available) == 14

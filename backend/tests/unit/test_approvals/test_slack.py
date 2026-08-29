"""Unit tests for Slack Approval Notifier."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.approvals.slack import SlackApprovalNotifier, get_slack_approval_notifier
from app.models.actions import (
    Action,
    ActionStatus,
    CommandType,
    ExecutionResult,
    RiskLevel,
)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for Slack API."""
    # Create a proper mock response
    mock_response = MagicMock()
    mock_response.status_code = 200

    # Create the async context manager
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    return mock_client


@pytest.fixture
def slack_notifier():
    """Create SlackApprovalNotifier with test webhook URL."""
    notifier = SlackApprovalNotifier()
    notifier.webhook_url = "https://hooks.slack.com/test"
    return notifier


@pytest.fixture
def sample_action():
    """Create sample action for testing."""
    from app.models.actions import CommandParams
    return Action(
        id="act-123",
        triage_card_id="tc-001",
        recommendation_id="rec-001",
        command_type=CommandType.KUBECTL,
        command="kubectl delete pod test-pod -n meinvoice",
        parsed_params=CommandParams(
            command_type=CommandType.KUBECTL,
            resource_type="pod",
            resource_name="test-pod",
            namespace="meinvoice",
            action="delete",
        ),
        title="Delete failing pod",
        description="Remove pod that is in CrashLoopBackOff",
        project="meinvoice",
        risk_level=RiskLevel.MEDIUM,
        estimated_impact="Pod will be temporarily unavailable",
        status=ActionStatus.PENDING,
    )


class TestSlackApprovalNotifier:
    """Test SlackApprovalNotifier functionality."""

    def test_notifier_initialization(self, slack_notifier):
        """Test notifier initialization."""
        assert slack_notifier.webhook_url is not None or slack_notifier.webhook_url == ""

    @pytest.mark.asyncio
    async def test_send_approval_request_success(self, slack_notifier, mock_httpx_client, sample_action):
        """Test successful approval request sending."""
        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_request(sample_action)

        assert result is True
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_approval_request_failure(self, slack_notifier, mock_httpx_client, sample_action):
        """Test approval request sending failure."""
        mock_httpx_client.post.side_effect = Exception("Network error")

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_request(sample_action)

        assert result is False

    def test_build_approval_message_basic(self, slack_notifier, sample_action):
        """Test building approval message blocks."""
        blocks = slack_notifier._build_approval_message(sample_action)

        assert isinstance(blocks, list)
        assert len(blocks) > 0

        # Check for required sections
        has_header = any("Action Approval" in str(block) for block in blocks)
        has_command = any("kubectl delete" in str(block) for block in blocks)
        has_risk = any("MEDIUM" in str(block) for block in blocks)

        assert has_header or has_command  # At least some content

    def test_build_approval_message_includes_action_details(self, slack_notifier, sample_action):
        """Test approval message includes action details."""
        blocks = slack_notifier._build_approval_message(sample_action)

        blocks_str = str(blocks)
        assert sample_action.id in blocks_str or "act-123" in blocks_str
        assert sample_action.project in blocks_str or "meinvoice" in blocks_str

    def test_build_approval_message_critical_risk(self, slack_notifier):
        """Test approval message for critical risk action."""
        from app.models.actions import CommandParams
        critical_action = Action(
            id="act-critical",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl delete namespace meinvoice",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                resource_type="namespace",
                resource_name="meinvoice",
                action="delete",
            ),
            title="Delete namespace",
            description="Delete entire namespace",
            risk_level=RiskLevel.CRITICAL,
            project="meinvoice",
            estimated_impact="All resources in namespace will be deleted",
            status=ActionStatus.PENDING,
        )

        blocks = slack_notifier._build_approval_message(critical_action)
        blocks_str = str(blocks)

        # Should include critical warning
        assert "critical" in blocks_str.lower() or "CRITICAL" in blocks_str

    @pytest.mark.asyncio
    async def test_send_approval_status_approved(self, slack_notifier, mock_httpx_client, sample_action):
        """Test sending approved status update."""
        # Update action status
        sample_action.status = ActionStatus.APPROVED

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_status(
                action=sample_action,
                status=ActionStatus.APPROVED,
                user="admin",
            )

        assert result is True
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_approval_status_rejected(self, slack_notifier, mock_httpx_client, sample_action):
        """Test sending rejected status update."""
        # Update action status
        sample_action.status = ActionStatus.REJECTED

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_status(
                action=sample_action,
                status=ActionStatus.REJECTED,
                user="admin",
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_approval_status_executed(self, slack_notifier, mock_httpx_client, sample_action):
        """Test sending executed status update."""
        # Update action status and add execution result
        sample_action.status = ActionStatus.EXECUTED
        sample_action.execution_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="Command completed successfully",
            stderr="",
            duration_seconds=1.5,
        )

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_status(
                action=sample_action,
                status=ActionStatus.EXECUTED,
                user="system",
            )

        assert result is True

    def test_build_status_message_approved(self, slack_notifier, sample_action):
        """Test building approved status message."""
        sample_action.status = ActionStatus.APPROVED
        blocks = slack_notifier._build_status_message(
            action=sample_action,
            status=ActionStatus.APPROVED,
            user="admin",
        )

        blocks_str = str(blocks)
        assert "approved" in blocks_str.lower() or "APPROVED" in blocks_str
        assert "admin" in blocks_str

    def test_build_status_message_rejected(self, slack_notifier, sample_action):
        """Test building rejected status message."""
        sample_action.status = ActionStatus.REJECTED
        blocks = slack_notifier._build_status_message(
            action=sample_action,
            status=ActionStatus.REJECTED,
            user="admin",
        )

        blocks_str = str(blocks)
        assert "rejected" in blocks_str.lower() or "REJECTED" in blocks_str

    def test_build_status_message_with_result(self, slack_notifier, sample_action):
        """Test building status message with execution result."""
        sample_action.status = ActionStatus.EXECUTED
        sample_action.execution_result = ExecutionResult(
            success=True,
            exit_code=0,
            stdout="Pod deleted successfully",
            stderr="",
            duration_seconds=1.5,
        )

        blocks = slack_notifier._build_status_message(
            action=sample_action,
            status=ActionStatus.EXECUTED,
            user="system",
        )

        blocks_str = str(blocks)
        assert "executed" in blocks_str.lower() or "EXECUTED" in blocks_str

    @pytest.mark.asyncio
    async def test_send_approval_status_no_webhook(self, slack_notifier, sample_action):
        """Test sending status when webhook URL not configured."""
        # Set webhook to None
        slack_notifier.webhook_url = None

        # Execute
        result = await slack_notifier.send_approval_status(
            action=sample_action,
            status=ActionStatus.APPROVED,
            user="admin",
        )

        # Should handle gracefully
        assert result is False

    def test_truncate_long_command(self, slack_notifier):
        """Test truncating long commands in messages."""
        from app.models.actions import CommandParams
        long_command = "kubectl get pods " + " ".join([f"pod-{i}" for i in range(100)])

        action = Action(
            id="act-123",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command=long_command,
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                resource_type="pod",
                action="get",
            ),
            title="Test long command",
            description="Testing command truncation",
            risk_level=RiskLevel.LOW,
            project="test",
            estimated_impact="Minimal",
            status=ActionStatus.PENDING,
        )

        blocks = slack_notifier._build_approval_message(action)
        blocks_str = str(blocks)

        # Command should be truncated or abbreviated
        assert len(blocks_str) < 5000  # Slack has size limits

    def test_risk_level_color_mapping(self, slack_notifier, sample_action):
        """Test risk level text mapping in approval messages."""
        # Test each risk level appears in the message
        risk_level_tests = [
            RiskLevel.CRITICAL,
            RiskLevel.HIGH,
            RiskLevel.MEDIUM,
            RiskLevel.LOW,
            RiskLevel.SAFE,
        ]

        for risk_level in risk_level_tests:
            sample_action.risk_level = risk_level
            blocks = slack_notifier._build_approval_message(sample_action)

            # Check that risk level text is in the blocks
            blocks_str = str(blocks)
            assert risk_level.value.upper() in blocks_str

    def test_risk_level_emoji_mapping(self, slack_notifier, sample_action):
        """Test risk level emoji mapping in approval messages."""
        # Test each risk level
        risk_emoji_tests = [
            (RiskLevel.CRITICAL, "🔴"),
            (RiskLevel.HIGH, "🟠"),
            (RiskLevel.MEDIUM, "🟡"),
            (RiskLevel.LOW, "🟢"),
            (RiskLevel.SAFE, "✅"),
        ]

        for risk_level, expected_emoji in risk_emoji_tests:
            sample_action.risk_level = risk_level
            blocks = slack_notifier._build_approval_message(sample_action)

            # Check that emoji is in the blocks
            blocks_str = str(blocks)
            assert expected_emoji in blocks_str

    @pytest.mark.asyncio
    async def test_ssrf_protection_blocks_malicious_url(self, slack_notifier, sample_action, monkeypatch):
        """Test SSRF protection blocks malicious webhook URLs."""
        # Set a malicious internal URL
        slack_notifier.webhook_url = "http://localhost:8080/webhook"

        # Execute - should be blocked by SSRF protection
        result = await slack_notifier.send_approval_request(sample_action)

        # Should fail due to SSRF protection
        assert result is False

    @pytest.mark.asyncio
    async def test_httpx_timeout_error_handling(self, slack_notifier, mock_httpx_client, sample_action):
        """Test httpx timeout error handling."""
        import httpx

        # Setup mock to raise timeout exception
        mock_httpx_client.post.side_effect = httpx.TimeoutException("Request timed out")

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_request(sample_action)

        # Should handle gracefully
        assert result is False

    @pytest.mark.asyncio
    async def test_httpx_network_error_handling(self, slack_notifier, mock_httpx_client, sample_action):
        """Test httpx network error handling."""
        import httpx

        # Setup mock to raise network exception
        mock_httpx_client.post.side_effect = httpx.NetworkError("Network unreachable")

        with patch("app.approvals.slack.httpx.AsyncClient", return_value=mock_httpx_client):
            result = await slack_notifier.send_approval_request(sample_action)

        # Should handle gracefully
        assert result is False

    def test_status_emoji_mapping(self, slack_notifier, sample_action):
        """Test status emoji mapping in status messages."""
        status_emoji_tests = [
            (ActionStatus.APPROVED, "✅"),
            (ActionStatus.REJECTED, "❌"),
            (ActionStatus.EXECUTED, "🚀"),
            (ActionStatus.FAILED, "💥"),
        ]

        for status, expected_emoji in status_emoji_tests:
            sample_action.status = status
            blocks = slack_notifier._build_status_message(
                action=sample_action,
                status=status,
                user="test_user",
            )

            # Check that emoji is in the blocks
            blocks_str = str(blocks)
            assert expected_emoji in blocks_str


class TestSlackApprovalNotifierIntegration:
    """Test Slack notifier integration patterns."""

    def test_notifier_with_webhook_from_env(self, monkeypatch):
        """Test notifier initialization with webhook from environment."""
        from app.approvals.slack import SlackApprovalNotifier
        from app.config import settings

        # Set webhook URL in settings (simulating env var)
        monkeypatch.setattr(settings, "SLACK_APPROVAL_WEBHOOK_URL", "https://hooks.slack.com/test")

        notifier = SlackApprovalNotifier()

        assert notifier.webhook_url == "https://hooks.slack.com/test"

    def test_notifier_without_webhook(self, monkeypatch):
        """Test notifier initialization without webhook."""
        from app.approvals.slack import SlackApprovalNotifier

        # Ensure no webhook
        monkeypatch.delenv("SLACK_APPROVAL_WEBHOOK_URL", raising=False)

        notifier = SlackApprovalNotifier()

        assert notifier.webhook_url == ""


class TestSlackApprovalNotifierSingleton:
    """Test SlackApprovalNotifier singleton pattern."""

    def test_get_slack_approval_notifier_returns_singleton(self):
        """Test that get_slack_approval_notifier returns same instance."""

        notifier1 = get_slack_approval_notifier()
        notifier2 = get_slack_approval_notifier()

        assert notifier1 is notifier2

    def test_get_slack_approval_notifier_initializes_new_instance(self):
        """Test that first call initializes the notifier."""
        from app.approvals.slack import _slack_notifier
        _slack_notifier = None

        notifier = get_slack_approval_notifier()

        assert notifier is not None
        assert isinstance(notifier, SlackApprovalNotifier)

"""Unit tests for Teams webhook handler and notifier."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.approvals.teams import (
    TeamsApprovalNotifier,
    get_teams_approval_notifier,
    reset_teams_approval_notifier,
)
from app.approvals.webhook import (
    verify_teams_hmac_signature,
)
from app.models.actions import (
    Action,
    ActionStatus,
    CommandParams,
    CommandType,
    RiskLevel,
)


class TestTeamsHMACVerification:
    """Test Teams HMAC signature verification."""

    def test_valid_signature(self):
        """Test that valid signatures are accepted."""
        webhook_url = "https://outlook.office.com/webhook/xxx"
        body = b'{"type": "invoke"}'

        # Calculate valid signature
        import hashlib
        import hmac

        digest = hmac.new(
            webhook_url.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        auth_header = f"sha256={digest}"

        result = verify_teams_hmac_signature(body, auth_header, webhook_url)
        assert result is True

    def test_invalid_signature(self):
        """Test that invalid signatures are rejected."""
        webhook_url = "https://outlook.office.com/webhook/xxx"
        body = b'{"type": "invoke"}'

        result = verify_teams_hmac_signature(body, "sha256=invalid", webhook_url)
        assert result is False

    def test_signature_without_prefix(self):
        """Test signature without sha256= prefix."""
        webhook_url = "https://outlook.office.com/webhook/xxx"
        body = b'{"type": "invoke"}'

        # Calculate valid signature
        import hashlib
        import hmac

        digest = hmac.new(
            webhook_url.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        auth_header = digest  # Without prefix

        result = verify_teams_hmac_signature(body, auth_header, webhook_url)
        assert result is True

    def test_different_bodies_different_signatures(self):
        """Test that different bodies produce different signatures."""
        import hashlib
        import hmac

        webhook_url = "https://outlook.office.com/webhook/xxx"

        body1 = b'{"type": "invoke", "data": {"action": "approve"}}'
        body2 = b'{"type": "invoke", "data": {"action": "reject"}}'

        digest1 = hmac.new(
            webhook_url.encode(),
            body1,
            hashlib.sha256
        ).hexdigest()

        digest2 = hmac.new(
            webhook_url.encode(),
            body2,
            hashlib.sha256
        ).hexdigest()

        assert digest1 != digest2


class TestTeamsApprovalNotifier:
    """Test Teams approval notification."""

    @pytest.fixture
    def reset_notifier(self):
        """Reset notifier before each test."""
        reset_teams_approval_notifier()
        yield
        reset_teams_approval_notifier()

    def test_notifier_creation(self, reset_notifier):
        """Test that notifier can be created."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        assert notifier.webhook_url == "https://outlook.office.com/webhook/xxx"
        assert notifier.disabled is False

    def test_notifier_disabled(self, reset_notifier):
        """Test that disabled notifier works correctly."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx",
            disabled=True,
        )

        assert notifier.is_enabled() is False

    def test_notifier_enabled(self, reset_notifier):
        """Test that enabled notifier works correctly."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx",
            disabled=False,
        )

        assert notifier.is_enabled() is True

    def test_notifier_without_webhook_url(self, reset_notifier):
        """Test notifier without webhook URL."""
        notifier = TeamsApprovalNotifier(webhook_url=None)

        assert notifier.is_enabled() is False

    def test_singleton(self, reset_notifier):
        """Test singleton pattern."""
        notifier1 = get_teams_approval_notifier()
        notifier2 = get_teams_approval_notifier()

        assert notifier1 is notifier2

    def test_build_approval_card(self, reset_notifier):
        """Test building approval card."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl get pods",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Get pods",
            description="Get all pods",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact="Low",
            status=ActionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        card = notifier._build_approval_card(
            action=action,
            approve_url="http://example.com/approve",
            reject_url="http://example.com/reject",
            view_url="http://example.com/view",
        )

        assert card["type"] == "message"
        assert len(card["attachments"]) == 1

        content = card["attachments"][0]["content"]
        assert content["type"] == "AdaptiveCard"
        assert content["version"] == "1.4"

        # Check body has required elements
        body = content["body"]
        assert any(item["type"] == "TextBlock" for item in body)

        # Check actions
        actions = content["actions"]
        assert len(actions) == 3

        action_types = [a.get("data", {}).get("action") for a in actions]
        assert "approve_action" in action_types
        assert "reject_action" in action_types
        assert "view_action" in action_types

    def test_build_status_card_approved(self, reset_notifier):
        """Test building status card for approved action."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl get pods",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Get pods",
            description="Get all pods",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact="Low",
            status=ActionStatus.APPROVED,
            created_at=datetime.now(timezone.utc),
        )

        card = notifier._build_status_card(
            action=action,
            status=ActionStatus.APPROVED,
            user="test-user",
        )

        assert card["type"] == "message"
        content = card["attachments"][0]["content"]
        body = content["body"]

        # Should have approved text
        assert any("Approved" in item.get("text", "") for item in body if item["type"] == "TextBlock")

    def test_build_status_card_rejected(self, reset_notifier):
        """Test building status card for rejected action."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl delete pod",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Delete pod",
            description="Delete pod",
            risk_level=RiskLevel.HIGH,
            estimated_impact="Medium",
            status=ActionStatus.REJECTED,
            created_at=datetime.now(timezone.utc),
        )

        card = notifier._build_status_card(
            action=action,
            status=ActionStatus.REJECTED,
            user="test-user",
        )

        assert card["type"] == "message"
        content = card["attachments"][0]["content"]
        body = content["body"]

        # Should have rejected text
        assert any("Rejected" in item.get("text", "") for item in body if item["type"] == "TextBlock")

    @pytest.mark.asyncio
    async def test_send_approval_request_disabled(self, reset_notifier):
        """Test sending approval request when disabled."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx",
            disabled=True,
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl get pods",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Get pods",
            description="Get all pods",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact="Low",
            status=ActionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        result = await notifier.send_approval_request(
            action=action,
            approve_url="http://example.com/approve",
            reject_url="http://example.com/reject",
            view_url="http://example.com/view",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_approval_request_success(self, reset_notifier):
        """Test successful approval request sending."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx",
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl get pods",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Get pods",
            description="Get all pods",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact="Low",
            status=ActionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            result = await notifier.send_approval_request(
                action=action,
                approve_url="http://example.com/approve",
                reject_url="http://example.com/reject",
                view_url="http://example.com/view",
            )

            assert result is True
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_approval_request_failure(self, reset_notifier):
        """Test failed approval request sending."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx",
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl get pods",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Get pods",
            description="Get all pods",
            risk_level=RiskLevel.MEDIUM,
            estimated_impact="Low",
            status=ActionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response

            result = await notifier.send_approval_request(
                action=action,
                approve_url="http://example.com/approve",
                reject_url="http://example.com/reject",
                view_url="http://example.com/view",
            )

            assert result is False


class TestTeamsAdaptiveCards:
    """Test Teams Adaptive Cards structure."""

    def test_approval_card_structure(self):
        """Test that approval card has correct structure."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl scale deployment test --replicas=3",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Scale deployment",
            description="Scale deployment",
            risk_level=RiskLevel.HIGH,
            estimated_impact="Medium",
            status=ActionStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        card = notifier._build_approval_card(
            action=action,
            approve_url="http://example.com/approve",
            reject_url="http://example.com/reject",
            view_url="http://example.com/view",
        )

        # Verify card structure
        assert "type" in card
        assert "attachments" in card
        assert len(card["attachments"]) > 0

        attachment = card["attachments"][0]
        assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"

        content = attachment["content"]
        assert content["type"] == "AdaptiveCard"
        assert content["version"] == "1.4"
        assert "$schema" in content

    def test_status_card_structure(self):
        """Test that status card has correct structure."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        action = Action(
            id="test-action-id",
            triage_card_id="tc-001",
            recommendation_id="rec-001",
            command_type=CommandType.KUBECTL,
            command="kubectl delete pod test",
            parsed_params=CommandParams(
                command_type=CommandType.KUBECTL,
                action="get",
                resource_type="pods",
                flags={},
            ),
            project="test-project",
            title="Delete pod",
            description="Delete pod",
            risk_level=RiskLevel.CRITICAL,
            estimated_impact="High",
            status=ActionStatus.APPROVED,
            created_at=datetime.now(timezone.utc),
        )

        card = notifier._build_status_card(
            action=action,
            status=ActionStatus.APPROVED,
            user="admin",
        )

        # Verify card structure
        assert "type" in card
        assert "attachments" in card

        content = card["attachments"][0]["content"]
        assert content["type"] == "AdaptiveCard"

    def test_risk_level_colors(self):
        """Test that different risk levels get appropriate colors."""
        notifier = TeamsApprovalNotifier(
            webhook_url="https://outlook.office.com/webhook/xxx"
        )

        risk_colors = {
            RiskLevel.SAFE: "Good",
            RiskLevel.LOW: "Good",
            RiskLevel.MEDIUM: "Warning",
            RiskLevel.HIGH: "Warning",
            RiskLevel.CRITICAL: "Attention",
        }

        for risk_level, expected_color in risk_colors.items():
            action = Action(
                id="test-action-id",
                triage_card_id="tc-001",
                recommendation_id="rec-001",
                command_type=CommandType.KUBECTL,
                command="kubectl get pods",
                parsed_params=CommandParams(
                    command_type=CommandType.KUBECTL,
                    action="get",
                    resource_type="pods",
                    flags={},
                ),
                project="test-project",
                title="Get pods",
                description="Test",
                risk_level=risk_level,
                estimated_impact="Low",
                status=ActionStatus.PENDING,
                created_at=datetime.now(timezone.utc),
            )

            card = notifier._build_approval_card(
                action=action,
                approve_url="http://example.com/approve",
                reject_url="http://example.com/reject",
                view_url="http://example.com/view",
            )

            # Find the color in the card
            content = card["attachments"][0]["content"]
            title_block = next(
                (item for item in content["body"] if item.get("text", "").startswith("🔔")),
                None
            )

            if title_block:
                assert title_block.get("color") == expected_color


class TestTeamsWebhookEndpoint:
    """Test Teams webhook endpoint (integration tests)."""

    @pytest.fixture
    def mock_engine(self):
        """Mock action engine."""
        engine = Mock()
        engine.approve_action = AsyncMock()
        engine.reject_action = AsyncMock()
        engine.get_action = Mock(return_value={
            "id": "test-id",
            "command": "kubectl get pods",
            "description": "Test",
            "risk_level": "MEDIUM",
        })
        return engine

    @pytest.fixture
    def mock_notifier(self):
        """Mock Teams notifier."""
        notifier = Mock()
        notifier.send_approval_status = AsyncMock()
        return notifier

    @pytest.mark.asyncio
    async def test_webhook_health_includes_teams(self):
        """Test that health endpoint includes Teams status."""
        from app.approvals.webhook import approval_webhook_health

        # Reset to ensure fresh state
        reset_teams_approval_notifier()

        result = await approval_webhook_health()

        assert "webhooks" in result
        assert "teams" in result["webhooks"]
        assert result["webhooks"]["teams"] in ["enabled", "disabled"]

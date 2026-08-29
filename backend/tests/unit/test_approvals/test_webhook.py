"""Unit tests for Webhook approval handlers."""

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.approvals.webhook import (
    verify_slack_signature,
    verify_teams_hmac_signature,
    slack_approval_webhook,
    teams_approval_webhook,
    approval_webhook_health,
    SLACK_SIGNATURE_VERSION,
    SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS,
)
from app.models.actions import ActionStatus


@pytest.fixture
def mock_action_engine():
    """Mock ActionEngine."""
    engine = AsyncMock()
    engine.approve_action = AsyncMock()
    engine.reject_action = AsyncMock()
    engine.get_action = MagicMock()
    return engine


@pytest.fixture
def mock_slack_notifier():
    """Mock SlackApprovalNotifier."""
    notifier = AsyncMock()
    notifier.send_approval_status = AsyncMock()
    notifier.webhook_url = "https://hooks.slack.com/test"
    return notifier


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.SLACK_SIGNING_SECRET = "test-secret"
    settings.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook"
    settings.ENVIRONMENT = "development"
    settings.ALLOWED_WEBHOOK_IPS = None
    return settings


class TestVerifySlackSignature:
    """Test Slack signature verification."""

    def test_valid_signature(self):
        """Test signature verification with valid signature."""
        # Use current timestamp to be within tolerance
        import time
        timestamp = str(int(time.time()))
        body = b'{"payload": "test"}'
        sig_basestring = f"{SLACK_SIGNATURE_VERSION}:{timestamp}:{body.decode('utf-8')}"
        digest = hmac.new(
            b"test-secret",
            sig_basestring.encode(),
            hashlib.sha256
        ).digest()
        expected_signature = f"{SLACK_SIGNATURE_VERSION}=" + digest.hex()

        result = verify_slack_signature(body, timestamp, expected_signature, "test-secret")
        assert result is True

    def test_invalid_signature(self):
        """Test signature verification with invalid signature."""
        # Use current timestamp to pass timestamp check
        import time
        timestamp = str(int(time.time()))
        body = b'{"payload": "test"}'
        invalid_signature = f"{SLACK_SIGNATURE_VERSION}=invalid"

        result = verify_slack_signature(body, timestamp, invalid_signature, "test-secret")
        assert result is False

    def test_old_timestamp_replay_attack(self):
        """Test timestamp validation rejects old timestamps."""
        # Use very old timestamp (100 seconds ago - beyond tolerance)
        import time
        old_timestamp = str(int(time.time()) - 100)
        body = b'{"payload": "test"}'

        with pytest.raises(HTTPException) as exc_info:
            verify_slack_signature(
                body,
                old_timestamp,
                f"{SLACK_SIGNATURE_VERSION}=dummy",
                "test-secret"
            )

        assert exc_info.value.status_code == 401
        assert "too old" in str(exc_info.value.detail).lower()

    def test_malformed_timestamp(self):
        """Test timestamp validation with malformed timestamp."""
        body = b'{"payload": "test"}'
        invalid_timestamp = "not-a-number"

        with pytest.raises(HTTPException) as exc_info:
            verify_slack_signature(
                body,
                invalid_timestamp,
                f"{SLACK_SIGNATURE_VERSION}=dummy",
                "test-secret"
            )

        assert exc_info.value.status_code == 401
        assert "invalid timestamp" in str(exc_info.value.detail).lower()


class TestVerifyTeamsHmacSignature:
    """Test Teams HMAC signature verification."""

    def test_valid_teams_signature(self):
        """Test Teams signature verification with valid signature."""
        webhook_url = "https://outlook.office.com/webhook"
        body = b'{"payload": "test"}'

        # Calculate valid signature
        digest = hmac.new(
            webhook_url.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        auth_header = f"sha256={digest}"

        result = verify_teams_hmac_signature(body, auth_header, webhook_url)
        assert result is True

    def test_invalid_teams_signature(self):
        """Test Teams signature verification with invalid signature."""
        webhook_url = "https://outlook.office.com/webhook"
        body = b'{"payload": "test"}'
        invalid_signature = "sha256=invalid"

        result = verify_teams_hmac_signature(body, invalid_signature, webhook_url)
        assert result is False

    def test_teams_signature_without_sha256_prefix(self):
        """Test Teams signature without sha256 prefix."""
        webhook_url = "https://outlook.office.com/webhook"
        body = b'{"payload": "test"}'

        # Calculate valid signature
        digest = hmac.new(
            webhook_url.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        auth_header = digest  # Without prefix

        result = verify_teams_hmac_signature(body, auth_header, webhook_url)
        assert result is True


class TestSlackApprovalWebhook:
    """Test Slack webhook endpoint."""

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI Request."""
        request = MagicMock()
        request.client = MagicMock(host="127.0.0.1")
        request.body = AsyncMock()
        request.form = AsyncMock()
        return request

    @pytest.mark.asyncio
    async def test_approve_action_happy_path(
        self,
        mock_request,
        mock_action_engine,
        mock_slack_notifier,
    ):
        """Test successful action approval via Slack webhook."""
        # Setup request
        payload = {
            "actions": [{"action_id": "approve_action", "value": "action:act-123"}],
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"timestamp_data"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        # Setup mocks
        mock_action_engine.approve_action.return_value = MagicMock(
            id="act-123",
            status=ActionStatus.APPROVED,
        )

        with patch("app.actions.engine.get_action_engine", return_value=mock_action_engine), \
             patch("app.approvals.webhook.get_slack_approval_notifier", return_value=mock_slack_notifier), \
             patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            result = await slack_approval_webhook(
                mock_request,
                x_slack_request_timestamp="1234567890",
                x_slack_signature="v0=valid",
            )

        assert result["response_type"] == "ephemeral"
        assert "approved" in result["text"].lower()
        mock_action_engine.approve_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_action_happy_path(
        self,
        mock_request,
        mock_action_engine,
        mock_slack_notifier,
    ):
        """Test successful action rejection via Slack webhook."""
        # Setup request
        payload = {
            "actions": [{"action_id": "reject_action", "value": "action:act-123"}],
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"timestamp_data"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        # Setup mocks
        mock_action_engine.reject_action.return_value = MagicMock(
            id="act-123",
            status=ActionStatus.REJECTED,
        )

        with patch("app.actions.engine.get_action_engine", return_value=mock_action_engine), \
             patch("app.approvals.webhook.get_slack_approval_notifier", return_value=mock_slack_notifier), \
             patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            result = await slack_approval_webhook(
                mock_request,
                x_slack_request_timestamp="1234567890",
                x_slack_signature="v0=valid",
            )

        assert result["response_type"] == "ephemeral"
        assert "rejected" in result["text"].lower()
        mock_action_engine.reject_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_view_action_happy_path(
        self,
        mock_request,
        mock_action_engine,
    ):
        """Test viewing action details via Slack webhook."""
        # Setup request
        payload = {
            "actions": [{"action_id": "view_action", "value": "action:act-123"}],
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"timestamp_data"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        # Setup mock action data
        mock_action_engine.get_action.return_value = {
            "id": "act-123",
            "command": "kubectl get pods",
            "description": "Check pod health",
            "risk_level": "low",
        }

        with patch("app.actions.engine.get_action_engine", return_value=mock_action_engine), \
             patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            result = await slack_approval_webhook(
                mock_request,
                x_slack_request_timestamp="1234567890",
                x_slack_signature="v0=valid",
            )

        assert result["response_type"] == "ephemeral"
        assert "action details" in result["text"].lower()
        assert "kubectl get pods" in result["text"]

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, mock_request):
        """Test invalid signature returns 401."""
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": "{}"}

        with patch("app.approvals.webhook.verify_slack_signature", return_value=False), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=invalid",
                )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_old_timestamp_returns_401(self, mock_request):
        """Test old timestamp returns 401."""
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": "{}"}

        # Make verify_slack_signature raise HTTPException for old timestamp
        with patch("app.approvals.webhook.verify_slack_signature") as mock_verify, \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_verify.side_effect = HTTPException(status_code=401, detail="Timestamp too old")

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1000000000",
                    x_slack_signature="v0=dummy",
                )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_payload_returns_400(self, mock_request):
        """Test missing payload returns 400."""
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {}  # No payload

        with patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_action_id_returns_400(self, mock_request):
        """Test invalid action ID returns 400."""
        # Setup request with invalid action value
        payload = {
            "actions": [{"action_id": "approve_action", "value": "invalid"}],  # No ":"
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        with patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_action_not_found_returns_404(
        self,
        mock_request,
        mock_action_engine,
    ):
        """Test viewing non-existent action returns 404."""
        # Setup request
        payload = {
            "actions": [{"action_id": "view_action", "value": "action:act-123"}],
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        # Setup mock to return None
        mock_action_engine.get_action.return_value = None

        with patch("app.actions.engine.get_action_engine", return_value=mock_action_engine), \
             patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_action_type_returns_400(self, mock_request):
        """Test unknown action type returns 400."""
        # Setup request with unknown action type
        payload = {
            "actions": [{"action_id": "unknown_action", "value": "action:act-123"}],
            "user": {"id": "U123", "name": "john.doe"},
        }
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": json.dumps(payload)}

        with patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_json_payload_returns_400(self, mock_request):
        """Test invalid JSON payload returns 400."""
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": "invalid json{"}

        with patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = None

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_ip_whitelist_check(self, mock_request):
        """Test IP whitelist validation."""
        mock_request.body.return_value = b"test_body"
        mock_request.form.return_value = {"payload": "{}"}
        mock_request.client.host = "192.168.1.100"  # Unauthorized IP

        with patch("app.approvals.webhook.verify_slack_signature", return_value=True), \
             patch("app.approvals.webhook.settings") as mock_settings_class:

            mock_settings_class.SLACK_SIGNING_SECRET = "test-secret"
            mock_settings_class.ALLOWED_WEBHOOK_IPS = ["127.0.0.1", "10.0.0.1"]

            with pytest.raises(HTTPException) as exc_info:
                await slack_approval_webhook(
                    mock_request,
                    x_slack_request_timestamp="1234567890",
                    x_slack_signature="v0=valid",
                )

        assert exc_info.value.status_code == 403


class TestTeamsApprovalWebhook:
    """Test Teams webhook endpoint."""

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI Request."""
        request = MagicMock()
        request.client = MagicMock(host="127.0.0.1")
        request.body = AsyncMock()
        request.json = AsyncMock(return_value={"type": "taskUpdate", "attachments": []})
        return request

    @pytest.mark.asyncio
    async def test_teams_webhook_invalid_action_id_returns_400(self, mock_request):
        """Test Teams webhook rejects payload without actionId."""
        mock_request.body.return_value = b'{"test": "data"}'

        with patch("app.approvals.webhook.settings") as mock_settings_class:
            mock_settings_class.ENVIRONMENT = "development"
            mock_settings_class.TEAMS_WEBHOOK_URL = None

            with pytest.raises(HTTPException) as exc_info:
                await teams_approval_webhook(mock_request, authorization=None)

        assert exc_info.value.status_code == 400
        assert "Invalid action ID" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_teams_webhook_production_requires_url(self, mock_request):
        """Test production requires TEAMS_WEBHOOK_URL."""
        mock_request.body.return_value = b'{"test": "data"}'

        with patch("app.approvals.webhook.settings") as mock_settings_class:
            mock_settings_class.ENVIRONMENT = "production"
            mock_settings_class.TEAMS_WEBHOOK_URL = None

            with pytest.raises(HTTPException) as exc_info:
                await teams_approval_webhook(mock_request, authorization=None)

        assert exc_info.value.status_code == 500
        assert "not configured" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_teams_webhook_production_requires_auth_header(self, mock_request):
        """Test production requires Authorization header."""
        mock_request.body.return_value = b'{"test": "data"}'

        with patch("app.approvals.webhook.settings") as mock_settings_class:
            mock_settings_class.ENVIRONMENT = "production"
            mock_settings_class.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook"

            with pytest.raises(HTTPException) as exc_info:
                await teams_approval_webhook(mock_request, authorization=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_teams_webhook_invalid_signature_returns_401(self, mock_request):
        """Test invalid signature returns 401."""
        mock_request.body.return_value = b'{"test": "data"}'

        with patch("app.approvals.webhook.settings") as mock_settings_class, \
             patch("app.approvals.webhook.verify_teams_hmac_signature", return_value=False):

            mock_settings_class.ENVIRONMENT = "production"
            mock_settings_class.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook"

            with pytest.raises(HTTPException) as exc_info:
                await teams_approval_webhook(
                    mock_request,
                    authorization="sha256=invalid"
                )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_teams_webhook_dev_optional_signature(self, mock_request):
        """Test development mode allows processing without signature (reaches payload parse)."""
        mock_request.body.return_value = b'{"test": "data"}'

        with patch("app.approvals.webhook.settings") as mock_settings_class:
            mock_settings_class.ENVIRONMENT = "development"
            mock_settings_class.TEAMS_WEBHOOK_URL = None

            with pytest.raises(HTTPException) as exc_info:
                await teams_approval_webhook(mock_request, authorization=None)

        # Unsigned dev request passes signature gate and fails on missing actionId
        assert exc_info.value.status_code == 400


class TestApprovalWebhookHealth:
    """Test webhook health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self):
        """Test health check returns healthy status."""
        result = await approval_webhook_health()

        assert result["status"] == "healthy"
        assert "webhooks" in result
        assert "slack" in result["webhooks"]
        assert "teams" in result["webhooks"]

    @pytest.mark.asyncio
    async def test_health_check_slack_status(self):
        """Test health check reflects Slack webhook status."""
        with patch("app.approvals.webhook.get_slack_approval_notifier") as mock_get:
            mock_notifier = MagicMock()
            mock_notifier.webhook_url = "https://hooks.slack.com/test"
            mock_get.return_value = mock_notifier

            result = await approval_webhook_health()

            assert result["webhooks"]["slack"] == "enabled"

    @pytest.mark.asyncio
    async def test_health_check_teams_disabled_by_default(self):
        """Test health check shows Teams as disabled when no webhook URL configured."""
        result = await approval_webhook_health()

        assert result["webhooks"]["teams"] == "disabled"

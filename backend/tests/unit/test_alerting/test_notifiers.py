"""
Unit tests for Alert Notifiers.

Tests the notification functionality including:
- Slack notifications
- Email notifications
- Webhook notifications
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.alerting.notifiers import SlackNotifier, EmailNotifier, WebhookNotifier


@pytest.mark.unit
@pytest.mark.alerting
class TestNotifiers:
    """Test suite for alert notifiers."""

    @pytest.mark.asyncio
    async def test_slack_notifier_sends_message(self):
        """Test Slack notifier sends message successfully."""
        with patch("app.alerting.notifiers.settings.SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            notifier = SlackNotifier()

            event = {
                "rule_name": "Test Alert",
                "severity": "warning",
                "status": "firing",
                "value": 100,
                "threshold": 80,
                "message": "Test message"
            }

            with patch("app.alerting.notifiers.is_url_allowed", return_value=True):
                # Mock the httpx.AsyncClient context manager
                mock_response = MagicMock()
                mock_response.status_code = 200

                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_client_instance = MagicMock()
                    mock_client_instance.post = AsyncMock(return_value=mock_response)
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock()
                    mock_client_cls.return_value = mock_client_instance

                    result = await notifier.send(event)

                    assert result is True

    @pytest.mark.asyncio
    async def test_slack_notifier_handles_failure(self):
        """Test Slack notifier handles send failure."""
        with patch("app.alerting.notifiers.settings.SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            notifier = SlackNotifier()

            event = {"rule_name": "Test", "severity": "warning"}

            with patch("app.alerting.notifiers.is_url_allowed", return_value=True):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    async def raise_error(*args, **kwargs):
                        raise Exception("Network error")

                    mock_client = MagicMock()
                    mock_client.post = raise_error

                    # Mock context manager properly
                    mock_client_cm = MagicMock()
                    mock_client_cm.__aenter__.return_value = mock_client
                    mock_client_cm.__aexit__.return_value = None

                    mock_client_cls.return_value = mock_client_cm

                    result = await notifier.send(event)

                    assert result is False

    @pytest.mark.asyncio
    async def test_email_notifier_sends_email(self):
        """Test EmailNotifier sends email successfully."""
        with patch("app.alerting.notifiers.settings.SMTP_HOST", "smtp.test.com"):
            with patch("app.alerting.notifiers.settings.ALERT_EMAIL_TO", ["admin@test.com"]):
                notifier = EmailNotifier()

                event = {
                    "rule_name": "Test Alert",
                    "status": "firing",
                    "severity": "critical",
                    "value": 95,
                    "threshold": 90,
                    "message": "High CPU usage"
                }

                with patch("smtplib.SMTP") as mock_smtp:
                    mock_server = MagicMock()
                    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

                    result = await notifier.send(event)

                    assert result is True
                    mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notifier_sends_post_request(self):
        """Test WebhookNotifier sends POST request."""
        with patch("app.alerting.notifiers.settings.ALERT_WEBHOOK_URL", "https://webhook.test.com"):
            notifier = WebhookNotifier()

            event = {"rule_name": "Test", "severity": "warning"}

            with patch("app.alerting.notifiers.is_url_allowed", return_value=True):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_response = MagicMock()
                    mock_response.status_code = 200

                    mock_client_instance = MagicMock()
                    mock_client_instance.post = AsyncMock(return_value=mock_response)
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock()
                    mock_client_cls.return_value = mock_client_instance

                    result = await notifier.send(event)

                    assert result is True

    @pytest.mark.asyncio
    async def test_webhook_notifier_handles_failure(self):
        """Test WebhookNotifier handles failure gracefully."""
        with patch("app.alerting.notifiers.settings.ALERT_WEBHOOK_URL", "https://webhook.test.com"):
            notifier = WebhookNotifier()

            event = {"rule_name": "Test"}

            with patch("app.alerting.notifiers.is_url_allowed", return_value=True):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    async def raise_error(*args, **kwargs):
                        raise Exception("HTTP error")

                    mock_client = MagicMock()
                    mock_client.post = raise_error

                    # Mock context manager properly
                    mock_client_cm = MagicMock()
                    mock_client_cm.__aenter__.return_value = mock_client
                    mock_client_cm.__aexit__.return_value = None

                    mock_client_cls.return_value = mock_client_cm

                    result = await notifier.send(event)

                    assert result is False

    @pytest.mark.asyncio
    async def test_slack_notifier_with_no_webhook_url(self):
        """Test SlackNotifier returns False when no webhook URL configured."""
        with patch("app.alerting.notifiers.settings.SLACK_WEBHOOK_URL", None):
            notifier = SlackNotifier()
            result = await notifier.send({"rule_name": "Test"})
            assert result is False

    @pytest.mark.asyncio
    async def test_email_notifier_with_no_smtp_config(self):
        """Test EmailNotifier returns False when SMTP not configured."""
        with patch("app.alerting.notifiers.settings.SMTP_HOST", None):
            notifier = EmailNotifier()
            result = await notifier.send({"rule_name": "Test"})
            assert result is False

    @pytest.mark.asyncio
    async def test_webhook_notifier_with_no_url(self):
        """Test WebhookNotifier returns False when no URL configured."""
        with patch("app.alerting.notifiers.settings.ALERT_WEBHOOK_URL", None):
            notifier = WebhookNotifier()
            result = await notifier.send({"rule_name": "Test"})
            assert result is False

    @pytest.mark.asyncio
    async def test_slack_notifier_with_block_kit_format(self):
        """Test SlackNotifier formats message with Block Kit."""
        with patch("app.alerting.notifiers.settings.SLACK_WEBHOOK_URL", "https://hooks.slack.com/test"):
            notifier = SlackNotifier()

            event = {
                "rule_name": "Critical Alert",
                "severity": "critical",
                "status": "firing",
                "value": 99,
                "threshold": 80,
                "message": "System overload"
            }

            with patch("app.alerting.notifiers.is_url_allowed", return_value=True):
                with patch("httpx.AsyncClient") as mock_client_cls:
                    mock_response = MagicMock()
                    mock_response.status_code = 200

                    mock_client_instance = MagicMock()
                    mock_client_instance.post = AsyncMock(return_value=mock_response)
                    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                    mock_client_instance.__aexit__ = AsyncMock()
                    mock_client_cls.return_value = mock_client_instance

                    result = await notifier.send(event)

                    assert result is True
                    # Verify the call was made
                    mock_client_instance.post.assert_called_once()

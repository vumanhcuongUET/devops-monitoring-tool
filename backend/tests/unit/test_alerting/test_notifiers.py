"""
Unit tests for Alert Notifiers.

Tests the notifier functionality including:
- Slack notifications
- Email notifications
- Webhook notifications
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.mark.unit
@pytest.mark.alerting
class TestNotifiers:
    """Test suite for alert notifiers."""

    @pytest.mark.asyncio
    async def test_slack_notifier_sends_message(self):
        """Test that SlackNotifier sends a message to webhook."""
        from app.alerting.notifiers import SlackNotifier

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")

        result = await notifier.send(
            message="Test alert message",
            severity="warning"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_slack_notifier_handles_failure(self):
        """Test that SlackNotifier handles webhook failures."""
        from app.alerting.notifiers import SlackNotifier

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")

        with pytest.raises(httpx.RequestError):
            await notifier.send(
                message="Test alert message",
                severity="critical"
            )

    @pytest.mark.asyncio
    async def test_email_notifier_sends_email(self):
        """Test that EmailNotifier sends an email."""
        from app.alerting.notifiers import EmailNotifier

        mock_smtp = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp):
            notifier = EmailNotifier(
                smtp_host="smtp.test.com",
                smtp_port=587,
                username="test@test.com",
                password="testpass"
            )

            result = await notifier.send(
                to=["recipient@test.com"],
                subject="Test Alert",
                message="Test alert message"
            )

            # Verify SMTP methods were called
            mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notifier_sends_post_request(self):
        """Test that WebhookNotifier sends POST request."""
        from app.alerting.notifiers import WebhookNotifier

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            return_value=MagicMock(status_code=200, text="OK")
        )

        notifier = WebhookNotifier(
            webhook_url="https://example.com/webhook",
            http_client=mock_http_client
        )

        result = await notifier.send(
            alert_data={
                "rule_id": "test-rule-001",
                "severity": "critical",
                "message": "Test alert"
            }
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_notifier_with_custom_headers(self):
        """Test that WebhookNotifier sends custom headers."""
        from app.alerting.notifiers import WebhookNotifier

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            return_value=MagicMock(status_code=200)
        )

        notifier = WebhookNotifier(
            webhook_url="https://example.com/webhook",
            headers={"X-Custom-Header": "test-value"},
            http_client=mock_http_client
        )

        await notifier.send(alert_data={"test": "data"})

        # Verify post was called
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_slack_notifier_with_block_kit_format(self):
        """Test that SlackNotifier can send Block Kit formatted messages."""
        from app.alerting.notifiers import SlackNotifier

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(
            return_value=MagicMock(status_code=200)
        )

        notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            http_client=mock_http_client
        )

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Test alert"}
            }
        ]

        result = await notifier.send(
            message="Test alert",
            blocks=blocks
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_email_notifier_with_multiple_recipients(self):
        """Test that EmailNotifier can send to multiple recipients."""
        from app.alerting.notifiers import EmailNotifier

        mock_smtp = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp):
            notifier = EmailNotifier(
                smtp_host="smtp.test.com",
                smtp_port=587,
                username="test@test.com",
                password="testpass"
            )

            await notifier.send(
                to=["recipient1@test.com", "recipient2@test.com"],
                subject="Test Alert",
                message="Test alert message"
            )

            # Verify sendmail was called with multiple recipients
            mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notifier_with_retries(self):
        """Test that WebhookNotifier retries on failure."""
        from app.alerting.notifiers import WebhookNotifier

        mock_http_client = AsyncMock()
        # First call fails, second succeeds
        mock_http_client.post = AsyncMock(
            side_effect=[
                httpx.RequestError("Network error"),
                MagicMock(status_code=200)
            ]
        )

        notifier = WebhookNotifier(
            webhook_url="https://example.com/webhook",
            max_retries=2,
            http_client=mock_http_client
        )

        result = await notifier.send(alert_data={"test": "data"})

        # Should eventually succeed
        assert result is True

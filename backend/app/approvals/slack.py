"""Slack approval integration with interactive buttons."""

import logging

import httpx

from app.config import settings
from app.models.actions import Action, ActionStatus, RiskLevel
from app.security import is_url_allowed

logger = logging.getLogger(__name__)


class SlackApprovalNotifier:
    """Send approval requests to Slack and handle button interactions."""

    def __init__(self):
        self.webhook_url = settings.SLACK_APPROVAL_WEBHOOK_URL
        self.timeout = 10

    async def send_approval_request(
        self,
        action: Action,
        slack_channel: str | None = None,
        slack_user: str | None = None,
    ) -> bool:
        """Send an approval request to Slack with interactive buttons.

        Args:
            action: The action requiring approval
            slack_channel: Target Slack channel (overrides default)
            slack_user: Target Slack user ID for DM

        Returns:
            True if the notification was sent successfully
        """
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured")
            return False

        if not is_url_allowed(self.webhook_url):
            logger.warning("Slack webhook URL blocked by SSRF protection")
            return False

        # Build the message with buttons
        blocks = self._build_approval_message(action)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json={"blocks": blocks},
                )
                if response.status_code == 200:
                    logger.info(f"Sent approval request for action {action.id} to Slack")
                    return True
                else:
                    logger.error(f"Failed to send Slack approval: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Error sending Slack approval request: {e}")
            return False

    def _build_approval_message(self, action: Action) -> list[dict]:
        """Build Slack Block Kit message for approval request."""

        # Color based on risk level
        risk_colors = {
            RiskLevel.CRITICAL: "#FF0000",  # Red
            RiskLevel.HIGH: "#FF6600",      # Orange
            RiskLevel.MEDIUM: "#FFCC00",    # Yellow
            RiskLevel.LOW: "#36A64F",       # Green
            RiskLevel.SAFE: "#36A64F",      # Green
        }
        _color = risk_colors.get(action.risk_level, "#FFCC00")

        # Risk level emoji
        risk_emojis = {
            RiskLevel.CRITICAL: "🔴",
            RiskLevel.HIGH: "🟠",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.LOW: "🟢",
            RiskLevel.SAFE: "✅",
        }
        risk_emoji = risk_emojis.get(action.risk_level, "⚠️")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{risk_emoji} Action Approval Required",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Action ID:*\n`{action.id}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Project:*\n{action.project}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Level:*\n{action.risk_level.value.upper()}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Command:*\n`{action.command}`",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{action.title}*\n{action.description}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Estimated Impact:*\n{action.estimated_impact}",
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Approve",
                            "emoji": True,
                        },
                        "style": "primary",
                        "value": f"approve:{action.id}",
                        "action_id": "approve_action",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "❌ Reject",
                            "emoji": True,
                        },
                        "style": "danger",
                        "value": f"reject:{action.id}",
                        "action_id": "reject_action",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 View Details",
                            "emoji": True,
                        },
                        "value": f"view:{action.id}",
                        "action_id": "view_action",
                    },
                ],
            },
        ]

        return blocks

    async def send_approval_status(
        self,
        action: Action,
        status: ActionStatus,
        user: str | None = None,
    ) -> bool:
        """Send a status update notification to Slack.

        Args:
            action: The action that was approved/rejected/executed
            status: The new status of the action
            user: User who performed the action

        Returns:
            True if the notification was sent successfully
        """
        if not self.webhook_url:
            return False

        if not is_url_allowed(self.webhook_url):
            return False

        blocks = self._build_status_message(action, status, user)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json={"blocks": blocks},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error sending Slack status update: {e}")
            return False

    def _build_status_message(
        self,
        action: Action,
        status: ActionStatus,
        user: str | None,
    ) -> list[dict]:
        """Build Slack message for status update."""

        status_emojis = {
            ActionStatus.APPROVED: "✅",
            ActionStatus.REJECTED: "❌",
            ActionStatus.EXECUTED: "🚀",
            ActionStatus.FAILED: "💥",
        }

        emoji = status_emojis.get(status, "ℹ️")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} Action *{action.id}* status updated to *{status.value}*",
                },
            },
        ]

        if user:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Performed by {user}",
                    },
                ],
            })

        if action.execution_result:
            result = action.execution_result
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Result:* {'Success' if result.success else 'Failed'}\n"
                           f"{'```' + result.stdout[:200] + '```' if result.stdout else ''}"
                           f"{'```' + result.stderr[:200] + '```' if result.stderr else ''}",
                },
            })

        return blocks


# Singleton instance
_slack_notifier: SlackApprovalNotifier | None = None


def get_slack_approval_notifier() -> SlackApprovalNotifier:
    """Get or create the singleton SlackApprovalNotifier instance."""
    global _slack_notifier
    if _slack_notifier is None:
        _slack_notifier = SlackApprovalNotifier()
    return _slack_notifier

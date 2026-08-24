"""Microsoft Teams approval notification using Adaptive Cards."""

import logging
import httpx
from typing import Any, Optional
from datetime import datetime, timezone

from app.models.actions import Action, ActionStatus, RiskLevel

logger = logging.getLogger(__name__)


class TeamsApprovalNotifier:
    """Send approval notifications to Microsoft Teams using Adaptive Cards."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        disabled: bool = False,
    ):
        """Initialize the Teams approval notifier.

        Args:
            webhook_url: Teams webhook URL for sending notifications
            disabled: If True, notifications are disabled (for testing)
        """
        self.webhook_url = webhook_url
        self.disabled = disabled

    def is_enabled(self) -> bool:
        """Check if Teams notifications are enabled."""
        return not self.disabled and bool(self.webhook_url)

    async def send_approval_request(
        self,
        action: Action,
        approve_url: str,
        reject_url: str,
        view_url: str,
    ) -> bool:
        """Send an approval request card to Teams.

        Args:
            action: The action awaiting approval
            approve_url: URL for approve button action
            reject_url: URL for reject button action
            view_url: URL for view details action

        Returns:
            True if notification was sent successfully
        """
        if not self.is_enabled():
            logger.warning("Teams notifications are disabled")
            return False

        if not self.webhook_url:
            logger.error("Teams webhook URL not configured")
            return False

        # Build Adaptive Card
        card = self._build_approval_card(
            action=action,
            approve_url=approve_url,
            reject_url=reject_url,
            view_url=view_url,
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=card,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    logger.info(f"Sent approval request to Teams for action {action.id}")
                    return True
                else:
                    logger.error(
                        f"Failed to send Teams notification: {response.status_code} - {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error sending Teams notification: {e}")
            return False

    async def send_approval_status(
        self,
        action: Action,
        status: ActionStatus,
        user: str,
    ) -> bool:
        """Send approval status update to Teams.

        Args:
            action: The action that was approved/rejected
            status: The new status of the action
            user: The user who approved/rejected

        Returns:
            True if notification was sent successfully
        """
        if not self.is_enabled():
            return False

        card = self._build_status_card(action, status, user)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=card,
                    headers={"Content-Type": "application/json"},
                )

                return response.status_code == 200

        except Exception as e:
            logger.error(f"Error sending Teams status update: {e}")
            return False

    def _build_approval_card(
        self,
        action: Action,
        approve_url: str,
        reject_url: str,
        view_url: str,
    ) -> dict[str, Any]:
        """Build an Adaptive Card for approval request.

        Args:
            action: The action awaiting approval
            approve_url: URL for approve button
            reject_url: URL for reject button
            view_url: URL for view details button

        Returns:
            Adaptive Card dictionary
        """
        # Determine color based on risk level (use enum value for lookup)
        risk_colors = {
            RiskLevel.SAFE: "Good",
            RiskLevel.LOW: "Good",
            RiskLevel.MEDIUM: "Warning",
            RiskLevel.HIGH: "Warning",
            RiskLevel.CRITICAL: "Attention",
        }
        risk_color = risk_colors.get(action.risk_level, "Warning")

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "🔔 Action Approval Required",
                                "weight": "Bolder",
                                "size": "Large",
                                "color": risk_color,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Action ID:", "value": action.id[:8]},
                                    {"title": "Project:", "value": action.project},
                                    {"title": "Command:", "value": action.command or "N/A"},
                                    {"title": "Risk Level:", "value": action.risk_level},
                                    {
                                        "title": "Created At:",
                                        "value": action.created_at.strftime("%Y-%m-%d %H:%M:%S")
                                        if action.created_at
                                        else "N/A",
                                    },
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": action.description or "",
                                "wrap": True,
                                "size": "Small",
                            },
                            {
                                "type": "TextBlock",
                                "text": "⚠️ Review the command and approve or reject below:",
                                "weight": "Bolder",
                                "color": risk_color,
                                "size": "Medium",
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.Execute",
                                "title": "✅ Approve",
                                "verb": "approve",
                                "data": {
                                    "action": "approve_action",
                                    "actionId": action.id,
                                },
                            },
                            {
                                "type": "Action.Execute",
                                "title": "❌ Reject",
                                "verb": "reject",
                                "data": {
                                    "action": "reject_action",
                                    "actionId": action.id,
                                },
                            },
                            {
                                "type": "Action.Execute",
                                "title": "🔍 View Details",
                                "verb": "view",
                                "data": {
                                    "action": "view_action",
                                    "actionId": action.id,
                                },
                            },
                        ],
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }

    def _build_status_card(
        self,
        action: Action,
        status: ActionStatus,
        user: str,
    ) -> dict[str, Any]:
        """Build an Adaptive Card for status update.

        Args:
            action: The action that was updated
            status: The new status
            user: The user who performed the action

        Returns:
            Adaptive Card dictionary
        """
        # Determine emoji and color based on status
        status_config = {
            ActionStatus.APPROVED: ("✅", "Good", "Approved"),
            ActionStatus.REJECTED: ("❌", "Warning", "Rejected"),
            ActionStatus.EXECUTED: ("🚀", "Good", "Executed"),
            ActionStatus.FAILED: ("💥", "Attention", "Failed"),
        }

        emoji, color, status_text = status_config.get(
            status,
            ("📋", "Default", status.value),
        )

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"{emoji} Action {status_text}",
                                "weight": "Bolder",
                                "size": "Large",
                                "color": color,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Action ID:", "value": action.id[:8]},
                                    {"title": "Project:", "value": action.project},
                                    {"title": "Command:", "value": action.command or "N/A"},
                                    {
                                        "title": "Status:",
                                        "value": status_text,
                                    },
                                    {
                                        "title": "By:",
                                        "value": user,
                                    },
                                    {
                                        "title": "At:",
                                        "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                                    },
                                ],
                            },
                        ],
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }


# Singleton instance
_teams_notifier: Optional[TeamsApprovalNotifier] = None


def get_teams_approval_notifier() -> TeamsApprovalNotifier:
    """Get or create the singleton TeamsApprovalNotifier instance."""
    global _teams_notifier

    if _teams_notifier is None:
        from app.config import settings

        # Check if Teams webhook is configured
        webhook_url = getattr(settings, "TEAMS_WEBHOOK_URL", None)
        disabled = not webhook_url

        _teams_notifier = TeamsApprovalNotifier(
            webhook_url=webhook_url,
            disabled=disabled,
        )

    return _teams_notifier


def reset_teams_approval_notifier():
    """Reset the singleton (for testing)."""
    global _teams_notifier
    _teams_notifier = None

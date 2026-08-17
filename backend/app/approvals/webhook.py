"""Webhook handler for Slack/Teams approval button interactions."""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException

from app.actions.engine import get_action_engine
from app.models.actions import ApproveActionRequest, RejectActionRequest
from app.approvals.slack import get_slack_approval_notifier

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)


@router.post("/webhook/slack")
async def slack_approval_webhook(request: Request) -> dict[str, Any]:
    """Handle Slack interactive button clicks for approval actions.

    This endpoint receives POST requests from Slack when users click
    Approve/Reject/View buttons on approval messages.
    """
    try:
        # Parse the request payload
        form_data = await request.form()
        payload_str = form_data.get("payload", "")

        if not payload_str:
            raise HTTPException(status_code=400, detail="Missing payload")

        payload = json.loads(payload_str)

        # Extract action details
        action_value = payload.get("actions", [{}])[0].get("value", "")
        action_id = action_value.split(":")[-1] if ":" in action_value else None

        if not action_id:
            raise HTTPException(status_code=400, detail="Invalid action ID")

        # Get user info
        user_id = payload.get("user", {}).get("id", "")
        user_name = payload.get("user", {}).get("name", user_id)

        # Process the action based on button clicked
        action_type = payload.get("actions", [{}])[0].get("action_id", "")

        engine = get_action_engine()
        slack_notifier = get_slack_approval_notifier()

        if action_type == "approve_action":
            # Approve the action
            result = await engine.approve_action(
                action_id=action_id,
                request=ApproveActionRequest(
                    approved_by=user_name,
                    comment=f"Approved via Slack by {user_name}",
                ),
            )

            # Send confirmation to Slack
            await slack_notifier.send_approval_status(
                action=result,
                status=result.status,
                user=user_name,
            )

            # Update the original message
            return {
                "response_type": "ephemeral",
                "text": f"✅ Action {action_id} has been approved by {user_name}",
            }

        elif action_type == "reject_action":
            # For reject, we need a reason - in real implementation,
            # we'd open a modal to collect the reason
            result = await engine.reject_action(
                action_id=action_id,
                request=RejectActionRequest(
                    rejected_by=user_name,
                    reason=f"Rejected via Slack by {user_name}",
                ),
            )

            # Send confirmation to Slack
            await slack_notifier.send_approval_status(
                action=result,
                status=result.status,
                user=user_name,
            )

            return {
                "response_type": "ephemeral",
                "text": f"❌ Action {action_id} has been rejected by {user_name}",
            }

        elif action_type == "view_action":
            # View action details
            action_data = engine.get_action(action_id)
            if not action_data:
                raise HTTPException(status_code=404, detail="Action not found")

            command = action_data.get("command", "")
            description = action_data.get("description", "")
            risk_level = action_data.get("risk_level", "unknown")

            return {
                "response_type": "ephemeral",
                "text": f"*Action Details:*\n"
                       f"• Command: `{command}`\n"
                       f"• Description: {description}\n"
                       f"• Risk Level: {risk_level}",
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {action_type}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Slack payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload format")
    except Exception as e:
        logger.error(f"Error processing Slack webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/teams")
async def teams_approval_webhook(request: Request) -> dict[str, Any]:
    """Handle Microsoft Teams approval button interactions.

    This endpoint receives POST requests from Teams when users click
    Approve/Reject buttons on adaptive cards.
    """
    # TODO: Implement Teams webhook handler
    # Teams uses a different format (Adaptive Cards) compared to Slack (Block Kit)
    logger.info("Received Teams webhook (not yet implemented)")
    return {"status": "not_implemented"}


@router.get("/health")
async def approval_webhook_health() -> dict:
    """Health check endpoint for approval webhook service."""
    return {
        "status": "healthy",
        "webhooks": {
            "slack": "enabled" if get_slack_approval_notifier().webhook_url else "disabled",
            "teams": "not_implemented",
        },
    }

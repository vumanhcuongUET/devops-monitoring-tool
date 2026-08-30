"""Webhook handler for Slack/Teams approval button interactions.

Security Features:
- Signature verification for Slack webhooks
- Timestamp validation to prevent replay attacks
- Source IP whitelist for webhook endpoints
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.approvals.slack import get_slack_approval_notifier
from app.config import settings

# Lazy import to avoid circular import with actions/engine
# from app.actions.engine import get_action_engine
from app.models.actions import ApproveActionRequest, RejectActionRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

# Security settings
SLACK_SIGNATURE_VERSION = "v0"
SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS = 60  # Reject requests older than 60 seconds


def verify_slack_signature(
    raw_body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
) -> bool:
    """Verify Slack webhook signature to prevent spoofing.

    Args:
        raw_body: Raw request body bytes
        timestamp: X-Slack-Request-Timestamp header value
        signature: X-Slack-Signature header value
        signing_secret: Slack app signing secret

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature is invalid or timestamp is too old
    """
    # Check timestamp to prevent replay attacks
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - request_time) > SIGNATURE_TIMESTAMP_TOLERANCE_SECONDS:
            logger.warning(f"Request timestamp too old: {timestamp}")
            raise HTTPException(
                status_code=401,
                detail="Request timestamp too old - possible replay attack"
            )
    except (ValueError, TypeError):
        logger.warning(f"Invalid timestamp format: {timestamp}")
        raise HTTPException(status_code=401, detail="Invalid timestamp format") from None

    # Calculate expected signature
    # Slack format: base64(hmac_sha256(signing_secret, base_version + ":" + timestamp + ":" + body))
    sig_basestring = f"{SLACK_SIGNATURE_VERSION}:{timestamp}:{raw_body.decode('utf-8', errors='replace')}"

    # Create HMAC
    digest = hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).digest()

    # Compare signatures securely
    expected_signature = f"{SLACK_SIGNATURE_VERSION}=" + digest.hex()

    if not hmac.compare_digest(expected_signature, signature):
        logger.warning(f"Signature mismatch: expected {expected_signature}, got {signature}")
        return False

    return True


def verify_teams_hmac_signature(
    raw_body: bytes,
    auth_header: str,
    key: str,
) -> bool:
    """Verify Teams webhook HMAC signature (S4 scheme).

    Format: hex(HMAC-SHA256(secret, body)) in the Authorization header as
    `sha256=<hex>`.

    Note: the legacy scheme keyed the HMAC with the webhook URL — the URL is
    not a secret, so anyone who knew it could forge valid signatures. This
    function is key-agnostic; the caller decides the key (secret first,
    legacy URL only behind the deprecation shim).

    Args:
        raw_body: Raw request body bytes
        auth_header: Authorization header value
        key: HMAC key (TEAMS_WEBHOOK_SECRET, or legacy webhook URL)

    Returns:
        True if signature is valid
    """
    digest = hmac.new(
        key.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(digest, auth_header.replace("sha256=", "", 1))


@router.post("/webhook/slack")
async def slack_approval_webhook(
    request: Request,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> dict[str, Any]:
    """Handle Slack interactive button clicks for approval actions.

    This endpoint receives POST requests from Slack when users click
    Approve/Reject/View buttons on approval messages.

    Security:
    - Verifies Slack webhook signature
    - Validates timestamp to prevent replay attacks
    - Checks against signing secret from config
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()

        # Verify signature (REQUIRED in production)
        if not settings.SLACK_SIGNING_SECRET:
            logger.error("SLACK_SIGNING_SECRET not configured - rejecting webhook request")
            raise HTTPException(
                status_code=500,
                detail="Webhook signature verification not configured - please set SLACK_SIGNING_SECRET"
            )

        if not verify_slack_signature(
            raw_body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.SLACK_SIGNING_SECRET,
        ):
            logger.warning(f"Invalid Slack signature from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Additional IP whitelist check if configured
        if settings.ALLOWED_WEBHOOK_IPS:
            client_ip = request.client.host if request.client else "unknown"
            if client_ip not in settings.ALLOWED_WEBHOOK_IPS:
                logger.warning(f"Webhook request from unauthorized IP: {client_ip}")
                raise HTTPException(status_code=403, detail="IP not allowed")
        # Parse the request payload. Slack sends application/x-www-form-urlencoded;
        # parse it directly (starlette's request.form() would require python-multipart).
        # raw_body was already read for signature verification above.
        payload_str = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="replace")).get("payload", [""])[0]

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

        # Lazy import to avoid circular import
        from app.actions.engine import get_action_engine
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
            action_data = await engine.get_action(action_id)
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
        raise HTTPException(status_code=400, detail="Invalid payload format") from e
    except HTTPException:
        # Re-raise HTTP exceptions with original status code
        raise
    except Exception as e:
        logger.error(f"Error processing Slack webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/webhook/teams")
async def teams_approval_webhook(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, Any]:
    """Handle Microsoft Teams approval button interactions.

    This endpoint receives POST requests from Teams when users click
    Approve/Reject buttons on adaptive cards.

    Security:
    - Verifies HMAC signature from Authorization header
    - Teams HMAC is calculated as: HMAC_SHA256(webhook_url, body)
    - FAILS HARD if signature verification is not configured in production

    Teams Adaptive Cards Format:
    - Uses Action.Submit actions for button interactions
    - Returns adaptive card updates for message modification
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()

        # Signature verification is REQUIRED in production. S4: the HMAC key is
        # TEAMS_WEBHOOK_SECRET (dedicated secret, not the webhook URL — a URL
        # is not a secret). The legacy URL-keyed scheme is accepted with a
        # deprecation warning for one release, then removed.
        legacy_key: str | None = None
        if settings.TEAMS_WEBHOOK_SECRET:
            hmac_key = settings.TEAMS_WEBHOOK_SECRET
        elif settings.TEAMS_WEBHOOK_URL:
            hmac_key = settings.TEAMS_WEBHOOK_URL
            legacy_key = settings.TEAMS_WEBHOOK_URL
        else:
            hmac_key = None

        if settings.ENVIRONMENT == "production" and not hmac_key:
            logger.error(
                "Teams webhook signature key not configured - rejecting Teams webhook request. "
                "Set TEAMS_WEBHOOK_SECRET (legacy TEAMS_WEBHOOK_URL keying deprecated)."
            )
            raise HTTPException(
                status_code=500,
                detail="Teams webhook signature verification not configured - please set TEAMS_WEBHOOK_SECRET"
            )

        if hmac_key:
            if not authorization:
                logger.error("Authorization header missing - rejecting Teams webhook request")
                raise HTTPException(
                    status_code=401,
                    detail="Authorization header is required for Teams webhook signature verification"
                )

            if not verify_teams_hmac_signature(raw_body, authorization, hmac_key):
                logger.warning(f"Invalid Teams signature from {request.client.host if request.client else 'unknown'}")
                raise HTTPException(status_code=401, detail="Invalid signature")
            if legacy_key:
                logger.warning(
                    "Teams webhook is using the deprecated TEAMS_WEBHOOK_URL-keyed HMAC scheme; "
                    "set TEAMS_WEBHOOK_SECRET before the shim is removed next release."
                )
        else:
            logger.warning(
                f"Teams webhook signature verification disabled (ENVIRONMENT={settings.ENVIRONMENT}). "
                "Set TEAMS_WEBHOOK_SECRET for production security."
            )

        # Parse Teams Adaptive Card payload
        payload = await request.json()

        # Extract action details from Teams adaptive card
        # Teams format: {"type": "invoke", "data": {"action": "approve", "actionId": "xxx"}}
        action_type = payload.get("data", {}).get("action", "")
        action_id = payload.get("data", {}).get("actionId", "")

        if not action_id:
            raise HTTPException(status_code=400, detail="Invalid action ID")

        # Get user info from Teams context
        user_data = payload.get("from", {})
        user_id = user_data.get("id", "")
        user_name = user_data.get("name", user_id)

        # Lazy import to avoid circular import
        from app.actions.engine import get_action_engine
        from app.approvals.teams import get_teams_approval_notifier
        engine = get_action_engine()
        teams_notifier = get_teams_approval_notifier()

        if action_type == "approve_action":
            # Approve the action
            result = await engine.approve_action(
                action_id=action_id,
                request=ApproveActionRequest(
                    approved_by=user_name,
                    comment=f"Approved via Teams by {user_name}",
                ),
            )

            # Send confirmation to Teams
            await teams_notifier.send_approval_status(
                action=result,
                status=result.status,
                user=user_name,
            )

            # Return adaptive card update
            return {
                "type": "invokeResponse",
                "value": {
                    "status": 200,
                    "body": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"✅ Action {action_id[:8]} has been approved by {user_name}",
                                "weight": "Bolder",
                                "color": "Good",
                                "size": "Medium",
                            }
                        ],
                    }
                },
            }

        elif action_type == "reject_action":
            # For reject, we'd normally collect reason via modal
            result = await engine.reject_action(
                action_id=action_id,
                request=RejectActionRequest(
                    rejected_by=user_name,
                    reason=f"Rejected via Teams by {user_name}",
                ),
            )

            # Send confirmation to Teams
            await teams_notifier.send_approval_status(
                action=result,
                status=result.status,
                user=user_name,
            )

            # Return adaptive card update
            return {
                "type": "invokeResponse",
                "value": {
                    "status": 200,
                    "body": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"❌ Action {action_id[:8]} has been rejected by {user_name}",
                                "weight": "Bolder",
                                "color": "Warning",
                                "size": "Medium",
                            }
                        ],
                    }
                },
            }

        elif action_type == "view_action":
            # View action details
            action_data = await engine.get_action(action_id)
            if not action_data:
                raise HTTPException(status_code=404, detail="Action not found")

            command = action_data.get("command", "")
            description = action_data.get("description", "")
            risk_level = action_data.get("risk_level", "unknown")

            # Return adaptive card with details
            return {
                "type": "invokeResponse",
                "value": {
                    "status": 200,
                    "body": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "Action Details",
                                "weight": "Bolder",
                                "size": "Large",
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Action ID:", "value": action_id[:8]},
                                    {"title": "Command:", "value": command},
                                    {"title": "Description:", "value": description},
                                    {"title": "Risk Level:", "value": risk_level},
                                ],
                            },
                        ],
                    }
                },
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {action_type}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Teams payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload format") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Teams webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/health")
async def approval_webhook_health():
    """Health check endpoint for approval webhook service."""
    from app.approvals.teams import get_teams_approval_notifier

    return {
        "status": "healthy",
        "webhooks": {
            "slack": "enabled" if get_slack_approval_notifier().webhook_url else "disabled",
            "teams": "enabled" if get_teams_approval_notifier().is_enabled() else "disabled",
        },
    }

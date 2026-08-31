"""Slack slash command `/devops` — read-only chatops (Phase A).

Slack requires the HTTP response within 3s, but our source queries can take
up to their client timeouts — so the handler ACKs immediately ("đang kiểm
tra…") and delivers the result to the `response_url` Slack provides, as a
background task.

Security:
- Signature verified with the SAME scheme as the approval webhook
  (`verify_slack_signature` — X-Slack-Signature + timestamp).
- `response_url` is attacker-controllable input, so it goes through the
  SSRF guard before anything is posted to it.
- Read-only by design: status/help. Mutating commands are Phase B and
  blocked on chat-user → local-user mapping.
"""

import asyncio
import logging
import urllib.parse

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from typing import Any

from app.approvals.chatops import HELP_TEXT, collect_system_status, format_status_text
from app.approvals.webhook import verify_slack_signature
from app.config import settings
from app.security import is_url_allowed

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

_ACK_TEXT = "⏳ Đang kiểm tra hệ thống…"


@router.post("/webhook/slack/command")
async def slack_command_webhook(
    request: Request,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature"),
) -> dict[str, str]:
    """Handle `/devops <subcommand>`; ACK fast, answer via response_url."""
    raw_body = await request.body()

    if not settings.SLACK_SIGNING_SECRET:
        logger.error("SLACK_SIGNING_SECRET not configured — rejecting slash command")
        raise HTTPException(
            status_code=500,
            detail="Slack signature verification not configured - "
            "please set SLACK_SIGNING_SECRET",
        )
    if not verify_slack_signature(
        raw_body, x_slack_request_timestamp, x_slack_signature,
        settings.SLACK_SIGNING_SECRET,
    ):
        logger.warning(
            "Invalid Slack command signature from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=401, detail="Invalid signature")

    form = urllib.parse.parse_qs(raw_body.decode("utf-8", errors="replace"))
    text = (form.get("text") or [""])[0].strip()
    response_url = (form.get("response_url") or [""])[0]
    user_name = (form.get("user_name") or ["unknown"])[0]

    subcommand = text.split()[0].lower() if text else "help"

    if subcommand not in ("status", "help"):
        await _deliver(response_url, HELP_TEXT)
        return {"response_type": "ephemeral", "text": _ACK_TEXT}

    if subcommand == "help":
        await _deliver(response_url, HELP_TEXT)
        return {"response_type": "ephemeral", "text": _ACK_TEXT}

    # status — query in the background, deliver to response_url
    asyncio.create_task(
        _status_task(request.app.state, response_url, user_name)
    )
    return {"response_type": "in_channel", "text": _ACK_TEXT}


async def _status_task(app_state: Any, response_url: str, user_name: str) -> None:
    """Run the read-only status query and post the formatted result."""
    try:
        status = await collect_system_status(app_state)
        text = format_status_text(status)
        text += f"\n_Yêu cầu bởi: {user_name}_"
        await _deliver(response_url, text)
    except Exception as e:
        logger.error("Slack /devops status task failed: %s", e, exc_info=True)
        try:
            await _deliver(response_url, "❌ Lỗi truy vấn trạng thái — xem log server.")
        except Exception:
            pass


async def _deliver(response_url: str, text: str) -> None:
    """POST the final answer to Slack's response_url (SSRF-guarded)."""
    if not response_url:
        logger.warning("No response_url — dropping Slack command answer")
        return
    if not is_url_allowed(response_url):
        logger.warning("Slack response_url blocked by SSRF protection: %s", response_url)
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                response_url,
                json={"response_type": "in_channel", "text": text},
            )
    except Exception as e:
        logger.error("Failed to deliver Slack command answer: %s", e)

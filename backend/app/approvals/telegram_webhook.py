"""Telegram webhook handler (Phase A chatops).

Security model — same shape as the Slack/Teams approval webhooks, whose
mount prefix (`/approvals/webhook/`) is exempt from bearer auth because the
platform signature IS the authentication:

- `X-Telegram-Bot-Api-Secret-Token` must equal TELEGRAM_WEBHOOK_SECRET
  (constant-time compare). Required whenever auth is enabled — an unkeyed
  Telegram webhook means unauthenticated chat access, so it fails hard.
- Chats are allowlisted via TELEGRAM_ALLOWED_CHAT_IDS; an empty list denies
  every chat (fail-closed).
- Read-only commands only: /status, /help. Approve/reject arrives as
  inline-keyboard callbacks gated by the Phase B mapping: the chat identity
  must map to a local platform user (CHATOPS_APPROVALS_ENABLED +
  TELEGRAM_APPROVER_MAP) that becomes both attribution and auth_user, so
  per-user RBAC narrowing and the self-approval ban apply exactly as on the
  web API.
"""

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.approvals.chatops import (
    HELP_TEXT,
    ChatopsApprovalDenied,
    collect_system_status,
    format_status_text,
    resolve_chatops_approver,
)
from app.approvals.telegram import get_telegram_notifier
from app.settings import settings
from app.models.actions import ApproveActionRequest, RejectActionRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

_CALLBACK_ACTIONS = {"approve", "reject", "view"}


def _verify_secret_token(header_value: str | None) -> None:
    """Fail hard when the webhook is unkeyed or the token mismatches."""
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if (settings.AUTH_ENABLED or settings.ENVIRONMENT == "production") and not secret:
        logger.error(
            "TELEGRAM_WEBHOOK_SECRET not configured — rejecting Telegram webhook. "
            "Set it to the secret-token used when registering the bot webhook."
        )
        raise HTTPException(
            status_code=500,
            detail="Telegram webhook signature verification not configured - "
            "please set TELEGRAM_WEBHOOK_SECRET",
        )
    if not header_value or not secret:
        raise HTTPException(status_code=401, detail="Missing secret token")
    # Constant-time compare — the token is the only authentication here.
    if not hmac.compare_digest(header_value, secret):
        logger.warning("Telegram secret-token mismatch (rejected)")
        raise HTTPException(status_code=401, detail="Invalid secret token")


def _verify_chat_allowed(chat_id: int | None) -> None:
    """Empty allowlist denies everyone; unlisted chats are rejected."""
    allowed = settings.TELEGRAM_ALLOWED_CHAT_IDS
    if not allowed:
        logger.warning("Telegram chat %s rejected: TELEGRAM_ALLOWED_CHAT_IDS is empty", chat_id)
        raise HTTPException(status_code=403, detail="No chats are allowlisted")
    if chat_id not in allowed:
        logger.warning("Telegram chat %s rejected: not allowlisted", chat_id)
        raise HTTPException(status_code=403, detail="Chat not allowlisted")


def _parse_callback(data: str) -> tuple[str, str]:
    """Split `approve:<action_id>` / `reject:<id>` / `view:<id>`.

    Raises ValueError for anything else — same value format as the Slack
    buttons, but Telegram input is not trusted to be well-formed.
    """
    if ":" not in data:
        raise ValueError("malformed callback data")
    verb, action_id = data.split(":", 1)
    verb = verb.strip().lower()
    action_id = action_id.strip()
    if verb not in _CALLBACK_ACTIONS or not action_id:
        raise ValueError(f"unsupported callback verb: {verb!r}")
    return verb, action_id


@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict[str, Any]:
    """Handle Telegram updates: inline-keyboard approvals + read commands."""
    _verify_secret_token(x_telegram_bot_api_secret_token)

    try:
        update = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    notifier = get_telegram_notifier()

    callback = update.get("callback_query")
    if callback:
        return await _handle_callback(request, callback, notifier)

    message = update.get("message")
    if message and isinstance(message.get("text"), str):
        return await _handle_command(request, message, notifier)

    # Edits, joins, non-message updates — nothing to do, ACK 200 so
    # Telegram doesn't retry.
    return {"ok": True}


async def _handle_callback(request: Request, callback: dict, notifier) -> dict[str, Any]:
    """Approve/Reject/View buttons — same engine path as Slack/Teams."""
    chat_id = (callback.get("message") or {}).get("chat", {}).get("id")
    _verify_chat_allowed(chat_id)

    data = callback.get("data", "")
    try:
        verb, action_id = _parse_callback(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid callback: {e}") from e

    sender = (callback.get("from") or {}).get("username") or str(
        (callback.get("from") or {}).get("id", "unknown")
    )

    # Lazy import to avoid circular import (mirrors webhook.py)
    from app.actions.engine import get_action_engine

    engine = get_action_engine()

    if verb in ("approve", "reject"):
        # Phase B gate: chat membership alone must not decide approvals. The
        # chat identity maps to a local platform user, which becomes both the
        # attribution and auth_user — per-user RBAC and the self-approval ban
        # in the engine only see canonical usernames.
        try:
            approver = resolve_chatops_approver(
                settings.TELEGRAM_APPROVER_MAP, sender, "telegram"
            )
        except ChatopsApprovalDenied as e:
            logger.warning("Telegram %s by %s denied: %s", verb, sender, e)
            await notifier.send_message(chat_id, f"⛔ {e}")
            return {"ok": True}

        try:
            if verb == "approve":
                result = await engine.approve_action(
                    action_id=action_id,
                    request=ApproveActionRequest(
                        approved_by=approver,
                        comment=f"Approved via Telegram by {sender}",
                    ),
                    auth_user=approver,
                )
            else:
                result = await engine.reject_action(
                    action_id=action_id,
                    request=RejectActionRequest(
                        rejected_by=approver,
                        reason=f"Rejected via Telegram by {sender}",
                    ),
                    auth_user=approver,
                )
        except PermissionError as e:
            # Engine-side RBAC narrowing / self-approval ban fired.
            logger.warning("Telegram %s of %s by %s refused: %s", verb, action_id, sender, e)
            await notifier.send_message(chat_id, f"⛔ Refused: {e}")
            return {"ok": True}
        except ValueError as e:
            # Unknown action id / not pending — surface to the chat, not a 500
            # that makes Telegram retry forever.
            await notifier.send_message(chat_id, f"⚠️ {e}")
            return {"ok": True}

        await notifier.send_approval_status(
            action=result, status=result.status, user=sender, chat_id=chat_id
        )
        return {"ok": True}

    # view — render the command from parsed_params, never the raw command
    # string: the raw text originates in LLM recommendations, so an injected
    # payload would be reflected verbatim into the chat.
    action_data = await engine.get_action(action_id)
    if not action_data:
        raise HTTPException(status_code=404, detail="Action not found")
    text = (
        f"*Action:* `{_command_display(action_data)}`\n"
        f"{action_data.get('description', '')}\n"
        f"Risk: {action_data.get('risk_level', 'unknown')}"
    )
    await notifier.send_message(chat_id, text)
    return {"ok": True}


def _command_display(action_data: dict) -> str:
    """Human-readable command from parsed params; sanitized raw as fallback.

    The fallback string is LLM-originated (see the view branch comment), so
    it is flattened and stripped of Markdown backticks before echoing into
    the chat — never reflected verbatim.
    """
    parsed = action_data.get("parsed_params")
    if isinstance(parsed, dict):
        action = parsed.get("action", "?")
        target = parsed.get("target") or parsed.get("resource") or ""
        params = {k: v for k, v in parsed.items() if k not in ("action", "target", "resource")}
        extras = " ".join(f"{k}={v}" for k, v in sorted(params.items()) if v not in (None, "", {}))
        return f"{action} {target} {extras}".strip()
    raw = str(action_data.get("command", ""))
    return raw.replace("`", "'").replace("\n", " ")[:200]


async def _handle_command(request: Request, message: dict, notifier) -> dict[str, Any]:
    """Read-only commands. No mutating command exists here by design."""
    chat_id = (message.get("chat") or {}).get("id")
    _verify_chat_allowed(chat_id)

    text = message["text"].strip()
    command = text.split()[0].split("@")[0].lower() if text else ""

    if command == "/status":
        status = await collect_system_status(request.app.state)
        await notifier.send_message(chat_id, format_status_text(status))
        return {"ok": True}

    await notifier.send_message(chat_id, HELP_TEXT)
    return {"ok": True}

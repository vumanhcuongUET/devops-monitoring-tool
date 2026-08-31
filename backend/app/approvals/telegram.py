"""Telegram approval integration (Phase A chatops).

Mirrors SlackApprovalNotifier/TeamsApprovalNotifier: send approval
interaction results back to the chat. Read-only queries live in
approvals/chatops.py; there is deliberately NO path from Telegram to a
mutating command — buttons only approve/reject actions that already went
through the engine's full gating (RBAC, approval, time window, audit).

Outbound calls go to the fixed api.telegram.org host with the bot token
(server-side setting) in the path — no user-controlled URL parts — and the
SSRF guard still runs on the final URL for consistency with the other
notifiers.
"""

import logging
from typing import Any

import httpx

from app.config import settings
from app.models.actions import Action, ActionStatus
from app.security import is_url_allowed

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    """Send Telegram messages (status updates, approval prompts)."""

    def __init__(self, bot_token: str | None = None, timeout: float = 10.0):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.timeout = timeout

    def is_enabled(self) -> bool:
        return bool(self.bot_token)

    def _api_url(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.bot_token}/{method}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        """Post one message; returns True on Telegram's ok:true."""
        if not self.is_enabled():
            logger.warning("Telegram notifier not configured (TELEGRAM_BOT_TOKEN empty)")
            return False

        url = self._api_url("sendMessage")
        if not is_url_allowed(url):
            logger.warning("Telegram API URL blocked by SSRF protection")
            return False

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200 and response.json().get("ok"):
                    return True
                logger.error(
                    "Telegram sendMessage failed: %s %s",
                    response.status_code, response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Error sending Telegram message: %s", e)
            return False

    async def send_approval_status(
        self,
        action: Action,
        status: ActionStatus,
        user: str | None = None,
        chat_id: int | None = None,
    ) -> bool:
        """Send a status update after an approve/reject/execute."""
        if chat_id is None:
            return False
        emoji = _STATUS_EMOJI.get(status, "ℹ️")
        text = f"{emoji} Action `{action.id}` → *{status.value}*"
        if user:
            text += f"\nBởi: {user}"
        return await self.send_message(chat_id, text)

    @staticmethod
    def approval_keyboard(action: Action) -> dict[str, Any]:
        """Inline keyboard with the SAME value format as the Slack buttons
        (`approve:<action_id>`), so the callback handler branches once."""
        return {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve:{action.id}"},
                {"text": "❌ Reject", "callback_data": f"reject:{action.id}"},
            ]],
        }


_STATUS_EMOJI = {
    ActionStatus.APPROVED: "✅",
    ActionStatus.REJECTED: "❌",
    ActionStatus.EXECUTED: "🚀",
    ActionStatus.FAILED: "💥",
    ActionStatus.PENDING: "⏳",
}


# Singleton instance
_telegram_notifier: TelegramNotifier | None = None


def get_telegram_notifier() -> TelegramNotifier:
    """Get or create the singleton TelegramNotifier instance."""
    global _telegram_notifier
    if _telegram_notifier is None:
        _telegram_notifier = TelegramNotifier()
    return _telegram_notifier

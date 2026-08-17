"""Approvals package for Phase 2: Slack approval integration."""

from app.approvals.store import get_approval_tracker, get_approval_history
from app.approvals.webhook import router as approvals_webhook_router
from app.approvals.slack import SlackApprovalClient

__all__ = [
    "get_approval_tracker",
    "get_approval_history",
    "approvals_webhook_router",
    "SlackApprovalClient",
]

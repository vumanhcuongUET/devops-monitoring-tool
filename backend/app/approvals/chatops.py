"""Channel-agnostic read-only system status for chat surfaces (Phase A).

Both the Telegram webhook and the Slack slash command answer the same
question — "hệ thống hiện tại thế nào?" — by reusing the overview
endpoint's health derivations verbatim instead of re-implementing them.
Everything here is READ-only: chat users get the same view the dashboard
gets, nothing more (Phase B — mutating commands from chat — is not built
until chat-user → local-user mapping exists).
"""

import asyncio
import logging
from typing import Any

from app.api.v1.overview import (
    _get_apm_health,
    _get_es_health,
    _get_infra_health,
    _get_k8s_health,
)

from app.settings import settings

logger = logging.getLogger(__name__)

_EMOJI = {
    "healthy": "🟢",
    "degraded": "🟡",
    "down": "🔴",
}


async def collect_system_status(app_state: Any) -> dict[str, Any]:
    """Gather the overview health snapshot; failures degrade to 'down'.

    Mirrors GET /api/v1/overview (same derivations, same per-source 5s
    timeouts via the clients themselves) without requiring an HTTP
    round-trip. Never raises: a broken source shows as down/red.
    """
    results = await asyncio.gather(
        _safe(_get_k8s_health(app_state.k8s_client)),
        _safe(_get_es_health(app_state.es_client)),
        _safe(_get_apm_health(app_state.apm_client)),
        _safe(_get_infra_health(app_state.prometheus_client, app_state.k8s_client)),
        return_exceptions=True,
    )

    systems = {}
    for name, result in zip(
        ("kubernetes", "elasticsearch", "apm", "infrastructure"),
        results,
        strict=True,
    ):
        if isinstance(result, Exception):
            logger.warning("chatops status: %s source failed: %s", name, result)
            systems[name] = {"status": "down", "error": str(result)}
        else:
            systems[name] = result.model_dump(mode="json")

    alert_state = getattr(app_state, "alert_state", None)
    firing = 0
    if isinstance(alert_state, dict):
        firing = sum(1 for s in alert_state.values() if s.get("status") == "firing")

    return {"systems": systems, "active_alerts": firing}


async def _safe(coro):
    """Await one source query, converting any failure into an exception
    value for asyncio.gather to collect."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001 — a dead source is data, not a crash
        return e


class ChatopsApprovalDenied(PermissionError):
    """Chat identity may not approve/reject (gate off, unmapped, or roleless)."""


def resolve_chatops_approver(
    mapping: dict[str, str], senders: str | list[str], channel: str
) -> str:
    """Map a chat identity to the local platform user allowed to decide.

    `senders` may be one identifier or several (Slack/Teams payloads carry
    both a stable user id and a changeable display name; the map may be keyed
    by either — the first identifier that matches wins).

    Fail-closed on every step: master gate off, unmapped sender, or a mapped
    username with no local role all deny. The returned username becomes BOTH
    the attribution (`approved_by`) and the authenticated identity
    (`auth_user`) — per-user RBAC narrowing and the self-approval ban in the
    action engine only work on that canonical identity, never on
    "telegram:<name>" labels.
    """
    if not settings.CHATOPS_APPROVALS_ENABLED:
        raise ChatopsApprovalDenied(
            f"{channel} approvals are disabled (set CHATOPS_APPROVALS_ENABLED)"
        )
    if isinstance(senders, str):
        senders = [senders]
    platform_user = None
    matched = None
    for sender in senders:
        if not sender:
            continue
        platform_user = mapping.get(sender) or mapping.get(sender.lower())
        if platform_user:
            matched = sender
            break
    if not platform_user:
        raise ChatopsApprovalDenied(
            f"{channel} user {senders[0]!r} is not mapped to a platform user"
        )
    from app.users import get_role

    if get_role(platform_user) is None:
        raise ChatopsApprovalDenied(
            f"mapped platform user {platform_user!r} has no local role"
        )
    del matched
    return platform_user


def format_status_text(status: dict[str, Any]) -> str:
    """Render the status snapshot as compact Vietnamese chat text."""
    systems = status.get("systems", {})
    lines = ["📊 *Trạng thái hệ thống*", ""]

    labels = {
        "kubernetes": "Kubernetes",
        "elasticsearch": "Elasticsearch",
        "apm": "APM",
        "infrastructure": "Infrastructure",
    }
    for key, label in labels.items():
        system = systems.get(key) or {}
        level = str(system.get("status", "down")).lower()
        emoji = _EMOJI.get(level, "🔴")
        detail = _system_detail(key, system)
        lines.append(f"{emoji} *{label}* — {level.upper()}{detail}")

    firing = status.get("active_alerts", 0)
    lines.append("")
    lines.append(f"🔥 Alerts đang firing: *{firing}*")
    return "\n".join(lines)


def _system_detail(key: str, system: dict[str, Any]) -> str:
    """One short parenthetical of the most useful number per system."""
    if key == "kubernetes":
        total = system.get("pods_total", "?")
        running = system.get("pods_running", "?")
        failed = system.get("pods_failed", 0)
        return f" (pods {running}/{total} running, {failed} failed)"
    if key == "elasticsearch":
        return f" ({system.get('error_count_1h', '?')} errors/1h, cluster {system.get('cluster_health', '?')})"
    if key == "apm":
        return f" (p95 {system.get('avg_latency_ms', '?')}ms, err {system.get('error_rate_percent', '?')}%)"
    if key == "infrastructure":
        return (
            f" (nodes {system.get('nodes_healthy', '?')}/{system.get('nodes_total', '?')}, "
            f"CPU {system.get('avg_cpu_percent', '?')}%)"
        )
    if system.get("error"):
        return f" ({system['error']})"
    return ""


HELP_TEXT = (
    "🤖 *DevOps Monitor — lệnh hỗ trợ*\n"
    "/status — trạng thái tổng hệ thống\n"
    "/help — danh sách lệnh\n\n"
    "Phê duyệt action: bấm nút ✅/❌ trên card phê duyệt."
)

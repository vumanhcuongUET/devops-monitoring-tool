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

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.slo import SloConfig
from app.services.slo_client import SloClient

logger = logging.getLogger(__name__)

LAST_REPORT_FILE = "data/slo_last_report.json"


class SloReporter:
    def __init__(self, slo_client: SloClient):
        self.slo_client = slo_client
        self._running = False

    async def start(self, app_state):
        self._running = True
        while self._running:
            if not settings.SLO_REPORT_ENABLED or not settings.SLACK_WEBHOOK_URL:
                await asyncio.sleep(3600)
                continue

            if self._should_report():
                try:
                    await self._send_daily_report(app_state)
                except Exception as e:
                    logger.error("SLO daily report failed: %s", e)

            await asyncio.sleep(600)  # check every 10 min

    def stop(self):
        self._running = False

    def _should_report(self) -> bool:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(settings, "SLO_REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
        now = datetime.now(tz)
        report_hour = getattr(settings, "SLO_REPORT_HOUR", 9)

        if now.hour != report_hour:
            return False

        last = self._load_last_report()
        if last and last.startswith(now.strftime("%Y-%m-%d")):
            return False

        return True

    async def _send_daily_report(self, app_state):
        from app.api.v1.slo import _load_configs

        configs_raw = _load_configs()
        configs = [SloConfig(**c) for c in configs_raw if c.get("enabled", True)]

        results = await asyncio.gather(
            *[self.slo_client.calculate_slo(c) for c in configs],
            return_exceptions=True,
        )
        slo_results = [r for r in results if not isinstance(r, Exception)]

        # Get slow APIs
        slow_apis_map: dict[str, list] = {}
        services = set(c.service_name for c in configs)
        for svc in services:
            svc_configs = [c for c in configs if c.service_name == svc]
            for cfg in svc_configs:
                try:
                    apis = await self.slo_client.get_slow_apis(svc, cfg)
                    failed = [a for a in apis if not a.slo_met]
                    if failed:
                        slow_apis_map.setdefault(svc, []).extend(
                            [a.model_dump() for a in failed[:5]]
                        )
                except Exception:
                    pass

        message = self._format_slack_message(slo_results, slow_apis_map)
        await self._post_to_slack(message)

        self._save_last_report()

    def _format_slack_message(self, results: list, slow_apis: dict) -> dict:
        from datetime import datetime as dt
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(settings, "SLO_REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
        date_str = dt.now(tz).strftime("%d/%m/%Y")

        healthy = sum(1 for r in results if r.status == "healthy")
        breached = sum(1 for r in results if r.status in ("critical", "breached"))
        warning = sum(1 for r in results if r.status == "warning")
        total = len(results)

        overall_color = "#36a64f" if breached == 0 else "#ff0000" if breached > total // 2 else "#ffaa00"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"SLO Daily Report — {date_str}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total SLOs:* {total}"},
                    {"type": "mrkdwn", "text": f"*Healthy:* {healthy}"},
                    {"type": "mrkdwn", "text": f"*Warning:* {warning}"},
                    {"type": "mrkdwn", "text": f"*Breached:* {breached}"},
                ],
            },
            {"type": "divider"},
        ]

        # Per-service SLO status
        services: dict[str, list] = {}
        for r in results:
            services.setdefault(r.service_name, []).append(r)

        for svc, svc_results in services.items():
            lines = []
            for r in svc_results:
                icon = {
                    "healthy": "green_circle",
                    "warning": "large_yellow_circle",
                    "critical": "red_circle",
                    "breached": "x",
                }.get(r.status, "white_circle")

                type_label = "Avail" if r.slo_type == "availability" else f"Lat<{r.target}%"
                lines.append(
                    f":{icon}: *{type_label} {r.window_days}d* — "
                    f"Target: `{r.target}%` | Current: `{r.current_value}%` | "
                    f"Budget: `{r.error_budget_remaining_percent}%`"
                )

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{svc}*\n" + "\n".join(lines)},
            })

        # Slow APIs section
        if slow_apis:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": ":warning: *Slow APIs (SLO not met)*"},
            })

            for svc, apis in slow_apis.items():
                api_lines = []
                for a in apis[:5]:
                    api_lines.append(
                        f"• `{a['transaction_name']}` — "
                        f"P95: {a['latency_p95']}ms | "
                        f"Avail: {a['availability_percent']}% | "
                        f"Errors: {a['error_count']}"
                    )
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{svc}:*\n" + "\n".join(api_lines)},
                })

        return {"attachments": [{"color": overall_color, "blocks": blocks}]}

    async def _post_to_slack(self, message: dict):
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(settings.SLACK_WEBHOOK_URL, json=message)
            if resp.status_code != 200:
                logger.error("Slack SLO report failed: %s %s", resp.status_code, resp.text)

    def _load_last_report(self) -> str | None:
        if os.path.exists(LAST_REPORT_FILE):
            with open(LAST_REPORT_FILE) as f:
                data = json.load(f)
                return data.get("last_report")
        return None

    def _save_last_report(self):
        os.makedirs(os.path.dirname(LAST_REPORT_FILE), exist_ok=True)
        with open(LAST_REPORT_FILE, "w") as f:
            json.dump({"last_report": datetime.now(timezone.utc).isoformat()}, f)

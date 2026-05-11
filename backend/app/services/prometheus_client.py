import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings


class PrometheusClient:
    def __init__(self):
        self.base_url = settings.PROMETHEUS_URL.rstrip("/")

    async def _query(self, expr: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/query",
                params={"query": expr},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("result", [])

    async def _query_range(self, expr: str, start: str, end: str, step: str = "60s") -> list[dict]:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/query_range",
                params={"query": expr, "start": start, "end": end, "step": step},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("result", [])

    async def get_node_metrics(self, minutes: int = 60) -> list[dict[str, Any]]:
        end_ts = datetime.now(timezone.utc).timestamp()
        start_ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp()

        queries = {
            "cpu": '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)) * 100',
            "memory": '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
            "disk": '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|nsfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|nsfs"}) * 100',
        }

        results: dict[str, list[dict]] = {}
        for key, expr in queries.items():
            try:
                results[key] = await asyncio.wait_for(
                    self._query_range(expr, str(start_ts), str(end_ts), "60s"),
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
            except Exception:
                results[key] = []

        # Merge by instance
        nodes: dict[str, dict] = {}
        for key, series_list in results.items():
            for series in series_list:
                instance = series["metric"].get("instance", "unknown")
                if instance not in nodes:
                    nodes[instance] = {"name": instance, "cpu_history": [], "memory_history": []}
                values = series.get("values", [])
                if key in ("cpu", "memory"):
                    history = [{"timestamp": datetime.fromtimestamp(float(v[0]), tz=timezone.utc).isoformat(), "value": float(v[1])} for v in values[-30:]]
                    nodes[instance][f"{key}_history"] = history
                    if values:
                        nodes[instance][f"{key}_percent"] = float(values[-1][1])
                elif key == "disk":
                    if values:
                        nodes[instance]["disk_percent"] = float(values[-1][1])

        return list(nodes.values())

    async def get_cpu_percent(self) -> float:
        try:
            results = await asyncio.wait_for(
                self._query('(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100'),
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            if results:
                return float(results[0]["value"][1])
        except Exception:
            pass
        return 0.0

    async def get_memory_percent(self) -> float:
        try:
            results = await asyncio.wait_for(
                self._query('(1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes)) * 100'),
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            if results:
                return float(results[0]["value"][1])
        except Exception:
            pass
        return 0.0

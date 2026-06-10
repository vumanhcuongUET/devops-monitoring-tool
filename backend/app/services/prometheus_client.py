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

    async def get_alerts(self, state: str | None = None) -> list[dict[str, Any]]:
        """
        Get alerts from Prometheus.

        Args:
            state: Filter by state ("firing", "pending", "inactive"). If None, returns all active (firing + pending).

        Returns:
            List of alert objects with labels, annotations, state, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                params = {}
                if state:
                    params["state"] = state
                else:
                    # Default to active alerts (firing + pending)
                    params["state"] = "active"

                resp = await client.get(
                    f"{self.base_url}/api/v1/alerts",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                alerts = data.get("data", {}).get("alerts", [])
                return alerts
        except Exception as e:
            print(f"Failed to fetch alerts: {e}")
            return []

    async def get_alerts_stats(self, namespaces: list[str] | None = None) -> dict[str, Any]:
        """
        Get alert statistics grouped by namespace.

        Args:
            namespaces: List of namespaces to include. If None, uses K8S_NAMESPACES from config.

        Returns:
            Dictionary with alert counts per namespace and summary.
        """
        alerts = await self.get_alerts()

        # Use configured namespaces if not specified
        if namespaces is None:
            namespaces = settings.K8S_NAMESPACES

        # Group alerts by namespace
        namespace_stats: dict[str, dict[str, Any]] = {ns: {
            "total": 0,
            "firing": 0,
            "pending": 0,
            "by_severity": {"critical": 0, "warning": 0, "info": 0},
            "alerts": [],
        } for ns in namespaces}

        for alert in alerts:
            # Extract namespace from labels
            alert_labels = alert.get("labels", {})
            namespace = alert_labels.get("namespace", "")

            # Skip if not in our target namespaces
            if namespace and namespace in namespace_stats:
                stats = namespace_stats[namespace]
                stats["total"] += 1

                # Count by state
                alert_state = alert.get("state", "")
                if alert_state == "firing":
                    stats["firing"] += 1
                elif alert_state == "pending":
                    stats["pending"] += 1

                # Count by severity (from labels)
                severity = alert_labels.get("severity", "warning").lower()
                if severity not in stats["by_severity"]:
                    stats["by_severity"][severity] = 0
                stats["by_severity"][severity] += 1

                # Store alert for top lists
                stats["alerts"].append({
                    "name": alert_labels.get("alertname", "Unknown"),
                    "severity": severity,
                    "state": alert_state,
                    "labels": alert_labels,
                    "annotations": alert.get("annotations", {}),
                })

        # Sort alerts by severity and limit
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        for ns_stats in namespace_stats.values():
            ns_stats["alerts"].sort(key=lambda a: (
                severity_order.get(a["severity"], 3),
                a["state"] != "firing",  # firing first
            ))

        return namespace_stats

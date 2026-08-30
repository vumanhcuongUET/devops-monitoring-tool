"""Shared Prometheus history fetcher for the capacity skills (Phase 13).

Turns range queries into plain float series (cluster-wide averages per
timestamp) — the shape the planner/growth-predictor analysis already
consumes. Missing series come back empty so the analysis reports
"insufficient data" instead of inventing numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

EXPRESSIONS = {
    "cpu": '(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance)) * 100',
    "memory": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
    "disk": '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|nsfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|nsfs"}) * 100',
}


async def fetch_metric_series(
    prom: Any,
    keys: list[str],
    days: int = 7,
    step: str = "1h",
) -> dict[str, list[float]]:
    """Return {key: [values...]} averaged across instances per timestamp."""

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(days, 1))
    series: dict[str, list[float]] = {}
    for key in keys:
        expr = EXPRESSIONS[key]
        try:
            rows = await prom.query_range(
                expr, str(start.timestamp()), str(end.timestamp()), step
            )
        except Exception:
            rows = []
        values: list[float] = []
        if rows:
            # average across instances per timestamp
            per_ts: dict[int, list[float]] = {}
            for row in rows:
                for ts, val in row.get("values", []):
                    try:
                        per_ts.setdefault(int(float(ts)), []).append(float(val))
                    except (TypeError, ValueError):
                        continue
            values = [
                round(sum(v) / len(v), 2) for _, v in sorted(per_ts.items())
            ]
        series[key] = values
    return series

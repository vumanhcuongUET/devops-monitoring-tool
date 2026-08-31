"""Phase A chatops: shared read-only status resolver."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.approvals.chatops import collect_system_status, format_status_text


def _app_state(es_ok=True, k8s_ok=True):
    """Fake app.state with the four monitoring clients."""

    async def es_error_count(minutes=60):
        if not es_ok:
            raise RuntimeError("es down")
        return 7

    async def es_cluster_health():
        return {"status": "green"}

    pods = [
        {"status": "Running"}, {"status": "Running"}, {"status": "Failed"},
    ]
    deployments = [{"available": 2, "replicas": 2}, {"available": 1, "replicas": 3}]

    async def list_pods():
        if not k8s_ok:
            raise RuntimeError("k8s down")
        return pods

    state = SimpleNamespace(
        es_client=SimpleNamespace(
            get_error_count=AsyncMock(side_effect=es_error_count),
            get_cluster_health=AsyncMock(side_effect=es_cluster_health),
        ),
        k8s_client=SimpleNamespace(
            list_pods=AsyncMock(side_effect=list_pods),
            list_deployments=AsyncMock(return_value=deployments),
            list_nodes=AsyncMock(return_value=[{"status": "Ready"}]),
        ),
        prometheus_client=SimpleNamespace(
            get_cpu_percent=AsyncMock(return_value=42.0),
            get_memory_percent=AsyncMock(return_value=55.0),
        ),
        apm_client=SimpleNamespace(
            get_summary=AsyncMock(return_value={
                "latency_p50": 120.0,
                "latency_p95": 450.0,
                "error_rate_percent": 0.4,
                "throughput": 600.0,
            }),
        ),
        alert_state={"a": {"status": "firing"}, "b": {"status": "ok"}},
    )
    return state


@pytest.mark.unit
class TestCollectSystemStatus:
    async def test_all_sources_present(self):
        status = await collect_system_status(_app_state())

        assert status["active_alerts"] == 1
        k8s = status["systems"]["kubernetes"]
        assert k8s["pods_total"] == 3
        assert k8s["pods_failed"] == 1
        assert status["systems"]["elasticsearch"]["error_count_1h"] == 7

    async def test_dead_source_degrades_to_down_not_crash(self):
        status = await collect_system_status(_app_state(es_ok=False))

        es = status["systems"]["elasticsearch"]
        assert es["status"] == "down"
        assert "es down" in es["error"]
        # other sources unaffected
        assert status["systems"]["kubernetes"]["pods_total"] == 3


@pytest.mark.unit
class TestFormatStatusText:
    async def test_contains_levels_and_firing_count(self):
        status = await collect_system_status(_app_state())

        text = format_status_text(status)

        assert "Trạng thái hệ thống" in text
        # 1 failed pod → DOWN per the overview derivation
        assert "*Kubernetes* — DOWN" in text
        assert "1 failed" in text
        assert "firing: *1*" in text

    async def test_down_source_shows_red(self):
        status = await collect_system_status(_app_state(es_ok=False))

        text = format_status_text(status)

        assert "🔴 *Elasticsearch* — DOWN" in text

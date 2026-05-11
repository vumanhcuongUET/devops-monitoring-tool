import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.models.common import HealthStatus
from app.models.overview import (
    KubernetesHealth,
    ElasticsearchHealth,
    ApmHealth,
    InfrastructureHealth,
    OverviewResponse,
)

router = APIRouter(tags=["overview"])


@router.get("/overview")
async def get_overview(request: Request):
    es = request.app.state.es_client
    prom = request.app.state.prometheus_client
    k8s = request.app.state.k8s_client
    apm = request.app.state.apm_client

    results = await asyncio.gather(
        _get_k8s_health(k8s),
        _get_es_health(es),
        _get_apm_health(apm),
        _get_infra_health(prom, k8s),
        return_exceptions=True,
    )

    k8s_health = results[0] if not isinstance(results[0], Exception) else KubernetesHealth(status=HealthStatus.DOWN)
    es_health = results[1] if not isinstance(results[1], Exception) else ElasticsearchHealth(status=HealthStatus.DOWN)
    apm_health = results[2] if not isinstance(results[2], Exception) else ApmHealth(status=HealthStatus.DOWN)
    infra_health = results[3] if not isinstance(results[3], Exception) else InfrastructureHealth(status=HealthStatus.DOWN)

    active_alerts = request.app.state.alert_state if hasattr(request.app.state, 'alert_state') else {}

    return OverviewResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        systems={
            "kubernetes": k8s_health,
            "elasticsearch": es_health,
            "apm": apm_health,
            "infrastructure": infra_health,
        },
        active_alerts=sum(1 for s in active_alerts.values() if s.get("status") == "firing") if isinstance(active_alerts, dict) else 0,
        recent_alerts=[],
    )


async def _get_k8s_health(k8s) -> KubernetesHealth:
    pods = await k8s.list_pods()
    deployments = await k8s.list_deployments()

    running = sum(1 for p in pods if p["status"] == "Running")
    pending = sum(1 for p in pods if p["status"] == "Pending")
    failed = sum(1 for p in pods if p["status"] in ("Failed", "Unknown"))
    available = sum(1 for d in deployments if d["available"] >= d["replicas"])

    if failed > 0:
        status = HealthStatus.DOWN
    elif pending > 0 or running < len(pods):
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return KubernetesHealth(
        status=status,
        pods_total=len(pods),
        pods_running=running,
        pods_pending=pending,
        pods_failed=failed,
        deployments_total=len(deployments),
        deployments_available=available,
    )


async def _get_es_health(es) -> ElasticsearchHealth:
    error_count = await es.get_error_count(minutes=60)
    try:
        health = await es.get_cluster_health()
        cluster_status = health.get("status", "unknown")
    except Exception:
        cluster_status = "unknown"

    if cluster_status == "red" or error_count > 100:
        status = HealthStatus.DOWN
    elif cluster_status == "yellow" or error_count > 20:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return ElasticsearchHealth(
        status=status,
        error_count_1h=error_count,
        cluster_health=cluster_status,
    )


async def _get_apm_health(apm) -> ApmHealth:
    summary = await apm.get_summary()
    error_rate = summary["error_rate_percent"]
    avg_latency = summary["latency_p95"]

    if error_rate > 5 or avg_latency > 2000:
        status = HealthStatus.DOWN
    elif error_rate > 1 or avg_latency > 500:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return ApmHealth(
        status=status,
        avg_latency_ms=summary["latency_p50"],
        error_rate_percent=error_rate,
        transactions_per_minute=round(summary["throughput"] / 60, 1),
    )


async def _get_infra_health(prom, k8s) -> InfrastructureHealth:
    nodes = await k8s.list_nodes()
    cpu = await prom.get_cpu_percent()
    memory = await prom.get_memory_percent()

    total = len(nodes)
    healthy = sum(1 for n in nodes if n["status"] == "Ready")

    if total == 0 or healthy == 0 or cpu > 90 or memory > 90:
        status = HealthStatus.DOWN
    elif healthy < total or cpu > 80 or memory > 80:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return InfrastructureHealth(
        status=status,
        nodes_total=total,
        nodes_healthy=healthy,
        avg_cpu_percent=round(cpu, 1),
        avg_memory_percent=round(memory, 1),
    )

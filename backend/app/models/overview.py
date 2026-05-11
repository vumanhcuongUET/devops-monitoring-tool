from pydantic import BaseModel

from app.models.common import HealthStatus


class KubernetesHealth(BaseModel):
    status: HealthStatus
    pods_total: int = 0
    pods_running: int = 0
    pods_pending: int = 0
    pods_failed: int = 0
    deployments_total: int = 0
    deployments_available: int = 0


class ElasticsearchHealth(BaseModel):
    status: HealthStatus
    error_count_1h: int = 0
    cluster_health: str = "unknown"


class ApmHealth(BaseModel):
    status: HealthStatus
    avg_latency_ms: float = 0
    error_rate_percent: float = 0
    transactions_per_minute: float = 0


class InfrastructureHealth(BaseModel):
    status: HealthStatus
    nodes_total: int = 0
    nodes_healthy: int = 0
    avg_cpu_percent: float = 0
    avg_memory_percent: float = 0


class OverviewResponse(BaseModel):
    timestamp: str
    systems: dict[str, KubernetesHealth | ElasticsearchHealth | ApmHealth | InfrastructureHealth]
    active_alerts: int = 0
    recent_alerts: list[dict] = []

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_prometheus_client
from app.models.infrastructure import NodeMetrics
from app.services.prometheus_client import PrometheusClient

router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])


@router.get("/metrics", response_model=list[NodeMetrics])
async def get_metrics(
    start: str | None = Query(None),
    end: str | None = Query(None),
    prom: PrometheusClient = Depends(get_prometheus_client),
):
    return await prom.get_node_metrics()

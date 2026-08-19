"""Prometheus metrics endpoint for application monitoring."""

import logging
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
from starlette.responses import Response
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])

# Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)

active_connections = Gauge(
    "active_connections",
    "Number of active WebSocket connections"
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["model", "status"]
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["model"]
)

actions_total = Counter(
    "actions_total",
    "Total actions executed",
    ["status", "risk_level"]
)

alert_checks_total = Counter(
    "alert_checks_total",
    "Total alert evaluation runs",
    ["status"]
)


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint for scraping."""
    return Response(generate_latest(REGISTRY), media_type="text/plain")


@router.get("/metrics/health")
async def metrics_health() -> dict:
    """Health check for metrics endpoint."""
    return {
        "status": "healthy",
        "metrics_count": len(REGISTRY.describe())
    }

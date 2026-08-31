"""Prometheus metrics endpoint for application monitoring."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

from app.auth import _is_valid_api_key, _is_valid_token
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


async def verify_metrics_auth(request: Request) -> None:
    """Verify authentication for metrics endpoint.

    Accepts either:
    - X-API-Key header with valid API key
    - Authorization: Bearer <token> header with valid token

    Raises HTTPException if authentication is required but not provided/invalid.
    """
    # Skip auth if disabled
    if not settings.AUTH_ENABLED:
        return

    # Check API key
    api_key = request.headers.get("X-API-Key")
    if api_key and _is_valid_api_key(api_key):
        return

    # Check Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _is_valid_token(token):
            return

    # No valid auth found
    raise HTTPException(
        status_code=401,
        detail="Authentication required for metrics endpoint. Provide valid X-API-Key or Authorization: Bearer <token> header."
    )


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


@router.get("/metrics", dependencies=[Depends(verify_metrics_auth)])
async def metrics() -> Response:
    """Prometheus metrics endpoint for scraping.

    Requires authentication via API key or bearer token.
    Configure Prometheus with authentication headers to scrape metrics.

    Example Prometheus configuration:
    ```yaml
    bearer_token: your-api-token
    ```
    or
    ```yaml
    headers:
      X-API-Key: your-api-key
    ```
    """
    return Response(generate_latest(REGISTRY), media_type="text/plain")


@router.get("/metrics/health")
async def metrics_health() -> dict:
    """Health check for metrics endpoint."""
    return {
        "status": "healthy",
        "metrics_count": len(REGISTRY.describe())
    }

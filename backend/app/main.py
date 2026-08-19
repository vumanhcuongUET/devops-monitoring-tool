import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager

import fastapi.responses
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.api.ws.live import router as ws_router, manager as ws_manager
from app.auth import api_key_auth, bearer_auth, _is_valid_api_key, _is_valid_token
from app.config import settings
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limit import RateLimitMiddleware
from app.utils.logging import SensitiveDataFilter

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce auth on all routes except whitelisted ones."""

    PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request, call_next):
        if not settings.AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        # Allow docs, health, and static assets
        if path in self.PUBLIC_PATHS or path.startswith("/docs/oauth2"):
            return await call_next(request)

        # Check API key
        api_key = request.headers.get("X-API-Key")
        if api_key and _is_valid_api_key(api_key):
            return await call_next(request)

        # Check Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if _is_valid_token(token):
                return await call_next(request)

        return fastapi.responses.JSONResponse(
            status_code=401, content={"detail": "Unauthorized"}
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply sensitive data filtering to all loggers
    root_logger = logging.getLogger()
    root_logger.addFilter(SensitiveDataFilter())

    # Import service clients (localized imports for clarity)
    from app.services.elasticsearch_client import ElasticsearchClient
    from app.services.prometheus_client import PrometheusClient
    from app.services.kubernetes_client import KubernetesClient
    from app.services.apm_client import ApmClient
    from app.services.slo_client import SloClient
    from app.alerting.engine import AlertEngine
    from app.alerting.slo_reporter import SloReporter
    # Phase 2: Action Engine
    from app.actions.engine import get_action_engine
    from app.approvals.store import get_approval_tracker

    app.state.es_client = ElasticsearchClient()
    app.state.prometheus_client = PrometheusClient()
    app.state.k8s_client = KubernetesClient()
    app.state.apm_client = ApmClient(es_client=app.state.es_client)
    app.state.slo_client = SloClient(es_client=app.state.es_client)

    alert_engine = AlertEngine()
    alert_engine.set_ws_manager(ws_manager)
    app.state.alert_engine = alert_engine
    app.state.alert_state = {}

    alert_task = asyncio.create_task(alert_engine.start(app.state))

    slo_reporter = SloReporter(slo_client=app.state.slo_client)
    slo_task = asyncio.create_task(slo_reporter.start(app.state))

    # Phase 2: Initialize Action Engine
    action_engine = get_action_engine()
    approval_tracker = get_approval_tracker()
    approval_tracker.set_ws_manager(ws_manager)
    app.state.action_engine = action_engine
    app.state.approval_tracker = approval_tracker
    logger.info("Phase 2: Action Engine initialized")

    if settings.AUTH_ENABLED and not settings.AUTH_SECRET:
        logger.warning("AUTH_ENABLED=true but AUTH_SECRET is empty — generate one!")
    if settings.AUTH_ENABLED and not settings.API_KEYS:
        logger.warning("AUTH_ENABLED=true but API_KEYS is empty — no one can authenticate!")

    yield

    alert_engine.stop()
    alert_task.cancel()
    slo_reporter.stop()
    slo_task.cancel()
    await app.state.es_client.close()


app = FastAPI(
    title="DevOps AI Agentics 2026",
    version="1.0.0",
    description="Unified DevOps monitoring platform with AI-powered observability copilot",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60, burst=20)
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["X-API-Key", "Authorization", "Content-Type"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/auth/token", include_in_schema=True)
async def create_auth_token():
    """Generate a new bearer token. Requires API key in header (enforced by middleware)."""
    from app.auth import create_token
    return {"access_token": create_token(), "token_type": "bearer"}

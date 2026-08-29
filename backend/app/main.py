import asyncio
import logging
import logging.config
from contextlib import asynccontextmanager

import fastapi.responses
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.api.ws.live import manager as ws_manager
from app.api.ws.live import router as ws_router
from app.auth import _is_valid_api_key, _is_valid_token
from app.config import settings
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limit import RateLimitMiddleware
from app.utils.logging import SensitiveDataFilter

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce auth on all routes except whitelisted ones."""

    PUBLIC_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

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

    # Phase 9 Sprint 4: Initialize OpenTelemetry tracing
    from app.telemetry import setup_telemetry, shutdown_telemetry
    setup_telemetry(app)
    logger.info("Phase 9 Sprint 4: OpenTelemetry tracing initialized")

    # Import service clients (localized imports for clarity)
    # Phase 2: Action Engine
    from app.actions.engine import get_action_engine
    from app.alerting.engine import AlertEngine
    from app.alerting.slo_reporter import SloReporter
    from app.api.v1 import config as config_api
    from app.api.v1 import optimization as optimization_api
    from app.approvals.store import get_approval_tracker

    # Phase 7 Sprint 4: Configuration Management
    from app.config import (
        AuditLogger,
        ConfigSecurity,
        ConfigValidator,
        ConfigVersionManager,
        GitOpsManager,
    )

    # Phase 7 Sprint 3: Performance Optimization
    from app.optimization import ConnectionPoolManager, QueryOptimizer, RateLimiter
    from app.services.apm_client import ApmClient
    from app.services.elasticsearch_client import ElasticsearchClient
    from app.services.kubernetes_client import KubernetesClient
    from app.services.prometheus_client import PrometheusClient
    from app.services.slo_client import SloClient

    app.state.es_client = ElasticsearchClient()
    app.state.prometheus_client = PrometheusClient()
    app.state.k8s_client = KubernetesClient()
    app.state.apm_client = ApmClient(es_client=app.state.es_client)
    app.state.slo_client = SloClient(es_client=app.state.es_client)

    # Phase 9: Use Redis for alert state if configured
    alert_engine = AlertEngine(use_redis=settings.ALERT_STATE_USE_REDIS)
    alert_engine.set_ws_manager(ws_manager)
    app.state.alert_engine = alert_engine
    app.state.alert_state = {}

    logger.info(f"Alert engine initialized with {'Redis' if settings.ALERT_STATE_USE_REDIS else 'file-based'} state storage")

    alert_task = asyncio.create_task(alert_engine.start(app.state))

    slo_reporter = SloReporter(slo_client=app.state.slo_client)
    slo_task = asyncio.create_task(slo_reporter.start(app.state))

    # Phase 2: Initialize Action Engine
    action_engine = get_action_engine()
    approval_tracker = get_approval_tracker(use_redis=settings.APPROVAL_STATE_USE_REDIS)
    approval_tracker.set_ws_manager(ws_manager)
    app.state.action_engine = action_engine
    app.state.approval_tracker = approval_tracker
    logger.info(f"Phase 2: Action Engine initialized with {'Redis' if settings.APPROVAL_STATE_USE_REDIS else 'file-based'} approval state")

    # Phase 7 Sprint 3: Initialize Performance Optimization
    query_optimizer = QueryOptimizer(
        es_client=app.state.es_client,
        prom_client=app.state.prometheus_client,
        k8s_client=app.state.k8s_client,
        l2_cache=None  # Will be integrated with cache module
    )

    pool_manager = ConnectionPoolManager()
    await pool_manager.start()

    rate_limiter = RateLimiter(default_rate=100.0, burst=20)

    # Store in app state and inject into API
    app.state.query_optimizer = query_optimizer
    app.state.pool_manager = pool_manager
    app.state.rate_limiter = rate_limiter

    optimization_api.set_optimization_instances(
        q_optimizer=query_optimizer,
        p_manager=pool_manager,
        r_limiter=rate_limiter
    )

    # Start rate limiter background replenishment
    replenish_task = asyncio.create_task(rate_limiter.start_background_replenish())

    # Store task in app state for proper cleanup
    app.state.replenish_task = replenish_task

    logger.info("Phase 7 Sprint 3: Performance Optimization initialized")

    # Phase 7 Sprint 4: Initialize Configuration Management
    import os
    config_storage_path = os.path.join(os.path.dirname(__file__), "..", "..", "configs")
    config_schema_path = os.path.join(config_storage_path, "global", "schemas")

    # Initialize config components
    config_validator = ConfigValidator(schema_path=config_schema_path)
    config_security = ConfigSecurity()

    # Initialize version manager
    config_version_manager = ConfigVersionManager(
        storage_path=config_storage_path,
        git_ops=None  # Will be initialized if needed
    )

    # Initialize audit logger
    config_audit_logger = AuditLogger(storage_path=config_storage_path)

    # Initialize GitOps manager (optional - requires Git repository)
    config_git_ops = None
    git_repo_path = os.getcwd()
    if os.path.exists(os.path.join(git_repo_path, ".git")):
        try:
            config_git_ops = GitOpsManager(repo_path=git_repo_path, auto_push=False)
            logger.info("GitOps manager initialized")
        except Exception as e:
            logger.warning(f"GitOps manager initialization failed: {e}")

    # Inject into API
    config_api.set_config_instances(
        validator=config_validator,
        version_manager=config_version_manager,
        git_ops=config_git_ops,
        audit_logger=config_audit_logger,
        security=config_security
    )

    # Store in app state
    app.state.config_validator = config_validator
    app.state.config_version_manager = config_version_manager
    app.state.config_audit_logger = config_audit_logger
    app.state.config_security = config_security
    app.state.config_git_ops = config_git_ops

    logger.info("Phase 7 Sprint 4: Configuration Management initialized")

    # Phase 10 Sprint 1: Optional PostgreSQL persistence layer
    app.state.db_enabled = False
    if settings.DATABASE_ENABLED:
        try:
            from app.database.session import (
                check_connection,
                close_engine,
                init_engine,
            )

            init_engine(
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_timeout=settings.DATABASE_POOL_TIMEOUT,
                pool_recycle=settings.DATABASE_POOL_RECYCLE,
            )
            if await check_connection():
                app.state.db_enabled = True
                logger.info("Phase 10: PostgreSQL persistence layer connected")
            else:
                await close_engine()
                logger.warning("Phase 10: PostgreSQL unreachable - running without database")
        except Exception as e:
            logger.warning(f"Phase 10: Database initialization failed: {e}")
    else:
        logger.info("Phase 10: Database disabled (set DATABASE_ENABLED=true to enable)")

    # Phase 10 Sprint 3: Multi-agent AI architecture
    from app.api.v1 import agents as agents_api

    try:
        from app.agents.model_selector import ModelSelector
        from app.agents.orchestrator import AgentOrchestrator

        agent_orchestrator = AgentOrchestrator(model_selector=ModelSelector())
        agents_api.set_agent_instances(agent_orchestrator)
        app.state.agent_orchestrator = agent_orchestrator
        from app.metrics import ORCHESTRATOR_UP
        ORCHESTRATOR_UP.set(1)
        logger.info(
            "Phase 10 Sprint 3: Multi-agent orchestrator initialized "
            f"({'API key set' if settings.ANTHROPIC_API_KEY else 'WARNING: ANTHROPIC_API_KEY missing'})"
        )
    except Exception as e:
        agents_api.set_agent_instances(None)
        from app.metrics import ORCHESTRATOR_UP
        ORCHESTRATOR_UP.set(0)
        logger.warning(f"Phase 10 Sprint 3: Agent orchestrator initialization failed: {e}")

    if settings.AUTH_ENABLED and not settings.AUTH_SECRET:
        logger.warning("AUTH_ENABLED=true but AUTH_SECRET is empty — generate one!")
    if settings.AUTH_ENABLED and not settings.API_KEYS:
        logger.warning("AUTH_ENABLED=true but API_KEYS is empty — no one can authenticate!")

    yield

    alert_engine.stop()
    alert_task.cancel()
    slo_reporter.stop()
    slo_task.cancel()

    # Cancel rate limiter replenish task if it exists
    if hasattr(app.state, 'replenish_task'):
        app.state.replenish_task.cancel()

    # Stop pool manager if it was initialized
    if hasattr(app.state, 'pool_manager'):
        await app.state.pool_manager.stop()

    # Close database engine if it was initialized
    if getattr(app.state, 'db_enabled', False):
        from app.database.session import close_engine
        await close_engine()

    # Close service clients
    await app.state.es_client.close()
    await app.state.prometheus_client.close()

    # Phase 9 Sprint 4: Shutdown telemetry
    shutdown_telemetry()
    logger.info("Phase 9 Sprint 4: Telemetry shutdown complete")


app = FastAPI(
    title="DevOps AI Agentics 2026",
    version="1.0.0",
    description="Unified DevOps monitoring platform with AI-powered observability copilot",
    lifespan=lifespan,
)

# Phase 8: Enable nonce-based CSP for enhanced security
# use_nonce=True enables per-request nonce generation for inline scripts
app.add_middleware(SecurityHeadersMiddleware, use_nonce=True)
# Phase 9: Support Redis-based rate limiting
app.add_middleware(RateLimitMiddleware, requests_per_minute=60, burst=20, use_redis=settings.RATE_LIMIT_USE_REDIS)
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
# Phase 12 debt: Prometheus agent metrics (review finding A1) — the
# agent-metrics.yaml alerts query these series. Auth-exempt via PUBLIC_PATHS;
# scrape target is cluster-internal.
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health():
    from app.api.v1.agents import _orchestrator as agent_orchestrator

    return {
        "status": "ok",
        "database": "enabled" if getattr(app.state, "db_enabled", False) else "disabled",
        "ai_agents": (
            f"{len(agent_orchestrator.agents)} available"
            if agent_orchestrator is not None
            else "unavailable"
        ),
    }


@app.post("/auth/token", include_in_schema=True)
async def create_auth_token():
    """Generate a new bearer token. Requires API key in header (enforced by middleware)."""
    from app.auth import create_token
    return {
        "access_token": create_token(),
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
    }


@app.post("/auth/refresh", include_in_schema=True)
async def refresh_auth_token(request: Request):
    """Exchange a still-valid bearer token for a fresh one (sliding session)."""
    from app.auth import _is_valid_token, create_token

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
    if settings.AUTH_ENABLED and not _is_valid_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {
        "access_token": create_token(),
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
    }

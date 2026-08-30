import asyncio
import logging
import logging.config
import time
from contextlib import asynccontextmanager

import fastapi.responses
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.api.ws.live import manager as ws_manager
from app.api.ws.live import router as ws_router
from app.auth import _is_valid_api_key, decode_token
from app.users import get_role
from app.config import settings
from app.middleware.security import SecurityHeadersMiddleware
from app.rate_limit import RateLimitMiddleware
from app.utils.logging import SensitiveDataFilter

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforce auth on all routes except whitelisted ones."""

    PUBLIC_PATHS = {"/health", "/health/ready", "/metrics", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/login"}

    # Chat-platform webhook paths exempt from bearer/api-key auth. The
    # platforms' own HMAC signature IS the authentication for these paths
    # (Slack fails hard without SLACK_SIGNING_SECRET; Teams fails hard in
    # production without TEAMS_WEBHOOK_SECRET — see approvals/webhook.py).
    WEBHOOK_AUTH_PATHS = "/api/v1/approvals/webhook/"

    async def dispatch(self, request, call_next):
        if not settings.AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        # Allow docs, health, and static assets
        if path in self.PUBLIC_PATHS or path.startswith("/docs/oauth2"):
            return await call_next(request)

        # Slack/Teams signature-verified webhooks: signature is the auth
        if path.startswith(self.WEBHOOK_AUTH_PATHS):
            return await call_next(request)

        # Check API key (service access — environment-keyed RBAC as before)
        api_key = request.headers.get("X-API-Key")
        if api_key and _is_valid_api_key(api_key):
            request.state.user = None  # service identity, no per-user RBAC
            return await call_next(request)

        # Check Bearer token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token(token)
            if payload is not None:
                # Phase 13 identity: user tokens carry a real username that
                # must still exist (revocation); "service" is the API-key-
                # minted automation subject with environment-keyed RBAC.
                sub = payload.get("sub", "service")
                if sub == "service":
                    request.state.user = None
                elif get_role(sub) is not None:
                    request.state.user = sub
                else:
                    logger.warning("Rejected token for revoked/unknown user %r", sub)
                    return fastapi.responses.JSONResponse(status_code=401, content={"detail": "User no longer exists"})
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
    from app.approvals.store import get_approval_tracker

    # Phase 7 Sprint 4: Configuration Management
    from app.config import (
        AuditLogger,
        ConfigSecurity,
        ConfigValidator,
        ConfigVersionManager,
        GitOpsManager,
    )

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

    # Phase 12 H1: when ALERT_ENGINE_LEADER_LOCK is on (multi-replica), every
    # pod starts run_as_leader; one pod wins the Redis lock and runs the
    # engine/SLO reporter, the others poll. Off (default) = today's behavior.
    if settings.ALERT_ENGINE_LEADER_LOCK:
        from app.alerting.leader import RedisLeaderLock, run_as_leader

        engine_lock = RedisLeaderLock("alert-engine")
        slo_lock = RedisLeaderLock("slo-reporter")
        alert_engine.leadership = engine_lock  # fencing before notifications
        alert_task = asyncio.create_task(
            run_as_leader(
                "alert-engine",
                lambda: alert_engine.start(app.state),
                engine_lock,
            )
        )
        slo_reporter = SloReporter(slo_client=app.state.slo_client)
        slo_reporter.leadership = slo_lock
        slo_task = asyncio.create_task(
            run_as_leader(
                "slo-reporter",
                lambda: slo_reporter.start(app.state),
                slo_lock,
            )
        )
        logger.info("Phase 12 H1: alert engine + SLO reporter under Redis leader lock")
    else:
        alert_task = asyncio.create_task(alert_engine.start(app.state))

        slo_reporter = SloReporter(slo_client=app.state.slo_client)
        slo_task = asyncio.create_task(slo_reporter.start(app.state))

    fanout_task = None
    if settings.WS_FANOUT_USE_REDIS:
        from app.api.ws.fanout import subscribe_loop

        fanout_task = asyncio.create_task(subscribe_loop(ws_manager.broadcast_local))
        logger.info("Phase 12 H1: WS fanout subscriber started (Redis pub/sub)")

    # Phase 2: Initialize Action Engine
    # Phase 12 B3: inject the real k8s client so impact estimation can use it.
    action_engine = get_action_engine(k8s_client=app.state.k8s_client)
    approval_tracker = get_approval_tracker(use_redis=settings.APPROVAL_STATE_USE_REDIS)
    approval_tracker.set_ws_manager(ws_manager)
    app.state.action_engine = action_engine
    app.state.approval_tracker = approval_tracker
    logger.info(f"Phase 2: Action Engine initialized with {'Redis' if settings.APPROVAL_STATE_USE_REDIS else 'file-based'} approval state")

    # Phase 7 Sprint 4: Initialize Configuration Management.
    # Phase 14: paths come from settings (anchored to the backend root, not
    # CWD or __file__/../../.. which resolved to /configs inside the
    # container and crashed startup under a read-only root filesystem), and
    # the whole subsystem degrades gracefully like the DB block below — a
    # missing/unwritable config store must not kill the app.
    import os
    config_storage_path = settings.CONFIG_STORAGE_PATH
    config_schema_path = os.path.join(config_storage_path, "global", "schemas")

    try:
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
    except Exception as e:
        logger.warning(
            "Configuration management disabled (storage path %s unusable: %s) — "
            "set CONFIG_STORAGE_PATH to a writable, mounted directory",
            config_storage_path, e,
        )

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
    if fanout_task is not None:
        fanout_task.cancel()

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

# Phase 8: security headers + CSP (no nonce — frontend is a static build, no inline scripts)
app.add_middleware(SecurityHeadersMiddleware)
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
    from app.skills.registry import EXPECTED_SKILL_COUNT, get_skill_registry

    skills = get_skill_registry().list_skills()
    stubs = sum(1 for s in skills if not s.get("implemented", True))

    return {
        "status": "ok",
        "database": "enabled" if getattr(app.state, "db_enabled", False) else "disabled",
        "ai_agents": (
            f"{len(agent_orchestrator.agents)} available"
            if agent_orchestrator is not None
            else "unavailable"
        ),
        "skills": {
            "registered": len(skills),
            "expected": EXPECTED_SKILL_COUNT,
            "stubs": stubs,
        },
    }


# Phase 14 residual #2: short, parallel dependency pings — the kubelet calls
# this every 10s, so the budget must be tighter than the clients' own
# REQUEST_TIMEOUT_SECONDS (5s) and the probe's timeoutSeconds.
READINESS_TIMEOUT_SECONDS = 2.0


def _redis_configured() -> bool:
    """Redis matters for readiness only when some feature actually uses it."""
    return bool(
        settings.REDIS_URL
        or settings.ALERT_STATE_USE_REDIS
        or settings.APPROVAL_STATE_USE_REDIS
        or settings.RATE_LIMIT_USE_REDIS
        or settings.WS_FANOUT_USE_REDIS
        or settings.ALERT_ENGINE_LEADER_LOCK
    )


async def _probe(check) -> dict:
    """Run one dependency check under a short timeout.

    Reports the exception CLASS only (never str(e)) — messages can carry
    URLs/credentials from settings.
    """
    start = time.perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=READINESS_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return {"status": "down", "latency_ms": round((time.perf_counter() - start) * 1000), "error": "timeout"}
    except Exception as e:
        return {"status": "down", "latency_ms": round((time.perf_counter() - start) * 1000), "error": type(e).__name__}
    return {"status": "up", "latency_ms": round((time.perf_counter() - start) * 1000)}


async def _check_kubernetes(k8s) -> None:
    # `available` is the cheap sync flag (config loaded at init); list_nodes
    # then proves the API actually answers — it swallows its own errors and
    # returns [], and a live cluster always has >=1 node, so empty == down.
    if not getattr(k8s, "available", False):
        raise RuntimeError("kubernetes client not loaded")
    if not await k8s.list_nodes():
        raise RuntimeError("kubernetes api returned no nodes")


async def _check_redis() -> None:
    # Reuse the shared lazy singleton (same client the leader lock and WS
    # fanout use) — no new client class, no extra connection.
    from app.redis_client import get_redis

    await get_redis().ping()


@app.get("/health/ready")
async def health_ready():
    """Honest readiness: ping the live dependencies in parallel.

    Status policy (deliberate): 200 "ok" when every checked source is up;
    200 "degraded" when SOME are down; 503 "down" only when ALL non-skipped
    sources are down. A single flaky dependency must not flap the pod out of
    the Service (that trades partial traffic for zero traffic), but a backend
    cut off from everything it monitors has no business receiving requests.

    Sources report "skipped" when the client is absent from app.state
    (dependency not configured / lifespan not run) or, for Redis, when no
    feature is configured to use it — absent is not down. With zero checked
    sources the answer is "ok" (nothing contradicts readiness).

    /health stays as-is: liveness answers "is the process alive", this
    answers "can it do its job".
    """
    es = getattr(app.state, "es_client", None)
    prom = getattr(app.state, "prometheus_client", None)
    k8s = getattr(app.state, "k8s_client", None)

    # Prometheus's convenience getters swallow errors and return 0.0 — use
    # the public query(), which raises, so down really reads as down.
    checks: dict[str, object] = {}
    if es is not None:
        checks["elasticsearch"] = _probe(es.get_cluster_health)
    if prom is not None:
        checks["prometheus"] = _probe(lambda: prom.query("up"))
    if k8s is not None:
        checks["kubernetes"] = _probe(lambda: _check_kubernetes(k8s))
    redis_on = _redis_configured()
    if redis_on:
        checks["redis"] = _probe(_check_redis)

    keys = list(checks)
    results = await asyncio.gather(*(checks[k] for k in keys))
    sources = dict(zip(keys, results, strict=True))
    for name in ("elasticsearch", "prometheus", "kubernetes", "redis"):
        sources.setdefault(name, {"status": "skipped", "latency_ms": None})

    checked = {k: v for k, v in sources.items() if v["status"] != "skipped"}
    down = [k for k, v in checked.items() if v["status"] == "down"]
    if not checked:
        overall, status_code = "ok", 200
    elif len(down) == len(checked):
        overall, status_code = "down", 503
    elif down:
        overall, status_code = "degraded", 200
    else:
        overall, status_code = "ok", 200

    return fastapi.responses.JSONResponse(
        status_code=status_code,
        content={"status": overall, "sources": sources},
    )


@app.post("/api/v1/auth/token", include_in_schema=True)
async def create_auth_token():
    """Generate a new bearer token. Requires API key in header (enforced by middleware)."""
    from app.auth import create_token
    return {
        "access_token": create_token(),
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
    }


@app.post("/api/v1/auth/refresh", include_in_schema=True)
async def refresh_auth_token(request: Request):
    """Exchange a still-valid bearer token for a fresh one (sliding session).

    Phase 13: refreshed token keeps the SAME subject — user tokens stay user
    tokens, service tokens stay service tokens.
    """
    from app.auth import create_token, decode_token
    from app.users import get_role

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
    payload = decode_token(token)
    if settings.AUTH_ENABLED and payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if settings.AUTH_ENABLED:
        sub = payload.get("sub", "service")
        if sub != "service" and get_role(sub) is None:
            logger.warning("Token refresh for revoked/unknown user %r", sub)
            raise HTTPException(status_code=401, detail="User no longer exists")
    sub = payload.get("sub", "service") if payload else "service"
    return {
        "access_token": create_token(sub),
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
    }


@app.post("/api/v1/auth/login", include_in_schema=True)
async def login(request: Request):
    """Username/password login — mints a user token (sub=<username>).

    Phase 13 per-user identity: the token subject IS the authenticated
    user; middleware propagates it as request.state.user and per-user RBAC
    applies. Public path (login IS the authentication).
    """
    from app.auth import create_token
    from app.users import verify_login

    try:
        body = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from err
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    # scrypt burns real CPU — keep it off the event loop
    role = await asyncio.to_thread(verify_login, username, password)
    if role is None:
        logger.warning("Failed login for %r", username or "<empty>")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {
        "access_token": create_token(username),
        "token_type": "bearer",
        "expires_in": settings.AUTH_TOKEN_TTL_SECONDS,
        "role": role,
    }

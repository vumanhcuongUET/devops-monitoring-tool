import secrets
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://elasticsearch:9200"
    ELASTICSEARCH_USERNAME: str = ""
    ELASTICSEARCH_PASSWORD: str = ""
    ELASTICSEARCH_INDEX_PATTERN: str = "logs-*"

    # APM (queries via ES on apm-* indices)
    APM_INDEX_PATTERN: str = "apm-*"

    # Prometheus
    PROMETHEUS_URL: str = "http://prometheus:9090"

    # Kubernetes
    KUBECONFIG_PATH: str = ""
    K8S_NAMESPACES: list[str] = ["default"]

    # Internal Services (for dependency health checks and skills)
    # Format: {"service-name": "http://service:port"}
    INTERNAL_SERVICES: dict[str, str] = {
        "auth-service": "http://auth-service:8080",
        "user-service": "http://user-service:8080",
        "notification-service": "http://notification-service:8080",
        "postgres-primary": "http://postgres-primary:5432",
        "redis-cache": "http://redis-cache:6379",
    }

    # External API endpoints (for dependency health checks)
    EXTERNAL_ENDPOINTS: dict[str, str] = {
        "stripe": "https://api.stripe.com/v1",
    }

    # Alerting
    ALERT_CHECK_INTERVAL_SECONDS: int = 30
    SLACK_WEBHOOK_URL: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = ""
    ALERT_EMAIL_TO: list[str] = []
    ALERT_WEBHOOK_URL: str = ""

    # App
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    REQUEST_TIMEOUT_SECONDS: int = 5

    # Auth
    AUTH_ENABLED: bool = True
    AUTH_SECRET: str = ""  # HMAC signing key — MUST be set in production
    API_KEYS: list[str] = []  # Valid API keys for X-API-Key header
    AUTH_TOKEN_TTL_SECONDS: int = 900  # 15 min — frontend tokenManager refreshes at 30s before expiry
    ALLOWED_WEBHOOK_HOSTS: list[str] = []  # If empty, allow all (legacy); set to restrict
    ENVIRONMENT: str = "development"  # Environment name (development/staging/production)

    # AI / LLM
    ANTHROPIC_API_KEY: str = ""  # Claude API key for Triage Card generation
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"  # Default model (Sonnet 4)
    AI_MAX_TOKENS: int = 4096  # Max tokens for LLM response

    # Phase 6: AI Input Optimization

    # SLO Reporting
    SLO_REPORT_ENABLED: bool = True
    SLO_REPORT_HOUR: int = 9
    SLO_REPORT_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # Phase 2: Action Engine & Approval Workflow

    # Approval

    # Context Registry

    # Audit

    # Slack Approval
    SLACK_APPROVAL_WEBHOOK_URL: str = ""  # Incoming webhook for button actions
    SLACK_SIGNING_SECRET: str = ""  # Slack app signing secret for webhook verification
    ALLOWED_WEBHOOK_IPS: list[str] = []  # IP whitelist for webhooks (empty = allow all)

    # Teams Approval
    TEAMS_WEBHOOK_URL: str = ""  # Teams webhook URL for card delivery (no longer an HMAC key — Phase 13)
    TEAMS_WEBHOOK_SECRET: str = ""  # Dedicated HMAC secret for Teams webhook verification

    # Phase 12 Sprint 3: OPA enforcement (default off — evaluation API only).
    # When true and OPA is reachable, execute_action denies on OPA DENY.
    OPA_ENFORCE: bool = False

    # Approvals integrity (Phase 12 S6): allow the creator to approve their own action.
    # Default False everywhere; flip only in dev where the creator and approver are
    # the same operator anyway.
    ALLOW_SELF_APPROVAL: bool = False

    # Phase 9: Redis Configuration for Distributed State
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB_ALERTS: int = 0
    REDIS_DB_APPROVALS: int = 1
    REDIS_DB_RATE_LIMIT: int = 2
    REDIS_URL: str | None = None  # Alternative: full Redis URL
    ALERT_STATE_USE_REDIS: bool = False  # Use Redis for alert state (default: file-based)
    APPROVAL_STATE_USE_REDIS: bool = False  # Use Redis for approval state (default: file-based)
    RATE_LIMIT_USE_REDIS: bool = False  # Use Redis for rate limiting (default: in-memory)
    # Phase 15 P2-14: CIDRs allowed to set X-Forwarded-For/X-Real-IP (ingress,
    # nginx). Empty = trust nobody: forwarded headers are ignored and the
    # direct connection IP is the rate-limit bucket. MUST be set behind an
    # ingress, or every client shares the ingress's single bucket.
    RATE_LIMIT_TRUSTED_PROXIES: list[str] = []
    # Phase 12 H1: multi-replica safe background tasks + cross-pod WS events.
    # Both require Redis; leave off for single-replica deployments.
    ALERT_ENGINE_LEADER_LOCK: bool = False  # Elect one alert-engine/SLO-reporter leader via Redis
    WS_FANOUT_USE_REDIS: bool = False  # Fanout /ws/live broadcasts across replicas via Redis pub/sub

    # Phase 10: PostgreSQL Database Configuration
    DATABASE_ENABLED: bool = False  # Enable PostgreSQL persistence layer (default: off)
    DATABASE_URL: str | None = None  # Full PostgreSQL URL (alternative to individual settings)
    DATABASE_HOST: str = "postgres"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "devops_monitor"
    DATABASE_USER: str = "devops_monitor"
    DATABASE_PASSWORD: str = ""  # MUST be set in production
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600

    # Connection Pool Settings
    PROM_MAX_CONNECTIONS: int = 20
    K8S_MAX_CONNECTIONS: int = 10

    # Phase 14: canonical locations for file-backed state and the config
    # subsystem. Anchored to the source tree (not CWD — running uvicorn from
    # the repo root used to silently create a second, empty data/ tree) and
    # overridable for containers via env: DATA_DIR / CONFIG_STORAGE_PATH.
    # The config tree ships at the repo root; in containers it must be
    # mounted and pointed at explicitly (startup degrades gracefully if not).
    DATA_DIR: str = str(Path(__file__).resolve().parents[1] / "data")
    CONFIG_STORAGE_PATH: str = str(Path(__file__).resolve().parents[2] / "configs")
    # GitOps needs the real git checkout (history/remotes). Defaults to the
    # repo root — same anchor as CONFIG_STORAGE_PATH — because os.getcwd()
    # followed wherever uvicorn was launched from; in containers, point this
    # at the mounted clone (startup degrades gracefully if it has no .git).
    GITOPS_REPO_PATH: str = str(Path(__file__).resolve().parents[2])

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def validate_security_config(self):
        """Validate security-related configuration."""
        import logging

        logger = logging.getLogger(__name__)

        # Check AUTH_SECRET in production
        if self.ENVIRONMENT == "production" and self.AUTH_ENABLED:
            if not self.AUTH_SECRET:
                raise ValueError(
                    "AUTH_SECRET must be set in production. "
                    "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
                )

        # Check API_KEYS in production
        if self.ENVIRONMENT == "production" and self.AUTH_ENABLED:
            if not self.API_KEYS:
                raise ValueError(
                    "API_KEYS must be set in production. "
                    "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
                )

        # Warn about empty AUTH_SECRET in non-production
        if self.AUTH_ENABLED and not self.AUTH_SECRET:
            logger.warning(
                "AUTH_SECRET is empty. Generating a secure random secret for development. "
                "Set AUTH_SECRET in .env for persistence."
            )
            # Generate a cryptographically secure secret
            self.AUTH_SECRET = secrets.token_hex(32)

        # Warn about empty API_KEYS in development
        if self.AUTH_ENABLED and not self.API_KEYS:
            logger.warning(
                "API_KEYS is empty. API authentication will not work! "
                "Add at least one API key to .env: API_KEYS=['dev-key-123']"
            )

        return self


settings = Settings()

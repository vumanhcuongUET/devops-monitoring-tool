import secrets
from pydantic_settings import BaseSettings
from pydantic import model_validator


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
    POLL_INTERVAL_SECONDS: int = 10
    REQUEST_TIMEOUT_SECONDS: int = 5

    # Auth
    AUTH_ENABLED: bool = True
    AUTH_SECRET: str = ""  # HMAC signing key — MUST be set in production
    API_KEYS: list[str] = []  # Valid API keys for X-API-Key header
    AUTH_TOKEN_TTL_SECONDS: int = 86400  # 24h token lifetime
    ALLOWED_WEBHOOK_HOSTS: list[str] = []  # If empty, allow all (legacy); set to restrict
    ENVIRONMENT: str = "development"  # Environment name (development/staging/production)

    # AI / LLM
    ANTHROPIC_API_KEY: str = ""  # Claude API key for Triage Card generation
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"  # Default model (Sonnet 4)
    AI_MAX_TOKENS: int = 4096  # Max tokens for LLM response

    # Phase 6: AI Input Optimization
    OPTIMIZATION_ENABLED: bool = True  # Enable token optimization
    OPTIMIZATION_DEFAULT_BUDGET: int = 2000  # Default token budget
    OPTIMIZATION_FALLBACK_ON_ERROR: bool = True  # Fallback to baseline on error
    OPTIMIZATION_ANOMALY_CPU_HIGH: float = 80.0  # CPU threshold for anomaly
    OPTIMIZATION_ANOMALY_CPU_LOW: float = 20.0
    OPTIMIZATION_ANOMALY_MEMORY_HIGH: float = 85.0
    OPTIMIZATION_ANOMALY_DISK_HIGH: float = 90.0
    OPTIMIZATION_LOG_SAMPLING_CRITICAL: int = 5  # Critical log quota
    OPTIMIZATION_LOG_SAMPLING_ERROR: int = 10  # Error log quota
    OPTIMIZATION_LOG_SAMPLING_WARNING: int = 10  # Warning log quota
    OPTIMIZATION_LOG_SAMPLING_INFO: int = 5  # Info log quota
    OPTIMIZATION_MAX_RESULTS_PER_SOURCE: int = 20  # Max results per data source

    # SLO Reporting
    SLO_REPORT_ENABLED: bool = True
    SLO_REPORT_HOUR: int = 9
    SLO_REPORT_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # Phase 2: Action Engine & Approval Workflow
    ACTION_EXECUTION_ENABLED: bool = True
    ACTION_MAX_EXECUTION_TIME_SECONDS: int = 300

    # Approval
    APPROVAL_REQUIRED_FOR_ACTIONS: list[str] = ["kubectl_delete", "helm_upgrade"]
    AUTO_APPROVE_LOW_RISK: bool = False

    # Context Registry
    PROJECTS_CONFIG_PATH: str = "projects"

    # Audit
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_LOG_MAX_ENTRIES: int = 1000

    # Slack Approval
    SLACK_APPROVAL_WEBHOOK_URL: str = ""  # Incoming webhook for button actions
    SLACK_SIGNING_SECRET: str = ""  # Slack app signing secret for webhook verification
    ALLOWED_WEBHOOK_IPS: list[str] = []  # IP whitelist for webhooks (empty = allow all)

    # Teams Approval
    TEAMS_WEBHOOK_URL: str = ""  # Teams webhook URL for signature verification
    TEAMS_SIGNING_SECRET: str = ""  # Teams signing secret for HMAC verification

    # Phase 9: Redis Configuration for Distributed State
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB_ALERTS: int = 0
    REDIS_DB_APPROVALS: int = 1
    REDIS_DB_RATE_LIMIT: int = 2
    REDIS_DB_CACHE: int = 3
    REDIS_URL: str | None = None  # Alternative: full Redis URL
    ALERT_STATE_USE_REDIS: bool = False  # Use Redis for alert state (default: file-based)
    APPROVAL_STATE_USE_REDIS: bool = False  # Use Redis for approval state (default: file-based)
    RATE_LIMIT_USE_REDIS: bool = False  # Use Redis for rate limiting (default: in-memory)

    # Connection Pool Settings
    ES_MAX_CONNECTIONS: int = 20
    PROM_MAX_CONNECTIONS: int = 20
    K8S_MAX_CONNECTIONS: int = 10

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

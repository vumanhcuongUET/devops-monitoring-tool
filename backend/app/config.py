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
    AUTH_SECRET: str = ""  # HMAC signing key — must be set in production
    API_KEYS: list[str] = []  # Valid API keys for X-API-Key header
    AUTH_TOKEN_TTL_SECONDS: int = 86400  # 24h token lifetime
    ALLOWED_WEBHOOK_HOSTS: list[str] = []  # If empty, allow all (legacy); set to restrict

    # SLO Reporting
    SLO_REPORT_ENABLED: bool = True
    SLO_REPORT_HOUR: int = 9
    SLO_REPORT_TIMEZONE: str = "Asia/Ho_Chi_Minh"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

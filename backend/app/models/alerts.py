from pydantic import BaseModel

from app.models.common import AlertSeverity


class AlertRule(BaseModel):
    id: str = ""
    name: str = ""
    source: str = ""
    metric: str = ""
    condition: str = "gt"
    threshold: float = 0
    duration_seconds: int = 60
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    notify_slack: bool = True
    notify_email: bool = False
    notify_webhook: bool = False
    labels: dict[str, str] = {}


class AlertEvent(BaseModel):
    id: str = ""
    rule_id: str = ""
    rule_name: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    status: str = "firing"
    value: float = 0
    threshold: float = 0
    message: str = ""
    timestamp: str = ""

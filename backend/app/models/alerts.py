from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

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


class PrometheusAlertState(str, Enum):
    """Prometheus alert states from API."""
    FIRING = "firing"
    PENDING = "pending"
    INACTIVE = "inactive"


class NamespaceAlertStats(BaseModel):
    """Alert statistics for a single namespace."""
    namespace: str = Field(..., description="Kubernetes namespace")
    total_alerts: int = Field(default=0, description="Total number of alerts")
    firing: int = Field(default=0, description="Number of firing alerts")
    pending: int = Field(default=0, description="Number of pending alerts")
    by_severity: dict[str, int] = Field(default_factory=dict, description="Alert count by severity")

    # Top alerts
    top_alerts: list[dict] = Field(default_factory=list, description="Top alerts by severity")

    class Config:
        json_schema_extra = {
            "example": {
                "namespace": "meinvoice",
                "total_alerts": 15,
                "firing": 8,
                "pending": 2,
                "by_severity": {"critical": 2, "warning": 6, "info": 7},
                "top_alerts": [
                    {"alert": "HighErrorRate", "severity": "critical", "state": "firing"},
                    {"alert": "PodRestart", "severity": "warning", "state": "firing"},
                ],
            }
        }


class ClusterAlertStats(BaseModel):
    """Alert statistics for entire cluster (all namespaces)."""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    total_namespaces: int = Field(..., description="Number of namespaces with alerts")
    total_alerts: int = Field(default=0, description="Total alerts across all namespaces")
    total_firing: int = Field(default=0, description="Total firing alerts across all namespaces")
    namespaces: list[NamespaceAlertStats] = Field(default_factory=list, description="Per-namespace breakdown")

    # Summary
    top_namespaces: list[dict] = Field(default_factory=list, description="Namespaces with most alerts")


class AlertStatsRequest(BaseModel):
    """Request model for alert statistics query."""
    namespaces: list[str] = Field(default=[], description="Specific namespaces to query (empty = all configured)")
    include_pending: bool = Field(default=True, description="Include pending alerts")
    top_n: int = Field(default=5, description="Number of top alerts to return per namespace")
    severity_filter: Optional[list[AlertSeverity]] = Field(None, description="Filter by severity (null = all)")


from typing import Literal
from pydantic import BaseModel


class SloConfig(BaseModel):
    id: str = ""
    service_name: str
    slo_type: Literal["availability", "latency"]
    target: float  # e.g. 99.9
    latency_threshold_ms: float | None = None  # only for latency type
    window_days: int = 30  # 7 or 30
    enabled: bool = True


class SloResult(BaseModel):
    config_id: str
    service_name: str
    slo_type: str
    target: float
    current_value: float
    total_requests: int
    good_requests: int
    bad_requests: int
    error_budget_remaining_percent: float
    error_budget_total: int
    error_budget_consumed: int
    status: Literal["healthy", "warning", "critical", "breached"]
    window_days: int
    latency_p50: float | None = None
    latency_p95: float | None = None
    latency_p99: float | None = None


class SloApiDetail(BaseModel):
    transaction_name: str
    total_requests: int
    error_count: int
    availability_percent: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    slo_met: bool
    slo_type: str
    target: float


class SloDashboard(BaseModel):
    timestamp: str
    total_slos: int
    healthy_count: int
    warning_count: int
    breached_count: int
    avg_budget_remaining: float
    results: list[SloResult]

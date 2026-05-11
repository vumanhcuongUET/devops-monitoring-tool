from pydantic import BaseModel


class Transaction(BaseModel):
    name: str
    type: str = "request"
    result: str = "success"
    latency_p50: float = 0
    latency_p95: float = 0
    latency_p99: float = 0
    throughput: int = 0


class ApmError(BaseModel):
    grouping_key: str = ""
    message: str = ""
    type: str = ""
    count: int = 0
    last_seen: str = ""


class ApmSummary(BaseModel):
    latency_p50: float = 0
    latency_p95: float = 0
    latency_p99: float = 0
    error_rate_percent: float = 0
    throughput: int = 0

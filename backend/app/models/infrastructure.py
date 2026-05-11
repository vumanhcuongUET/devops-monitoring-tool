from pydantic import BaseModel


class MetricSeries(BaseModel):
    timestamp: str
    value: float


class NodeMetrics(BaseModel):
    name: str = ""
    cpu_percent: float = 0
    memory_percent: float = 0
    disk_percent: float = 0
    cpu_history: list[MetricSeries] = []
    memory_history: list[MetricSeries] = []

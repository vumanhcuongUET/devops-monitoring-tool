from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: str = ""
    level: str = ""
    service: str = ""
    message: str = ""
    metadata: dict | None = None


class LogsResponse(BaseModel):
    total: int = 0
    page: int = 1
    size: int = 50
    items: list[dict] = []

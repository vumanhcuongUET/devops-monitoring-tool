from fastapi import APIRouter, Depends, Query

from app.api.deps import get_es_client
from app.models.logs import LogsResponse
from app.security import sanitize_es_query, validate_identifier
from app.services.elasticsearch_client import ElasticsearchClient

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
async def get_logs(
    q: str = Query("*", max_length=1000),
    level: str | None = Query(None, max_length=32),
    service: str | None = Query(None, max_length=128),
    start: str | None = Query(None, max_length=32),
    end: str | None = Query(None, max_length=32),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    es: ElasticsearchClient = Depends(get_es_client),
) -> LogsResponse:
    q = sanitize_es_query(q)
    if level:
        level = validate_identifier(level, "level")
    if service:
        service = validate_identifier(service, "service")
    items, total = await es.search_logs(
        query=q, level=level, service=service,
        start=start, end=end, page=page, size=size,
    )
    return LogsResponse(total=total, page=page, size=size, items=items)

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from elasticsearch import AsyncElasticsearch

from app.config import settings

# Default _source projection for search_logs. Full documents can be huge
# (stack traces, kubernetes metadata, agent fields); every current caller
# only reads these five. Pass source_includes explicitly to widen.
DEFAULT_LOG_SOURCE_INCLUDES = ["message", "level", "service", "@timestamp", "log"]


class ElasticsearchClient:
    def __init__(self):
        kwargs: dict[str, Any] = {}
        if settings.ELASTICSEARCH_USERNAME:
            kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)

        # Phase 9: Add connection pooling
        # NOTE: no max_connections kwarg — es-py 8.x AsyncElasticsearch rejects it
        # (TypeError at init = startup crash; review finding N1, 2026-08-29).
        self.client = AsyncElasticsearch(
            settings.ELASTICSEARCH_URL,
            request_timeout=settings.REQUEST_TIMEOUT_SECONDS,
            max_retries=3,
            retry_on_timeout=True,
            http_compress=True,
            **kwargs,
        )

    async def close(self):
        await self.client.close()

    async def search_logs(
        self,
        query: str = "*",
        level: str | None = None,
        service: str | None = None,
        start: str | None = None,
        end: str | None = None,
        page: int = 1,
        size: int = 50,
        source_includes: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        must = []
        if query and query != "*":
            # Phase 12 Sprint 3: bound query breadth to log fields — a bare
            # query_string would otherwise scan every indexed field.
            must.append({
                "query_string": {
                    "query": query,
                    "default_field": "message",
                    "fields": ["message", "log", "service", "level"],
                }
            })
        if level:
            must.append({"term": {"level": level.upper()}})
        if service:
            must.append({"term": {"service": service}})

        time_range = {}
        if start:
            time_range["gte"] = start
        if end:
            time_range["lte"] = end
        if time_range:
            must.append({"range": {"@timestamp": time_range}})

        body: dict[str, Any] = {
            "query": {"bool": {"must": must}} if must else {"match_all": {}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": (page - 1) * size,
            "size": size,
            # Token optimization: project only the fields callers read
            # instead of shipping full _source docs to the LLM/API.
            "_source": source_includes
            if source_includes is not None
            else DEFAULT_LOG_SOURCE_INCLUDES,
        }

        resp = await asyncio.wait_for(
            self.client.search(index=settings.ELASTICSEARCH_INDEX_PATTERN, body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        hits = resp["hits"]["hits"]
        total = resp["hits"]["total"]["value"] if isinstance(resp["hits"]["total"], dict) else resp["hits"]["total"]
        return [h["_source"] for h in hits], total

    async def get_error_count(self, minutes: int = 60) -> int:
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"level": "ERROR"}},
                        {"range": {"@timestamp": {"gte": since}}},
                    ]
                }
            },
            "size": 0,
        }
        resp = await asyncio.wait_for(
            self.client.search(index=settings.ELASTICSEARCH_INDEX_PATTERN, body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        return resp["hits"]["total"]["value"] if isinstance(resp["hits"]["total"], dict) else resp["hits"]["total"]

    async def get_cluster_health(self) -> dict:
        return await asyncio.wait_for(
            self.client.cluster.health(),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

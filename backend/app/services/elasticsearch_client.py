import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from elasticsearch import AsyncElasticsearch

from app.config import settings


class ElasticsearchClient:
    def __init__(self):
        kwargs: dict[str, Any] = {}
        if settings.ELASTICSEARCH_USERNAME:
            kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
        self.client = AsyncElasticsearch(
            settings.ELASTICSEARCH_URL,
            request_timeout=settings.REQUEST_TIMEOUT_SECONDS,
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
    ) -> tuple[list[dict], int]:
        must = []
        if query and query != "*":
            must.append({"query_string": {"query": query}})
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

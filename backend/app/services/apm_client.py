import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.elasticsearch_client import ElasticsearchClient
from app.config import settings


class ApmClient:
    def __init__(self, es_client: ElasticsearchClient):
        self.es = es_client

    async def get_transactions(
        self,
        service: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        must: list[dict] = [{"term": {"processor.event": "transaction"}}]
        if service:
            must.append({"term": {"service.name": service}})
        if start or end:
            range_q: dict[str, str] = {}
            if start:
                range_q["gte"] = start
            if end:
                range_q["lte"] = end
            must.append({"range": {"@timestamp": range_q}})
        else:
            since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            must.append({"range": {"@timestamp": {"gte": since}}})

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "transactions": {
                    "terms": {"field": "transaction.name", "size": 50},
                    "aggs": {
                        "p50": {"percentiles": {"field": "transaction.duration.us", "percents": [50, 95, 99]}},
                        "throughput": {"value_count": {"field": "transaction.id"}},
                    },
                }
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=f"{settings.APM_INDEX_PATTERN}-transaction*", body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        results = []
        for bucket in resp.get("aggregations", {}).get("transactions", {}).get("buckets", []):
            percentiles = bucket.get("p50", {}).get("values", {})
            results.append({
                "name": bucket["key"],
                "type": "request",
                "result": "success",
                "latency_p50": _us_to_ms(percentiles.get("50.0", 0)),
                "latency_p95": _us_to_ms(percentiles.get("95.0", 0)),
                "latency_p99": _us_to_ms(percentiles.get("99.0", 0)),
                "throughput": bucket.get("throughput", {}).get("value", 0),
            })
        return results

    async def get_errors(
        self,
        service: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict[str, Any]]:
        must: list[dict] = [{"term": {"processor.event": "error"}}]
        if service:
            must.append({"term": {"service.name": service}})
        if start or end:
            range_q: dict[str, str] = {}
            if start:
                range_q["gte"] = start
            if end:
                range_q["lte"] = end
            must.append({"range": {"@timestamp": range_q}})
        else:
            since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            must.append({"range": {"@timestamp": {"gte": since}}})

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "errors": {
                    "terms": {"field": "error.grouping_key", "size": 50},
                    "aggs": {
                        "latest": {"top_hits": {"size": 1, "sort": [{"@timestamp": "desc"}]}},
                    },
                }
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=f"{settings.APM_INDEX_PATTERN}-error*", body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        results = []
        for bucket in resp.get("aggregations", {}).get("errors", {}).get("buckets", []):
            top_hit = bucket.get("latest", {}).get("hits", {}).get("hits", [])
            source = top_hit[0]["_source"] if top_hit else {}
            results.append({
                "grouping_key": bucket["key"],
                "message": source.get("error", {}).get("message", "Unknown"),
                "type": source.get("error", {}).get("type", "Unknown"),
                "count": bucket["doc_count"],
                "last_seen": source.get("@timestamp", ""),
            })
        return results

    async def get_summary(self, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        must: list[dict] = [{"term": {"processor.event": "transaction"}}]
        if start or end:
            range_q: dict[str, str] = {}
            if start:
                range_q["gte"] = start
            if end:
                range_q["lte"] = end
            must.append({"range": {"@timestamp": range_q}})
        else:
            since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            must.append({"range": {"@timestamp": {"gte": since}}})

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "latency": {"percentiles": {"field": "transaction.duration.us", "percents": [50, 95, 99]}},
                "total": {"value_count": {"field": "transaction.id"}},
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=f"{settings.APM_INDEX_PATTERN}-transaction*", body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        aggs = resp.get("aggregations", {})
        percentiles = aggs.get("latency", {}).get("values", {})
        total_transactions = aggs.get("total", {}).get("value", 0)

        # Error count
        error_must = must.copy()
        error_must[0] = {"term": {"processor.event": "error"}}
        error_body = {"size": 0, "query": {"bool": {"must": error_must}}}
        error_resp = await asyncio.wait_for(
            self.es.client.search(index=f"{settings.APM_INDEX_PATTERN}-error*", body=error_body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        total_errors = error_resp["hits"]["total"]["value"] if isinstance(error_resp["hits"]["total"], dict) else error_resp["hits"]["total"]

        error_rate = (total_errors / total_transactions * 100) if total_transactions > 0 else 0

        return {
            "latency_p50": _us_to_ms(percentiles.get("50.0", 0)),
            "latency_p95": _us_to_ms(percentiles.get("95.0", 0)),
            "latency_p99": _us_to_ms(percentiles.get("99.0", 0)),
            "error_rate_percent": round(error_rate, 2),
            "throughput": total_transactions,
        }


def _us_to_ms(us: float) -> float:
    return round(us / 1000, 2)

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.elasticsearch_client import ElasticsearchClient
from app.models.slo import SloConfig, SloResult, SloApiDetail
from app.config import settings


class SloClient:
    def __init__(self, es_client: ElasticsearchClient):
        self.es = es_client

    async def calculate_slo(self, config: SloConfig) -> SloResult:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=config.window_days)).isoformat()
        end = now.isoformat()
        index = f"{settings.APM_INDEX_PATTERN}-transaction*"

        if config.slo_type == "availability":
            return await self._calc_availability(config, index, start, end)
        else:
            return await self._calc_latency(config, index, start, end)

    async def _calc_availability(
        self, config: SloConfig, index: str, start: str, end: str
    ) -> SloResult:
        must: list[dict] = [
            {"term": {"processor.event": "transaction"}},
            {"range": {"@timestamp": {"gte": start, "lte": end}}},
        ]
        if config.service_name and config.service_name != "all":
            must.append({"term": {"service.name": config.service_name}})

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "total": {"value_count": {"field": "transaction.id"}},
                "errors": {
                    "filter": {"bool": {"should": [
                        {"term": {"transaction.result": "Error"}},
                        {"term": {"transaction.result": "HTTP 5xx"}},
                    ]}},
                    "aggs": {"count": {"value_count": {"field": "transaction.id"}}},
                },
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=index, body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        aggs = resp.get("aggregations", {})
        total = aggs.get("total", {}).get("value", 0)
        errors = aggs.get("errors", {}).get("doc_count", 0)

        good = total - errors
        current = (good / total * 100) if total > 0 else 100.0

        budget_total = max(0, int(total * (1 - config.target / 100)))
        budget_consumed = min(errors, budget_total)
        budget_remaining = max(0, (1 - budget_consumed / budget_total) * 100) if budget_total > 0 else 100.0

        return SloResult(
            config_id=config.id,
            service_name=config.service_name,
            slo_type="availability",
            target=config.target,
            current_value=round(current, 3),
            total_requests=total,
            good_requests=good,
            bad_requests=errors,
            error_budget_remaining_percent=round(budget_remaining, 1),
            error_budget_total=budget_total,
            error_budget_consumed=budget_consumed,
            status=_derive_status(config.target, current, budget_remaining),
            window_days=config.window_days,
        )

    async def _calc_latency(
        self, config: SloConfig, index: str, start: str, end: str
    ) -> SloResult:
        threshold_us = (config.latency_threshold_ms or 200) * 1000

        must: list[dict] = [
            {"term": {"processor.event": "transaction"}},
            {"range": {"@timestamp": {"gte": start, "lte": end}}},
        ]
        if config.service_name and config.service_name != "all":
            must.append({"term": {"service.name": config.service_name}})

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "total": {"value_count": {"field": "transaction.id"}},
                "fast_enough": {
                    "filter": {"range": {"transaction.duration.us": {"lte": threshold_us}}},
                    "aggs": {"count": {"value_count": {"field": "transaction.id"}}},
                },
                "latency": {"percentiles": {"field": "transaction.duration.us", "percents": [50, 95, 99]}},
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=index, body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        aggs = resp.get("aggregations", {})
        total = aggs.get("total", {}).get("value", 0)
        fast = aggs.get("fast_enough", {}).get("doc_count", 0)
        percentiles = aggs.get("latency", {}).get("values", {})

        slow = total - fast
        current = (fast / total * 100) if total > 0 else 100.0

        budget_total = max(0, int(total * (1 - config.target / 100)))
        budget_consumed = min(slow, budget_total)
        budget_remaining = max(0, (1 - budget_consumed / budget_total) * 100) if budget_total > 0 else 100.0

        return SloResult(
            config_id=config.id,
            service_name=config.service_name,
            slo_type="latency",
            target=config.target,
            current_value=round(current, 3),
            total_requests=total,
            good_requests=fast,
            bad_requests=slow,
            error_budget_remaining_percent=round(budget_remaining, 1),
            error_budget_total=budget_total,
            error_budget_consumed=budget_consumed,
            status=_derive_status(config.target, current, budget_remaining),
            window_days=config.window_days,
            latency_p50=_us_to_ms(percentiles.get("50.0", 0)),
            latency_p95=_us_to_ms(percentiles.get("95.0", 0)),
            latency_p99=_us_to_ms(percentiles.get("99.0", 0)),
        )

    async def get_slow_apis(
        self, service_name: str, config: SloConfig
    ) -> list[SloApiDetail]:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=config.window_days)).isoformat()
        end = now.isoformat()
        index = f"{settings.APM_INDEX_PATTERN}-transaction*"

        must: list[dict] = [
            {"term": {"processor.event": "transaction"}},
            {"term": {"service.name": service_name}},
            {"range": {"@timestamp": {"gte": start, "lte": end}}},
        ]

        body = {
            "size": 0,
            "query": {"bool": {"must": must}},
            "aggs": {
                "apis": {
                    "terms": {"field": "transaction.name", "size": 100},
                    "aggs": {
                        "total": {"value_count": {"field": "transaction.id"}},
                        "errors": {
                            "filter": {"bool": {"should": [
                                {"term": {"transaction.result": "Error"}},
                                {"term": {"transaction.result": "HTTP 5xx"}},
                            ]}},
                            "aggs": {"count": {"value_count": {"field": "transaction.id"}}},
                        },
                        "latency": {"percentiles": {"field": "transaction.duration.us", "percents": [50, 95, 99]}},
                    },
                }
            },
        }

        resp = await asyncio.wait_for(
            self.es.client.search(index=index, body=body),
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

        results: list[SloApiDetail] = []
        for bucket in resp.get("aggregations", {}).get("apis", {}).get("buckets", []):
            total = bucket.get("total", {}).get("value", 0)
            errors = bucket.get("errors", {}).get("doc_count", 0)
            percentiles = bucket.get("latency", {}).get("values", {})
            p95 = _us_to_ms(percentiles.get("95.0", 0))
            availability = ((total - errors) / total * 100) if total > 0 else 100.0

            if config.slo_type == "availability":
                slo_met = availability >= config.target
            else:
                slo_met = p95 <= (config.latency_threshold_ms or 200)

            results.append(SloApiDetail(
                transaction_name=bucket["key"],
                total_requests=total,
                error_count=errors,
                availability_percent=round(availability, 2),
                latency_p50=_us_to_ms(percentiles.get("50.0", 0)),
                latency_p95=p95,
                latency_p99=_us_to_ms(percentiles.get("99.0", 0)),
                slo_met=slo_met,
                slo_type=config.slo_type,
                target=config.target,
            ))

        return sorted(results, key=lambda x: x.slo_met)


def _derive_status(target: float, current: float, budget_remaining: float) -> str:
    if current < target:
        return "breached"
    if budget_remaining < 20:
        return "critical"
    if budget_remaining < 50:
        return "warning"
    return "healthy"


def _us_to_ms(us: float) -> float:
    return round(us / 1000, 2)

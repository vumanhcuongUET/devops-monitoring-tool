import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.slo import SloConfig, SloResult, SloApiDetail, SloDashboard
from app.security import validate_identifier
from app.services.slo_client import SloClient
from app.services.elasticsearch_client import ElasticsearchClient
from app.api.deps import get_es_client

router = APIRouter(prefix="/slo", tags=["slo"])

CONFIGS_FILE = "data/slo_configs.json"
DEFAULT_CONFIGS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "alerting", "default_slo_configs.yaml")


def _load_configs() -> list[dict]:
    if os.path.exists(CONFIGS_FILE):
        with open(CONFIGS_FILE) as f:
            return json.load(f)
    return _load_defaults()


def _load_defaults() -> list[dict]:
    import yaml
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "alerting", "default_slo_configs.yaml")
    if not os.path.exists(yaml_path):
        return []
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    configs = []
    for i, c in enumerate(data.get("slo_configs", [])):
        c.setdefault("id", f"default-{i}")
        configs.append(c)
    return configs


def _save_configs(configs: list[dict]):
    os.makedirs(os.path.dirname(CONFIGS_FILE), exist_ok=True)
    with open(CONFIGS_FILE, "w") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)


def _get_slo_client(request: Request) -> SloClient:
    return request.app.state.slo_client


@router.get("/configs", response_model=list[SloConfig])
async def list_configs():
    return _load_configs()


@router.post("/configs", response_model=SloConfig, status_code=201)
async def create_config(config: SloConfig):
    configs = _load_configs()
    config.id = str(uuid.uuid4())
    configs.append(config.model_dump())
    _save_configs(configs)
    return config


@router.put("/configs/{config_id}", response_model=SloConfig)
async def update_config(config_id: str, config_update: SloConfig):
    configs = _load_configs()
    for i, c in enumerate(configs):
        if c["id"] == config_id:
            config_update.id = config_id
            configs[i] = config_update.model_dump()
            _save_configs(configs)
            return config_update
    raise HTTPException(status_code=404, detail="SLO config not found")


@router.delete("/configs/{config_id}", status_code=204)
async def delete_config(config_id: str):
    configs = _load_configs()
    configs = [c for c in configs if c["id"] != config_id]
    _save_configs(configs)


@router.get("/dashboard", response_model=SloDashboard)
async def get_dashboard(
    window_days: int | None = Query(None, ge=1, le=365),
    slo: SloClient = Depends(_get_slo_client),
):
    configs = [SloConfig(**c) for c in _load_configs() if c.get("enabled", True)]
    if window_days:
        configs = [c for c in configs if c.window_days == window_days]

    results = await asyncio.gather(
        *[slo.calculate_slo(c) for c in configs],
        return_exceptions=True,
    )

    slo_results: list[SloResult] = []
    for r in results:
        if isinstance(r, SloResult):
            slo_results.append(r)

    healthy = sum(1 for r in slo_results if r.status == "healthy")
    warning = sum(1 for r in slo_results if r.status == "warning")
    breached = sum(1 for r in slo_results if r.status in ("critical", "breached"))
    avg_budget = (
        sum(r.error_budget_remaining_percent for r in slo_results) / len(slo_results)
        if slo_results else 100.0
    )

    return SloDashboard(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_slos=len(slo_results),
        healthy_count=healthy,
        warning_count=warning,
        breached_count=breached,
        avg_budget_remaining=round(avg_budget, 1),
        results=slo_results,
    )


@router.get("/service/{service_name}", response_model=list[SloResult])
async def get_service_slo(
    service_name: str,
    slo: SloClient = Depends(_get_slo_client),
):
    service_name = validate_identifier(service_name, "service_name")
    configs = [
        SloConfig(**c)
        for c in _load_configs()
        if c.get("service_name") == service_name and c.get("enabled", True)
    ]
    results = await asyncio.gather(
        *[slo.calculate_slo(c) for c in configs],
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, SloResult)]


@router.get("/service/{service_name}/slow-apis", response_model=list[SloApiDetail])
async def get_slow_apis(
    service_name: str,
    slo: SloClient = Depends(_get_slo_client),
):
    service_name = validate_identifier(service_name, "service_name")
    configs = [
        SloConfig(**c)
        for c in _load_configs()
        if c.get("service_name") == service_name and c.get("enabled", True)
    ]
    if not configs:
        return []

    all_apis: list[SloApiDetail] = []
    for config in configs:
        apis = await slo.get_slow_apis(service_name, config)
        all_apis.extend(apis)

    seen: set[str] = set()
    unique: list[SloApiDetail] = []
    for api in all_apis:
        key = f"{api.transaction_name}:{api.slo_type}"
        if key not in seen:
            seen.add(key)
            unique.append(api)

    return sorted(unique, key=lambda x: x.slo_met)


@router.get("/report")
async def get_report(slo: SloClient = Depends(_get_slo_client)):
    configs = [SloConfig(**c) for c in _load_configs() if c.get("enabled", True)]
    results = await asyncio.gather(
        *[slo.calculate_slo(c) for c in configs],
        return_exceptions=True,
    )
    slo_results = [r for r in results if isinstance(r, SloResult)]

    slow_apis_map: dict[str, list[SloApiDetail]] = {}
    for config in configs:
        if config.service_name not in slow_apis_map:
            try:
                apis = await slo.get_slow_apis(config.service_name, config)
                slow_apis_map[config.service_name] = [a for a in apis if not a.slo_met]
            except Exception:
                slow_apis_map[config.service_name] = []

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(slo_results),
            "healthy": sum(1 for r in slo_results if r.status == "healthy"),
            "warning": sum(1 for r in slo_results if r.status == "warning"),
            "breached": sum(1 for r in slo_results if r.status in ("critical", "breached")),
        },
        "results": [r.model_dump() for r in slo_results],
        "slow_apis": {k: [a.model_dump() for a in v] for k, v in slow_apis_map.items()},
    }

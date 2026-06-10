import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.models.alerts import AlertRule, AlertStatsRequest, ClusterAlertStats, NamespaceAlertStats

router = APIRouter(prefix="/alerts", tags=["alerts"])

RULES_FILE = "data/alert_rules.json"


def _load_rules() -> list[dict]:
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE) as f:
        return json.load(f)


def _save_rules(rules: list[dict]):
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


@router.get("/rules", response_model=list[AlertRule])
async def list_rules():
    return _load_rules()


@router.post("/rules", response_model=AlertRule, status_code=201)
async def create_rule(rule: AlertRule):
    rules = _load_rules()
    rule.id = str(uuid.uuid4())
    rules.append(rule.model_dump())
    _save_rules(rules)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_rule(rule_id: str, rule_update: AlertRule):
    rules = _load_rules()
    for i, r in enumerate(rules):
        if r["id"] == rule_id:
            rule_update.id = rule_id
            rules[i] = rule_update.model_dump()
            _save_rules(rules)
            return rule_update
    raise HTTPException(status_code=404, detail="Rule not found")


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str):
    rules = _load_rules()
    rules = [r for r in rules if r["id"] != rule_id]
    _save_rules(rules)


@router.get("/history")
async def get_history():
    history_file = "data/alert_history.json"
    if not os.path.exists(history_file):
        return []
    with open(history_file) as f:
        return json.load(f)


@router.get("/prometheus/stats", response_model=ClusterAlertStats)
async def get_prometheus_alert_stats(
    request: Request,
    namespaces: Optional[str] = None,
    include_pending: bool = True,
    top_n: int = 5,
):
    """
    Get alert statistics from Prometheus grouped by namespace.

    Query Parameters:
    - namespaces: Comma-separated list of namespaces (default: all configured)
    - include_pending: Include pending alerts in counts (default: true)
    - top_n: Number of top alerts to return per namespace (default: 5)

    Returns:
        ClusterAlertStats with per-namespace breakdown
    """
    prom = request.app.state.prometheus_client

    # Parse namespaces from query param
    ns_list = None
    if namespaces:
        ns_list = [ns.strip() for ns in namespaces.split(",")]

    # Get stats from Prometheus
    stats = await prom.get_alerts_stats(namespaces=ns_list)

    # Build response
    namespace_responses = []
    total_alerts = 0
    total_firing = 0

    for namespace, ns_stats in stats.items():
        total_alerts += ns_stats["total"]
        total_firing += ns_stats["firing"]

        # Build top alerts list
        top_alerts = []
        for alert in ns_stats["alerts"][:top_n]:
            top_alerts.append({
                "name": alert["name"],
                "severity": alert["severity"],
                "state": alert["state"],
                "summary": alert["annotations"].get("summary", ""),
            })

        namespace_responses.append(NamespaceAlertStats(
            namespace=namespace,
            total_alerts=ns_stats["total"],
            firing=ns_stats["firing"],
            pending=ns_stats["pending"] if include_pending else 0,
            by_severity=ns_stats["by_severity"],
            top_alerts=top_alerts,
        ))

    # Sort namespaces by firing count (descending)
    namespace_responses.sort(key=lambda x: x.firing, reverse=True)

    # Build top namespaces summary
    top_ns = [
        {"namespace": ns.namespace, "firing": ns.firing, "total": ns.total_alerts}
        for ns in namespace_responses[:5]
    ]

    return ClusterAlertStats(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_namespaces=len(namespace_responses),
        total_alerts=total_alerts,
        total_firing=total_firing,
        namespaces=namespace_responses,
        top_namespaces=top_ns,
    )


@router.get("/prometheus/namespace/{namespace}", response_model=NamespaceAlertStats)
async def get_namespace_alert_stats(
    namespace: str,
    request: Request,
    include_pending: bool = True,
    top_n: int = 10,
):
    """
    Get alert statistics for a specific namespace.

    Path Parameters:
    - namespace: Kubernetes namespace to query

    Query Parameters:
    - include_pending: Include pending alerts (default: true)
    - top_n: Number of top alerts to return (default: 10)
    """
    prom = request.app.state.prometheus_client

    stats = await prom.get_alerts_stats(namespaces=[namespace])

    if namespace not in stats:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace}' not found or has no alerts")

    ns_stats = stats[namespace]

    # Build top alerts
    top_alerts = []
    for alert in ns_stats["alerts"][:top_n]:
        top_alerts.append({
            "name": alert["name"],
            "severity": alert["severity"],
            "state": alert["state"],
            "summary": alert["annotations"].get("summary", ""),
            "labels": alert["labels"],
        })

    return NamespaceAlertStats(
        namespace=namespace,
        total_alerts=ns_stats["total"],
        firing=ns_stats["firing"],
        pending=ns_stats["pending"] if include_pending else 0,
        by_severity=ns_stats["by_severity"],
        top_alerts=top_alerts,
    )

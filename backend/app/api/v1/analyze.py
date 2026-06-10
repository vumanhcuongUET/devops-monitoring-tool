"""
Analyze API - AI-powered incident analysis endpoint.

This endpoint integrates with the LLM service to generate Triage Cards
for incident analysis and response recommendations.

Based on strategic roadmap: docs/chien_luoc_tong_the.md (Giai đoạn 1)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request, HTTPException, status

from app.models.triage_card import (
    SeverityLevel,
    TriageCard,
    TriageCardRequest,
    TriageCardResponse,
)
from app.services.llm_client import get_llm_client


router = APIRouter(tags=["analyze"])


@router.post("/analyze", response_model=TriageCardResponse)
async def analyze_incident(request: Request, triage_request: TriageCardRequest):
    """
    Generate an AI-powered Triage Card for incident analysis.

    This endpoint:
    1. Collects context data from monitoring sources (logs, metrics, APM, K8s)
    2. Sends the data to Claude LLM for analysis
    3. Returns a structured Triage Card with findings and recommendations

    **Note:** This is a READ-ONLY operation (Giai đoạn 1). No actions are executed.

    Example request:
    ```json
    {
      "project": "meinvoice",
      "incident_id": "alert-123",
      "alert_message": "High error rate detected in production API",
      "time_range_minutes": 60,
      "include_recommendations": true,
      "severity_threshold": "medium"
    }
    ```
    """
    # Get the monitoring clients from app state
    es_client = request.app.state.es_client
    prom_client = request.app.state.prometheus_client
    k8s_client = request.app.state.k8s_client
    apm_client = request.app.state.apm_client

    # Get LLM client
    try:
        llm_client = get_llm_client()
    except ValueError as e:
        return TriageCardResponse(
            success=False,
            error=f"LLM service not configured: {e}",
            triage_card=None,
        )

    # Collect context data from all sources (in parallel)
    time_delta = timedelta(minutes=triage_request.time_range_minutes)

    try:
        context_data = await _collect_context_data(
            es_client=es_client,
            prom_client=prom_client,
            k8s_client=k8s_client,
            apm_client=apm_client,
            project=triage_request.project,
            time_delta=time_delta,
            severity_threshold=triage_request.severity_threshold,
        )
    except Exception as e:
        return TriageCardResponse(
            success=False,
            error=f"Failed to collect context data: {e}",
            triage_card=None,
        )

    # Generate Triage Card using LLM
    try:
        triage_card = await llm_client.generate_triage_card(
            request=triage_request,
            context_data=context_data,
        )

        return TriageCardResponse(
            success=True,
            triage_card=triage_card,
            error=None,
        )
    except Exception as e:
        return TriageCardResponse(
            success=False,
            error=f"Failed to generate triage card: {e}",
            triage_card=None,
            debug_info={"context_sources": list(context_data.keys())},
        )


@router.get("/analyze/health")
async def analyze_health(request: Request):
    """Check if the analyze service (LLM) is healthy and accessible."""
    try:
        llm_client = get_llm_client()
        is_healthy = await llm_client.health_check()
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "model": llm_client.model,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service not available: {e}",
        )


async def _collect_context_data(
    es_client,
    prom_client,
    k8s_client,
    apm_client,
    project: str,
    time_delta: timedelta,
    severity_threshold: SeverityLevel,
) -> dict[str, Any]:
    """
    Collect context data from all monitoring sources in parallel.

    Returns a dict with keys: logs, apm, metrics, kubernetes, alerts
    """
    results = await asyncio.gather(
        _get_logs_context(es_client, project, time_delta),
        _get_apm_context(apm_client),
        _get_metrics_context(prom_client),
        _get_kubernetes_context(k8s_client),
        _get_alerts_context(es_client, project, time_delta, severity_threshold),
        return_exceptions=True,
    )

    return {
        "logs": results[0] if not isinstance(results[0], Exception) else [],
        "apm": results[1] if not isinstance(results[1], Exception) else {},
        "metrics": results[2] if not isinstance(results[2], Exception) else {},
        "kubernetes": results[3] if not isinstance(results[3], Exception) else {},
        "alerts": results[4] if not isinstance(results[4], Exception) else [],
    }


async def _get_logs_context(es_client, project: str, time_delta: timedelta) -> list:
    """Collect recent error logs from Elasticsearch."""
    try:
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - time_delta).isoformat()
        logs, _ = await es_client.search_logs(
            query=f"{project} AND (error OR ERROR OR critical OR fail)",
            start=since,
            size=50,
        )
        return logs
    except Exception:
        return []


async def _get_apm_context(apm_client) -> dict:
    """Collect APM performance data."""
    try:
        summary = await apm_client.get_summary()
        errors = await apm_client.get_errors()

        return {
            "summary": {
                "latency_p50_ms": summary["latency_p50"],
                "latency_p95_ms": summary["latency_p95"],
                "latency_p99_ms": summary["latency_p99"],
                "error_rate_percent": summary["error_rate_percent"],
                "throughput_per_minute": round(summary["throughput"] / 60, 1),
            },
            "top_errors": errors[:10],
        }
    except Exception:
        return {}


async def _get_metrics_context(prom_client) -> dict:
    """Collect key metrics from Prometheus."""
    try:
        cpu = await prom_client.get_cpu_percent()
        memory = await prom_client.get_memory_percent()
        # disk = await prom_client.get_disk_percent()  # Method doesn't exist

        return {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(memory, 1),
            "disk_percent": 0.0,  # Placeholder
        }
    except Exception:
        return {}


async def _get_kubernetes_context(k8s_client) -> dict:
    """Collect Kubernetes state information."""
    try:
        pods = await k8s_client.list_pods()
        deployments = await k8s_client.list_deployments()

        # Count pod statuses
        pod_status_counts = {}
        for pod in pods:
            status = pod.get("status", "Unknown")
            pod_status_counts[status] = pod_status_counts.get(status, 0) + 1

        # Check deployment health
        unhealthy_deployments = [d["name"] for d in deployments if d["available"] < d["replicas"]]

        return {
            "pods_total": len(pods),
            "pod_status_counts": pod_status_counts,
            "deployments_total": len(deployments),
            "unhealthy_deployments": unhealthy_deployments,
        }
    except Exception:
        return {}


async def _get_alerts_context(es_client, project: str, time_delta: timedelta, severity_threshold: SeverityLevel = SeverityLevel.MEDIUM) -> list:
    """Collect recent alerts from the alert system."""
    try:
        import json
        import os
        from datetime import datetime, timedelta, timezone

        history_file = "data/alert_history.json"
        if not os.path.exists(history_file):
            return []

        with open(history_file) as f:
            all_alerts = json.load(f)

        # Filter by project if available and time range
        since = datetime.now(timezone.utc) - time_delta
        filtered_alerts = []

        # Severity ordering for threshold comparison
        severity_order = {
            SeverityLevel.CRITICAL: 4,
            SeverityLevel.HIGH: 3,
            SeverityLevel.MEDIUM: 2,
            SeverityLevel.LOW: 1,
            SeverityLevel.INFO: 0,
        }
        min_severity_value = severity_order.get(severity_threshold, 2)

        for alert in all_alerts:
            # Check time range
            alert_time_str = alert.get("timestamp", "")
            if alert_time_str:
                try:
                    alert_time = datetime.fromisoformat(alert_time_str.replace("Z", "+00:00"))
                    if alert_time < since:
                        continue
                except ValueError:
                    pass

            # Filter by project (check if project name appears in rule name or message)
            rule_name = alert.get("rule_name", "").lower()
            message = alert.get("message", "").lower()
            if project.lower() not in rule_name and project.lower() not in message:
                continue

            # Filter by severity threshold
            alert_severity_str = alert.get("severity", "info").lower()
            try:
                alert_severity = SeverityLevel(alert_severity_str)
                alert_severity_value = severity_order.get(alert_severity, 0)
                if alert_severity_value < min_severity_value:
                    continue
            except ValueError:
                # Invalid severity, include it anyway
                pass

            filtered_alerts.append({
                "rule_name": alert.get("rule_name"),
                "severity": alert.get("severity"),
                "status": alert.get("status"),
                "message": alert.get("message"),
                "timestamp": alert.get("timestamp"),
            })

        return filtered_alerts[-20:]  # Return last 20 alerts
    except Exception:
        return []

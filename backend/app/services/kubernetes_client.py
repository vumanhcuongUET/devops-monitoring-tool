import asyncio
from typing import Any

from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException

from app.config import settings


class KubernetesClient:
    def __init__(self):
        try:
            if settings.KUBECONFIG_PATH:
                k8s_config.load_kube_config(config_file=settings.KUBECONFIG_PATH)
            else:
                k8s_config.load_incluster_config()
            self.core = client.CoreV1Api()
            self.apps = client.AppsV1Api()
            self._available = True
        except Exception:
            self.core = None
            self.apps = None
            self._available = False

    def _safe(self) -> bool:
        return self._available and self.core is not None

    async def list_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        namespaces = [namespace] if namespace else settings.K8S_NAMESPACES
        pods: list[dict] = []
        for ns in namespaces:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.core.list_namespaced_pod, ns),
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                for p in result.items:
                    pods.append({
                        "name": p.metadata.name,
                        "namespace": p.metadata.namespace,
                        "status": p.status.phase,
                        "restarts": sum(cs.restart_count for cs in (p.status.container_statuses or [])),
                        "age": _format_age(p.metadata.creation_timestamp),
                        "node": p.spec.node_name or "",
                    })
            except Exception:
                continue
        return pods

    async def list_deployments(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        namespaces = [namespace] if namespace else settings.K8S_NAMESPACES
        deployments: list[dict] = []
        for ns in namespaces:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.apps.list_namespaced_deployment, ns),
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                for d in result.items:
                    deployments.append({
                        "name": d.metadata.name,
                        "namespace": d.metadata.namespace,
                        "replicas": d.spec.replicas or 0,
                        "available": d.status.available_replicas or 0,
                        "updated": d.status.updated_replicas or 0,
                        "image": d.spec.template.spec.containers[0].image if d.spec.template.spec.containers else "",
                    })
            except Exception:
                continue
        return deployments

    async def list_nodes(self) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.core.list_node),
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            return [
                {
                    "name": n.metadata.name,
                    "status": _node_status(n),
                    "labels": n.metadata.labels or {},
                }
                for n in result.items
            ]
        except Exception:
            return []

    async def get_events(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        namespaces = [namespace] if namespace else settings.K8S_NAMESPACES
        events: list[dict] = []
        for ns in namespaces:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.core.list_namespaced_event, ns),
                    timeout=settings.REQUEST_TIMEOUT_SECONDS,
                )
                for e in result.items:
                    events.append({
                        "timestamp": e.last_timestamp.isoformat() if e.last_timestamp else "",
                        "type": e.type or "",
                        "reason": e.reason or "",
                        "message": e.message or "",
                        "object": f"{e.involved_object.kind}/{e.involved_object.name}" if e.involved_object else "",
                    })
            except Exception:
                continue
        return sorted(events, key=lambda x: x["timestamp"], reverse=True)[:50]


def _format_age(ts) -> str:
    if ts is None:
        return ""
    from datetime import datetime, timezone
    delta = datetime.now(timezone.utc) - ts
    days = delta.days
    if days > 0:
        return f"{days}d"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h"
    return f"{delta.seconds // 60}m"


def _node_status(node) -> str:
    conditions = node.status.conditions or []
    for c in conditions:
        if c.type == "Ready":
            return "Ready" if c.status == "True" else "NotReady"
    return "Unknown"

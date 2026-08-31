import asyncio
import logging
from typing import Any

from kubernetes import client
from kubernetes import config as k8s_config

from app.config import settings

logger = logging.getLogger(__name__)


class KubernetesClient:
    def __init__(self):
        try:
            if settings.KUBECONFIG_PATH:
                k8s_config.load_kube_config(config_file=settings.KUBECONFIG_PATH)
            else:
                k8s_config.load_incluster_config()

            # Phase 9: Configure connection pool settings.
            # get_default_copy() preserves the auth loaded above; a bare
            # Configuration() has no credentials and every call would 401.
            configuration = client.Configuration.get_default_copy()
            configuration.connection_pool_size = settings.K8S_MAX_CONNECTIONS

            self.core = client.CoreV1Api(configuration)
            self.apps = client.AppsV1Api(configuration)
            self._available = True
        except Exception as exc:
            # Security recheck 2026-08-29: init failure was silent — empty K8s
            # pages with zero diagnostic signal. Log once at init.
            logger.warning(
                "Kubernetes client init failed; K8s endpoints return empty data: %s",
                exc,
            )
            self.core = None
            self.apps = None
            self._available = False

    def _safe(self) -> bool:
        return self._available and self.core is not None

    @property
    def available(self) -> bool:
        """Whether the K8s API is usable (Phase 13: lets skills tell
        'cluster unreachable' apart from 'zero deployments')."""
        return self._safe()

    @staticmethod
    def _raise_if_total_failure(failed: int, attempted: int, what: str) -> None:
        """Phase 15: partial failures degrade gracefully (per-ns skip), but a
        TOTAL failure previously read as "zero resources" — alert rules then
        treated an API outage as a healthy cluster. Raise so the fetch is
        counted as failed (ALERT_EVAL_ERRORS / overview error path)."""
        if attempted and failed == attempted:
            raise ConnectionError(
                f"Kubernetes API failed for all {attempted} namespace(s) while listing {what}"
            )


    async def list_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        namespaces = [namespace] if namespace else settings.K8S_NAMESPACES
        pods: list[dict] = []
        failed = 0
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
                failed += 1
                continue
        self._raise_if_total_failure(failed, len(namespaces), "pods")
        return pods

    async def list_deployments(self, namespace: str | None = None) -> list[dict[str, Any]]:
        if not self._safe():
            return []
        namespaces = [namespace] if namespace else settings.K8S_NAMESPACES
        deployments: list[dict] = []
        failed = 0
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
                failed += 1
                continue
        self._raise_if_total_failure(failed, len(namespaces), "deployments")
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
        failed = 0
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
                failed += 1
                continue
        self._raise_if_total_failure(failed, len(namespaces), "events")
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

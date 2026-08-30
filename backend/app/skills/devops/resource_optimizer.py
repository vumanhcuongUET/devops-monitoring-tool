"""Resource Optimizer skill — usage vs requests from Prometheus (Phase 13).

Was a stub. Now reads real per-pod CPU/memory usage and requests via the
prometheus client injected by the skills API and flags over/under-provisioned
pods. No cost model is configured, so savings stay 0.0 (honest).
"""

import logging
from typing import Any

from app.skills.base import (
    AnalysisResult,
    BaseSkill,
    Recommendation,
    SkillCategory,
    SkillConfig,
    SkillPriority,
)

logger = logging.getLogger(__name__)


class ResourceOptimizerSkill(BaseSkill):
    """Optimize Kubernetes resource requests based on actual usage."""

    skill_id = "devops_resource_optimizer"
    name = "Resource Optimizer"
    description = "Optimize Kubernetes resource requests and limits based on actual usage"
    category = SkillCategory.DEVOPS
    priority = SkillPriority.MEDIUM
    version = "2.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Analyze resource utilization.

        Args:
            project: Project name
            parameters: Analysis parameters ({"days": N} — metric window)
            context: Registry context (needs context["clients"]["prometheus"])

        Returns:
            AnalysisResult with optimization recommendations
        """
        try:
            days = parameters.get("days", 7)
            namespace = parameters.get("namespace")
            if namespace:
                # Interpolated into PromQL selectors and kubectl strings —
                # reject anything outside safe identifier characters.
                from app.security import validate_identifier

                validate_identifier(namespace, "namespace")

            resources = await self._fetch_resource_metrics(project, days, context, namespace)
            over_provisioned = self._find_over_provisioned(resources)
            under_provisioned = self._find_under_provisioned(resources)
            monthly_savings = self._calculate_savings(over_provisioned)

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.8,
                data={
                    "resources": resources,
                    "over_provisioned": over_provisioned,
                    "under_provisioned": under_provisioned,
                    "monthly_savings": monthly_savings,
                },
            )
        except Exception as e:
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Resource optimization analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Rightsizing recommendations for over-provisioned pods."""
        from app.skills.registry import get_skill_registry

        registry = get_skill_registry()
        result = registry.get_result(analysis_id)

        if not result or not result.success:
            return []

        recommendations = []
        for resource in result.data["over_provisioned"]:
            recommendations.append(Recommendation(
                title=f"Reduce resource allocation for {resource['name']}",
                description=(
                    f"Pod uses far below its requests. Current: {resource['current_requests']}, "
                    f"Recommended: {resource['recommended_requests']}."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                estimated_effort="15 minutes",
                risk_level="low",
                commands=[
                    "# Update deployment resources",
                    f"kubectl set resources deployment {resource['deployment']} "
                    f"-n {resource['namespace']} "
                    f"--requests={resource['recommended_requests']}",
                ],
            ))
        return recommendations

    async def _fetch_resource_metrics(
        self,
        project: str,
        days: int,
        context: dict[str, Any] | None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch per-pod usage vs requests from Prometheus (Phase 13).

        The prometheus client comes from context["clients"]["prometheus"],
        injected by the skills API. `namespace` scopes the analysis; without
        it the whole cluster is analyzed (projects are not namespaces).
        """
        clients = (context or {}).get("clients") or {}
        prom = clients.get("prometheus")
        if prom is None:
            raise RuntimeError(
                "No Prometheus in context['clients']['prometheus'] — skill requires Prometheus"
            )
        window = f"{max(days, 1)}d"
        selector = f'{{namespace="{namespace}"}}' if namespace else ""

        async def q(expr):
            try:
                return await prom.query(expr)
            except Exception:
                return []  # missing series degrades to "unknown", never fails the run

        # resolve real deployment names when a k8s client is available —
        # beats the pod-name heuristic, which is wrong for StatefulSets
        deployment_names: set[str] = set()
        k8s = ((context or {}).get("clients") or {}).get("k8s")
        if k8s is not None and getattr(k8s, "available", True):
            try:
                for d in await k8s.list_deployments(namespace):
                    deployment_names.add(d["name"])
            except Exception:
                pass  # heuristic fallback stays

        usage_cpu = await q(
            "sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!=\"\""
            + selector + "}[" + window + "]))"
        )
        usage_mem = await q(
            'sum by (namespace, pod) (container_memory_working_set_bytes{container!=""'
            + selector + "})"
        )
        req_cpu = await q(
            'sum by (namespace, pod) (kube_pod_container_resource_requests{resource="cpu"'
            + selector + "})"
        )
        req_mem = await q(
            'sum by (namespace, pod) (kube_pod_container_resource_requests{resource="memory"'
            + selector + "})"
        )

        def index(rows):
            return {
                (r["metric"].get("namespace", ""), r["metric"].get("pod", "")): float(r["value"][1])
                for r in rows
                if r.get("value")
            }

        uc, um = index(usage_cpu), index(usage_mem)
        rc, rm = index(req_cpu), index(req_mem)

        resources = []
        for pod_key in sorted(set(uc) | set(um)):
            ns, pod = pod_key
            cpu_u, mem_u = uc.get(pod_key, 0.0), um.get(pod_key, 0.0)
            cpu_r, mem_r = rc.get(pod_key), rm.get(pod_key)
            rec_cpu = round(cpu_u * 1.5, 4) if cpu_r else None
            rec_mem = round(mem_u * 1.5, 1) if mem_r else None
            # longest real deployment name the pod starts with; heuristic
            # fallback (strip ReplicaSet/Pod hash suffix) otherwise
            deployment = next(
                (name for name in sorted(deployment_names, key=len, reverse=True)
                 if pod.startswith(name + "-")),
                pod.rsplit("-", 2)[0] if pod.count("-") >= 2 else pod,
            )
            resources.append({
                "namespace": ns,
                "pod": pod,
                "name": pod,
                "deployment": deployment,
                "cpu_usage": round(cpu_u, 4),
                "mem_usage_bytes": round(mem_u, 1),
                "cpu_request": cpu_r,
                "mem_request_bytes": mem_r,
                "current_requests": f"cpu={cpu_r}, mem={mem_r}",
                "recommended_requests": f"cpu={rec_cpu}, mem={rec_mem}",
            })
        return resources

    def _find_over_provisioned(self, resources: list) -> list[dict[str, Any]]:
        """Find over-provisioned pods (usage well below requests)."""
        over = []
        for r in resources:
            over_cpu = r["cpu_request"] and r["cpu_usage"] < r["cpu_request"] * 0.25
            over_mem = r["mem_request_bytes"] and r["mem_usage_bytes"] < r["mem_request_bytes"] * 0.25
            if over_cpu or over_mem:
                over.append(r)
        return over

    def _find_under_provisioned(self, resources: list) -> list[dict[str, Any]]:
        """Find under-provisioned pods (usage close to or above requests)."""
        under = []
        for r in resources:
            hot_cpu = r["cpu_request"] and r["cpu_usage"] > r["cpu_request"] * 0.9
            hot_mem = r["mem_request_bytes"] and r["mem_usage_bytes"] > r["mem_request_bytes"] * 0.9
            if hot_cpu or hot_mem:
                under.append(r)
        return under

    def _calculate_savings(self, over_provisioned: list) -> float:
        """No cost model configured — savings stay 0.0 (honest) until a
        price table exists (ponytail: fabricated dollars are worse than none)."""
        return 0.0

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate parameters."""
        return True, []

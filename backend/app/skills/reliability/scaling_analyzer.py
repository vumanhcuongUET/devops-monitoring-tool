"""Reliability Scaling Analyzer Skill — real Kubernetes state (Phase 13).

Was a stub inventing HPA effectiveness numbers. Now it reads live cluster
state through the injected Kubernetes client: replica headroom per
deployment, pods that cannot schedule, restart storms, and scaling-related
events (FailedScheduling, OOMKilled, HPA failures).
"""

from __future__ import annotations

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

# Events that indicate a service cannot scale or is scaling badly.
_SCALING_EVENT_REASONS = {
    "FailedScheduling",
    "FailedGetResourceMetric",
    "FailedComputeMetricsReplicas",
}


class ScalingAnalyzerSkill(BaseSkill):
    """Analyze scaling readiness from live Kubernetes deployments/pods/events."""

    skill_id = "reliability_scaling_analyzer"
    name = "Reliability Scaling Analyzer"
    description = (
        "Analyze scaling readiness and blockers from live Kubernetes state: "
        "replica headroom, unschedulable pods, restart storms and scaling events."
    )
    category = SkillCategory.RELIABILITY
    priority = SkillPriority.HIGH
    version = "2.0.0"

    def __init__(self, config: SkillConfig | None = None):
        super().__init__(config)

    async def analyze(
        self,
        project: str,
        parameters: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        try:
            namespace = parameters.get("namespace")
            deployment_name = parameters.get("deployment")

            k8s = ((context or {}).get("clients") or {}).get("k8s")
            if k8s is None:
                raise RuntimeError(
                    "No Kubernetes client in context['clients']['k8s'] — "
                    "skill requires a live cluster"
                )

            deployments = await k8s.list_deployments(namespace)
            pods = await k8s.list_pods(namespace)
            events = await k8s.get_events(namespace)

            if deployment_name:
                deployments = [
                    d for d in deployments if d.get("name") == deployment_name
                ]
                if not deployments:
                    return AnalysisResult(
                        success=False,
                        skill_id=self.skill_id,
                        errors=[f"Deployment {deployment_name!r} not found"],
                    )

            deployment_status = []
            for d in deployments:
                replicas = d.get("replicas", 0)
                available = d.get("available", 0)
                if replicas == 0:
                    scale_state = "scaled_to_zero"
                elif available < replicas:
                    scale_state = "degraded"
                else:
                    scale_state = "ready"
                deployment_status.append({
                    "name": d.get("name"),
                    "namespace": d.get("namespace"),
                    "replicas": replicas,
                    "available": available,
                    "state": scale_state,
                    "can_scale_up": scale_state == "ready",
                })

            blocked_pods = [
                {
                    "name": p.get("name"),
                    "namespace": p.get("namespace"),
                    "status": p.get("status"),
                    "restarts": p.get("restarts", 0),
                }
                for p in pods
                if p.get("status") in ("Pending", "Failed")
                or p.get("restarts", 0) >= 5
            ]

            scaling_events = [
                {
                    "reason": e.get("reason"),
                    "type": e.get("type"),
                    "object": e.get("object"),
                    "message": e.get("message"),
                    "timestamp": e.get("timestamp"),
                }
                for e in events
                if e.get("reason") in _SCALING_EVENT_REASONS
                or "OOMKilled" in (e.get("message") or "")
                or "horizontalpodautoscaler" in (e.get("object") or "").lower()
            ][:20]

            blockers = []
            if blocked_pods:
                blockers.append(f"{len(blocked_pods)} pods pending/failing/restart-looping")
            if scaling_events:
                blockers.append(f"{len(scaling_events)} scaling-related events")

            return AnalysisResult(
                success=True,
                skill_id=self.skill_id,
                confidence=0.9,
                data={
                    "namespace": namespace or "all configured",
                    "deployments": deployment_status,
                    "blocked_pods": blocked_pods,
                    "scaling_events": scaling_events,
                    "summary": {
                        "deployments_analyzed": len(deployment_status),
                        "ready": sum(1 for d in deployment_status if d["can_scale_up"]),
                        "degraded": sum(1 for d in deployment_status if d["state"] == "degraded"),
                        "scaled_to_zero": sum(
                            1 for d in deployment_status if d["state"] == "scaled_to_zero"
                        ),
                        "scaling_blockers": blockers,
                    },
                },
                warnings=blockers,
            )
        except Exception as e:
            logger.error(f"{self.skill_id} failed for {project}: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.skill_id,
                errors=[f"Scaling analysis failed: {e!s}"],
            )

    async def get_recommendations(
        self, analysis_id: str, project: str
    ) -> list[Recommendation]:
        from app.skills.registry import get_skill_registry

        result = get_skill_registry().get_result(analysis_id)
        if not result or not result.success:
            return []

        data = result.data
        recommendations = []

        degraded = [d for d in data.get("deployments", []) if d["state"] == "degraded"]
        if degraded:
            names = ", ".join(d["name"] for d in degraded[:5])
            recommendations.append(Recommendation(
                title="Deployments below desired replicas",
                description=(
                    f"{len(degraded)} deployment(s) cannot reach desired replicas "
                    f"({names}) — scaling up will fail until the cause is fixed."
                ),
                priority=SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))

        if data.get("blocked_pods"):
            recommendations.append(Recommendation(
                title="Pods blocking scale-out",
                description=(
                    f"{len(data['blocked_pods'])} pods are Pending/Failed or in a "
                    "restart loop — check scheduling capacity and crash causes."
                ),
                priority=SkillPriority.HIGH,
                action_type="investigate",
                risk_level="high",
            ))

        oom_events = [
            e for e in data.get("scaling_events", []) if "OOMKilled" in (e.get("message") or "")
        ]
        if oom_events:
            recommendations.append(Recommendation(
                title="OOM kills during scale-out",
                description=(
                    f"{len(oom_events)} OOMKilled events — raise memory limits "
                    "before scaling further."
                ),
                priority=SkillPriority.MEDIUM,
                action_type="manual",
                risk_level="medium",
            ))

        return recommendations

    def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, list[str]]:
        return True, []

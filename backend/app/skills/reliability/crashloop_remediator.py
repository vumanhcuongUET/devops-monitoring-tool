"""CrashLoopBackOff remediation skill.

This skill detects pods with high restart counts (CrashLoopBackOff pattern)
and provides autonomous remediation recommendations.
"""

import logging
from typing import Any, Dict
from datetime import datetime, timezone

from app.skills.base import (
    BaseSkill,
    SkillConfig,
    AnalysisResult,
    Recommendation,
)
from app.registry.loader import get_registry

logger = logging.getLogger(__name__)


class CrashLoopRemediatorSkill(BaseSkill):
    """Skill for detecting and remediating CrashLoopBackOff pods.

    This skill analyzes pod restart patterns and provides remediation
    actions for pods stuck in crash loops.
    """

    # Skill configuration
    config = SkillConfig(
        skill_id="crashloop_remediator",
        name="CrashLoopBackOff Remediation",
        description="Detects and remediates pods with high restart counts",
        version="1.0.0",
        category="reliability",
        enabled=True,
        priority=10,  # High priority for reliability
        timeout_seconds=60,
        parameters={
            "namespace": {
                "type": "string",
                "description": "Kubernetes namespace to analyze",
                "default": "default",
            },
            "restart_threshold": {
                "type": "integer",
                "description": "Minimum restart count to trigger remediation",
                "default": 5,
            },
            "label_selector": {
                "type": "string",
                "description": "Label selector to filter pods (optional)",
                "default": "",
            },
        },
    )

    async def analyze(
        self,
        project: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> AnalysisResult:
        """Analyze pods for CrashLoopBackOff patterns.

        Args:
            project: Project name
            parameters: Analysis parameters
            context: Additional context (services, clients)

        Returns:
            AnalysisResult with crashloop pod findings
        """
        namespace = parameters.get("namespace", "default")
        restart_threshold = parameters.get("restart_threshold", 5)
        label_selector = parameters.get("label_selector", "")

        try:
            registry = get_registry()
            project_config = registry.get_project(project)
            if not project_config:
                return AnalysisResult(
                    success=False,
                    skill_id=self.config.skill_id,
                    confidence=0.0,
                    data={"error": f"Project '{project}' not found"},
                )

            # Get Kubernetes client from context
            k8s_client = context.get("k8s_client")
            if not k8s_client:
                return AnalysisResult(
                    success=False,
                    skill_id=self.config.skill_id,
                    confidence=0.0,
                    data={"error": "Kubernetes client not available"},
                )

            # List pods in namespace
            pods = await k8s_client.list_pods(namespace=namespace)

            # Analyze pods for crashloop patterns
            crashloop_pods = []
            unhealthy_pods = []

            for pod in pods:
                pod_name = pod.get("name", "")
                restart_count = pod.get("restarts", 0)
                status = pod.get("status", "")
                ready = pod.get("ready", False)

                # Check for crashloop pattern
                if restart_count >= restart_threshold:
                    crashloop_pods.append({
                        "name": pod_name,
                        "restarts": restart_count,
                        "status": status,
                        "ready": ready,
                        "reason": self._get_crashloop_reason(pod),
                    })
                elif restart_count >= 3 or status in ("Error", "CrashLoopBackOff"):
                    unhealthy_pods.append({
                        "name": pod_name,
                        "restarts": restart_count,
                        "status": status,
                        "ready": ready,
                    })

            # Calculate confidence based on findings
            if crashloop_pods:
                confidence = 0.95  # High confidence when crashloop detected
            elif unhealthy_pods:
                confidence = 0.70  # Medium confidence for unhealthy pods
            else:
                confidence = 1.0  # Full confidence when healthy

            return AnalysisResult(
                success=True,
                skill_id=self.config.skill_id,
                confidence=confidence,
                data={
                    "namespace": namespace,
                    "crashloop_pods": crashloop_pods,
                    "unhealthy_pods": unhealthy_pods,
                    "total_pods_analyzed": len(pods),
                    "restart_threshold": restart_threshold,
                },
                warnings=[
                    f"{len(crashloop_pods)} pods in crashloop detected"
                ] if crashloop_pods else [],
                metadata={
                    "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                    "project": project,
                },
            )

        except Exception as e:
            logger.error(f"CrashLoopRemediator analysis failed: {e}")
            return AnalysisResult(
                success=False,
                skill_id=self.config.skill_id,
                confidence=0.0,
                data={"error": str(e)},
            )

    def _get_crashloop_reason(self, pod: Dict[str, Any]) -> str:
        """Determine likely reason for crashloop.

        Args:
            pod: Pod data

        Returns:
            Likely crash reason
        """
        # Check container status for crash reasons
        container_statuses = pod.get("container_statuses", [])
        if container_statuses:
            state = container_statuses[0].get("state", {})
            if "waiting" in state:
                return state["waiting"].get("reason", "Unknown")
            if "terminated" in state:
                return state["terminated"].get("reason", "Terminated")

        return "High restart count"

    async def get_recommendations(
        self,
        analysis_id: str,
        project: str,
    ) -> list[Recommendation]:
        """Generate remediation recommendations based on analysis.

        Args:
            analysis_id: Analysis ID to get results from
            project: Project name

        Returns:
            List of recommendations
        """
        # Get analysis results from registry
        registry = get_registry()
        analysis_result = registry.get_analysis_result(analysis_id)

        if not analysis_result or not analysis_result.success:
            return []

        data = analysis_result.data
        crashloop_pods = data.get("crashloop_pods", [])
        namespace = data.get("namespace", "default")

        recommendations = []

        # Generate recommendation for each crashloop pod
        for pod_info in crashloop_pods:
            pod_name = pod_info["name"]
            restart_count = pod_info["restarts"]
            reason = pod_info.get("reason", "Unknown")

            recommendations.append(
                Recommendation(
                    title=f"Delete CrashLoop pod: {pod_name}",
                    description=f"Pod has restarted {restart_count} times. "
                    f"Likely cause: {reason}. Deleting will allow "
                    f"the deployment controller to recreate it.",
                    impact="high",
                    effort="low",
                    priority="high" if restart_count >= 10 else "medium",
                    action_type="automated",  # Safe to automate
                    commands=[
                        f"kubectl delete pod {pod_name} -n {namespace}",
                    ],
                    actions=[
                        f"Delete pod {pod_name}",
                        "Monitor pod restart",
                        "Check logs for root cause",
                    ],
                    metadata={
                        "action_id": f"kubectl_delete_{pod_name}",
                        "risk_level": "low",
                        "estimated_recovery_time_seconds": 30,
                    },
                )
            )

        # If no crashloop pods but unhealthy ones exist
        if not crashloop_pods and data.get("unhealthy_pods"):
            unhealthy = data["unhealthy_pods"]
            recommendations.append(
                Recommendation(
                    title=f"Monitor {len(unhealthy)} unhealthy pods",
                    description=f"Found {len(unhealthy)} pods with elevated restart counts. "
                    f"Monitor these pods for potential crashloop.",
                    impact="medium",
                    effort="low",
                    priority="low",
                    action_type="manual",
                    commands=[
                        f"kubectl get pods -n {namespace} -o wide",
                    ],
                    actions=[
                        "Check pod logs",
                        "Monitor restart counts",
                        "Review application logs",
                    ],
                )
            )

        return recommendations


# Register the skill
def register_skill():
    """Register this skill with the registry."""
    from app.skills.registry import get_skill_registry
    registry = get_skill_registry()
    registry.register(CrashLoopRemediatorSkill())

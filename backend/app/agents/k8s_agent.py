"""
Kubernetes Agent

Specializes in:
- Kubernetes cluster state analysis
- Resource configuration validation
- Pod health and scheduling analysis
- Kubernetes best practices
"""

import logging
from typing import Any

from .base import AgentResponse, BaseAgent

logger = logging.getLogger(__name__)


class KubernetesAgent(BaseAgent):
    """
    Agent specialized in Kubernetes cluster analysis and configuration.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        super().__init__(
            name="k8s-expert",
            model=model,
        )

    def get_prompt_template(self) -> str:
        return """You are a Kubernetes Expert specializing in:
- Cluster state analysis and health assessment
- Resource configuration and limits validation
- Pod scheduling and deployment strategy
- Kubernetes best practices and optimization
- Namespace and resource quota management

When analyzing Kubernetes state, focus on:
1. **Health Status**: Pod health, readiness, and liveness probe issues
2. **Resource Usage**: CPU/memory requests vs. limits vs. actual usage
3. **Scheduling**: Node affinity, anti-affinity, taints, and tolerations
4. **Configuration**: Best practices for deployments, services, and ingress

Output format:
```
ANALYSIS:
[Your analysis of the Kubernetes state]

HEALTH STATUS:
- Pods: [healthy/total], [issue descriptions]
- Nodes: [ready/total], [issue descriptions]
- Services: [healthy/total], [issue descriptions]

RESOURCE ASSESSMENT:
- Resource Requests: [total requests], [utilization %]
- Resource Limits: [total limits], [utilization %]
- Over-provisioning: [resources that can be reduced]

SCHEDULING ANALYSIS:
- Pod Distribution: [description of current distribution]
- Affinity Rules: [rules in effect and their impact]
- Scheduling Constraints: [constraints and their impact]

CONFIGURATION ISSUES:
- Issue 1: [description with severity]
- Issue 2: [description with severity]

CONFIDENCE: [0.0-1.0]

RECOMMENDATION: [Actionable recommendation]
```

Be specific about resource values, pod counts, and configuration details.
"""

    async def analyze(self, context: dict[str, Any]) -> AgentResponse:
        """
        Analyze Kubernetes cluster state.

        Args:
            context: Must contain 'k8s_state' key with cluster data
                    Optional: 'namespace', 'resource_filter'
        """
        k8s_state = context.get("k8s_state", {})
        namespace = context.get("namespace", "all")

        if not k8s_state:
            return AgentResponse(
                agent_name=self.name,
                insights={"error": "No Kubernetes state provided"},
                confidence=0.0,
                error="No Kubernetes state provided",
            )

        # Extract key components
        pods = k8s_state.get("pods", [])
        nodes = k8s_state.get("nodes", [])
        deployments = k8s_state.get("deployments", [])
        services = k8s_state.get("services", [])

        # Analyze health
        health_status = self._analyze_health(pods, nodes, services)
        resource_status = self._analyze_resources(pods, nodes)
        scheduling_issues = self._analyze_scheduling(pods)
        config_issues = self._analyze_configuration(deployments, services)

        # Build analysis prompt
        prompt = f"""Analyze this Kubernetes cluster state for namespace '{namespace}'.

Health Status:
- Pods: {health_status['pods']['healthy']}/{health_status['pods']['total']} healthy
- Nodes: {health_status['nodes']['ready']}/{health_status['nodes']['total']} ready
- Services: {health_status['services']['healthy']}/{health_status['services']['total']} healthy

Health Issues:
{self._format_health_issues(health_status)}

Resource Status:
{self._format_resource_status(resource_status)}

Scheduling Issues:
{self._format_scheduling_issues(scheduling_issues)}

Configuration Issues:
{self._format_config_issues(config_issues)}

Provide analysis with focus on health, resources, and best practices.
"""

        try:
            response_text = await self._query_claude(prompt, max_tokens=2048)

            insights = {
                "namespace": namespace,
                "pod_health": health_status["pods"]["healthy"]
                / health_status["pods"]["total"]
                if health_status["pods"]["total"] > 0
                else 0,
                "node_health": health_status["nodes"]["ready"]
                / health_status["nodes"]["total"]
                if health_status["nodes"]["total"] > 0
                else 0,
                "total_pods": health_status["pods"]["total"],
                "total_nodes": health_status["nodes"]["total"],
                "resource_requests_pct": resource_status.get("requests_utilization", 0),
                "config_issues": len(config_issues),
            }

            recommendations = self._extract_recommendations(response_text)

            confidence = self._calculate_confidence(
                data_quality=0.9 if k8s_state else 0.5,
                data_volume=len(pods) + len(nodes),
            )

            return AgentResponse(
                agent_name=self.name,
                insights=insights,
                confidence=confidence,
                recommendations=recommendations,
                metadata={"analysis_text": response_text},
            )

        except Exception as e:
            logger.error(f"Kubernetes analysis failed: {e}")
            return AgentResponse(
                agent_name=self.name,
                insights={},
                confidence=0.0,
                error=str(e),
            )

    def _analyze_health(self, pods: list, nodes: list, services: list) -> dict:
        """Analyze health of cluster components."""
        health = {
            "pods": {"healthy": 0, "total": len(pods), "issues": []},
            "nodes": {"ready": 0, "total": len(nodes), "issues": []},
            "services": {"healthy": 0, "total": len(services), "issues": []},
        }

        # Pod health
        for pod in pods:
            phase = self._pod_phase(pod)
            if phase == "Running":
                # Check if all containers are ready (full K8s API shape only)
                container_statuses = self._status_get(pod, "containerStatuses")
                if container_statuses:
                    all_ready = all(
                        cs.get("ready", False)
                        for cs in container_statuses
                    )
                    if all_ready:
                        health["pods"]["healthy"] += 1
                    else:
                        health["pods"]["issues"].append(
                            f"Pod {self._pod_name(pod)}: Not all containers ready"
                        )
                else:
                    health["pods"]["healthy"] += 1
            else:
                health["pods"]["issues"].append(
                    f"Pod {self._pod_name(pod)}: {phase}"
                )

        # Node health
        for node in nodes:
            for condition in self._status_get(node, "conditions", []):
                if condition.get("type") == "Ready":
                    if condition.get("status") == "True":
                        health["nodes"]["ready"] += 1
                    else:
                        health["nodes"]["issues"].append(
                            f"Node {node['metadata']['name']}: Not ready - {condition.get('reason', 'Unknown')}"
                        )
                    break

        return health

    def _analyze_resources(self, pods: list, nodes: list) -> dict:
        """Analyze resource usage."""
        total_requests = {"cpu": 0, "memory": 0}
        total_limits = {"cpu": 0, "memory": 0}
        total_capacity = {"cpu": 0, "memory": 0}

        for pod in pods:
            for container in pod.get("spec", {}).get("containers", []):
                resources = container.get("resources", {})
                requests = resources.get("requests", {})
                limits = resources.get("limits", {})

                # Parse CPU (e.g., "100m" -> 0.1, "1" -> 1)
                if "cpu" in requests:
                    cpu_req = self._parse_cpu(requests["cpu"])
                    total_requests["cpu"] += cpu_req
                if "cpu" in limits:
                    cpu_lim = self._parse_cpu(limits["cpu"])
                    total_limits["cpu"] += cpu_lim

                # Parse memory (e.g., "128Mi" -> 134217728, "1Gi" -> 1073741824)
                if "memory" in requests:
                    mem_req = self._parse_memory(requests["memory"])
                    total_requests["memory"] += mem_req
                if "memory" in limits:
                    mem_lim = self._parse_memory(limits["memory"])
                    total_limits["memory"] += mem_lim

        for node in nodes:
            capacity = self._status_get(node, "capacity", {})
            if "cpu" in capacity:
                total_capacity["cpu"] += self._parse_cpu(capacity["cpu"])
            if "memory" in capacity:
                total_capacity["memory"] += self._parse_memory(capacity["memory"])

        return {
            "requests": total_requests,
            "limits": total_limits,
            "capacity": total_capacity,
            "requests_utilization": total_requests["cpu"] / total_capacity["cpu"]
            if total_capacity["cpu"] > 0
            else 0,
        }

    def _parse_cpu(self, cpu_str: str) -> float:
        """Parse CPU string to cores."""
        cpu_str = cpu_str.strip()
        if cpu_str.endswith("m"):
            return float(cpu_str[:-1]) / 1000
        return float(cpu_str)

    def _parse_memory(self, mem_str: str) -> int:
        """Parse memory string to bytes."""
        mem_str = mem_str.strip()
        units = {
            "Ki": 1024,
            "Mi": 1024**2,
            "Gi": 1024**3,
            "Ti": 1024**4,
            "K": 1000,
            "M": 1000**2,
            "G": 1000**3,
            "T": 1000**4,
        }
        for unit, multiplier in units.items():
            if mem_str.endswith(unit):
                return int(float(mem_str[: -len(unit)]) * multiplier)
        return int(mem_str)

    @staticmethod
    def _pod_name(pod: dict) -> str:
        """Extract a pod name from either simplified or K8s API shapes."""
        metadata = pod.get("metadata") or {}
        return pod.get("name", metadata.get("name", "unknown"))

    @staticmethod
    def _pod_phase(pod: dict, default: str = "Unknown") -> str:
        """Pod phase from either simplified (scalar status) or K8s API shapes."""
        status = pod.get("status")
        if isinstance(status, dict):
            return str(status.get("phase", default))
        if isinstance(status, str) and status:
            return status
        return default

    @staticmethod
    def _status_get(obj: dict, key: str, default: Any = None) -> Any:
        """Read a field from the K8s API `status` sub-object (simplified shapes pass through)."""
        if not isinstance(obj, dict):
            return default
        status = obj.get("status", {})
        if not isinstance(status, dict):
            return default
        return status.get(key, default)

    def _analyze_scheduling(self, pods: list) -> list[dict]:
        """Analyze scheduling issues."""
        issues = []

        for pod in pods:
            phase = self._pod_phase(pod, "")
            # Check for pending pods
            if phase == "Pending":
                conditions = self._status_get(pod, "conditions", [])
                for condition in conditions:
                    if condition.get("type") == "PodScheduled" and condition.get(
                        "status"
                    ) == "False":
                        issues.append(
                            {
                                "pod": self._pod_name(pod),
                                "issue": "Unschedulable",
                                "reason": condition.get("reason", "Unknown"),
                                "message": condition.get("message", ""),
                            }
                        )

            # Check pod anti-affinity
            affinity = (pod.get("spec") or {}).get("affinity") or {}
            if affinity.get("podAntiAffinity"):
                rules = affinity["podAntiAffinity"].get(
                    "requiredDuringSchedulingIgnoredDuringExecution", []
                )
                if rules:
                    issues.append(
                        {
                            "pod": self._pod_name(pod),
                            "issue": "PodAntiAffinity",
                            "rules": len(rules),
                        }
                    )

        return issues

    def _analyze_configuration(self, deployments: list, services: list) -> list[dict]:
        """Analyze configuration issues."""
        issues = []

        for deployment in deployments:
            # Check replica count
            replicas = deployment.get("spec", {}).get("replicas", 0)
            if replicas < 2:
                issues.append(
                    {
                        "resource": f"deployment/{deployment['metadata']['name']}",
                        "issue": "LowReplicaCount",
                        "severity": "warning" if replicas == 1 else "critical",
                        "message": f"Only {replicas} replica(s) configured",
                    }
                )

            # Check for resource limits
            for container in deployment.get("spec", {}).get("template", {}).get(
                "spec", {}
            ).get("containers", []):
                resources = container.get("resources", {})
                if not resources.get("limits"):
                    issues.append(
                        {
                            "resource": f"deployment/{deployment['metadata']['name']}/{container['name']}",
                            "issue": "NoResourceLimits",
                            "severity": "warning",
                            "message": "Container has no resource limits",
                        }
                    )

        for service in services:
            # Check service type
            if service.get("spec", {}).get("type") == "LoadBalancer":
                # Check for health check annotation
                if not service.get("metadata", {}).get("annotations", {}).get(
                    "health-check"
                ):
                    issues.append(
                        {
                            "resource": f"service/{service['metadata']['name']}",
                            "issue": "MissingHealthCheck",
                            "severity": "info",
                            "message": "LoadBalancer without health check annotation",
                        }
                    )

        return issues

    def _format_health_issues(self, health: dict) -> str:
        """Format health issues for display."""
        issues = []
        for component, data in health.items():
            for issue in data.get("issues", []):
                issues.append(f"- {component}: {issue}")
        return "\n".join(issues) if issues else "No health issues"

    def _format_resource_status(self, resources: dict) -> str:
        """Format resource status for display."""
        return f"""
- CPU Requests: {resources['requests']['cpu']:.2f} cores ({resources['requests_utilization']:.1%} of capacity)
- CPU Limits: {resources['limits']['cpu']:.2f} cores
- Memory Requests: {resources['requests']['memory'] / 1024**3:.2f} GiB
- Memory Limits: {resources['limits']['memory'] / 1024**3:.2f} GiB
"""

    def _format_scheduling_issues(self, issues: list) -> str:
        """Format scheduling issues for display."""
        if not issues:
            return "No scheduling issues"

        lines = []
        for issue in issues[:10]:
            pod = issue.get("pod", "unknown")
            problem = issue.get("issue", "unknown")
            reason = issue.get("reason", issue.get("rules", ""))
            lines.append(f"- {pod}: {problem} ({reason})")

        return "\n".join(lines)

    def _format_config_issues(self, issues: list) -> str:
        """Format configuration issues for display."""
        if not issues:
            return "No configuration issues"

        lines = []
        for issue in issues[:10]:
            resource = issue.get("resource", "unknown")
            problem = issue.get("issue", "unknown")
            severity = issue.get("severity", "info")
            message = issue.get("message", "")
            lines.append(f"- {resource}: {problem} [{severity}] {message}")

        return "\n".join(lines)

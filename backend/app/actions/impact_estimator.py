"""Impact estimation for actions before execution."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ImpactLevel(str, Enum):
    """Impact level classification."""
    LOW = "low"  # Affects < 5 pods/deployments
    MEDIUM = "medium"  # Affects 5-20 pods/deployments
    HIGH = "high"  # Affects 20-100 pods/deployments
    CRITICAL = "critical"  # Affects > 100 pods/deployments or entire namespace/cluster


@dataclass
class ResourceImpact:
    """Impact on a specific resource type."""
    resource_type: str  # "pods", "deployments", "services", etc.
    affected_count: int  # Number of resources that will be affected
    namespace: str | None = None  # Namespace if scoped
    details: dict[str, Any] = field(default_factory=dict)  # Additional details


@dataclass
class ImpactEstimate:
    """Complete impact estimate for an action."""
    action_id: str
    command: str
    total_affected_resources: int  # Total count of all affected resources
    impact_level: ImpactLevel
    resource_impacts: list[ResourceImpact]  # Breakdown by resource type
    estimated_duration_seconds: float | None = None  # Estimated execution time
    risk_factors: list[str] = field(default_factory=list)  # Identified risk factors
    recommendations: list[str] = field(default_factory=list)  # Safety recommendations
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ImpactThresholds:
    """Configuration for impact level thresholds."""
    low_max: int = 5  # Max resources for LOW impact
    medium_max: int = 20  # Max resources for MEDIUM impact
    high_max: int = 100  # Max resources for HIGH impact
    # Above high_max is CRITICAL

    # Special thresholds for critical operations
    namespace_wide_critical: bool = True  # Treat namespace-wide ops as critical
    cluster_wide_always_critical: bool = True  # Always treat cluster-wide ops as critical

    # Heuristic fallback counts, used only when no cluster client is
    # available (or the live query failed). They directly drive approval
    # gating (HIGH/CRITICAL impact forces approval), so they are deployment
    # config, not code constants — tune them per cluster via
    # get_impact_estimator(ImpactThresholds(...)).
    heuristic_namespace_counts: dict[str, int] = field(default_factory=lambda: {
        "pods": 20,
        "deployments": 10,
        "services": 5,
        "configmaps": 10,
        "secrets": 15,
    })
    heuristic_rollout_pods: int = 10  # Typical deployment size for restarts


class ImpactEstimator:
    """Estimate the impact of actions before execution.

    This class analyzes commands and estimates:
    - How many resources will be affected
    - The impact level (LOW, MEDIUM, HIGH, CRITICAL)
    - Risk factors and safety recommendations
    """

    def __init__(self, thresholds: ImpactThresholds | None = None):
        """Initialize the impact estimator.

        Args:
            thresholds: Optional custom impact thresholds
        """
        self.thresholds = thresholds or ImpactThresholds()

    async def estimate(
        self,
        action_id: str,
        command: str,
        k8s_client: Any | None = None,  # Kubernetes client (optional)
        dry_run: bool = True,
    ) -> ImpactEstimate:
        """Estimate the impact of executing a command.

        Args:
            action_id: ID of the action being estimated
            command: Command to analyze
            k8s_client: Optional Kubernetes client for real queries
            dry_run: If True, don't make actual API calls (use heuristics)

        Returns:
            ImpactEstimate with detailed impact analysis
        """
        # Parse command to determine operation and scope
        parsed = self._parse_command(command)

        # Determine if this is cluster-wide or namespace-scoped
        is_cluster_wide = self._is_cluster_wide_operation(parsed)
        is_namespace_wide = self._is_namespace_wide_operation(parsed)

        # Calculate resource impacts
        resource_impacts = await self._calculate_resource_impacts(
            parsed, k8s_client, dry_run
        )

        # Sum total affected resources
        total_affected = sum(r.affected_count for r in resource_impacts)

        # Determine impact level
        impact_level = self._determine_impact_level(
            total_affected, is_cluster_wide, is_namespace_wide
        )

        # Identify risk factors
        risk_factors = self._identify_risk_factors(
            parsed, total_affected, is_cluster_wide, is_namespace_wide
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            impact_level, risk_factors, parsed
        )

        # Estimate duration based on operation type and resource count
        estimated_duration = self._estimate_duration(parsed, total_affected)

        return ImpactEstimate(
            action_id=action_id,
            command=command,
            total_affected_resources=total_affected,
            impact_level=impact_level,
            resource_impacts=resource_impacts,
            estimated_duration_seconds=estimated_duration,
            risk_factors=risk_factors,
            recommendations=recommendations,
        )

    def _parse_command(self, command: str) -> dict[str, Any]:
        """Parse a command into its components.

        Args:
            command: Command string to parse

        Returns:
            Dict with parsed components
        """
        parts = command.strip().split()
        if not parts:
            return {"tool": None, "operation": None, "args": [], "flags": {}}

        result = {
            "tool": parts[0],
            "operation": None,
            "args": [],
            "flags": {},
            "raw": command,
        }

        i = 1
        while i < len(parts):
            part = parts[i]

            # Check for flags
            if part.startswith("-"):
                flag_name = part.lstrip("-")
                # Check if this flag has a value
                if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                    result["flags"][flag_name] = parts[i + 1]
                    i += 2
                else:
                    result["flags"][flag_name] = True
                    i += 1
            else:
                # Non-flag argument
                if result["operation"] is None:
                    result["operation"] = part
                else:
                    result["args"].append(part)
                i += 1

        return result

    def _is_cluster_wide_operation(self, parsed: dict[str, Any]) -> bool:
        """Check if operation affects the entire cluster."""
        flags = parsed.get("flags", {})

        # Check for cluster-wide flags (both short and long forms)
        if "A" in flags or "all-namespaces" in flags:  # kubectl --all-namespaces
            return True

        # Check for cluster-wide operations
        operation = parsed.get("operation", "")
        tool = parsed.get("tool", "")

        # Certain operations are cluster-wide
        if tool == "kubectl" and operation in ("delete", "get"):
            # Check if targeting cluster-wide resources
            args = parsed.get("args", [])
            cluster_resources = ("nodes", "namespaces", "pv", "storageclass",
                               "clusterrole", "clusterrolebinding")
            if any(arg in cluster_resources for arg in args):
                return True

        # ArgoCD cluster operations
        if tool == "argocd" and operation in ("repo", "cluster"):
            return True

        return False

    def _is_namespace_wide_operation(self, parsed: dict[str, Any]) -> bool:
        """Check if operation affects an entire namespace."""
        operation = parsed.get("operation", "")
        args = parsed.get("args", [])

        # Delete without specific resource name (e.g., "kubectl delete pods")
        # vs with specific name (e.g., "kubectl delete pod my-pod")
        if operation == "delete":
            # If args contain singular resource type and no specific name
            # e.g., "kubectl delete pods" (not "delete pod my-pod")
            if len(args) >= 1 and args[0].endswith("s"):  # Plural form
                # No specific resource name means namespace-wide
                if len(args) == 1 or (len(args) > 1 and not args[1].startswith("-")):
                    return True

        # Rollout restart affects all pods in deployment
        if operation == "rollout" and "restart" in args:
            return True

        return False

    async def _calculate_resource_impacts(
        self,
        parsed: dict[str, Any],
        k8s_client: Any | None,
        dry_run: bool,
    ) -> list[ResourceImpact]:
        """Calculate impact on specific resource types.

        Args:
            parsed: Parsed command
            k8s_client: Optional Kubernetes client
            dry_run: If True, use heuristics instead of real queries

        Returns:
            List of ResourceImpact objects
        """
        impacts = []
        operation = parsed.get("operation", "")
        args = parsed.get("args", [])
        flags = parsed.get("flags", {})

        # Determine namespace
        namespace = flags.get("n") or flags.get("namespace")

        # Determine resource type from args
        resource_type = None
        if args:
            # First arg is usually the resource type
            resource_type = args[0]

        # If we have a k8s client and not in dry run, get actual counts
        if k8s_client and not dry_run:
            impacts = await self._get_real_resource_impacts(
                k8s_client, operation, resource_type, namespace, args
            )
        else:
            # Use heuristics based on command
            impacts = self._get_heuristic_impacts(operation, resource_type, namespace, args)

        return impacts

    async def _get_real_resource_impacts(
        self,
        k8s_client: Any,
        operation: str,
        resource_type: str | None,
        namespace: str | None,
        args: list[str],
    ) -> list[ResourceImpact]:
        """Get real resource counts from Kubernetes.

        Args:
            k8s_client: Kubernetes client instance
            operation: Operation being performed
            resource_type: Type of resource being affected
            namespace: Optional namespace scope
            args: Additional arguments

        Returns:
            List of ResourceImpact with real counts
        """
        impacts = []

        try:
            # Map common resource types to k8s client methods
            if resource_type in ("pods", "pod") or operation == "rollout":
                pods = await k8s_client.list_pods(namespace=namespace)
                impacts.append(ResourceImpact(
                    resource_type="pods",
                    affected_count=len(pods),
                    namespace=namespace,
                ))

            elif resource_type in ("deployments", "deployment", "deploy"):
                deployments = await k8s_client.list_deployments(namespace=namespace)
                impacts.append(ResourceImpact(
                    resource_type="deployments",
                    affected_count=len(deployments),
                    namespace=namespace,
                ))

            elif resource_type in ("services", "service", "svc"):
                services = await k8s_client.list_services(namespace=namespace)
                impacts.append(ResourceImpact(
                    resource_type="services",
                    affected_count=len(services),
                    namespace=namespace,
                ))

            elif resource_type in ("configmaps", "configmap", "cm"):
                configmaps = await k8s_client.list_configmaps(namespace=namespace)
                impacts.append(ResourceImpact(
                    resource_type="configmaps",
                    affected_count=len(configmaps),
                    namespace=namespace,
                ))

            elif resource_type in ("secrets", "secret"):
                secrets = await k8s_client.list_secrets(namespace=namespace)
                impacts.append(ResourceImpact(
                    resource_type="secrets",
                    affected_count=len(secrets),
                    namespace=namespace,
                ))

            else:
                # Unknown resource type, estimate conservatively
                impacts.append(ResourceImpact(
                    resource_type=resource_type or "resources",
                    affected_count=1,  # Conservative estimate
                    namespace=namespace,
                ))

        except Exception as e:
            logger.warning(f"Failed to get real resource counts: {e}")
            # Fall back to heuristic estimate
            impacts = self._get_heuristic_impacts(operation, resource_type, namespace, args)

        return impacts

    def _get_heuristic_impacts(
        self,
        operation: str,
        resource_type: str | None,
        namespace: str | None,
        args: list[str],
    ) -> list[ResourceImpact]:
        """Get heuristic impact estimates.

        Args:
            operation: Operation being performed
            resource_type: Type of resource being affected
            namespace: Optional namespace scope
            args: Additional arguments

        Returns:
            List of ResourceImpact with estimated counts
        """
        impacts = []

        # Check if targeting specific resource by name
        has_specific_name = False
        if len(args) > 1:
            # Second arg might be a specific resource name
            # (not a flag or value)
            for arg in args[1:]:
                if not arg.startswith("-") and "=" not in arg:
                    has_specific_name = True
                    break

        if has_specific_name:
            # Targeting a specific resource, minimal impact
            impacts.append(ResourceImpact(
                resource_type=resource_type or "resource",
                affected_count=1,
                namespace=namespace,
            ))
        else:
            # Namespace-wide or broader operation
            # Use conservative estimates based on operation type
            if operation in ("delete", "remove") and resource_type:
                count = self.thresholds.heuristic_namespace_counts.get(
                    resource_type.lower(), 5
                )
                impacts.append(ResourceImpact(
                    resource_type=resource_type,
                    affected_count=count,
                    namespace=namespace,
                ))
            elif operation == "rollout" and "restart" in args:
                # Rollout restart affects deployment's pods
                impacts.append(ResourceImpact(
                    resource_type="pods",
                    affected_count=self.thresholds.heuristic_rollout_pods,
                    namespace=namespace,
                ))
            else:
                # Default estimate
                impacts.append(ResourceImpact(
                    resource_type=resource_type or "resources",
                    affected_count=1,
                    namespace=namespace,
                ))

        return impacts

    def _determine_impact_level(
        self,
        total_affected: int,
        is_cluster_wide: bool,
        is_namespace_wide: bool,
    ) -> ImpactLevel:
        """Determine the impact level based on factors.

        Args:
            total_affected: Total number of affected resources
            is_cluster_wide: Whether operation is cluster-wide
            is_namespace_wide: Whether operation is namespace-wide

        Returns:
            ImpactLevel classification
        """
        # Cluster-wide operations are always critical
        if is_cluster_wide and self.thresholds.cluster_wide_always_critical:
            return ImpactLevel.CRITICAL

        # Namespace-wide operations can be critical if configured
        if is_namespace_wide and self.thresholds.namespace_wide_critical:
            if total_affected > self.thresholds.medium_max:
                return ImpactLevel.CRITICAL

        # Determine based on resource count
        if total_affected <= self.thresholds.low_max:
            return ImpactLevel.LOW
        elif total_affected <= self.thresholds.medium_max:
            return ImpactLevel.MEDIUM
        elif total_affected <= self.thresholds.high_max:
            return ImpactLevel.HIGH
        else:
            return ImpactLevel.CRITICAL

    def _identify_risk_factors(
        self,
        parsed: dict[str, Any],
        total_affected: int,
        is_cluster_wide: bool,
        is_namespace_wide: bool,
    ) -> list[str]:
        """Identify risk factors for the action.

        Args:
            parsed: Parsed command
            total_affected: Total affected resources
            is_cluster_wide: Whether operation is cluster-wide
            is_namespace_wide: Whether operation is namespace-wide

        Returns:
            List of identified risk factors
        """
        risks = []
        operation = parsed.get("operation", "")
        tool = parsed.get("tool", "")

        if is_cluster_wide:
            risks.append("Cluster-wide operation - affects all namespaces")

        if is_namespace_wide:
            risks.append("Namespace-wide operation - affects all resources in namespace")

        if operation in ("delete", "remove", "uninstall"):
            risks.append("Destructive operation - resources will be deleted")

        if total_affected > self.thresholds.high_max:
            risks.append(f"High resource count ({total_affected} resources affected)")

        # Tool-specific risks
        if tool == "helm" and operation == "uninstall":
            risks.append("Helm uninstall - removes release and all associated resources")

        if tool == "kubectl" and operation == "delete":
            flags = parsed.get("flags", {})
            if "f" in flags or "filename" in flags:
                risks.append("Delete from file - batch operation")

        # Check for force flags
        flags = parsed.get("flags", {})
        if flags.get("force") or flags.get("grace-period") == "0":
            risks.append("Force operation - no graceful shutdown")

        return risks

    def _generate_recommendations(
        self,
        impact_level: ImpactLevel,
        risk_factors: list[str],
        parsed: dict[str, Any],
    ) -> list[str]:
        """Generate safety recommendations based on impact.

        Args:
            impact_level: Calculated impact level
            risk_factors: Identified risk factors
            parsed: Parsed command

        Returns:
            List of safety recommendations
        """
        recommendations = []

        # Based on impact level
        if impact_level == ImpactLevel.CRITICAL:
            recommendations.append("Require additional approval for critical impact")
            recommendations.append("Consider performing during maintenance window")

        if impact_level in (ImpactLevel.HIGH, ImpactLevel.CRITICAL):
            recommendations.append("Review affected resources before execution")
            recommendations.append("Ensure rollback plan is in place")

        # Based on risk factors
        if any("delete" in r.lower() for r in risk_factors):
            recommendations.append("Verify resource names to avoid accidental deletion")
            recommendations.append("Consider backup before deletion")

        if any("namespace-wide" in r.lower() for r in risk_factors):
            recommendations.append("Test in non-production namespace first")

        if any("cluster-wide" in r.lower() for r in risk_factors):
            recommendations.append("Executive approval required for cluster-wide changes")
            recommendations.append("Notify all teams of potential impact")

        # Operation-specific recommendations
        operation = parsed.get("operation", "")
        if operation == "rollout" and "restart" in parsed.get("args", []):
            recommendations.append("Monitor application health after restart")

        return recommendations

    def _estimate_duration(
        self,
        parsed: dict[str, Any],
        total_affected: int,
    ) -> float:
        """Estimate execution duration in seconds.

        Args:
            parsed: Parsed command
            total_affected: Total affected resources

        Returns:
            Estimated duration in seconds
        """
        operation = parsed.get("operation", "")
        tool = parsed.get("tool", "")

        # Base duration per operation type
        base_durations = {
            "get": 2.0,
            "describe": 3.0,
            "logs": 5.0,
            "delete": 5.0 + (total_affected * 0.5),
            "apply": 10.0 + (total_affected * 0.3),
            "create": 10.0 + (total_affected * 0.5),
            "rollout": 15.0 + (total_affected * 1.0),  # Restart takes time
            "scale": 10.0 + (total_affected * 0.5),
            "exec": 5.0,
            "list": 2.0,
            "install": 30.0,
            "upgrade": 45.0,
            "uninstall": 20.0,
        }

        base = base_durations.get(operation, 10.0)

        # Helm and ArgoCD operations typically take longer
        if tool == "helm":
            base *= 1.5
        elif tool == "argocd":
            base *= 2.0

        return min(base, 600.0)  # Cap at 10 minutes

    def update_thresholds(self, thresholds: ImpactThresholds) -> None:
        """Update impact thresholds.

        Args:
            thresholds: New thresholds to apply
        """
        self.thresholds = thresholds


# Global singleton instance
_impact_estimator: ImpactEstimator | None = None


def get_impact_estimator(thresholds: ImpactThresholds | None = None) -> ImpactEstimator:
    """Get or create the global ImpactEstimator instance.

    Args:
        thresholds: Optional thresholds to use on first creation

    Returns:
        The ImpactEstimator singleton instance
    """
    global _impact_estimator
    if _impact_estimator is None:
        _impact_estimator = ImpactEstimator(thresholds)
    elif thresholds:
        _impact_estimator.update_thresholds(thresholds)
    return _impact_estimator

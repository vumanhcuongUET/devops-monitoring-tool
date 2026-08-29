"""Resource limiter for checking cluster resources before action execution."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """Types of cluster resources."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    PODS = "pods"


@dataclass
class ResourceThreshold:
    """Threshold configuration for a resource type."""
    resource_type: ResourceType
    warning_percent: float = 70.0  # Warning at this % of capacity
    critical_percent: float = 85.0  # Block actions at this % of capacity
    emergency_reserve: float = 10.0  # Always keep this % free


@dataclass
class ResourceStatus:
    """Current status of cluster resources."""
    resource_type: ResourceType
    total_capacity: float  # Total capacity in resource units
    used_capacity: float  # Currently used capacity
    available_capacity: float  # Available capacity
    usage_percent: float  # Percentage used
    status: str  # "healthy", "warning", "critical"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ResourceCheckResult:
    """Result of a resource limit check."""
    allowed: bool
    reason: str
    resource_statuses: list[ResourceStatus]
    blocking_resource: ResourceType | None = None
    recommendations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ResourceLimiter:
    """Check cluster resources before action execution.

    This class provides:
    - CPU/memory/disk capacity checking
    - Pod count limits
    - Configurable thresholds
    - Resource status reporting
    """

    def __init__(self):
        """Initialize the resource limiter."""
        self._thresholds: dict[ResourceType, ResourceThreshold] = {}
        self._load_default_thresholds()

    def _load_default_thresholds(self):
        """Load default resource thresholds."""
        self._thresholds[ResourceType.CPU] = ResourceThreshold(
            resource_type=ResourceType.CPU,
            warning_percent=70.0,
            critical_percent=85.0,
            emergency_reserve=10.0,
        )
        self._thresholds[ResourceType.MEMORY] = ResourceThreshold(
            resource_type=ResourceType.MEMORY,
            warning_percent=70.0,
            critical_percent=85.0,
            emergency_reserve=10.0,
        )
        self._thresholds[ResourceType.DISK] = ResourceThreshold(
            resource_type=ResourceType.DISK,
            warning_percent=80.0,
            critical_percent=90.0,
            emergency_reserve=5.0,
        )
        self._thresholds[ResourceType.PODS] = ResourceThreshold(
            resource_type=ResourceType.PODS,
            warning_percent=70.0,
            critical_percent=85.0,
            emergency_reserve=10.0,
        )

    def set_threshold(self, threshold: ResourceThreshold) -> None:
        """Set a custom resource threshold.

        Args:
            threshold: ResourceThreshold to set
        """
        self._thresholds[threshold.resource_type] = threshold
        logger.info(f"Updated threshold for {threshold.resource_type.value}")

    def get_threshold(self, resource_type: ResourceType) -> ResourceThreshold | None:
        """Get the threshold for a resource type.

        Args:
            resource_type: Type of resource

        Returns:
            ResourceThreshold or None
        """
        return self._thresholds.get(resource_type)

    def check_resources(
        self,
        k8s_client: Any,
        check_types: list[ResourceType] | None = None,
    ) -> ResourceCheckResult:
        """Check if cluster has sufficient resources for action execution.

        Args:
            k8s_client: Kubernetes client for querying resources
            check_types: List of resource types to check (defaults to all)

        Returns:
            ResourceCheckResult with check details
        """
        if check_types is None:
            check_types = list(ResourceType)

        resource_statuses = []
        blocking_resource = None
        recommendations = []

        for resource_type in check_types:
            try:
                status = self._get_resource_status(k8s_client, resource_type)
                resource_statuses.append(status)

                # Check if this resource blocks execution
                threshold = self._thresholds.get(resource_type)
                if threshold and status.usage_percent >= threshold.critical_percent:
                    blocking_resource = resource_type
                    recommendations.append(
                        f"{resource_type.value.upper()} usage at {status.usage_percent:.1f}% exceeds critical threshold {threshold.critical_percent}%"
                    )

            except Exception as e:
                logger.warning(f"Failed to check {resource_type.value}: {e}")
                # Create an unknown status
                resource_statuses.append(ResourceStatus(
                    resource_type=resource_type,
                    total_capacity=0,
                    used_capacity=0,
                    available_capacity=0,
                    usage_percent=0,
                    status="unknown",
                ))

        allowed = blocking_resource is None

        # Generate general recommendations if needed
        if not allowed:
            recommendations.insert(0, "Cluster resources are at critical capacity. Postpone non-urgent actions.")
        else:
            # Check for warnings
            for status in resource_statuses:
                threshold = self._thresholds.get(status.resource_type)
                if threshold and status.usage_percent >= threshold.warning_percent:
                    recommendations.append(
                        f"{status.resource_type.value.upper()} usage elevated at {status.usage_percent:.1f}%"
                    )

        return ResourceCheckResult(
            allowed=allowed,
            reason="Resource check passed" if allowed else f"Blocked by {blocking_resource.value if blocking_resource else 'unknown'} resource limit",
            resource_statuses=resource_statuses,
            blocking_resource=blocking_resource,
            recommendations=recommendations,
        )

    def _get_resource_status(
        self,
        k8s_client: Any,
        resource_type: ResourceType,
    ) -> ResourceStatus:
        """Get current status of a resource type.

        Args:
            k8s_client: Kubernetes client
            resource_type: Type of resource to check

        Returns:
            ResourceStatus with current metrics
        """
        if resource_type == ResourceType.PODS:
            return self._get_pod_status(k8s_client)
        elif resource_type == ResourceType.CPU:
            return self._get_cpu_status(k8s_client)
        elif resource_type == ResourceType.MEMORY:
            return self._get_memory_status(k8s_client)
        elif resource_type == ResourceType.DISK:
            return self._get_disk_status(k8s_client)
        else:
            return ResourceStatus(
                resource_type=resource_type,
                total_capacity=0,
                used_capacity=0,
                available_capacity=0,
                usage_percent=0,
                status="unknown",
            )

    def _get_pod_status(self, k8s_client: Any) -> ResourceStatus:
        """Get pod resource status."""
        try:
            nodes = k8s_client.list_nodes()
            pods = k8s_client.list_pods()

            # Calculate pod capacity from nodes
            total_capacity = 0
            used_capacity = len(pods)

            for node in nodes:
                # Get pod capacity from node status
                capacity = node.get("capacity", {}).get("pods", "110")
                try:
                    total_capacity += int(capacity)
                except (ValueError, TypeError):
                    total_capacity += 110  # Default Kubernetes capacity

            if total_capacity == 0:
                total_capacity = 110 * len(nodes) if nodes else 110

            available_capacity = max(0, total_capacity - used_capacity)
            usage_percent = (used_capacity / total_capacity * 100) if total_capacity > 0 else 0

            threshold = self._thresholds.get(ResourceType.PODS)
            status = "healthy"
            if threshold and usage_percent >= threshold.critical_percent:
                status = "critical"
            elif threshold and usage_percent >= threshold.warning_percent:
                status = "warning"

            return ResourceStatus(
                resource_type=ResourceType.PODS,
                total_capacity=total_capacity,
                used_capacity=used_capacity,
                available_capacity=available_capacity,
                usage_percent=usage_percent,
                status=status,
            )

        except Exception as e:
            logger.error(f"Failed to get pod status: {e}")
            raise

    def _get_cpu_status(self, k8s_client: Any) -> ResourceStatus:
        """Get CPU resource status."""
        try:
            nodes = k8s_client.list_nodes()

            total_capacity = 0.0
            used_capacity = 0.0

            for node in nodes:
                # Get CPU capacity (in cores or millicores)
                capacity_str = node.get("capacity", {}).get("cpu", "0")
                allocatable_str = node.get("allocatable", {}).get("cpu", "0")

                # Convert to cores
                capacity_cores = self._parse_cpu_resource(capacity_str)
                allocatable_cores = self._parse_cpu_resource(allocatable_str)

                # Estimate used = total - allocatable
                used_cores = capacity_cores - allocatable_cores

                total_capacity += capacity_cores
                used_capacity += used_cores

            if total_capacity == 0:
                return ResourceStatus(
                    resource_type=ResourceType.CPU,
                    total_capacity=0,
                    used_capacity=0,
                    available_capacity=0,
                    usage_percent=0,
                    status="unknown",
                )

            available_capacity = max(0, total_capacity - used_capacity)
            usage_percent = (used_capacity / total_capacity * 100) if total_capacity > 0 else 0

            threshold = self._thresholds.get(ResourceType.CPU)
            status = "healthy"
            if threshold and usage_percent >= threshold.critical_percent:
                status = "critical"
            elif threshold and usage_percent >= threshold.warning_percent:
                status = "warning"

            return ResourceStatus(
                resource_type=ResourceType.CPU,
                total_capacity=total_capacity,
                used_capacity=used_capacity,
                available_capacity=available_capacity,
                usage_percent=usage_percent,
                status=status,
            )

        except Exception as e:
            logger.error(f"Failed to get CPU status: {e}")
            raise

    def _get_memory_status(self, k8s_client: Any) -> ResourceStatus:
        """Get memory resource status."""
        try:
            nodes = k8s_client.list_nodes()

            total_capacity = 0.0
            used_capacity = 0.0

            for node in nodes:
                # Get memory capacity (in bytes)
                capacity_str = node.get("capacity", {}).get("memory", "0")
                allocatable_str = node.get("allocatable", {}).get("memory", "0")

                # Convert to bytes
                capacity_bytes = self._parse_memory_resource(capacity_str)
                allocatable_bytes = self._parse_memory_resource(allocatable_str)

                # Estimate used = total - allocatable
                used_bytes = capacity_bytes - allocatable_bytes

                total_capacity += capacity_bytes
                used_capacity += used_bytes

            if total_capacity == 0:
                return ResourceStatus(
                    resource_type=ResourceType.MEMORY,
                    total_capacity=0,
                    used_capacity=0,
                    available_capacity=0,
                    usage_percent=0,
                    status="unknown",
                )

            available_capacity = max(0, total_capacity - used_capacity)
            usage_percent = (used_capacity / total_capacity * 100) if total_capacity > 0 else 0

            threshold = self._thresholds.get(ResourceType.MEMORY)
            status = "healthy"
            if threshold and usage_percent >= threshold.critical_percent:
                status = "critical"
            elif threshold and usage_percent >= threshold.warning_percent:
                status = "warning"

            return ResourceStatus(
                resource_type=ResourceType.MEMORY,
                total_capacity=total_capacity,
                used_capacity=used_capacity,
                available_capacity=available_capacity,
                usage_percent=usage_percent,
                status=status,
            )

        except Exception as e:
            logger.error(f"Failed to get memory status: {e}")
            raise

    def _get_disk_status(self, k8s_client: Any) -> ResourceStatus:
        """Get disk resource status."""
        # Disk status requires node metrics or external monitoring
        # Return a placeholder for now
        return ResourceStatus(
            resource_type=ResourceType.DISK,
            total_capacity=0,
            used_capacity=0,
            available_capacity=0,
            usage_percent=0,
            status="unknown",
        )

    def _parse_cpu_resource(self, resource_str: str) -> float:
        """Parse CPU resource string to cores.

        Args:
            resource_str: CPU resource string (e.g., "4", "4000m")

        Returns:
            CPU cores as float
        """
        if not resource_str:
            return 0.0

        resource_str = resource_str.strip().lower()

        if resource_str.endswith("m"):
            # Millicores
            try:
                millicores = int(resource_str[:-1])
                return millicores / 1000.0
            except (ValueError, TypeError):
                return 0.0
        else:
            # Cores
            try:
                return float(resource_str)
            except (ValueError, TypeError):
                return 0.0

    def _parse_memory_resource(self, resource_str: str) -> float:
        """Parse memory resource string to bytes.

        Args:
            resource_str: Memory resource string (e.g., "16Gi", "16384Mi")

        Returns:
            Memory bytes as float
        """
        if not resource_str:
            return 0.0

        resource_str = resource_str.strip().upper()

        # Map suffixes to multipliers
        multipliers = {
            "K": 1024,
            "KI": 1024,
            "M": 1024 ** 2,
            "MI": 1024 ** 2,
            "G": 1024 ** 3,
            "GI": 1024 ** 3,
            "T": 1024 ** 4,
            "TI": 1024 ** 4,
        }

        # Find the suffix
        for suffix, multiplier in multipliers.items():
            if resource_str.endswith(suffix):
                try:
                    value = float(resource_str[:-len(suffix)])
                    return value * multiplier
                except (ValueError, TypeError):
                    return 0.0

        # No suffix - assume bytes
        try:
            return float(resource_str)
        except (ValueError, TypeError):
            return 0.0

    def get_all_thresholds(self) -> dict[ResourceType, ResourceThreshold]:
        """Get all resource thresholds.

        Returns:
            Dict of resource type to threshold
        """
        return self._thresholds.copy()


# Global singleton instance
_resource_limiter: ResourceLimiter | None = None


def get_resource_limiter() -> ResourceLimiter:
    """Get or create the global ResourceLimiter instance.

    Returns:
        The ResourceLimiter singleton instance
    """
    global _resource_limiter
    if _resource_limiter is None:
        _resource_limiter = ResourceLimiter()
    return _resource_limiter

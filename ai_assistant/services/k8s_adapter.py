"""
Kubernetes Adapter for AI Assistant.

Provides sync wrapper around async KubernetesClient from backend.

Architecture Note:
This adapter uses sys.path manipulation to import backend clients.
See docs/adr/001-backend-integration-via-sys-path.md for rationale.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend to Python path
# NOTE: This is an intentional integration pattern for the monorepo.
# If backend/ moves, update this path. See ADR 001.
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from app.services.kubernetes_client import KubernetesClient
    BACKEND_AVAILABLE = True
except ImportError:
    BACKEND_AVAILABLE = False

# Import sync_bridge (handle both relative and absolute import)
try:
    from ..core.sync_bridge import sync_async_bridge
except ImportError:
    # Fallback when run as script or tests
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.sync_bridge import sync_async_bridge


class KubernetesAdapter:
    """
    Sync adapter for async KubernetesClient.

    Allows ai_assistant to use backend's K8s client for
    pod, deployment, and cluster status.
    """

    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize adapter.

        Args:
            fallback_enabled: If True, returns empty results if backend unavailable
        """
        self._client = None
        self._fallback_enabled = fallback_enabled

        if not BACKEND_AVAILABLE and not fallback_enabled:
            raise RuntimeError(f"{type(self).__name__}: backend client unavailable and fallback disabled")

        if BACKEND_AVAILABLE:
            try:
                self._client = KubernetesClient()
            except Exception as e:
                if not fallback_enabled:
                    raise RuntimeError(f"Failed to initialize KubernetesClient: {e}") from e

    @property
    def available(self) -> bool:
        """Check if backend client is available."""
        return self._client is not None

    @sync_async_bridge
    async def list_pods(
        self,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List pods in namespace(s).

        Args:
            namespace: Specific namespace (None = all namespaces)

        Returns:
            List of pod dictionaries
        """
        if not self.available:
            return []

        return await self._client.list_pods()

    @sync_async_bridge
    async def list_deployments(
        self,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List deployments in namespace(s).

        Args:
            namespace: Specific namespace (None = all namespaces)

        Returns:
            List of deployment dictionaries
        """
        if not self.available:
            return []

        return await self._client.list_deployments()

    @sync_async_bridge
    async def list_nodes(self) -> List[Dict[str, Any]]:
        """
        List cluster nodes.

        Returns:
            List of node dictionaries
        """
        if not self.available:
            return []

        return await self._client.list_nodes()

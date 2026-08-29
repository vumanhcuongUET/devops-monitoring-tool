"""
APM Adapter for AI Assistant.

Provides sync wrapper around async ApmClient from backend.

Architecture Note:
This adapter uses sys.path manipulation to import backend clients.
See docs/adr/001-backend-integration-via-sys-path.md for rationale.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

# Add backend to Python path
# NOTE: This is an intentional integration pattern for the monorepo.
# If backend/ moves, update this path. See ADR 001.
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from app.services.apm_client import ApmClient
    from app.services.elasticsearch_client import ElasticsearchClient
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


class ApmAdapter:
    """
    Sync adapter for async ApmClient.

    Allows ai_assistant to use backend's APM client for
    transaction and error analysis.
    """

    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize adapter.

        Args:
            fallback_enabled: If True, falls back to direct HTTP if backend unavailable
        """
        self._client = None
        self._fallback_enabled = fallback_enabled

        if not BACKEND_AVAILABLE and not fallback_enabled:
            raise RuntimeError(f"{type(self).__name__}: backend client unavailable and fallback disabled")

        if BACKEND_AVAILABLE:
            try:
                # APM client depends on ES client
                es_client = ElasticsearchClient()
                self._client = ApmClient(es_client=es_client)
            except Exception as e:
                if not fallback_enabled:
                    raise RuntimeError(f"Failed to initialize ApmClient: {e}") from e

    @property
    def available(self) -> bool:
        """Check if backend client is available."""
        return self._client is not None

    @sync_async_bridge
    async def get_transactions(
        self,
        service_name: str,
        size: int = 10
    ) -> Dict[str, Any]:
        """
        Get recent transactions for a service.

        Args:
            service_name: Service to query
            size: Maximum number of results

        Returns:
            Transaction data dictionary
        """
        if not self.available:
            return {"transactions": []}

        return await self._client.get_transactions()

    @sync_async_bridge
    async def get_errors(
        self,
        service_name: Optional[str] = None,
        size: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent errors.

        Args:
            service_name: Filter by service (optional)
            size: Maximum number of results

        Returns:
            List of error dictionaries
        """
        if not self.available:
            return []

        errors = await self._client.get_errors()
        # size=None (default) returns the unbounded result set; the old
        # default of 10 made the unbounded branch unreachable (review F3).
        return errors[:size] if size else errors

    @sync_async_bridge
    async def get_summary(self) -> Dict[str, Any]:
        """
        Get APM summary metrics.

        Returns:
            Summary with latency, throughput, error rate
        """
        if not self.available:
            return {
                "latency_p50": 0,
                "latency_p95": 0,
                "latency_p99": 0,
                "error_rate_percent": 0,
                "throughput": 0
            }

        return await self._client.get_summary()

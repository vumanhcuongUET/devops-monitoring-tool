"""
Prometheus Adapter for AI Assistant.

Provides sync wrapper around async PrometheusClient from backend.

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
    from app.services.prometheus_client import PrometheusClient
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


class PrometheusAdapter:
    """
    Sync adapter for async PrometheusClient.

    Allows ai_assistant to use backend's Prometheus client
    with proper connection handling.
    """

    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize adapter.

        Args:
            fallback_enabled: If True, falls back to direct HTTP if backend unavailable
        """
        self._client = None
        self._fallback_enabled = fallback_enabled

        if BACKEND_AVAILABLE:
            try:
                self._client = PrometheusClient()
            except Exception as e:
                if not fallback_enabled:
                    raise RuntimeError(f"Failed to initialize PrometheusClient: {e}")

    @property
    def available(self) -> bool:
        """Check if backend client is available."""
        return self._client is not None

    @sync_async_bridge
    async def query(self, promql: str) -> Dict[str, Any]:
        """
        Execute instant query.

        Args:
            promql: PromQL query string

        Returns:
            Query results dictionary
        """
        if not self.available:
            raise RuntimeError("PrometheusClient not available")

        result = await self._client._query(promql)
        return result

    @sync_async_bridge
    async def query_range(
        self,
        promql: str,
        start: str,
        end: str,
        step: str
    ) -> Dict[str, Any]:
        """
        Execute range query.

        Args:
            promql: PromQL query string
            start: Start timestamp (RFC3339)
            end: End timestamp (RFC3339)
            step: Query step duration

        Returns:
            Query results dictionary
        """
        if not self.available:
            raise RuntimeError("PrometheusClient not available")

        result = await self._client._query_range(promql, start, end, step)
        return result

    @sync_async_bridge
    async def get_alerts(self) -> List[Dict[str, Any]]:
        """
        Get current firing alerts.

        Returns:
            List of alert dictionaries
        """
        if not self.available:
            return []

        return await self._client.get_alerts()

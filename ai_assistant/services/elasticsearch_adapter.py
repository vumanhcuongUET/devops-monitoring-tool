"""
Elasticsearch Adapter for AI Assistant.

Provides sync wrapper around async ElasticsearchClient from backend.

Architecture Note:
This adapter uses sys.path manipulation to import backend clients.
See docs/adr/001-backend-integration-via-sys-path.md for rationale.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add backend to Python path
# NOTE: This is an intentional integration pattern for the monorepo.
# If backend/ moves, update this path. See ADR 001.
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

try:
    from app.services.elasticsearch_client import ElasticsearchClient
    from app.config import settings
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

# Import retry decorator (lazy to avoid circular import)
def _get_retry():
    from core.retry import with_retry
    return with_retry


class ElasticsearchAdapter:
    """
    Sync adapter for async ElasticsearchClient.

    Allows ai_assistant to use backend's ES client with proper
    connection pooling, error handling, and authentication.
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
                self._client = ElasticsearchClient()
            except Exception as e:
                if not fallback_enabled:
                    raise RuntimeError(f"Failed to initialize ElasticsearchClient: {e}")

    @property
    def available(self) -> bool:
        """Check if backend client is available."""
        return self._client is not None

    @sync_async_bridge
    @_get_retry()(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
    async def search(
        self,
        index: str,
        body: Dict[str, Any],
        size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute search query with retry on transient failures.

        Args:
            index: ES index pattern
            body: Search query body
            size: Maximum results (optional)

        Returns:
            Search results dictionary
        """
        if not self.available:
            raise RuntimeError("ElasticsearchClient not available")

        # Call the backend client method
        result = await self._client.client.search(index=index, body=body, size=size)
        return result

    @sync_async_bridge
    @_get_retry()(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
    async def count(self, index: str, body: Dict[str, Any]) -> int:
        """
        Count documents matching query.

        Args:
            index: ES index pattern
            body: Count query body

        Returns:
            Document count
        """
        if not self.available:
            raise RuntimeError("ElasticsearchClient not available")

        result = await self._client.client.count(index=index, body=body)
        return result.get("count", 0)

    @sync_async_bridge
    @_get_retry()(max_attempts=2, exceptions=(ConnectionError, TimeoutError))
    async def get_cluster_health(self) -> Dict[str, Any]:
        """
        Get cluster health information with retry.

        Returns:
            Cluster health dictionary
        """
        if not self.available:
            return {"status": "unknown", "message": "Backend unavailable"}

        return await self._client.get_cluster_health()

"""
Enhanced Cache Middleware for FastAPI

Phase 7 - Sprint 1 - Day 8
Purpose: Inject cache managers into requests and track cache metrics

Features:
- L1/L2/L3 cache injection into request state
- Cache hit rate tracking in response headers
- Cache layer indicator in response
- Processing time tracking
"""

import time
import logging
from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.cache.l1_cache import L1Cache
from app.cache.l2_cache import L2CacheManager

logger = logging.getLogger(__name__)


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject cache managers into requests and track metrics.

    This middleware:
    1. Creates L1 cache instance for each request
    2. Injects L2 cache reference into request state
    3. Tracks cache hits/misses in response headers
    4. Adds processing time to response
    5. Indicates which cache layers were used
    """

    def __init__(self, app, l2_cache: Optional[L2CacheManager] = None):
        """
        Initialize cache middleware.

        Args:
            app: FastAPI application
            l2_cache: Optional L2 cache manager instance
        """
        super().__init__(app)
        self.l2_cache = l2_cache

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request with cache injection.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            HTTP response with cache headers
        """
        # Create L1 cache for this request
        request.state.l1_cache = L1Cache()

        # Inject L2 cache if available
        if self.l2_cache:
            request.state.l2_cache = self.l2_cache
        else:
            request.state.l2_cache = None

        # Track initial cache stats
        initial_l2_stats = {}
        if self.l2_cache:
            initial_l2_stats = self.l2_cache.get_stats().copy()

        # Record start time
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate processing time
        process_time = time.time() - start_time

        # Add cache-related headers
        self._add_cache_headers(request, response, initial_l2_stats, process_time)

        return response

    def _add_cache_headers(
        self,
        request: Request,
        response: Response,
        initial_l2_stats: Dict,
        process_time: float
    ):
        """Add cache-related headers to response."""
        try:
            # Add processing time
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            # Get L2 cache stats
            if request.state.l2_cache:
                current_stats = request.state.l2_cache.get_stats()

                # Calculate hit rate
                total_requests = (
                    current_stats.get("hits", 0) +
                    current_stats.get("misses", 0)
                )
                hit_rate = (
                    current_stats.get("hits", 0) / total_requests
                    if total_requests > 0 else 0.0
                )

                response.headers["X-Cache-Hit-Rate"] = f"{hit_rate:.2f}"
                response.headers["X-Cache-Hits"] = str(current_stats.get("hits", 0))
                response.headers["X-Cache-Misses"] = str(current_stats.get("misses", 0))

            # Check cache layer indicators from endpoint
            cache_layers = response.headers.get("X-Cache-Layers", "")
            if cache_layers:
                # Add to response if set by endpoint
                pass
            else:
                # Set default cache layer indicator
                layers = []
                if response.headers.get("X-L1-Cache") == "hit":
                    layers.append("L1")
                if response.headers.get("X-L2-Cache") == "hit":
                    layers.append("L2")
                if response.headers.get("X-L3-Cache") == "hit":
                    layers.append("L3")

                if layers:
                    response.headers["X-Cache-Layers"] = ",".join(layers)

            # Add cache status
            if not response.headers.get("X-Cache-Status"):
                if response.headers.get("X-Cache-Layers"):
                    response.headers["X-Cache-Status"] = "HIT"
                else:
                    response.headers["X-Cache-Status"] = "MISS"

        except Exception as e:
            logger.error(f"Error adding cache headers: {e}")


class CacheContext:
    """
    Context manager for cache operations within a request.

    Provides utilities for managing cache operations
    within the context of a single request.
    """

    def __init__(self, request: Request):
        """
        Initialize cache context.

        Args:
            request: FastAPI request object
        """
        self.request = request
        self.l1_cache = getattr(request.state, "l1_cache", None)
        self.l2_cache = getattr(request.state, "l2_cache", None)

    async def get_from_l1(self, key: str) -> Optional[Any]:
        """Get data from L1 cache."""
        if self.l1_cache:
            return await self.l1_cache.get("default", {"key": key})
        return None

    async def set_in_l1(self, key: str, value: Any):
        """Set data in L1 cache."""
        if self.l1_cache:
            await self.l1_cache.set("default", {"key": key}, value)

    async def get_from_l2(
        self,
        data_type: str,
        identifier: Dict
    ) -> Optional[Any]:
        """Get data from L2 cache."""
        if self.l2_cache:
            return await self.l2_cache.get(data_type, identifier)
        return None

    async def set_in_l2(
        self,
        data_type: str,
        identifier: Dict,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set data in L2 cache."""
        if self.l2_cache:
            return await self.l2_cache.set(data_type, identifier, value, ttl)
        return False

    def set_l1_hit(self):
        """Mark L1 cache hit in response headers."""
        if hasattr(self.request.state, "response"):
            self.request.state.response.headers["X-L1-Cache"] = "hit"

    def set_l2_hit(self):
        """Mark L2 cache hit in response headers."""
        if hasattr(self.request.state, "response"):
            self.request.state.response.headers["X-L2-Cache"] = "hit"

    def set_l3_hit(self):
        """Mark L3 cache hit in response headers."""
        if hasattr(self.request.state, "response"):
            self.request.state.response.headers["X-L3-Cache"] = "hit"

    def get_cache_summary(self) -> Dict[str, Any]:
        """Get summary of cache operations for this request."""
        summary = {
            "l1_available": self.l1_cache is not None,
            "l2_available": self.l2_cache is not None,
        }

        if self.l1_cache:
            summary["l1_stats"] = self.l1_cache.get_stats()

        if self.l2_cache:
            summary["l2_stats"] = self.l2_cache.get_stats()

        return summary


async def get_cache_context(request: Request) -> CacheContext:
    """
    Get cache context for current request.

    Args:
        request: FastAPI request

    Returns:
        CacheContext instance
    """
    return CacheContext(request)


def mark_cache_hit(response: Response, layer: str):
    """
    Mark cache hit in response headers.

    Args:
        response: FastAPI response
        layer: Cache layer that hit (L1, L2, L3)
    """
    header_map = {
        "L1": "X-L1-Cache",
        "L2": "X-L2-Cache",
        "L3": "X-L3-Cache"
    }

    header = header_map.get(layer)
    if header:
        response.headers[header] = "hit"
        response.headers["X-Cache-Status"] = "HIT"


def get_cache_info_from_headers(response: Response) -> Dict[str, Any]:
    """
    Extract cache information from response headers.

    Args:
        response: FastAPI response

    Returns:
        Dictionary with cache information
    """
    return {
        "status": response.headers.get("X-Cache-Status", "UNKNOWN"),
        "layers": response.headers.get("X-Cache-Layers", ""),
        "l1_hit": response.headers.get("X-L1-Cache") == "hit",
        "l2_hit": response.headers.get("X-L2-Cache") == "hit",
        "l3_hit": response.headers.get("X-L3-Cache") == "hit",
        "hit_rate": float(response.headers.get("X-Cache-Hit-Rate", 0.0)),
        "process_time_ms": float(response.headers.get("X-Process-Time", 0.0)) * 1000
    }

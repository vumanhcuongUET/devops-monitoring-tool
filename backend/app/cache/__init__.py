"""
Phase 7 - Multi-Layer Caching Implementation

This module implements the three-layer caching strategy:
- L1: In-memory, per-request cache (deduplication within single request)
- L2: Redis distributed cache (5-15 minute TTL)
- L3: Semantic cache (pattern-based, 1-24 hour TTL)

Author: Phase 7 Sprint 1
Date: 2026-08-23
"""

from .config import CacheSettings, cache_settings, get_cache_settings
from .l1_cache import L1Cache, RequestCacheMiddleware, cached
from .l2_cache import L2CacheManager, SerializationFormat, create_l2_cache_from_env
from .single_flight import SingleFlight, single_flight

__all__ = [
    # L1 Cache
    "L1Cache",
    "cached",
    "RequestCacheMiddleware",
    # L2 Cache
    "L2CacheManager",
    "SerializationFormat",
    "create_l2_cache_from_env",
    # Single Flight
    "SingleFlight",
    "single_flight",
    # Config
    "CacheSettings",
    "get_cache_settings",
    "cache_settings",
]

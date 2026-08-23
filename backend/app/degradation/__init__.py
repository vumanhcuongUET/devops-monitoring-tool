"""
Degradation Module - Phase 7 Sprint 2

This module provides graceful degradation capabilities for the DevOps monitoring platform:

- Priority-based data fetching (P0, P1, P2, P3)
- Critical data caching with auto-refresh
- Disaster Recovery mode handling (NORMAL, DEGRADED, EMERGENCY)
- On-call integration for mode transitions

Components:
- PriorityConfig: Priority configuration management
- PriorityQueue: Priority-based data fetching
- CriticalCache: Persistent critical data cache
- DRHandler: Disaster Recovery mode handler
"""

from app.degradation.priority_config import (
    Priority,
    PriorityConfig,
    PriorityConfigManager
)

from app.degradation.priority_queue import (
    PriorityDataFetcher,
    FetchResult
)

from app.degradation.critical_cache import (
    CriticalDataCache,
    CriticalDataEntry
)

from app.degradation.dr_handler import (
    DRMode,
    DRHandler,
    ModeTransition
)

__all__ = [
    # Priority Config
    "Priority",
    "PriorityConfig",
    "PriorityConfigManager",

    # Priority Queue
    "PriorityDataFetcher",
    "FetchResult",

    # Critical Cache
    "CriticalDataCache",
    "CriticalDataEntry",

    # DR Handler
    "DRMode",
    "DRHandler",
    "ModeTransition"
]

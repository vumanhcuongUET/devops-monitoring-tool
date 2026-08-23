"""
Critical Data Cache - Phase 7 Sprint 2 Day 13-14

Purpose: Persistent cache for critical data during outages with auto-refresh

Features:
- Persistent storage for critical data
- Auto-refresh every 5 minutes
- Stale data handling with age indicators
- TTL-based expiration
- Priority-based storage
- Background refresh tasks
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class DataFreshness(Enum):
    """Freshness levels for cached data."""
    FRESH = "fresh"  # < 5 minutes old
    STALE = "stale"  # 5-15 minutes old
    EXPIRED = "expired"  # > 15 minutes old


@dataclass
class CriticalDataEntry:
    """Entry in the critical data cache."""
    project: str
    source_name: str
    data: Any
    timestamp: str
    ttl_seconds: int = 900  # Default 15 minutes
    priority: str = "medium"
    last_refresh: str = field(default_factory=lambda: datetime.now().isoformat())
    refresh_count: int = 0
    version: int = 1

    def is_expired(self) -> bool:
        """Check if entry is expired."""
        created = datetime.fromisoformat(self.timestamp)
        return datetime.now() - created > timedelta(seconds=self.ttl_seconds)

    def get_age_seconds(self) -> int:
        """Get age of entry in seconds."""
        created = datetime.fromisoformat(self.timestamp)
        return int((datetime.now() - created).total_seconds())

    def get_freshness(self) -> DataFreshness:
        """Get freshness level of entry."""
        age = self.get_age_seconds()

        if age < 300:  # 5 minutes
            return DataFreshness.FRESH
        elif age < 900:  # 15 minutes
            return DataFreshness.STALE
        else:
            return DataFreshness.EXPIRED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CriticalDataEntry':
        """Create from dictionary."""
        return cls(**data)


class CriticalDataCache:
    """
    Persistent cache for critical data during outages.

    Features:
    - Redis-backed storage for persistence
    - Auto-refresh every 5 minutes
    - Stale data handling with age indicators
    - TTL-based expiration
    - Priority-based storage
    """

    # Default TTL for different data types
    DEFAULT_TTLS = {
        "health_endpoints": 300,  # 5 minutes
        "active_alerts": 300,  # 5 minutes
        "pod_status": 600,  # 10 minutes
        "metrics_current": 300,  # 5 minutes
        "deployment_status": 600,  # 10 minutes
        "slo_data": 900,  # 15 minutes
        "critical": 900,  # 15 minutes for critical data
    }

    def __init__(
        self,
        redis_client,
        auto_refresh: bool = True,
        refresh_interval: int = 300,  # 5 minutes
        key_prefix: str = "critical_cache"
    ):
        """
        Initialize critical data cache.

        Args:
            redis_client: Redis client instance
            auto_refresh: Enable auto-refresh of cached data
            refresh_interval: Refresh interval in seconds
            key_prefix: Prefix for Redis keys
        """
        self.redis = redis_client
        self.auto_refresh = auto_refresh
        self.refresh_interval = refresh_interval
        self.key_prefix = key_prefix

        # Background refresh task
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_callbacks: Dict[str, Callable] = {}

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "refreshes": 0,
            "expirations": 0
        }

        logger.info(
            f"CriticalDataCache initialized with auto_refresh={auto_refresh}, "
            f"refresh_interval={refresh_interval}s"
        )

    async def start(self):
        """Start the background refresh task."""
        if self.auto_refresh and not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._refresh_loop())
            logger.info("Started critical cache auto-refresh loop")

    async def stop(self):
        """Stop the background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped critical cache auto-refresh loop")

    async def _refresh_loop(self):
        """Background refresh loop."""
        while True:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self._refresh_all_entries()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")

    async def set_critical_data(
        self,
        project: str,
        source_name: str,
        data: Any,
        ttl: Optional[int] = None,
        priority: str = "medium"
    ) -> bool:
        """
        Store critical data in cache.

        Args:
            project: Project name
            source_name: Source/data name
            data: Data to store (must be JSON-serializable)
            ttl: TTL in seconds (None for default)
            priority: Priority level (low, medium, high, critical)

        Returns:
            True if successful
        """
        try:
            # Use default TTL if not specified
            if ttl is None:
                ttl = self.DEFAULT_TTLS.get(source_name, 900)

            entry = CriticalDataEntry(
                project=project,
                source_name=source_name,
                data=data,
                timestamp=datetime.now().isoformat(),
                ttl_seconds=ttl,
                priority=priority
            )

            # Store in Redis
            key = self._make_key(project, source_name)
            value = json.dumps(entry.to_dict())

            await self.redis.setex(
                key,
                ttl + 60,  # Add buffer to prevent premature expiration
                value
            )

            # Also store in index for this project
            await self._add_to_index(project, source_name)

            logger.debug(
                f"Stored critical data: {project}/{source_name} "
                f"(TTL={ttl}s, priority={priority})"
            )

            return True

        except Exception as e:
            logger.error(f"Error storing critical data {project}/{source_name}: {e}")
            return False

    async def get_critical_data(
        self,
        project: str,
        source_name: str,
        allow_stale: bool = True
    ) -> Optional[Any]:
        """
        Get critical data from cache.

        Args:
            project: Project name
            source_name: Source/data name
            allow_stale: Return stale data if available

        Returns:
            Cached data or None if not found/expired
        """
        try:
            key = self._make_key(project, source_name)
            value = await self.redis.get(key)

            if not value:
                self.stats["misses"] += 1
                return None

            entry = CriticalDataEntry.from_dict(json.loads(value))

            # Check if expired
            if entry.is_expired() and not allow_stale:
                self.stats["expirations"] += 1
                logger.debug(f"Critical data expired: {project}/{source_name}")
                return None

            self.stats["hits"] += 1

            # Return data with metadata
            return {
                "data": entry.data,
                "age": entry.get_age_seconds(),
                "freshness": entry.get_freshness().value,
                "timestamp": entry.timestamp,
                "refresh_count": entry.refresh_count
            }

        except Exception as e:
            logger.error(f"Error getting critical data {project}/{source_name}: {e}")
            return None

    async def get_all_critical_data(
        self,
        project: str,
        allow_stale: bool = True
    ) -> Dict[str, Any]:
        """
        Get all critical data for a project.

        Args:
            project: Project name
            allow_stale: Return stale data if available

        Returns:
            Dictionary of source_name -> data
        """
        try:
            # Get all sources for this project
            sources = await self._get_project_sources(project)

            result = {}
            for source_name in sources:
                data = await self.get_critical_data(project, source_name, allow_stale)
                if data is not None:
                    result[source_name] = data

            return result

        except Exception as e:
            logger.error(f"Error getting all critical data for {project}: {e}")
            return {}

    async def invalidate(self, project: str, source_name: Optional[str] = None):
        """
        Invalidate cached data.

        Args:
            project: Project name
            source_name: Optional specific source to invalidate (None for all)
        """
        try:
            if source_name:
                # Invalidate specific source
                key = self._make_key(project, source_name)
                await self.redis.delete(key)
                await self._remove_from_index(project, source_name)
                logger.debug(f"Invalidated critical data: {project}/{source_name}")
            else:
                # Invalidate all sources for project
                sources = await self._get_project_sources(project)
                for source in sources:
                    key = self._make_key(project, source)
                    await self.redis.delete(key)

                # Clear index
                index_key = self._make_index_key(project)
                await self.redis.delete(index_key)
                logger.debug(f"Invalidated all critical data for: {project}")

        except Exception as e:
            logger.error(f"Error invalidating critical data: {e}")

    async def refresh_entry(
        self,
        project: str,
        source_name: str,
        fetcher: Optional[Callable] = None
    ):
        """
        Refresh a specific cache entry.

        Args:
            project: Project name
            source_name: Source name
            fetcher: Optional async function to fetch fresh data
        """
        try:
            if fetcher:
                # Fetch fresh data
                fresh_data = await fetcher()

                # Get existing entry to preserve metadata
                key = self._make_key(project, source_name)
                existing = await self.redis.get(key)

                if existing:
                    entry = CriticalDataEntry.from_dict(json.loads(existing))
                    entry.data = fresh_data
                    entry.timestamp = datetime.now().isoformat()
                    entry.refresh_count += 1
                    entry.version += 1
                else:
                    # Create new entry
                    ttl = self.DEFAULT_TTLS.get(source_name, 900)
                    entry = CriticalDataEntry(
                        project=project,
                        source_name=source_name,
                        data=fresh_data,
                        timestamp=datetime.now().isoformat(),
                        ttl_seconds=ttl
                    )

                # Store updated entry
                value = json.dumps(entry.to_dict())
                await self.redis.setex(
                    key,
                    entry.ttl_seconds + 60,
                    value
                )

                self.stats["refreshes"] += 1
                logger.debug(f"Refreshed critical data: {project}/{source_name}")

        except Exception as e:
            logger.error(f"Error refreshing {project}/{source_name}: {e}")

    async def _refresh_all_entries(self):
        """Refresh all entries in the cache."""
        try:
            # Get all projects with critical data
            pattern = f"{self.key_prefix}:index:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key.decode() if isinstance(key, bytes) else key)

            for index_key in keys:
                project = index_key.split(":")[-1]
                sources = await self._get_project_sources(project)

                for source_name in sources:
                    # Check if registered callback exists
                    callback_key = f"{project}:{source_name}"
                    if callback_key in self._refresh_callbacks:
                        try:
                            await self.refresh_entry(
                                project,
                                source_name,
                                self._refresh_callbacks[callback_key]
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to refresh {project}/{source_name}: {e}"
                            )

            logger.debug(f"Refreshed critical cache entries")

        except Exception as e:
            logger.error(f"Error in _refresh_all_entries: {e}")

    def register_refresh_callback(
        self,
        project: str,
        source_name: str,
        callback: Callable
    ):
        """
        Register a callback for refreshing specific data.

        Args:
            project: Project name
            source_name: Source name
            callback: Async function to fetch fresh data
        """
        key = f"{project}:{source_name}"
        self._refresh_callbacks[key] = callback
        logger.debug(f"Registered refresh callback for {key}")

    def unregister_refresh_callback(
        self,
        project: str,
        source_name: str
    ):
        """
        Unregister a refresh callback.

        Args:
            project: Project name
            source_name: Source name
        """
        key = f"{project}:{source_name}"
        if key in self._refresh_callbacks:
            del self._refresh_callbacks[key]
            logger.debug(f"Unregistered refresh callback for {key}")

    async def _add_to_index(self, project: str, source_name: str):
        """Add source to project index."""
        try:
            index_key = self._make_index_key(project)
            await self.redis.sadd(index_key, source_name)
        except Exception as e:
            logger.warning(f"Error adding to index: {e}")

    async def _remove_from_index(self, project: str, source_name: str):
        """Remove source from project index."""
        try:
            index_key = self._make_index_key(project)
            await self.redis.srem(index_key, source_name)
        except Exception as e:
            logger.warning(f"Error removing from index: {e}")

    async def _get_project_sources(self, project: str) -> List[str]:
        """Get all sources for a project."""
        try:
            index_key = self._make_index_key(project)
            members = await self.redis.smembers(index_key)
            return [m.decode() if isinstance(m, bytes) else m for m in members]
        except Exception as e:
            logger.warning(f"Error getting project sources: {e}")
            return []

    def _make_key(self, project: str, source_name: str) -> str:
        """Make Redis key for an entry."""
        return f"{self.key_prefix}:{project}:{source_name}"

    def _make_index_key(self, project: str) -> str:
        """Make Redis key for project index."""
        return f"{self.key_prefix}:index:{project}"

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "hits": 0,
            "misses": 0,
            "refreshes": 0,
            "expirations": 0
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the critical cache.

        Returns:
            Health status dictionary
        """
        try:
            # Check Redis connection
            await self.redis.ping()

            # Get all projects
            pattern = f"{self.key_prefix}:index:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key.decode() if isinstance(key, bytes) else key)

            # Count total entries
            total_entries = 0
            expired_entries = 0
            stale_entries = 0

            for index_key in keys:
                project = index_key.split(":")[-1]
                sources = await self._get_project_sources(project)

                for source_name in sources:
                    total_entries += 1
                    data = await self.get_critical_data(project, source_name)
                    if data:
                        if data["freshness"] == "expired":
                            expired_entries += 1
                        elif data["freshness"] == "stale":
                            stale_entries += 1

            return {
                "status": "healthy",
                "redis_connected": True,
                "total_projects": len(keys),
                "total_entries": total_entries,
                "fresh_entries": total_entries - stale_entries - expired_entries,
                "stale_entries": stale_entries,
                "expired_entries": expired_entries,
                "auto_refresh_enabled": self.auto_refresh,
                "stats": self.stats
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "redis_connected": False,
                "stats": self.stats
            }

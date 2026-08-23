"""
Priority Data Fetcher - Phase 7 Sprint 2 Day 11-12

Purpose: Fetch data based on priority during degradation with hysteresis

Features:
- Priority-based fetching (P0 → P1 → P2 → P3)
- Hysteresis to prevent mode flapping
- Retry logic with exponential backoff
- Fallback to cache on failure
- Timeout management per priority level
- Detailed fetch result tracking
"""

import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from app.degradation.priority_config import (
    Priority,
    PriorityConfig,
    PriorityConfigManager
)

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a data fetch operation."""
    source_name: str
    status: str  # success, cached, timeout, error, skipped
    priority: str
    data: Optional[Any] = None
    error: Optional[str] = None
    timeout_ms: int = 0
    cache_age: Optional[str] = None
    fetch_time_ms: float = 0
    retry_attempts: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FetchSummary:
    """Summary of a batch fetch operation."""
    total_sources: int = 0
    successful: int = 0
    cached: int = 0
    timeouts: int = 0
    errors: int = 0
    skipped: int = 0
    total_time_ms: float = 0
    by_priority: Dict[str, Dict[str, int]] = field(default_factory=dict)


class PriorityDataFetcher:
    """
    Fetch data based on priority during degradation.

    Features:
    - Respects priority levels (P0 always fetched)
    - Hysteresis to prevent mode flapping
    - Retry logic with exponential backoff
    - Fallback to cached data
    - Per-priority timeout management
    """

    # Default timeout allocation per priority (milliseconds)
    PRIORITY_TIMEOUTS = {
        Priority.P0: 5000,  # Critical: 5 seconds
        Priority.P1: 3000,  # High: 3 seconds
        Priority.P2: 2000,  # Medium: 2 seconds
        Priority.P3: 1000,  # Low: 1 second
    }

    def __init__(
        self,
        priority_config: PriorityConfigManager,
        hysteresis_factor: float = 0.1,
        mode_change_cooldown: timedelta = timedelta(minutes=5),
        l2_cache=None,
        critical_cache=None
    ):
        """
        Initialize priority data fetcher.

        Args:
            priority_config: Priority configuration manager
            hysteresis_factor: Hysteresis factor (10% = 0.1) to prevent flapping
            mode_change_cooldown: Minimum time between mode changes
            l2_cache: L2 cache instance for fallback
            critical_cache: Critical cache instance for fallback
        """
        self.config = priority_config
        self.hysteresis = hysteresis_factor
        self.mode_change_cooldown = mode_change_cooldown

        # State tracking
        self.current_mode: str = "normal"
        self.last_mode_change: Optional[datetime] = None
        self.mode_change_count: int = 0

        # Cache instances for fallback
        self.l2_cache = l2_cache
        self.critical_cache = critical_cache

        logger.info(
            f"PriorityDataFetcher initialized with hysteresis={hysteresis_factor}, "
            f"cooldown={mode_change_cooldown.total_seconds()}s"
        )

    async def fetch_by_priority(
        self,
        fetchers: Dict[str, Callable[[], Awaitable[Any]]],
        total_timeout: int = 15000,
        project: Optional[str] = None
    ) -> Dict[str, FetchResult]:
        """
        Fetch data respecting priorities and timeouts.

        Args:
            fetchers: Dictionary of source_name -> async fetcher function
            total_timeout: Total timeout in milliseconds
            project: Optional project name for project-specific configs

        Returns:
            Dictionary of source_name -> FetchResult
        """
        start_time = datetime.now()
        results: Dict[str, FetchResult] = {}

        # Group tasks by priority
        tasks_by_priority = self._group_by_priority(fetchers, project)

        # Fetch in priority order
        remaining_timeout = total_timeout

        for priority in Priority:
            tasks = tasks_by_priority.get(priority, [])
            if not tasks:
                continue

            # Calculate timeout for this priority level
            priority_timeout = min(
                self.PRIORITY_TIMEOUTS.get(priority, 1000),
                remaining_timeout
            )

            logger.debug(
                f"Fetching {len(tasks)} sources with priority {priority.name}, "
                f"timeout={priority_timeout}ms"
            )

            # Fetch all tasks at this priority level concurrently
            priority_results = await self._fetch_priority_level(
                tasks,
                priority_timeout,
                priority
            )

            results.update(priority_results)
            remaining_timeout -= priority_timeout

            if remaining_timeout <= 0:
                logger.warning("Total timeout exceeded, skipping lower priorities")
                break

        # Log summary
        total_time = (datetime.now() - start_time).total_seconds() * 1000
        summary = self._create_summary(results, total_time)
        logger.info(
            f"Priority fetch complete: {summary.successful} success, "
            f"{summary.cached} cached, {summary.timeouts} timeouts, "
            f"{summary.errors} errors in {total_time:.0f}ms"
        )

        return results

    def _group_by_priority(
        self,
        fetchers: Dict[str, Callable[[], Awaitable[Any]]],
        project: Optional[str] = None
    ) -> Dict[Priority, List[tuple]]:
        """Group fetchers by priority level."""
        tasks_by_priority: Dict[Priority, List[tuple]] = {
            Priority.P0: [],
            Priority.P1: [],
            Priority.P2: [],
            Priority.P3: []
        }

        for source_name, fetcher in fetchers.items():
            config = self.config.get_config(source_name, project)

            if not config or not config.enabled:
                # Skip disabled sources
                tasks_by_priority[Priority.P3].append((
                    source_name,
                    fetcher,
                    config
                ))
            else:
                tasks_by_priority[config.priority].append((
                    source_name,
                    fetcher,
                    config
                ))

        return tasks_by_priority

    async def _fetch_priority_level(
        self,
        tasks: List[tuple],
        timeout_ms: int,
        priority: Priority
    ) -> Dict[str, FetchResult]:
        """Fetch all tasks at a given priority level."""
        results: Dict[str, FetchResult] = {}

        # Create fetch tasks
        fetch_tasks = []
        for source_name, fetcher, config in tasks:
            fetch_tasks.append(self._fetch_single(
                source_name,
                fetcher,
                config,
                timeout_ms,
                priority
            ))

        # Execute concurrently
        if fetch_tasks:
            level_results = await asyncio.gather(
                *fetch_tasks,
                return_exceptions=True
            )

            for result in level_results:
                if isinstance(result, FetchResult):
                    results[result.source_name] = result
                else:
                    logger.error(f"Unexpected result type: {type(result)}")

        return results

    async def _fetch_single(
        self,
        source_name: str,
        fetcher: Callable[[], Awaitable[Any]],
        config: Optional[PriorityConfig],
        timeout_ms: int,
        priority: Priority
    ) -> FetchResult:
        """Fetch a single data source with retry and fallback."""
        start_time = datetime.now()

        try:
            if config and config.retry_count > 0:
                # Fetch with retry
                data = await self._fetch_with_retry(
                    fetcher,
                    config.retry_count,
                    timeout_ms / 1000
                )
                retry_attempts = config.retry_count
            else:
                # Direct fetch
                data = await asyncio.wait_for(fetcher(), timeout=timeout_ms / 1000)
                retry_attempts = 0

            fetch_time = (datetime.now() - start_time).total_seconds() * 1000

            return FetchResult(
                source_name=source_name,
                status="success",
                priority=priority.name,
                data=data,
                timeout_ms=timeout_ms,
                fetch_time_ms=fetch_time,
                retry_attempts=retry_attempts
            )

        except asyncio.TimeoutError:
            # Try fallback cache
            cached_data = await self._get_fallback_cache(source_name, config)
            fetch_time = (datetime.now() - start_time).total_seconds() * 1000

            if cached_data is not None:
                return FetchResult(
                    source_name=source_name,
                    status="cached",
                    priority=priority.name,
                    data=cached_data.get("data"),
                    timeout_ms=timeout_ms,
                    cache_age=cached_data.get("age"),
                    fetch_time_ms=fetch_time,
                    retry_attempts=0
                )

            return FetchResult(
                source_name=source_name,
                status="timeout",
                priority=priority.name,
                error="Request timeout",
                timeout_ms=timeout_ms,
                fetch_time_ms=fetch_time,
                retry_attempts=0
            )

        except Exception as e:
            logger.error(f"Error fetching {source_name}: {e}")
            fetch_time = (datetime.now() - start_time).total_seconds() * 1000

            # Try fallback cache
            cached_data = await self._get_fallback_cache(source_name, config)
            if cached_data is not None:
                return FetchResult(
                    source_name=source_name,
                    status="cached",
                    priority=priority.name,
                    data=cached_data.get("data"),
                    timeout_ms=timeout_ms,
                    cache_age=cached_data.get("age"),
                    fetch_time_ms=fetch_time,
                    retry_attempts=0
                )

            return FetchResult(
                source_name=source_name,
                status="error",
                priority=priority.name,
                error=str(e),
                timeout_ms=timeout_ms,
                fetch_time_ms=fetch_time,
                retry_attempts=0
            )

    async def _fetch_with_retry(
        self,
        task: Awaitable[Any],
        retry_count: int,
        timeout: float
    ) -> Any:
        """Fetch with retry logic and exponential backoff."""
        last_error = None

        for attempt in range(retry_count + 1):
            try:
                return await asyncio.wait_for(task, timeout=timeout)
            except Exception as e:
                last_error = e

                if attempt < retry_count:
                    # Exponential backoff
                    backoff_time = 0.1 * (2 ** attempt)
                    logger.debug(
                        f"Retry {attempt + 1}/{retry_count} after {backoff_time}s error: {e}"
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    logger.warning(f"All {retry_count} retries failed: {e}")

        raise last_error

    async def _get_fallback_cache(
        self,
        source_name: str,
        config: Optional[PriorityConfig]
    ) -> Optional[Dict[str, Any]]:
        """Get fallback cached data."""
        if not config or not config.fallback_to_cache:
            return None

        cached_data = None

        # Try L2 cache first
        if self.l2_cache:
            try:
                cached = await self.l2_cache.get(
                    "fallback",
                    {"source": source_name}
                )
                if cached:
                    cached_data = {"data": cached, "age": "L2"}
                    logger.debug(f"L2 cache hit for fallback: {source_name}")
            except Exception as e:
                logger.warning(f"L2 cache fallback failed: {e}")

        # Try critical cache
        if not cached_data and self.critical_cache:
            try:
                cached = await self.critical_cache.get_critical_data(
                    "global",
                    source_name
                )
                if cached:
                    cached_data = {"data": cached, "age": "critical"}
                    logger.debug(f"Critical cache hit for fallback: {source_name}")
            except Exception as e:
                logger.warning(f"Critical cache fallback failed: {e}")

        return cached_data

    def _create_summary(
        self,
        results: Dict[str, FetchResult],
        total_time_ms: float
    ) -> FetchSummary:
        """Create summary of fetch results."""
        summary = FetchSummary(
            total_sources=len(results),
            total_time_ms=total_time_ms
        )

        by_priority: Dict[str, Dict[str, int]] = {
            "P0": {"success": 0, "cached": 0, "timeout": 0, "error": 0},
            "P1": {"success": 0, "cached": 0, "timeout": 0, "error": 0},
            "P2": {"success": 0, "cached": 0, "timeout": 0, "error": 0},
            "P3": {"success": 0, "cached": 0, "timeout": 0, "error": 0},
        }

        for result in results.values():
            if result.status == "success":
                summary.successful += 1
                by_priority[result.priority]["success"] += 1
            elif result.status == "cached":
                summary.cached += 1
                by_priority[result.priority]["cached"] += 1
            elif result.status == "timeout":
                summary.timeouts += 1
                by_priority[result.priority]["timeout"] += 1
            elif result.status == "error":
                summary.errors += 1
                by_priority[result.priority]["error"] += 1

        summary.by_priority = by_priority
        return summary

    def get_hysteresis_upper_bound(self, threshold: float) -> float:
        """
        Get upper bound with hysteresis.

        Used for mode transitions to prevent flapping.
        """
        return threshold * (1 + self.hysteresis)

    def get_hysteresis_lower_bound(self, threshold: float) -> float:
        """
        Get lower bound with hysteresis.

        Used for mode transitions to prevent flapping.
        """
        return threshold * (1 - self.hysteresis)

    def can_change_mode(self) -> bool:
        """
        Check if mode can be changed (respecting cooldown).

        Returns:
            True if mode change is allowed
        """
        if self.last_mode_change is None:
            return True

        time_since_change = datetime.now() - self.last_mode_change
        return time_since_change >= self.mode_change_cooldown

    def record_mode_change(self, new_mode: str):
        """
        Record a mode change.

        Args:
            new_mode: New mode name
        """
        self.current_mode = new_mode
        self.last_mode_change = datetime.now()
        self.mode_change_count += 1

        logger.info(
            f"Mode changed to {new_mode} (change #{self.mode_change_count})"
        )


class PriorityFetcherBuilder:
    """Builder for PriorityDataFetcher with fluent API."""

    def __init__(self):
        self.config_manager: Optional[PriorityConfigManager] = None
        self.hysteresis_factor: float = 0.1
        self.cooldown: timedelta = timedelta(minutes=5)
        self.l2_cache = None
        self.critical_cache = None

    def with_config(self, config_manager: PriorityConfigManager) -> 'PriorityFetcherBuilder':
        """Set config manager."""
        self.config_manager = config_manager
        return self

    def with_hysteresis(self, factor: float) -> 'PriorityFetcherBuilder':
        """Set hysteresis factor."""
        self.hysteresis_factor = factor
        return self

    def with_cooldown(self, cooldown: timedelta) -> 'PriorityFetcherBuilder':
        """Set mode change cooldown."""
        self.cooldown = cooldown
        return self

    def with_l2_cache(self, l2_cache) -> 'PriorityFetcherBuilder':
        """Set L2 cache."""
        self.l2_cache = l2_cache
        return self

    def with_critical_cache(self, critical_cache) -> 'PriorityFetcherBuilder':
        """Set critical cache."""
        self.critical_cache = critical_cache
        return self

    def build(self) -> PriorityDataFetcher:
        """Build the PriorityDataFetcher."""
        if not self.config_manager:
            raise ValueError("Config manager is required")

        return PriorityDataFetcher(
            priority_config=self.config_manager,
            hysteresis_factor=self.hysteresis_factor,
            mode_change_cooldown=self.cooldown,
            l2_cache=self.l2_cache,
            critical_cache=self.critical_cache
        )

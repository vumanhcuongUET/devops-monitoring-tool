"""
Single Flight Pattern Implementation

Phase 7 - Sprint 1 - Day 4
Purpose: Prevent cache stampede by ensuring only one request for in-flight data

When multiple concurrent requests ask for the same uncached data,
this pattern ensures only one actual fetch occurs, and all waiters
get the same result.

Example scenario:
- Request 1 asks for data X (cache miss) → starts fetching
- Request 2 asks for data X (cache miss) → waits for Request 1
- Request 3 asks for data X (cache miss) → waits for Request 1
- Request 1 completes → Requests 2, 3 get same result

This prevents:
- Multiple duplicate queries to backend services
- Cache stampede when cache expires
- Wasted resources on redundant fetches
"""

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class SingleFlight:
    """
    Ensure only one request for in-flight data.

    Multiple concurrent requests for the same data will wait
    for the first request to complete and share its result.

    Usage:
        single_flight = SingleFlight()

        async def get_data(key):
            return await single_flight.execute(
                key=key,
                func=fetch_from_source,
                key=key
            )

        # Multiple concurrent calls with same key:
        # Only one fetch_from_source() is executed
    """

    def __init__(self):
        # Track in-flight requests
        # {key: {"event": asyncio.Event, "result": Any, "error": Exception}}
        self._in_flight: dict[str, dict[str, Any]] = {}
        # Statistics
        self._stats = defaultdict(lambda: {
            "executions": 0,
            "waits": 0,
            "errors": 0,
            "total_wait_time": 0.0
        })

    async def execute(
        self,
        key: str,
        func: Callable,
        *args,
        timeout: float | None = None,
        **kwargs
    ) -> Any:
        """
        Execute with single flight guarantee.

        Args:
            key: Unique identifier for this request
            func: Async function to execute if not already in flight
            *args: Arguments for func
            timeout: Optional timeout for waiting on in-flight request
            **kwargs: Keyword arguments for func

        Returns:
            Result from func (either newly executed or cached from in-flight)

        Raises:
            asyncio.TimeoutError: If timeout expires while waiting
            Exception: Any exception from func execution
        """
        stats = self._stats[key]

        # Check if request is already in flight
        if key in self._in_flight:
            flight = self._in_flight[key]
            stats["waits"] += 1
            wait_start = time.time()

            logger.debug(f"SingleFlight: Waiting on in-flight request: {key}")

            try:
                # Wait for the in-flight request to complete
                if timeout:
                    await asyncio.wait_for(flight["event"].wait(), timeout=timeout)
                else:
                    await flight["event"].wait()

                # Return result or raise error
                if flight["error"] is not None:
                    stats["errors"] += 1
                    raise flight["error"]

                return flight["result"]

            finally:
                stats["total_wait_time"] += time.time() - wait_start

        # Start new flight
        logger.debug(f"SingleFlight: Starting new flight: {key}")
        stats["executions"] += 1

        # Create event for waiters
        event = asyncio.Event()
        self._in_flight[key] = {
            "event": event,
            "result": None,
            "error": None
        }

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Cache result and notify waiters
            self._in_flight[key]["result"] = result
            event.set()

            return result

        except Exception as e:
            # Cache error and notify waiters
            self._in_flight[key]["error"] = e
            event.set()
            stats["errors"] += 1
            raise

        finally:
            # Clean up after a short delay to allow waiters to wake up
            async def cleanup():
                await asyncio.sleep(0.1)
                if key in self._in_flight and self._in_flight[key]["event"].is_set():
                    del self._in_flight[key]

            asyncio.create_task(cleanup())

    def get_stats(self, key: str | None = None) -> dict[str, Any]:
        """
        Get statistics for single flight operations.

        Args:
            key: Specific key to get stats for, or None for all stats

        Returns:
            Statistics dictionary
        """
        if key:
            return dict(self._stats[key])
        return {k: dict(v) for k, v in self._stats.items()}

    def get_summary(self) -> dict[str, Any]:
        """
        Get overall single flight summary.

        Returns:
            Summary with execution counts, wait counts, efficiency
        """
        total_executions = sum(s["executions"] for s in self._stats.values())
        total_waits = sum(s["waits"] for s in self._stats.values())
        total_errors = sum(s["errors"] for s in self._stats.values())

        # Calculate efficiency: how many duplicate requests were avoided
        efficiency = 0
        if total_executions > 0:
            efficiency = total_waits / (total_executions + total_waits)

        return {
            "total_executions": total_executions,
            "total_waits": total_waits,
            "total_errors": total_errors,
            "efficiency_rate": round(efficiency, 4),
            "active_flights": len(self._in_flight),
            "unique_keys": len(self._stats),
        }


def single_flight(key_func: Callable):
    """
    Decorator for single flight pattern on async functions.

    Args:
        key_func: Function that generates unique key from function arguments

    Example:
        @single_flight(lambda project, time_range: f"{project}:{time_range}")
        async def get_overview(project, time_range):
            return await fetch_overview(project, time_range)
    """
    def decorator(func):
        _single_flight = SingleFlight()

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate key from arguments
            key = key_func(*args, **kwargs)

            # Execute with single flight
            return await _single_flight.execute(
                key,
                func,
                *args,
                **kwargs
            )

        # Add method to access stats
        wrapper.get_stats = _single_flight.get_stats
        wrapper.get_summary = _single_flight.get_summary

        return wrapper

    from functools import wraps
    return decorator


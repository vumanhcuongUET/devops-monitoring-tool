"""
Single-flight deduplication for concurrent requests.

Ensures that only one request is made for the same key concurrently.
Subsequent requests wait for the first to complete.
"""

import threading
from typing import Any, Callable, Dict, Optional, TypeVar
from dataclasses import dataclass

T = TypeVar("T")


# Import logging helpers (lazy to avoid circular import)
def _get_logger():
    from core.logging_config import get_logger
    return get_logger(__name__)


def _get_metrics():
    from core.logging_config import get_metrics
    return get_metrics()


@dataclass
class Flight:
    """Represents an in-flight request."""
    event: threading.Event
    result: Any = None
    error: Exception = None


class SingleFlight:
    """
    Single-flight deduplication for sync code.

    Prevents duplicate concurrent requests for the same key.
    """

    def __init__(self):
        self._flights: Dict[str, Flight] = {}
        self._lock = threading.Lock()

    def execute(self, key: str, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with single-flight deduplication.

        If another request with the same key is in progress,
        wait for its result instead of executing again.

        Args:
            key: Request identifier key
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Exception: If function execution fails
        """
        # Check if request is already in flight
        with self._lock:
            existing = self._flights.get(key)
            if existing:
                # Wait for existing request
                _get_logger().debug("Single-flight: waiting for existing request", key=key[:32])
                _get_metrics().increment("single_flight_wait_total")
                existing.event.wait()
                if existing.error:
                    _get_metrics().increment("single_flight_error_total")
                    raise existing.error
                _get_metrics().increment("single_flight_dedup_total")
                _get_logger().debug("Single-flight: reused result", key=key[:32])
                return existing.result

            # Create new flight
            flight = Flight(event=threading.Event())
            self._flights[key] = flight
            _get_logger().debug("Single-flight: starting new request", key=key[:32])
            _get_metrics().increment("single_flight_execute_total")

        try:
            # Execute the function
            result = func(*args, **kwargs)
            flight.result = result
            _get_logger().debug("Single-flight: request completed", key=key[:32])
            return result
        except Exception as e:
            flight.error = e
            _get_logger().warning(f"Single-flight: request failed key={key[:32]} error={e}")
            raise
        finally:
            # Clean up
            flight.event.set()
            with self._lock:
                self._flights.pop(key, None)

    def stats(self) -> Dict[str, Any]:
        """
        Get single-flight statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "in_flight_count": len(self._flights),
            "keys": list(self._flights.keys())
        }


# Global single-flight instance
_global_single_flight: Optional[SingleFlight] = None


def get_global_single_flight() -> SingleFlight:
    """
    Get or create the global in-memory single-flight instance.
    """
    global _global_single_flight

    if _global_single_flight is None:
        from core.config_loader import get_feature_flags

        flags = get_feature_flags()

        # Check if deduplication is enabled
        if not flags.get("optimization", {}).get("deduplication_enabled", True):
            # Return a no-op instance
            _global_single_flight = SingleFlight()
            _get_logger().info("Single-flight disabled")
            return _global_single_flight

        _global_single_flight = SingleFlight()
        _get_logger().info("Using in-memory single-flight")

    return _global_single_flight


def single_flight(key: str):
    """
    Decorator for single-flight deduplication.

    Args:
        key: Function to generate cache key from arguments,
             or a static string key

    Example:
        @single_flight(lambda self, url: f"fetch:{url}")
        def fetch(self, url):
            return requests.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            from core.config_loader import is_feature_enabled

            # Check if deduplication is enabled
            if not is_feature_enabled("optimization.deduplication_enabled"):
                return func(*args, **kwargs)

            # Generate key
            if callable(key):
                flight_key = key(*args, **kwargs)
            else:
                flight_key = str(key)

            sf = get_global_single_flight()
            return sf.execute(flight_key, func, *args, **kwargs)

        return wrapper
    return decorator


def get_single_flight_stats() -> Dict[str, Any]:
    """
    Get global single-flight statistics.

    Returns:
        Single-flight statistics dictionary
    """
    sf = get_global_single_flight()
    return sf.stats()

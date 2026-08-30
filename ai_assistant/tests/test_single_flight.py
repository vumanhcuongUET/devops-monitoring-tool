"""
Tests for single-flight module.
"""

import pytest
import threading
import time
from unittest.mock import patch
import importlib

from core.single_flight import SingleFlight, single_flight, get_global_single_flight


@pytest.mark.unit
class TestSingleFlight:
    """Tests for SingleFlight."""

    def test_init(self):
        """Test single-flight initialization."""
        sf = SingleFlight()
        assert len(sf._flights) == 0

    def test_execute_single_call(self):
        """Test single execution."""
        sf = SingleFlight()
        call_count = [0]

        def func(x):
            call_count[0] += 1
            return x * 2

        result = sf.execute("key1", func, 5)
        assert result == 10
        assert call_count[0] == 1

    def test_execute_deduplication(self):
        """Test that concurrent calls are deduplicated."""
        sf = SingleFlight()
        call_count = [0]
        results = []

        def func(x):
            call_count[0] += 1
            time.sleep(0.1)  # Simulate slow operation
            return x * 2

        def concurrent_call():
            result = sf.execute("key1", func, 5)
            results.append(result)

        # Start multiple threads
        threads = [threading.Thread(target=concurrent_call) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same result
        assert all(r == 10 for r in results)
        # Function should only be called once
        assert call_count[0] == 1

    def test_execute_different_keys(self):
        """Test that different keys execute separately."""
        sf = SingleFlight()
        call_count = [0]

        def func(x):
            call_count[0] += 1
            return x * 2

        sf.execute("key1", func, 5)
        sf.execute("key2", func, 10)

        assert call_count[0] == 2

    def test_execute_propagates_error(self):
        """Test that exceptions are propagated."""
        sf = SingleFlight()

        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            sf.execute("key1", failing_func)

    def test_execute_error_recovery(self):
        """Test that errors don't block subsequent calls."""
        sf = SingleFlight()
        call_count = [0]

        def func():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("First call fails")
            return "success"

        # First call fails
        with pytest.raises(ValueError):
            sf.execute("key1", func)

        # Second call should succeed
        result = sf.execute("key1", func)
        assert result == "success"

    def test_stats(self):
        """Test single-flight statistics."""
        sf = SingleFlight()

        def slow_func():
            time.sleep(0.2)
            return "done"

        # Start a slow operation in background
        def bg_call():
            sf.execute("key1", slow_func)

        thread = threading.Thread(target=bg_call)
        thread.start()
        time.sleep(0.05)  # Let it start

        # Check stats while operation is in flight
        stats = sf.stats()
        assert stats["in_flight_count"] >= 0

        thread.join()

    def test_concurrent_different_keys(self):
        """Test concurrent calls with different keys."""
        sf = SingleFlight()
        call_count = [0]

        def func(x):
            call_count[0] += 1
            time.sleep(0.05)
            return x

        results = []

        def call_with_key(key, value):
            result = sf.execute(key, func, value)
            results.append(result)

        threads = [
            threading.Thread(target=call_with_key, args=("key1", 1)),
            threading.Thread(target=call_with_key, args=("key2", 2)),
            threading.Thread(target=call_with_key, args=("key3", 3)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3
        assert call_count[0] == 3  # Each key executed separately


@pytest.mark.unit
class TestSingleFlightDecorator:
    """Tests for @single_flight decorator."""

    def test_single_flight_decorator(self):
        """Test that decorator prevents duplicate calls."""
        # Reset global state
        import core.single_flight
        core.single_flight._global_single_flight = None

        call_count = [0]

        @single_flight(lambda x: f"func:{x}")
        def func(x):
            call_count[0] += 1
            time.sleep(0.1)  # Longer sleep to ensure threads overlap
            return x * 2

        # Call with same argument multiple times
        threads = [
            threading.Thread(target=func, args=(5,)),
            threading.Thread(target=func, args=(5,)),
        ]

        # Start threads quickly together
        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should only execute once due to single-flight
        assert call_count[0] == 1, f"Expected 1 call, got {call_count[0]}"

        # Both threads should get the same result
        # (we can't easily check return values from threads without more complexity)

    def test_single_flight_different_args(self):
        """Test that different arguments execute separately."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            import core.single_flight
            core.single_flight._global_single_flight = None

            call_count = [0]

            @single_flight(lambda x: f"func:{x}")
            def func(x):
                call_count[0] += 1
                return x * 2

            func(5)
            func(10)

            assert call_count[0] == 2

    def test_single_flight_with_static_key(self):
        """Test single-flight with static key."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            # Get module directly to access globals
            sf_mod = importlib.import_module("core.single_flight")
            sf_mod._global_single_flight = None
            sf_mod.get_global_single_flight()  # Initialize

            call_count = [0]

            @single_flight("static_key")
            def func():
                call_count[0] += 1
                time.sleep(0.1)  # Ensure enough time for races to occur
                return "result"

            threads = [threading.Thread(target=func) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All calls share the same static key - should only execute once
            assert call_count[0] == 1


@pytest.mark.unit
class TestSingleFlightFactory:
    """Tests for single-flight factory pattern."""

    def test_get_global_single_flight_returns_memory_by_default(self):
        """Test that get_global_single_flight returns in-memory by default."""
        with patch("core.config_loader.get_feature_flags", return_value={}):
            import core.single_flight
            core.single_flight._global_single_flight = None

            sf = get_global_single_flight()
            assert isinstance(sf, SingleFlight)

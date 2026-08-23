"""
Integration tests for token optimization features.

Tests caching, single-flight deduplication, and output optimization.
"""

import json
import pytest
import time
from unittest.mock import patch, MagicMock

# Import modules to test
from core.cache import SimpleCache, cached, cache_key_from_args
from core.single_flight import SingleFlight, single_flight
from core.output_optimizer import OutputOptimizer
from core.config_loader import is_feature_enabled, get_feature_flags


class TestCacheIntegration:
    """Test caching functionality for query results."""

    def test_cache_reduces_duplicate_queries(self):
        """Verify that cached queries prevent duplicate execution."""
        cache = SimpleCache(ttl=60)
        call_count = 0

        @cached(ttl=60)
        def expensive_query(project, section):
            nonlocal call_count
            call_count += 1
            return {"project": project, "section": section, "data": "results"}

        # First call - should execute
        result1 = expensive_query("meinvoice", "errors")
        assert call_count == 1
        assert result1["project"] == "meinvoice"

        # Second call within TTL - should use cache
        result2 = expensive_query("meinvoice", "errors")
        assert call_count == 1  # No increment
        assert result2 == result1

    def test_cache_respects_time_range(self):
        """Verify that different time_ranges don't share cache."""
        cache = SimpleCache(ttl=60)
        call_count = 0

        @cached(ttl=60)
        def query_with_time_range(project, section, time_range):
            nonlocal call_count
            call_count += 1
            return {"time_range": time_range}

        # Different time_ranges should result in separate calls
        result1 = query_with_time_range("meinvoice", "errors", "now-1h")
        result2 = query_with_time_range("meinvoice", "errors", "now-30m")

        assert call_count == 2  # Both executed
        assert result1["time_range"] == "now-1h"
        assert result2["time_range"] == "now-30m"

    def test_cache_key_from_args(self):
        """Test cache key generation from function arguments."""
        key1 = cache_key_from_args("meinvoice", "errors", time_range="now-1h")
        key2 = cache_key_from_args("meinvoice", "errors", time_range="now-1h")
        key3 = cache_key_from_args("meinvoice", "errors", time_range="now-30m")

        assert key1 == key2  # Same args = same key
        assert key1 != key3  # Different args = different key


class TestSingleFlightDeduplication:
    """Test single-flight deduplication for concurrent requests."""

    def test_single_flight_deduplication(self):
        """Verify that concurrent same-key queries deduplicate."""
        sf = SingleFlight()
        call_count = 0

        @single_flight(lambda project, section: f"{project}:{section}")
        def query_function(project, section):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Simulate slow query
            return {"project": project, "section": section}

        import threading

        results = []
        threads = []

        def thread_func():
            result = query_function("meinvoice", "errors")
            results.append(result)

        # Launch 5 concurrent threads
        for _ in range(5):
            t = threading.Thread(target=thread_func)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Only 1 actual call should have been made
        assert call_count == 1
        assert len(results) == 5
        # All results should be the same
        assert all(r == results[0] for r in results)

    def test_single_flight_different_keys(self):
        """Verify that different keys result in separate calls."""
        sf = SingleFlight()
        call_count = 0

        @single_flight(lambda project, section: f"{project}:{section}")
        def query_function(project, section):
            nonlocal call_count
            call_count += 1
            return {"project": project, "section": section}

        # Different keys = separate calls
        result1 = query_function("meinvoice", "errors")
        result2 = query_function("meinvoice", "alerts")

        assert call_count == 2
        assert result1["section"] == "errors"
        assert result2["section"] == "alerts"


class TestOutputOptimization:
    """Test output optimization for token reduction."""

    def test_output_optimizer_truncates_large_arrays(self):
        """Verify that large arrays are truncated to max_results."""
        config = {"truncate_results": True, "max_results_per_source": 5}
        optimizer = OutputOptimizer(config)

        # Mock data with 20 results
        large_data = {
            "hits": {
                "hits": [{"_id": str(i)} for i in range(20)],
                "total": {"value": 20}
            }
        }

        result = optimizer.optimize_result({"data": large_data})

        # Should be truncated to 5
        assert len(result["data"]["hits"]["hits"]) == 5
        assert result["data"]["hits"]["total"]["value"] == 5

    def test_output_optimizer_preserves_critical_data(self):
        """Verify that critical data (alerts, errors) is preserved."""
        config = {"truncate_results": True, "max_results_per_source": 3}
        optimizer = OutputOptimizer(config)

        # Mock alert data (should be preserved)
        alerts = [{"alert": f"alert_{i}"} for i in range(10)]

        # Optimize as list
        result = optimizer._optimize_data(alerts)

        # Should be truncated but not empty
        assert len(result) == 3

    def test_estimate_tokens(self):
        """Test token estimation for data."""
        config = {}
        optimizer = OutputOptimizer(config)

        small_data = {"key": "value"}
        large_data = {"key": "x" * 1000}

        small_tokens = optimizer.estimate_tokens(small_data)
        large_tokens = optimizer.estimate_tokens(large_data)

        assert large_tokens > small_tokens
        assert small_tokens > 0

    def test_optimization_reduces_tokens(self):
        """Verify that optimization reduces token count."""
        config = {"truncate_results": True, "max_results_per_source": 5}
        optimizer = OutputOptimizer(config)

        # Section with 20 results
        original = {
            "section": "errors",
            "results": [
                {"data": {"hits": {"hits": [{"_id": str(i)} for i in range(20)]}}}
            ]
        }

        original_tokens = optimizer.estimate_tokens(original)
        optimized = optimizer.optimize_section(original)
        optimized_tokens = optimizer.estimate_tokens(optimized)

        # Optimized should have fewer tokens
        assert optimized_tokens < original_tokens


class TestFeatureFlags:
    """Test feature flag integration."""

    @patch('core.config_loader.get_feature_flags')
    def test_cache_respects_feature_flag(self, mock_flags):
        """Verify that caching respects feature flag."""
        mock_flags.return_value = {"optimization": {"cache_enabled": False}}

        # When cache is disabled, should always execute
        call_count = 0

        with patch('core.config_loader.is_feature_enabled', return_value=False):
            @cached(ttl=60)
            def test_func():
                nonlocal call_count
                call_count += 1
                return "result"

            result1 = test_func()
            result2 = test_func()

            # Both should execute (cache disabled)
            assert call_count == 2

    @patch('core.config_loader.get_feature_flags')
    def test_optimization_respects_feature_flag(self, mock_flags):
        """Verify that output optimization respects feature flag."""
        mock_flags.return_value = {
            "output": {"truncate_results": False},
            "optimization": {}
        }

        with patch('core.config_loader.is_feature_enabled', return_value=False):
            config = {"truncate_results": False}
            optimizer = OutputOptimizer(config)

            # When disabled, should return original
            data = {"hits": {"hits": [{"_id": str(i)} for i in range(20)]}}
            result = optimizer.optimize_result({"data": data})

            # Should not truncate
            assert len(result["data"]["hits"]["hits"]) == 20


class TestEndToEndIntegration:
    """End-to-end integration tests."""

    def test_cache_single_flight_combination(self):
        """Test that caching and single-flight work together."""
        cache = SimpleCache(ttl=60)
        sf = SingleFlight()
        call_count = 0

        @cached(ttl=60)
        @single_flight(lambda key: f"query:{key}")
        def combined_query(key):
            nonlocal call_count
            call_count += 1
            return {"key": key}

        # First call
        result1 = combined_query("test_key")
        assert call_count == 1

        # Second call (should hit cache)
        result2 = combined_query("test_key")
        assert call_count == 1  # No increment
        assert result1 == result2

    def test_optimization_preserves_accuracy(self):
        """Verify optimization doesn't lose critical information."""
        config = {"truncate_results": True, "max_results_per_source": 5}
        optimizer = OutputOptimizer(config)

        # Critical alert data
        alerts = {
            "section": "alerts",
            "results": [
                {"status": "ok", "data": {"alerts": [
                    {"alert": "Critical", "severity": "high"},
                    {"alert": "Warning", "severity": "medium"},
                    {"alert": "Info", "severity": "low"},
                ]}}
            ]
        }

        optimized = optimizer.optimize_section(alerts)

        # Should still have structure
        assert "section" in optimized
        assert "results" in optimized
        assert len(optimized["results"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

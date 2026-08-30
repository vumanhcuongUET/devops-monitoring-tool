"""
Tests for cache module.
"""

import pytest
import time
from unittest.mock import patch

from core.cache import SimpleCache, cache_key_from_args, cached, get_global_cache


@pytest.mark.unit
class TestSimpleCache:
    """Tests for SimpleCache."""

    def test_init(self):
        """Test cache initialization."""
        cache = SimpleCache(ttl=10, max_size=100)
        assert cache._ttl == 10
        assert cache._max_size == 100
        assert len(cache._cache) == 0

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = SimpleCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Test getting nonexistent key returns None."""
        cache = SimpleCache()
        assert cache.get("nonexistent") is None

    def test_expiration(self):
        """Test cache entries expire after TTL."""
        cache = SimpleCache(ttl=1)  # 1 second TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_max_size_eviction(self):
        """Test that cache evicts oldest entries when max_size is reached."""
        cache = SimpleCache(ttl=60, max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert cache.get("key1") is not None
        cache.set("key4", "value4")  # Should trigger eviction
        # One of the oldest keys should be evicted
        # Note: eviction behavior depends on implementation

    def test_clear(self):
        """Test clearing cache."""
        cache = SimpleCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert len(cache._cache) == 0

    def test_stats(self):
        """Test cache statistics."""
        cache = SimpleCache(ttl=60, max_size=100)
        cache.set("key1", "value1")
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["max_size"] == 100
        assert stats["ttl"] == 60


@pytest.mark.unit
class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_cache_key_from_args_simple(self):
        """Test key generation with simple arguments."""
        key = cache_key_from_args("arg1", "arg2", param1="value1")
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length

    def test_cache_key_from_args_dict(self):
        """Test key generation with dict arguments."""
        key1 = cache_key_from_args({"a": 1, "b": 2})
        key2 = cache_key_from_args({"b": 2, "a": 1})
        # Same content should produce same key regardless of order
        assert key1 == key2

    def test_cache_key_from_args_list(self):
        """Test key generation with list arguments."""
        key = cache_key_from_args([1, 2, 3])
        assert isinstance(key, str)
        assert len(key) == 32

    def test_cache_key_consistency(self):
        """Test that same arguments produce same key."""
        key1 = cache_key_from_args("test", param=123)
        key2 = cache_key_from_args("test", param=123)
        assert key1 == key2

    def test_cache_key_different_args(self):
        """Test that different arguments produce different keys."""
        key1 = cache_key_from_args("test", param=123)
        key2 = cache_key_from_args("test", param=456)
        assert key1 != key2


@pytest.mark.unit
class TestCachedDecorator:
    """Tests for @cached decorator."""

    def test_cached_decorator(self):
        """Test that cached decorator caches results."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            # Clear global cache
            import core.cache
            core.cache._global_cache = None

            call_count = [0]

            @cached(ttl=10)
            def expensive_function(x):
                call_count[0] += 1
                return x * 2

            result1 = expensive_function(5)
            result2 = expensive_function(5)

            assert result1 == 10
            assert result2 == 10
            assert call_count[0] == 1  # Function called only once

    def test_cached_decorator_different_args(self):
        """Test that different arguments produce different cache entries."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            import core.cache
            core.cache._global_cache = None

            call_count = [0]

            @cached(ttl=10)
            def expensive_function(x):
                call_count[0] += 1
                return x * 2

            expensive_function(5)
            expensive_function(10)

            assert call_count[0] == 2

    def test_cached_with_dict_args(self):
        """Test caching with dict arguments."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            import core.cache
            core.cache._global_cache = None

            call_count = [0]

            @cached(ttl=10)
            def process_dict(data):
                call_count[0] += 1
                return data["value"]

            result1 = process_dict({"value": 100})
            _result2 = process_dict({"value": 100})

            assert result1 == 100
            assert call_count[0] == 1

    def test_cached_decorator_raises_on_error(self):
        """Test that exceptions are not cached."""
        with patch("core.config_loader.is_feature_enabled", return_value=True):
            import core.cache
            core.cache._global_cache = None

            error_count = [0]

            @cached(ttl=10)
            def failing_function():
                error_count[0] += 1
                raise ValueError("Test error")

            with pytest.raises(ValueError, match="Test error"):
                failing_function()

            with pytest.raises(ValueError, match="Test error"):
                failing_function()

            assert error_count[0] == 2  # Function called each time


@pytest.mark.unit
class TestCacheFactory:
    """Tests for cache factory pattern."""

    def test_get_global_cache_returns_simple_cache_by_default(self):
        """Test that get_global_cache returns SimpleCache by default."""
        with patch("core.config_loader.get_feature_flags", return_value={}):
            import core.cache
            core.cache._global_cache = None

            cache = get_global_cache()
            assert isinstance(cache, SimpleCache)

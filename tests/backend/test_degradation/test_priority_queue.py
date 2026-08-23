"""
Tests for Priority Data Fetcher - Phase 7 Sprint 2
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.degradation.priority_queue import (
    PriorityDataFetcher,
    FetchResult,
    FetchSummary,
    PriorityFetcherBuilder
)
from app.degradation.priority_config import (
    Priority,
    PriorityConfig,
    PriorityConfigManager
)


class TestFetchResult:
    """Tests for FetchResult model."""

    def test_create_success_result(self):
        """Test creating a successful fetch result."""
        result = FetchResult(
            source_name="test_source",
            status="success",
            priority="P0",
            data={"key": "value"},
            timeout_ms=5000,
            fetch_time_ms=150.5
        )

        assert result.source_name == "test_source"
        assert result.status == "success"
        assert result.data == {"key": "value"}
        assert result.priority == "P0"
        assert result.fetch_time_ms == 150.5

    def test_create_cached_result(self):
        """Test creating a cached fetch result."""
        result = FetchResult(
            source_name="test_source",
            status="cached",
            priority="P1",
            data={"cached": True},
            cache_age="L2"
        )

        assert result.status == "cached"
        assert result.cache_age == "L2"

    def test_create_error_result(self):
        """Test creating an error fetch result."""
        result = FetchResult(
            source_name="test_source",
            status="error",
            priority="P2",
            error="Connection timeout"
        )

        assert result.status == "error"
        assert result.error == "Connection timeout"
        assert result.data is None


class TestFetchSummary:
    """Tests for FetchSummary model."""

    def test_empty_summary(self):
        """Test creating an empty summary."""
        summary = FetchSummary()

        assert summary.total_sources == 0
        assert summary.successful == 0
        assert summary.timeouts == 0
        assert summary.total_time_ms == 0

    def test_summary_with_results(self):
        """Test summary populated with results."""
        summary = FetchSummary(
            total_sources=5,
            successful=3,
            cached=1,
            timeouts=1,
            errors=0,
            total_time_ms=1500.0
        )

        assert summary.total_sources == 5
        assert summary.successful == 3
        assert summary.cached == 1
        assert summary.timeouts == 1


class TestPriorityDataFetcher:
    """Tests for PriorityDataFetcher."""

    @pytest.fixture
    def priority_manager(self):
        """Create a priority config manager for testing."""
        return PriorityConfigManager(auto_save=False)

    @pytest.fixture
    def fetcher(self, priority_manager):
        """Create a priority data fetcher for testing."""
        return PriorityDataFetcher(
            priority_config=priority_manager,
            hysteresis_factor=0.1,
            mode_change_cooldown=timedelta(minutes=5)
        )

    @pytest.fixture
    def mock_l2_cache(self):
        """Create a mock L2 cache."""
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        return cache

    @pytest.fixture
    def mock_critical_cache(self):
        """Create a mock critical cache."""
        cache = AsyncMock()
        cache.get_critical_data = AsyncMock(return_value=None)
        return cache

    def test_initialization(self, priority_manager):
        """Test fetcher initialization."""
        fetcher = PriorityDataFetcher(
            priority_config=priority_manager,
            hysteresis_factor=0.15
        )

        assert fetcher.config == priority_manager
        assert fetcher.hysteresis == 0.15
        assert fetcher.current_mode == "normal"

    def test_priority_timeouts(self):
        """Test priority timeout allocations."""
        assert PriorityDataFetcher.PRIORITY_TIMEOUTS[Priority.P0] == 5000
        assert PriorityDataFetcher.PRIORITY_TIMEOUTS[Priority.P1] == 3000
        assert PriorityDataFetcher.PRIORITY_TIMEOUTS[Priority.P2] == 2000
        assert PriorityDataFetcher.PRIORITY_TIMEOUTS[Priority.P3] == 1000

    def test_hysteresis_bounds(self, fetcher):
        """Test hysteresis calculation."""
        threshold = 0.8

        upper = fetcher.get_hysteresis_upper_bound(threshold)
        lower = fetcher.get_hysteresis_lower_bound(threshold)

        assert upper == 0.88  # 0.8 * 1.1
        assert lower == 0.72  # 0.8 * 0.9

    def test_mode_change_cooldown(self, fetcher):
        """Test mode change cooldown logic."""
        # Initially can change
        assert fetcher.can_change_mode() is True

        # Record a change
        fetcher.record_mode_change("degraded")

        # Should not be able to change immediately
        assert fetcher.can_change_mode() is False

        # But after cooldown, should be able to change
        with patch('app.degradation.priority_queue.datetime') as mock_datetime:
            # Mock time to be after cooldown
            mock_datetime.now.return_value = (
                datetime.now() + timedelta(minutes=10)
            )
            # Note: This test would need more sophisticated mocking

    @pytest.mark.asyncio
    async def test_group_by_priority(self, fetcher):
        """Test grouping fetchers by priority."""
        fetchers = {
            "health": AsyncMock(return_value={"status": "ok"}),
            "analytics": AsyncMock(return_value={"data": []}),
        }

        grouped = fetcher._group_by_priority(fetchers, None)

        # Health endpoints should be P0
        assert Priority.P0 in grouped
        health_tasks = [t for t in grouped[Priority.P0] if t[0] == "health"]
        assert len(health_tasks) > 0

        # Analytics should be P3
        assert Priority.P3 in grouped
        analytics_tasks = [t for t in grouped[Priority.P3] if t[0] == "analytics"]
        assert len(analytics_tasks) > 0

    @pytest.mark.asyncio
    async def test_fetch_by_priority_basic(self, fetcher):
        """Test basic priority-based fetching."""
        fetchers = {
            "health_endpoints": AsyncMock(return_value={"status": "healthy"}),
        }

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=10000)

        assert "health_endpoints" in results
        assert results["health_endpoints"].status == "success"

    @pytest.mark.asyncio
    async def test_fetch_with_timeout(self, fetcher):
        """Test fetch with timeout handling."""
        async def slow_fetcher():
            await asyncio.sleep(10)  # Longer than timeout
            return {"data": "too slow"}

        fetchers = {
            "slow_source": slow_fetcher
        }

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=1000)

        # Should timeout
        assert results["slow_source"].status in ["timeout", "cached"]

    @pytest.mark.asyncio
    async def test_fetch_with_fallback_cache(self, fetcher, mock_l2_cache):
        """Test fallback to cache on timeout."""
        fetcher.l2_cache = mock_l2_cache

        # Configure cache to return data
        mock_l2_cache.get.return_value = {
            "data": {"cached": True},
            "age": "2 minutes"
        }

        async def failing_fetcher():
            await asyncio.sleep(10)  # Will timeout
            return {"data": "never returned"}

        fetchers = {
            "failing_source": failing_fetcher
        }

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=1000)

        # Should fall back to cache
        assert results["failing_source"].status == "cached"
        assert results["failing_source"].data is not None

    @pytest.mark.asyncio
    async def test_fetch_with_retry(self, fetcher):
        """Test fetch with retry logic."""
        attempt_count = 0

        async def flaky_fetcher():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Temporary failure")
            return {"data": "success"}

        fetchers = {
            "flaky_source": flaky_fetcher
        }

        # Get config for flaky_source with retries
        config = PriorityConfig(
            source_name="flaky_source",
            priority=Priority.P1,
            timeout_ms=5000,
            retry_count=3
        )
        fetcher.config.update_config("flaky_source", config)

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=15000)

        # Should succeed after retries
        assert results["flaky_source"].status == "success"
        assert attempt_count == 3  # Failed twice, succeeded on 3rd

    @pytest.mark.asyncio
    async def test_priority_order_respected(self, fetcher):
        """Test that P0 sources are fetched before P3."""
        call_order = []

        async def p0_fetcher():
            call_order.append("P0")
            return {"priority": "P0"}

        async def p3_fetcher():
            call_order.append("P3")
            return {"priority": "P3"}

        fetchers = {
            "p3_source": p3_fetcher,
            "p0_source": p0_fetcher,
        }

        # Override configs to set priorities
        p0_config = PriorityConfig(
            source_name="p0_source",
            priority=Priority.P0,
            timeout_ms=100
        )
        p3_config = PriorityConfig(
            source_name="p3_source",
            priority=Priority.P3,
            timeout_ms=100
        )
        fetcher.config.update_config("p0_source", p0_config)
        fetcher.config.update_config("p3_source", p3_config)

        await fetcher.fetch_by_priority(fetchers, total_timeout=1000)

        # P0 should be called before P3
        assert call_order.index("P0") < call_order.index("P3")

    @pytest.mark.asyncio
    async def test_create_summary(self, fetcher):
        """Test summary creation from results."""
        results = {
            "source1": FetchResult(
                source_name="source1",
                status="success",
                priority="P0",
                data={"ok": True}
            ),
            "source2": FetchResult(
                source_name="source2",
                status="cached",
                priority="P1",
                data={"cached": True}
            ),
            "source3": FetchResult(
                source_name="source3",
                status="timeout",
                priority="P2"
            ),
        }

        summary = fetcher._create_summary(results, 1500.0)

        assert summary.total_sources == 3
        assert summary.successful == 1
        assert summary.cached == 1
        assert summary.timeouts == 1
        assert summary.total_time_ms == 1500.0

    @pytest.mark.asyncio
    async def test_fetch_with_error_and_cache(self, fetcher, mock_l2_cache, mock_critical_cache):
        """Test error handling with both cache types."""
        fetcher.l2_cache = mock_l2_cache
        fetcher.critical_cache = mock_critical_cache

        async def error_fetcher():
            raise ValueError("Database error")

        # L2 cache returns None, critical cache has data
        mock_l2_cache.get.return_value = None
        mock_critical_cache.get_critical_data.return_value = {
            "data": {"critical": True}
        }

        fetchers = {"error_source": error_fetcher}

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=5000)

        # Should fall back to critical cache
        assert results["error_source"].status == "cached"


class TestPriorityFetcherBuilder:
    """Tests for PriorityFetcherBuilder."""

    def test_builder_pattern(self):
        """Test builder pattern for PriorityDataFetcher."""
        manager = PriorityConfigManager(auto_save=False)

        fetcher = (PriorityFetcherBuilder()
                   .with_config(manager)
                   .with_hysteresis(0.15)
                   .with_cooldown(timedelta(minutes=10))
                   .build())

        assert isinstance(fetcher, PriorityDataFetcher)
        assert fetcher.hysteresis == 0.15
        assert fetcher.mode_change_cooldown == timedelta(minutes=10)

    def test_builder_without_config_raises(self):
        """Test builder without config raises error."""
        builder = PriorityFetcherBuilder()

        with pytest.raises(ValueError, match="Config manager is required"):
            builder.build()

    def test_builder_with_cache_instances(self):
        """Test builder with cache instances."""
        manager = PriorityConfigManager(auto_save=False)
        mock_l2 = Mock()
        mock_critical = Mock()

        fetcher = (PriorityFetcherBuilder()
                   .with_config(manager)
                   .with_l2_cache(mock_l2)
                   .with_critical_cache(mock_critical)
                   .build())

        assert fetcher.l2_cache == mock_l2
        assert fetcher.critical_cache == mock_critical


@pytest.mark.asyncio
class TestPriorityFetcherIntegration:
    """Integration tests for priority fetcher."""

    async def test_full_fetch_cycle(self):
        """Test complete fetch cycle with mixed results."""
        manager = PriorityConfigManager(auto_save=False)

        async def fast_p0():
            return {"fast": True}

        async def slow_p1():
            await asyncio.sleep(0.1)
            return {"slow": True}

        async def failing_p2():
            raise ConnectionError("Failed")

        fetcher = PriorityDataFetcher(priority_config=manager)

        fetchers = {
            "fast_p0": fast_p0,
            "slow_p1": slow_p1,
            "failing_p2": failing_p2,
        }

        # Configure priorities
        manager.update_config("fast_p0", PriorityConfig(
            source_name="fast_p0",
            priority=Priority.P0,
            timeout_ms=1000
        ))
        manager.update_config("slow_p1", PriorityConfig(
            source_name="slow_p1",
            priority=Priority.P1,
            timeout_ms=1000
        ))
        manager.update_config("failing_p2", PriorityConfig(
            source_name="failing_p2",
            priority=Priority.P2,
            timeout_ms=1000,
            fallback_to_cache=False
        ))

        results = await fetcher.fetch_by_priority(fetchers, total_timeout=5000)

        assert results["fast_p0"].status == "success"
        assert results["slow_p1"].status == "success"
        assert results["failing_p2"].status == "error"

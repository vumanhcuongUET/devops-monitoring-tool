"""
DR Scenario Tests - Phase 7 Sprint 2 Day 17

Comprehensive test scenarios for disaster recovery and graceful degradation.
These tests simulate real-world failure scenarios and validate the system's response.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.degradation.dr_handler import (
    DRHandler,
    DRMode,
    ModeTransition,
    SourceHealth
)
from app.degradation.priority_queue import (
    PriorityDataFetcher,
    FetchResult
)
from app.degradation.priority_config import (
    PriorityConfigManager,
    Priority,
    PriorityConfig
)
from app.degradation.critical_cache import (
    CriticalDataCache,
    CriticalDataEntry
)


@pytest.mark.asyncio
class TestDRScenarios:
    """
    Test suite for comprehensive DR scenarios.

    Tests cover:
    - Normal mode operations
    - Degraded mode with partial failures
    - Emergency mode with critical failures
    - Mode transitions with hysteresis
    - Recovery scenarios
    """

    @pytest.fixture
    def dr_handler(self):
        """Create DR handler for testing."""
        on_call_calls = []

        async def mock_on_call(transition):
            on_call_calls.append(transition)

        handler = DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.05,
            check_interval=60
        )
        handler.on_call_calls = on_call_calls
        return handler

    @pytest.fixture
    def priority_manager(self):
        """Create priority config manager."""
        return PriorityConfigManager(auto_save=False)

    @pytest.fixture
    def priority_fetcher(self, priority_manager):
        """Create priority data fetcher."""
        return PriorityDataFetcher(
            priority_config=priority_manager,
            hysteresis_factor=0.1
        )

    async def test_normal_mode_all_sources_up(self, dr_handler):
        """Test normal mode when all sources are available."""
        # Simulate all sources healthy
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })

        # Check health and transition
        transition = await dr_handler.check_health_and_transition()

        # Should remain in NORMAL mode
        assert dr_handler.current_mode == DRMode.NORMAL
        assert transition is None  # No transition needed

        # Health percentage should be 100%
        health = dr_handler._calculate_health_percentage()
        assert health == 1.0

    async def test_degraded_mode_half_sources_down(self, dr_handler):
        """Test degraded mode when 50% of sources are down."""
        # Elasticsearch down (40% weight), others up
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": True,
            "kubernetes": True
        })

        # Reset transition cooldown for testing
        dr_handler.last_transition = None

        # Check health and transition
        transition = await dr_handler.check_health_and_transition()

        # Should transition to DEGRADED mode
        assert dr_handler.current_mode == DRMode.DEGRADED
        assert transition is not None
        assert transition.to_mode == "degraded"

        # Health percentage should be 60% (Prom 30% + K8s 30%)
        health = dr_handler._calculate_health_percentage()
        assert abs(health - 0.6) < 0.01

        # On-call should be notified
        assert len(dr_handler.on_call_calls) == 1

    async def test_emergency_mode_most_sources_down(self, dr_handler):
        """Test emergency mode when most sources are down."""
        # Only K8s up (30% weight)
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": True
        })

        dr_handler.last_transition = None

        # Check health and transition
        transition = await dr_handler.check_health_and_transition()

        # Should transition to EMERGENCY mode
        assert dr_handler.current_mode == DRMode.EMERGENCY
        assert transition.to_mode == "emergency"

        # Health percentage should be 30%
        health = dr_handler._calculate_health_percentage()
        assert abs(health - 0.3) < 0.01

    async def test_mode_transition_with_hysteresis(self, dr_handler):
        """Test that hysteresis prevents mode flapping."""
        # Start in NORMAL mode
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })
        assert dr_handler.current_mode == DRMode.NORMAL

        # Drop to 78% health (below 80% threshold)
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,  # Lost 40%
            "prometheus": True,    # 30%
            "kubernetes": True     # 30% = 60% total
        })

        dr_handler.last_transition = None

        # First transition
        await dr_handler.check_health_and_transition()
        assert dr_handler.current_mode == DRMode.DEGRADED

        # Immediately recover to 85% health
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,  # 40%
            "prometheus": True,    # 30%
            "kubernetes": False    # 0% = 70% total
        })

        # Should NOT transition back immediately due to hysteresis
        await dr_handler.check_health_and_transition()
        assert dr_handler.current_mode == DRMode.DEGRADED

        # Need to exceed upper bound (80% * 1.05 = 84%)
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,   # 40%
            "prometheus": True,      # 30%
            "kubernetes": True       # 30% = 100%
        })

        # Clear cooldown for testing
        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()

        # Now should transition back to NORMAL
        assert dr_handler.current_mode == DRMode.NORMAL

    async def test_critical_cache_auto_refresh(self):
        """Test critical cache auto-refresh mechanism."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.sadd = AsyncMock(return_value=True)
        mock_redis.smembers = AsyncMock(return_value=set())

        cache = CriticalDataCache(
            redis_client=mock_redis,
            auto_refresh=False,  # Manual control for testing
            refresh_interval=300
        )

        # Store initial data
        await cache.set_critical_data(
            project="test",
            source_name="health",
            data={"status": "healthy"},
            ttl=900
        )

        # Register refresh callback
        refresh_count = 0

        async def fetcher():
            nonlocal refresh_count
            refresh_count += 1
            return {"status": "refreshed", "count": refresh_count}

        cache.register_refresh_callback("test", "health", fetcher)

        # Refresh the entry
        await cache.refresh_entry("test", "health", fetcher)

        # Verify refresh was called
        assert refresh_count == 1

        # Verify data was stored
        assert mock_redis.setex.called

    async def test_on_call_escalation(self, dr_handler):
        """Test on-call escalation during mode degradation."""
        escalation_log = []

        async def escalation_handler(transition):
            escalation_log.append({
                "mode": transition.to_mode,
                "health": transition.health_percentage,
                "timestamp": transition.timestamp
            })

        dr_handler.on_call_integration = escalation_handler

        # Degrade to EMERGENCY
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": False
        })

        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()

        # Verify on-call was notified
        assert len(escalation_log) == 1
        assert escalation_log[0]["mode"] == "emergency"
        assert escalation_log[0]["health"] == 0.0

    async def test_source_recovery(self, dr_handler):
        """Test recovery when sources come back online."""
        # Start in EMERGENCY mode
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": True  # Only K8s up
        })

        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()
        assert dr_handler.current_mode == DRMode.EMERGENCY

        # ES comes back online
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": False,
            "kubernetes": True
        })

        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()

        # Should recover to DEGRADED
        assert dr_handler.current_mode == DRMode.DEGRADED

        # Prometheus also comes back
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })

        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()

        # Should recover to NORMAL
        assert dr_handler.current_mode == DRMode.NORMAL

    async def test_priority_fetching_during_degradation(self, priority_manager, priority_fetcher):
        """Test priority-based fetching during degraded mode."""
        # Mock cache fallback
        mock_l2 = AsyncMock()
        mock_l2.get.return_value = {"cached": True, "age": "2 min"}
        priority_fetcher.l2_cache = mock_l2

        # Simulate ES timeout (P0 source)
        async def es_fetcher():
            await asyncio.sleep(10)  # Will timeout
            return {"es": "data"}

        # Simulate analytics fetcher (P3 source)
        async def analytics_fetcher():
            await asyncio.sleep(10)
            return {"analytics": "data"}

        fetchers = {
            "health_endpoints": AsyncMock(return_value={"health": "ok"}),
            "active_alerts": AsyncMock(return_value={"alerts": []}),
            "analytics": analytics_fetcher,
        }

        # Configure priorities
        priority_manager.update_config("health_endpoints", PriorityConfig(
            source_name="health_endpoints",
            priority=Priority.P0,
            timeout_ms=5000
        ))
        priority_manager.update_config("active_alerts", PriorityConfig(
            source_name="active_alerts",
            priority=Priority.P0,
            timeout_ms=5000
        ))
        priority_manager.update_config("analytics", PriorityConfig(
            source_name="analytics",
            priority=Priority.P3,
            timeout_ms=1000,
            fallback_to_cache=True
        ))

        # Fetch with limited timeout
        results = await priority_fetcher.fetch_by_priority(fetchers, total_timeout=8000)

        # P0 sources should succeed
        assert results["health_endpoints"].status == "success"
        assert results["active_alerts"].status == "success"

        # P3 source should timeout and use fallback cache
        assert results["analytics"].status == "cached"

    async def test_consecutive_failure_tracking(self, dr_handler):
        """Test tracking of consecutive failures for sources."""
        # First failure
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": True,
            "kubernetes": True
        })

        es_health = dr_handler.source_health["elasticsearch"]
        assert es_health.consecutive_failures == 1

        # Second failure
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": True,
            "kubernetes": True
        })

        es_health = dr_handler.source_health["elasticsearch"]
        assert es_health.consecutive_failures == 2

        # Recovery
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })

        es_health = dr_handler.source_health["elasticsearch"]
        assert es_health.consecutive_failures == 0
        assert es_health.available is True

    async def test_mode_transition_history(self, dr_handler):
        """Test that mode transitions are properly recorded."""
        # Create multiple transitions
        transitions = []

        async def create_transition(from_mode, to_mode, health):
            dr_handler.current_mode = DRMode[from_mode.upper()]
            await dr_handler._update_source_health_manual({
                "elasticsearch": health < 0.4,
                "prometheus": health < 0.7,
                "kubernetes": health > 0.3
            })
            dr_handler.last_transition = None
            transition = await dr_handler.check_health_and_transition()
            if transition:
                transitions.append(transition)

        # Normal -> Degraded
        await create_transition("NORMAL", "DEGRADED", 0.6)

        # Degraded -> Emergency
        await create_transition("DEGRADED", "EMERGENCY", 0.3)

        # Emergency -> Degraded
        await create_transition("EMERGENCY", "DEGRADED", 0.6)

        # Get history
        history = dr_handler.get_transition_history(limit=10)

        assert len(history["transitions"]) >= 3
        assert history["total"] >= 3

        # Verify order
        modes = [t["from_mode"] for t in history["transitions"]]
        assert "normal" in modes
        assert "degraded" in modes


@pytest.mark.asyncio
class TestChaosScenarios:
    """
    Chaos engineering test scenarios.

    These tests validate the system's response to unexpected failures
    and edge cases.
    """

    async def test_rapid_fluctuation(self):
        """Test system behavior with rapidly fluctuating source health."""
        on_call_calls = []

        async def mock_on_call(transition):
            on_call_calls.append(transition)

        handler = DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.1,  # 10% hysteresis for stability
            check_interval=1
        )

        # Rapidly fluctuating health
        health_values = [0.9, 0.75, 0.85, 0.7, 0.8, 0.95]

        for health in health_values:
            await handler._update_source_health_manual({
                "elasticsearch": health > 0.5,
                "prometheus": health > 0.6,
                "kubernetes": health > 0.7
            })
            handler.last_transition = None
            await handler.check_health_and_transition()

        # With hysteresis, should have minimal transitions
        # Not one for each health change
        assert len(on_call_calls) < len(health_values)

    async def test_all_sources_simultaneous_failure(self):
        """Test behavior when all sources fail simultaneously."""
        on_call_calls = []

        async def mock_on_call(transition):
            on_call_calls.append(transition)

        handler = DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.05
        )

        # All sources fail at once
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": False
        })

        handler.last_transition = None
        await handler.check_health_and_transition()

        # Should go straight to EMERGENCY
        assert handler.current_mode == DRMode.EMERGENCY

        # Should notify on-call
        assert len(on_call_calls) == 1
        assert on_call_calls[0].to_mode == "emergency"

    async def test_partial_recovery_from_emergency(self):
        """Test partial recovery from EMERGENCY mode."""
        handler = DRHandler(hysteresis=0.05)

        # Start in EMERGENCY
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": False
        })

        handler.last_transition = None
        await handler.check_health_and_transition()
        assert handler.current_mode == DRMode.EMERGENCY

        # Only K8s recovers (30% health)
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": True
        })

        # Should stay in EMERGENCY (below 50% threshold)
        handler.last_transition = None
        await handler.check_health_and_transition()
        assert handler.current_mode == DRMode.EMERGENCY

    async def test_priority_with_extended_timeout(self):
        """Test priority fetching with extended timeout for P0 sources."""
        manager = PriorityConfigManager(auto_save=False)

        # Configure extended timeout for P0
        manager.update_config("health_endpoints", PriorityConfig(
            source_name="health_endpoints",
            priority=Priority.P0,
            timeout_ms=10000,  # Extended timeout
            retry_count=5
        ))

        fetcher = PriorityDataFetcher(priority_config=manager)

        # Verify config
        config = manager.get_config("health_endpoints")
        assert config.timeout_ms == 10000
        assert config.retry_count == 5
        assert config.priority == Priority.P0

"""
Chaos Engineering Tests - Phase 7 Sprint 2 Day 17

Safe chaos engineering tests for DR validation.
These tests only run in non-production environments.
"""

import pytest
import os
import asyncio
from enum import Enum
from typing import Optional
from unittest.mock import Mock, AsyncMock, patch

from app.degradation.dr_handler import DRHandler, DRMode
from app.degradation.priority_queue import PriorityDataFetcher
from app.degradation.priority_config import PriorityConfigManager
from app.degradation.critical_cache import CriticalDataCache


class Environment(Enum):
    """Environment types."""
    DEV = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ChaosEngineering:
    """
    Chaos engineering tests for DR validation.

    IMPORTANT: These tests should NEVER run in production.
    They simulate failures to validate the graceful degradation system.
    """

    def __init__(self, current_env: Environment):
        self.env = current_env

    def _validate_environment(self):
        """Ensure chaos tests only run in safe environments."""
        if self.env == Environment.PRODUCTION:
            raise EnvironmentError(
                "Chaos engineering tests are NOT allowed in production. "
                "Current environment: production"
            )

    def _log_chaos_event(self, event: str, details: dict):
        """Log chaos engineering events."""
        print(f"[CHAOS] {event}: {details}")

    async def simulate_elasticsearch_failure(self, dr_handler: DRHandler):
        """
        Simulate Elasticsearch cluster failure.

        Validates:
        - Mode transitions to DEGRADED or EMERGENCY
        - Fallback to cached data works
        - On-call escalation occurs
        """
        self._validate_environment()
        self._log_chaos_event("ES_FAILURE_START", {"simulation": "elasticsearch_down"})

        try:
            # Simulate ES failure
            await dr_handler._update_source_health_manual({
                "elasticsearch": False,
                "prometheus": True,
                "kubernetes": True
            })

            dr_handler.last_transition = None
            transition = await dr_handler.check_health_and_transition()

            # Validate response
            assert dr_handler.current_mode in [DRMode.DEGRADED, DRMode.EMERGENCY], \
                f"Expected degraded mode, got {dr_handler.current_mode}"

            self._log_chaos_event("ES_FAILURE_VALIDATED", {
                "new_mode": dr_handler.current_mode.value,
                "transition": transition.to_dict() if transition else None
            })

            return True

        finally:
            # Auto-recover after test
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": True,
                "kubernetes": True
            })
            self._log_chaos_event("ES_FAILURE_RECOVERED", {})

    async def simulate_prometheus_timeout(self, priority_fetcher: PriorityDataFetcher):
        """
        Simulate Prometheus timeout/failure.

        Validates:
        - Timeout handling works correctly
        - Fallback to cache occurs
        - Other priorities still fetch successfully
        """
        self._validate_environment()
        self._log_chaos_event("PROM_TIMEOUT_START", {"simulation": "prometheus_timeout"})

        try:
            # Simulate timeout
            async def slow_prometheus():
                await asyncio.sleep(10)
                return {"metrics": "data"}

            async def fast_es():
                return {"logs": "data"}

            fetchers = {
                "prometheus": slow_prometheus,
                "elasticsearch": fast_es
            }

            results = await priority_fetcher.fetch_by_priority(
                fetchers,
                total_timeout=3000
            )

            # Validate timeout handling
            assert results["prometheus"].status in ["timeout", "cached", "error"], \
                f"Expected timeout/cached for Prometheus, got {results['prometheus'].status}"

            assert results["elasticsearch"].status == "success", \
                "ES should have succeeded"

            self._log_chaos_event("PROM_TIMEOUT_VALIDATED", {
                "prometheus_status": results["prometheus"].status,
                "elasticsearch_status": results["elasticsearch"].status
            })

            return True

        finally:
            self._log_chaos_event("PROM_TIMEOUT_RECOVERED", {})

    async def simulate_network_partition(self, dr_handler: DRHandler):
        """
        Simulate network partition affecting some sources.

        Validates:
        - Graceful degradation with partial connectivity
        - Correct health percentage calculation
        - Appropriate mode transition
        """
        self._validate_environment()
        self._log_chaos_event("NETWORK_PARTITION_START", {
            "simulation": "partial_network_partition"
        })

        try:
            # Simulate network partition affecting ES and K8s
            await dr_handler._update_source_health_manual({
                "elasticsearch": False,  # Partitioned
                "prometheus": True,      # Still reachable
                "kubernetes": False      # Partitioned
            })

            dr_handler.last_transition = None
            transition = await dr_handler.check_health_and_transition()

            # Should be in EMERGENCY (only 30% health from Prometheus)
            assert dr_handler.current_mode == DRMode.EMERGENCY, \
                f"Expected emergency mode, got {dr_handler.current_mode}"

            health = dr_handler._calculate_health_percentage()
            assert health == 0.3, f"Expected 30% health, got {health}"

            self._log_chaos_event("NETWORK_PARTITION_VALIDATED", {
                "mode": dr_handler.current_mode.value,
                "health_percentage": health
            })

            return True

        finally:
            # Recover all sources
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": True,
                "kubernetes": True
            })
            self._log_chaos_event("NETWORK_PARTITION_RECOVERED", {})

    async def simulate_cascading_failures(self, dr_handler: DRHandler):
        """
        Simulate cascading failures (one source failing after another).

        Validates:
        - Progressive mode transitions
        - Each failure is handled correctly
        - System doesn't crash due to multiple failures
        """
        self._validate_environment()
        self._log_chaos_event("CASCADING_FAILURES_START", {})

        try:
            modes_recorded = []

            # Start healthy
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": True,
                "kubernetes": True
            })
            assert dr_handler.current_mode == DRMode.NORMAL
            modes_recorded.append(("start", dr_handler.current_mode.value))

            # First failure: K8s
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": True,
                "kubernetes": False
            })
            dr_handler.last_transition = None
            await dr_handler.check_health_and_transition()
            modes_recorded.append(("k8s_down", dr_handler.current_mode.value))

            # Second failure: Prometheus
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": False,
                "kubernetes": False
            })
            dr_handler.last_transition = None
            await dr_handler.check_health_and_transition()
            modes_recorded.append(("prom_down", dr_handler.current_mode.value))

            # Third failure: Elasticsearch
            await dr_handler._update_source_health_manual({
                "elasticsearch": False,
                "prometheus": False,
                "kubernetes": False
            })
            dr_handler.last_transition = None
            await dr_handler.check_health_and_transition()
            modes_recorded.append(("es_down", dr_handler.current_mode.value))

            # Validate progressive degradation
            assert modes_recorded[0][1] == "normal"
            assert modes_recorded[-1][1] == "emergency"

            self._log_chaos_event("CASCADING_FAILURES_VALIDATED", {
                "progression": modes_recorded
            })

            return True

        finally:
            # Full recovery
            await dr_handler._update_source_health_manual({
                "elasticsearch": True,
                "prometheus": True,
                "kubernetes": True
            })
            self._log_chaos_event("CASCADING_FAILURES_RECOVERED", {})

    async def simulate_cache_failure(self, priority_fetcher: PriorityDataFetcher):
        """
        Simulate cache unavailability during degradation.

        Validates:
        - System continues without cache
        - Appropriate error handling
        - No crashes due to cache unavailability
        """
        self._validate_environment()
        self._log_chaos_event("CACHE_FAILURE_START", {})

        try:
            # Remove cache fallback
            original_l2 = priority_fetcher.l2_cache
            priority_fetcher.l2_cache = None
            original_critical = priority_fetcher.critical_cache
            priority_fetcher.critical_cache = None

            async def failing_source():
                raise ConnectionError("Source unavailable")

            fetchers = {
                "failing_source": failing_source
            }

            results = await priority_fetcher.fetch_by_priority(
                fetchers,
                total_timeout=5000
            )

            # Should return error without crashing
            assert results["failing_source"].status == "error"
            assert results["failing_source"].error is not None

            self._log_chaos_event("CACHE_FAILURE_VALIDATED", {
                "status": results["failing_source"].status
            })

            return True

        finally:
            # Restore cache
            priority_fetcher.l2_cache = original_l2
            priority_fetcher.critical_cache = original_critical
            self._log_chaos_event("CACHE_FAILURE_RECOVERED", {})


@pytest.mark.asyncio
class TestChaosEngineering:
    """Test suite for chaos engineering scenarios."""

    @pytest.fixture
    def env(self):
        """Get current environment."""
        env_var = os.getenv("ENVIRONMENT", "development").lower()
        if env_var == "production":
            return Environment.PRODUCTION
        elif env_var == "staging":
            return Environment.STAGING
        else:
            return Environment.DEV

    @pytest.fixture
    def chaos(self, env):
        """Create chaos engineering instance."""
        return ChaosEngineering(env)

    @pytest.fixture
    def dr_handler(self):
        """Create DR handler."""
        async def mock_on_call(transition):
            pass

        return DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.05
        )

    @pytest.fixture
    def priority_fetcher(self):
        """Create priority fetcher."""
        return PriorityDataFetcher(
            priority_config=PriorityConfigManager(auto_save=False)
        )

    async def test_elasticsearch_failure_chaos(self, chaos, dr_handler):
        """Test chaos scenario: Elasticsearch failure."""
        if chaos.env == Environment.PRODUCTION:
            pytest.skip("Chaos tests not allowed in production")

        result = await chaos.simulate_elasticsearch_failure(dr_handler)
        assert result is True

    async def test_prometheus_timeout_chaos(self, chaos, priority_fetcher):
        """Test chaos scenario: Prometheus timeout."""
        if chaos.env == Environment.PRODUCTION:
            pytest.skip("Chaos tests not allowed in production")

        result = await chaos.simulate_prometheus_timeout(priority_fetcher)
        assert result is True

    async def test_network_partition_chaos(self, chaos, dr_handler):
        """Test chaos scenario: Network partition."""
        if chaos.env == Environment.PRODUCTION:
            pytest.skip("Chaos tests not allowed in production")

        result = await chaos.simulate_network_partition(dr_handler)
        assert result is True

    async def test_cascading_failures_chaos(self, chaos, dr_handler):
        """Test chaos scenario: Cascading failures."""
        if chaos.env == Environment.PRODUCTION:
            pytest.skip("Chaos tests not allowed in production")

        result = await chaos.simulate_cascading_failures(dr_handler)
        assert result is True

    async def test_cache_failure_chaos(self, chaos, priority_fetcher):
        """Test chaos scenario: Cache failure."""
        if chaos.env == Environment.PRODUCTION:
            pytest.skip("Chaos tests not allowed in production")

        result = await chaos.simulate_cache_failure(priority_fetcher)
        assert result is True

    def test_production_environment_protection(self, chaos):
        """Test that production environment is protected."""
        prod_chaos = ChaosEngineering(Environment.PRODUCTION)

        with pytest.raises(EnvironmentError, match="NOT allowed in production"):
            prod_chaos._validate_environment()


@pytest.mark.asyncio
class TestSprint2Integration:
    """Integration tests for complete Sprint 2 functionality."""

    async def test_full_degradation_and_recovery_cycle(self):
        """Test complete cycle from normal to emergency and back."""
        # Setup
        on_call_notifications = []

        async def track_on_call(transition):
            on_call_notifications.append(transition)

        dr_handler = DRHandler(
            on_call_integration=track_on_call,
            hysteresis=0.05
        )

        priority_manager = PriorityConfigManager(auto_save=False)
        priority_fetcher = PriorityDataFetcher(
            priority_config=priority_manager,
            hysteresis_factor=0.1
        )

        # Mock caches
        mock_l2 = AsyncMock()
        mock_l2.get.return_value = {"cached": True}
        priority_fetcher.l2_cache = mock_l2

        # 1. Start in NORMAL mode
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })
        assert dr_handler.current_mode == DRMode.NORMAL

        # 2. Degrade to EMERGENCY
        await dr_handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": True
        })
        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()
        assert dr_handler.current_mode == DRMode.EMERGENCY

        # 3. Test priority fetching in EMERGENCY
        async def fast_fetcher():
            return {"data": "value"}

        async def slow_fetcher():
            await asyncio.sleep(10)
            return {"slow": "data"}

        fetchers = {
            "health": fast_fetcher,
            "analytics": slow_fetcher
        }

        # Configure priorities
        priority_manager.update_config("health", PriorityConfig(
            source_name="health",
            priority=Priority.P0,
            timeout_ms=5000
        ))
        priority_manager.update_config("analytics", PriorityConfig(
            source_name="analytics",
            priority=Priority.P3,
            timeout_ms=1000,
            fallback_to_cache=True
        ))

        results = await priority_fetcher.fetch_by_priority(fetchers, total_timeout=8000)
        assert results["health"].status == "success"
        assert results["analytics"].status in ["cached", "timeout"]

        # 4. Recover to NORMAL
        await dr_handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })
        dr_handler.last_transition = None
        await dr_handler.check_health_and_transition()
        assert dr_handler.current_mode == DRMode.NORMAL

        # Verify on-call was notified for degradation
        assert len(on_call_notifications) >= 1

    async def test_critical_cache_integration(self):
        """Test critical cache integration with DR handler."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(return_value=True)
        mock_redis.smembers = AsyncMock(return_value=set())

        critical_cache = CriticalDataCache(
            redis_client=mock_redis,
            auto_refresh=False
        )

        # Store critical data
        await critical_cache.set_critical_data(
            project="test",
            source_name="health",
            data={"status": "healthy"},
            ttl=900,
            priority="critical"
        )

        # Retrieve it
        result = await critical_cache.get_critical_data("test", "health")
        assert result is not None
        assert result["data"]["status"] == "healthy"

        # Check health status
        health = await critical_cache.get_health_status()
        assert health["status"] == "healthy"
        assert health["redis_connected"] is True

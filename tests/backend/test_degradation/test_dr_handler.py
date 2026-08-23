"""
Tests for DR Handler - Phase 7 Sprint 2
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


class TestDRMode:
    """Tests for DRMode enum."""

    def test_mode_values(self):
        """Test DR mode values."""
        assert DRMode.NORMAL.value == "normal"
        assert DRMode.DEGRADED.value == "degraded"
        assert DRMode.EMERGENCY.value == "emergency"

    def test_mode_comparison(self):
        """Test mode ordering comparison."""
        assert DRMode.EMERGENCY.value < DRMode.DEGRADED.value
        assert DRMode.DEGRADED.value < DRMode.NORMAL.value


class TestSourceHealth:
    """Tests for SourceHealth model."""

    def test_create_healthy_source(self):
        """Test creating a healthy source status."""
        health = SourceHealth(
            source_name="elasticsearch",
            available=True,
            response_time_ms=150.5,
            last_check=datetime.now().isoformat()
        )

        assert health.source_name == "elasticsearch"
        assert health.available is True
        assert health.response_time_ms == 150.5
        assert health.consecutive_failures == 0

    def test_create_unhealthy_source(self):
        """Test creating an unhealthy source status."""
        health = SourceHealth(
            source_name="prometheus",
            available=False,
            response_time_ms=0,
            last_check=datetime.now().isoformat(),
            error="Connection timeout",
            consecutive_failures=3
        )

        assert health.available is False
        assert health.error == "Connection timeout"
        assert health.consecutive_failures == 3

    def test_to_dict(self):
        """Test converting source health to dictionary."""
        health = SourceHealth(
            source_name="kubernetes",
            available=True,
            response_time_ms=100.0,
            last_check="2026-08-23T10:00:00"
        )

        data = health.to_dict()

        assert data["source_name"] == "kubernetes"
        assert data["available"] is True
        assert data["response_time_ms"] == 100.0


class TestModeTransition:
    """Tests for ModeTransition model."""

    def test_create_transition(self):
        """Test creating a mode transition record."""
        transition = ModeTransition(
            from_mode="normal",
            to_mode="degraded",
            timestamp=datetime.now().isoformat(),
            reason="Elasticsearch cluster down",
            available_sources=2,
            total_sources=3,
            health_percentage=0.66,
            triggered_by="automatic"
        )

        assert transition.from_mode == "normal"
        assert transition.to_mode == "degraded"
        assert transition.available_sources == 2
        assert transition.total_sources == 3

    def test_to_dict(self):
        """Test converting transition to dictionary."""
        transition = ModeTransition(
            from_mode="degraded",
            to_mode="emergency",
            timestamp=datetime.now().isoformat(),
            reason="Multiple systems down",
            available_sources=1,
            total_sources=3,
            health_percentage=0.33,
            triggered_by="health_check"
        )

        data = transition.to_dict()

        assert data["from_mode"] == "degraded"
        assert data["to_mode"] == "emergency"
        assert data["health_percentage"] == 0.33


class TestDRHandler:
    """Tests for DRHandler."""

    @pytest.fixture
    def mock_on_call(self):
        """Create a mock on-call integration."""
        return AsyncMock()

    @pytest.fixture
    def handler(self, mock_on_call):
        """Create a DR handler for testing."""
        return DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.05,
            check_interval=60
        )

    def test_initialization(self, mock_on_call):
        """Test handler initialization."""
        handler = DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.1,
            check_interval=120
        )

        assert handler.on_call_integration == mock_on_call
        assert handler.hysteresis == 0.1
        assert handler.check_interval == 120
        assert handler.current_mode == DRMode.NORMAL

    def test_mode_thresholds(self):
        """Test mode transition thresholds."""
        assert DRHandler.MODE_THRESHOLDS[DRMode.EMERGENCY] == 0.5
        assert DRHandler.MODE_THRESHOLDS[DRMode.DEGRADED] == 0.8
        assert DRHandler.MODE_THRESHOLDS[DRMode.NORMAL] == 1.0

    def test_source_weights(self):
        """Test source weights sum to 1.0."""
        total = sum(DRHandler.SOURCE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01  # Allow floating point tolerance

    def test_get_current_mode(self, handler):
        """Test getting current mode."""
        assert handler.get_current_mode() == DRMode.NORMAL

    @pytest.mark.asyncio
    async def test_update_source_health_manual(self, handler):
        """Test updating source health from manual input."""
        statuses = {
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": False
        }

        await handler._update_source_health_manual(statuses)

        assert "elasticsearch" in handler.source_health
        assert handler.source_health["elasticsearch"].available is True
        assert handler.source_health["kubernetes"].available is False

    @pytest.mark.asyncio
    async def test_calculate_health_percentage_all_healthy(self, handler):
        """Test health percentage when all sources healthy."""
        await handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })

        health = handler._calculate_health_percentage()
        assert health == 1.0

    @pytest.mark.asyncio
    async def test_calculate_health_percentage_partial_down(self, handler):
        """Test health percentage when some sources down."""
        await handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": False,
            "kubernetes": True
        })

        health = handler._calculate_health_percentage()
        # ES (0.4) + K8s (0.3) = 0.7
        assert abs(health - 0.7) < 0.01

    @pytest.mark.asyncio
    async def test_calculate_health_percentage_critical_down(self, handler):
        """Test health percentage when critical source down."""
        await handler._update_source_health_manual({
            "elasticsearch": False,  # Most critical
            "prometheus": True,
            "kubernetes": True
        })

        health = handler._calculate_health_percentage()
        # Prom (0.3) + K8s (0.3) = 0.6
        assert abs(health - 0.6) < 0.01

    @pytest.mark.asyncio
    async def test_determine_mode_normal(self, handler):
        """Test mode determination for normal health."""
        mode = handler._determine_mode(0.9)
        assert mode == DRMode.NORMAL

    @pytest.mark.asyncio
    async def test_determine_mode_degraded(self, handler):
        """Test mode determination for degraded health."""
        mode = handler._determine_mode(0.6)
        assert mode == DRMode.DEGRADED

    @pytest.mark.asyncio
    async def test_determine_mode_emergency(self, handler):
        """Test mode determination for emergency health."""
        mode = handler._determine_mode(0.4)
        assert mode == DRMode.EMERGENCY

    @pytest.mark.asyncio
    async def test_should_transition_no_cooldown(self, handler):
        """Test transition check with no recent transition."""
        # No previous transition
        assert handler._should_transition(DRMode.DEGRADED, 0.6) is True

    @pytest.mark.asyncio
    async def test_should_transition_with_cooldown(self, handler):
        """Test transition check respects cooldown."""
        # Create a recent transition
        handler.last_transition = ModeTransition(
            from_mode="normal",
            to_mode="degraded",
            timestamp=datetime.now().isoformat(),
            reason="Test",
            available_sources=2,
            total_sources=3,
            health_percentage=0.6,
            triggered_by="test"
        )

        # Should not transition immediately after
        result = handler._should_transition(DRMode.NORMAL, 0.9)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_transition_with_hysteresis(self, handler):
        """Test transition check applies hysteresis."""
        # Set up degraded mode with health at threshold
        handler.current_mode = DRMode.DEGRADED

        # Health at exactly threshold - should not transition down (hysteresis)
        result = handler._should_transition(DRMode.EMERGENCY, 0.5)
        # With hysteresis, need to be below 0.475 (0.5 * 0.95)
        assert result is False

    @pytest.mark.asyncio
    async def test_manual_transition_to_degraded(self, handler, mock_on_call):
        """Test manual mode transition to degraded."""
        transition = await handler.manual_transition(
            DRMode.DEGRADED,
            "Testing degraded mode"
        )

        assert handler.current_mode == DRMode.DEGRADED
        assert transition.from_mode == "normal"
        assert transition.to_mode == "degraded"
        assert transition.triggered_by == "manual"

        # On-call should be notified when degrading
        mock_on_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_transition_to_normal(self, handler, mock_on_call):
        """Test manual transition back to normal."""
        handler.current_mode = DRMode.DEGRADED

        transition = await handler.manual_transition(
            DRMode.NORMAL,
            "Systems recovered"
        )

        assert handler.current_mode == DRMode.NORMAL
        assert transition.from_mode == "degraded"
        assert transition.to_mode == "normal"

        # On-call should NOT be notified when recovering
        mock_on_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_to_normal(self, handler):
        """Test resetting to normal mode."""
        handler.current_mode = DRMode.EMERGENCY

        transition = await handler.reset_to_normal("Manual reset")

        assert handler.current_mode == DRMode.NORMAL
        assert transition.triggered_by == "manual_reset"

    @pytest.mark.asyncio
    async def test_check_health_and_transition_no_change(self, handler):
        """Test health check when mode shouldn't change."""
        await handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })

        transition = await handler.check_health_and_transition()

        # No transition should occur
        assert transition is None
        assert handler.current_mode == DRMode.NORMAL

    @pytest.mark.asyncio
    async def test_check_health_and_transition_emergency(self, handler):
        """Test health check triggers emergency mode."""
        # All sources down
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": False
        })

        # Mock cooldown check
        handler.last_transition = None

        transition = await handler.check_health_and_transition()

        # Should transition to emergency
        assert transition is not None
        assert transition.to_mode == "emergency"
        assert handler.current_mode == DRMode.EMERGENCY

    def test_get_mode_status(self, handler):
        """Test getting detailed mode status."""
        handler.source_health["elasticsearch"] = SourceHealth(
            source_name="elasticsearch",
            available=True,
            response_time_ms=100,
            last_check=datetime.now().isoformat()
        )

        status = handler.get_mode_status()

        assert status["current_mode"] == "normal"
        assert "health_percentage" in status
        assert "source_health" in status
        assert status["running"] is False

    def test_get_transition_history(self, handler):
        """Test getting transition history."""
        # Add some transitions
        transition1 = ModeTransition(
            from_mode="normal",
            to_mode="degraded",
            timestamp=datetime.now().isoformat(),
            reason="Test 1",
            available_sources=2,
            total_sources=3,
            health_percentage=0.6,
            triggered_by="test"
        )

        transition2 = ModeTransition(
            from_mode="degraded",
            to_mode="normal",
            timestamp=datetime.now().isoformat(),
            reason="Test 2",
            available_sources=3,
            total_sources=3,
            health_percentage=1.0,
            triggered_by="test"
        )

        handler.transition_history = [transition1, transition2]

        history = handler.get_transition_history(limit=10)

        assert len(history["transitions"]) == 2
        assert history["total"] == 2

    def test_get_source_health(self, handler):
        """Test getting all source health status."""
        handler.source_health = {
            "elasticsearch": SourceHealth(
                source_name="elasticsearch",
                available=True,
                response_time_ms=100,
                last_check=datetime.now().isoformat()
            ),
            "prometheus": SourceHealth(
                source_name="prometheus",
                available=False,
                response_time_ms=0,
                last_check=datetime.now().isoformat(),
                error="Timeout"
            )
        }

        health = handler.get_source_health()

        assert len(health) == 2
        assert health["elasticsearch"]["available"] is True
        assert health["prometheus"]["available"] is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self, handler):
        """Test starting and stopping health check loop."""
        # Start
        await handler.start()
        assert handler._running is True
        assert handler._health_check_task is not None

        # Stop
        await handler.stop()
        assert handler._running is False
        # Task should be cancelled


@pytest.mark.asyncio
class TestDRHandlerIntegration:
    """Integration tests for DR handler."""

    async def test_full_degradation_cycle(self):
        """Test complete degradation and recovery cycle."""
        on_call_calls = []

        async def mock_on_call(transition):
            on_call_calls.append(transition)

        handler = DRHandler(
            on_call_integration=mock_on_call,
            hysteresis=0.05
        )

        # Start healthy
        await handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })
        assert handler.current_mode == DRMode.NORMAL

        # Degrade
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": True,
            "kubernetes": True
        })
        handler.last_transition = None  # Reset cooldown for testing
        await handler.check_health_and_transition()
        assert handler.current_mode == DRMode.DEGRADED
        assert len(on_call_calls) == 1

        # Further degrade to emergency
        await handler._update_source_health_manual({
            "elasticsearch": False,
            "prometheus": False,
            "kubernetes": True
        })
        # Mock time passed for cooldown
        handler.last_transition = None
        await handler.check_health_and_transition()
        assert handler.current_mode == DRMode.EMERGENCY
        assert len(on_call_calls) == 2

        # Recover
        await handler._update_source_health_manual({
            "elasticsearch": True,
            "prometheus": True,
            "kubernetes": True
        })
        handler.last_transition = None
        await handler.check_health_and_transition()
        assert handler.current_mode == DRMode.NORMAL
        # No new on-call for recovery
        assert len(on_call_calls) == 2

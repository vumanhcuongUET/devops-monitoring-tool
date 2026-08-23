"""
DR Handler - Phase 7 Sprint 2 Day 15-16

Purpose: Disaster Recovery mode handler with automatic transitions

Features:
- Mode detection (NORMAL, DEGRADED, EMERGENCY)
- Automatic mode transitions with hysteresis
- On-call integration for mode changes
- Mode-specific behaviors
- Health monitoring of data sources
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from app.degradation.priority_config import Priority, PriorityConfig

logger = logging.getLogger(__name__)


class DRMode(Enum):
    """Disaster Recovery operating modes."""
    NORMAL = "normal"  # All systems operational
    DEGRADED = "degraded"  # Some systems down, degraded service
    EMERGENCY = "emergency"  # Critical systems down, minimal service


@dataclass
class ModeTransition:
    """Record of a mode transition."""
    from_mode: str
    to_mode: str
    timestamp: str
    reason: str
    available_sources: int
    total_sources: int
    health_percentage: float
    triggered_by: str  # automatic, manual, health_check
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "from_mode": self.from_mode,
            "to_mode": self.to_mode,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "available_sources": self.available_sources,
            "total_sources": self.total_sources,
            "health_percentage": self.health_percentage,
            "triggered_by": self.triggered_by,
            "metadata": self.metadata
        }


@dataclass
class SourceHealth:
    """Health status of a data source."""
    source_name: str
    available: bool
    response_time_ms: float
    last_check: str
    error: Optional[str] = None
    consecutive_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_name": self.source_name,
            "available": self.available,
            "response_time_ms": self.response_time_ms,
            "last_check": self.last_check,
            "error": self.error,
            "consecutive_failures": self.consecutive_failures
        }


class DRHandler:
    """
    Disaster Recovery mode handler.

    Features:
    - Automatic mode detection based on source health
    - Hysteresis to prevent mode flapping
    - Weighted source health calculation
    - On-call integration
    - Mode transition history
    """

    # Mode thresholds (with hysteresis applied separately)
    MODE_THRESHOLDS = {
        DRMode.EMERGENCY: 0.5,  # Below 50% health
        DRMode.DEGRADED: 0.8,  # Below 80% health (but above 50%)
        DRMode.NORMAL: 1.0     # 100% health
    }

    # Source weights (total = 1.0)
    SOURCE_WEIGHTS = {
        "elasticsearch": 0.4,  # Most critical
        "prometheus": 0.3,     # Critical
        "kubernetes": 0.3      # Critical
    }

    # Mode transition cooldown
    TRANSITION_COOLDOWN = timedelta(minutes=5)

    def __init__(
        self,
        on_call_integration: Optional[Callable] = None,
        hysteresis: float = 0.05,  # 5% hysteresis
        check_interval: int = 60  # Check every 60 seconds
    ):
        """
        Initialize DR handler.

        Args:
            on_call_integration: Optional callback for on-call alerts
            hysteresis: Hysteresis factor to prevent mode flapping
            check_interval: Health check interval in seconds
        """
        self.on_call_integration = on_call_integration
        self.hysteresis = hysteresis
        self.check_interval = check_interval

        # Current state
        self.current_mode = DRMode.NORMAL
        self.last_mode_check: Optional[datetime] = None
        self.last_transition: Optional[ModeTransition] = None

        # Source health tracking
        self.source_health: Dict[str, SourceHealth] = {}

        # Transition history
        self.transition_history: List[ModeTransition] = []
        self.max_history_size = 100

        # Background health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"DRHandler initialized with hysteresis={hysteresis}, "
            f"check_interval={check_interval}s"
        )

    async def start(self):
        """Start background health checks."""
        if not self._running:
            self._running = True
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Started DR handler health check loop")

    async def stop(self):
        """Stop background health checks."""
        if self._running:
            self._running = False
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            logger.info("Stopped DR handler health check loop")

    async def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_health_and_transition()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def check_health_and_transition(
        self,
        source_statuses: Optional[Dict[str, bool]] = None,
        manual_trigger: bool = False
    ) -> Optional[ModeTransition]:
        """
        Check health of sources and transition mode if needed.

        Args:
            source_statuses: Optional manual source status override
            manual_trigger: If True, this is a manual check (not scheduled)

        Returns:
            ModeTransition if mode changed, None otherwise
        """
        self.last_mode_check = datetime.now()

        # Update source health
        if source_statuses:
            await self._update_source_health_manual(source_statuses)
        else:
            await self._update_source_health_from_checks()

        # Calculate overall health
        health_percentage = self._calculate_health_percentage()

        # Determine target mode
        target_mode = self._determine_mode(health_percentage)

        # Check if transition is needed
        if target_mode != self.current_mode:
            # Check hysteresis
            if self._should_transition(target_mode, health_percentage):
                transition = await self._transition_to_mode(
                    target_mode,
                    health_percentage,
                    "automatic" if not manual_trigger else "manual"
                )
                return transition

        return None

    async def _update_source_health_manual(self, statuses: Dict[str, bool]):
        """Update source health from manual status input."""
        for source_name, available in statuses.items():
            if source_name not in self.source_health:
                self.source_health[source_name] = SourceHealth(
                    source_name=source_name,
                    available=available,
                    response_time_ms=0,
                    last_check=datetime.now().isoformat()
                )
            else:
                health = self.source_health[source_name]
                health.available = available
                health.last_check = datetime.now().isoformat()

                # Update consecutive failures
                if available:
                    health.consecutive_failures = 0
                else:
                    health.consecutive_failures += 1

    async def _update_source_health_from_checks(self):
        """Update source health from actual health checks."""
        # This would typically call health check endpoints
        # For now, we'll update based on existing state
        # In production, you'd implement actual health checks here
        pass

    def _calculate_health_percentage(self) -> float:
        """
        Calculate overall health percentage.

        Uses weighted average based on SOURCE_WEIGHTS.
        """
        if not self.source_health:
            return 1.0  # Assume healthy if no sources tracked

        total_weight = 0.0
        available_weight = 0.0

        for source_name, weight in self.SOURCE_WEIGHTS.items():
            if source_name in self.source_health:
                total_weight += weight
                if self.source_health[source_name].available:
                    available_weight += weight

        if total_weight == 0:
            return 1.0

        return available_weight / total_weight

    def _determine_mode(self, health_percentage: float) -> DRMode:
        """Determine target mode based on health percentage."""
        if health_percentage < self.MODE_THRESHOLDS[DRMode.EMERGENCY]:
            return DRMode.EMERGENCY
        elif health_percentage < self.MODE_THRESHOLDS[DRMode.DEGRADED]:
            return DRMode.DEGRADED
        else:
            return DRMode.NORMAL

    def _should_transition(self, target_mode: DRMode, health: float) -> bool:
        """
        Check if mode transition should occur (with hysteresis).

        Hysteresis prevents rapid mode switching near thresholds.
        """
        # If we just transitioned, respect cooldown
        if self.last_transition:
            last_time = datetime.fromisoformat(self.last_transition.timestamp)
            if datetime.now() - last_time < self.TRANSITION_COOLDOWN:
                return False

        # Apply hysteresis
        current_level = self.MODE_THRESHOLDS.get(self.current_mode, 1.0)

        if target_mode.value < self.current_mode.value:  # Degrading
            # Use lower threshold (more strict) for degrading
            threshold = current_level * (1 - self.hysteresis)
            return health < threshold

        else:  # Recovering
            # Use upper threshold (more lenient) for recovery
            next_threshold = self.MODE_THRESHOLDS.get(target_mode, 1.0)
            threshold = next_threshold * (1 + self.hysteresis)
            return health >= threshold

    async def _transition_to_mode(
        self,
        new_mode: DRMode,
        health_percentage: float,
        triggered_by: str
    ) -> ModeTransition:
        """Execute mode transition."""
        old_mode = self.current_mode
        self.current_mode = new_mode

        # Count available sources
        available_count = sum(
            1 for h in self.source_health.values() if h.available
        )
        total_count = len(self.source_health)

        # Create transition record
        transition = ModeTransition(
            from_mode=old_mode.value,
            to_mode=new_mode.value,
            timestamp=datetime.now().isoformat(),
            reason=self._generate_transition_reason(new_mode, health_percentage),
            available_sources=available_count,
            total_sources=total_count,
            health_percentage=health_percentage,
            triggered_by=triggered_by,
            metadata={
                "hysteresis_applied": self.hysteresis,
                "source_health": {
                    name: h.to_dict() for name, h in self.source_health.items()
                }
            }
        )

        # Store in history
        self.transition_history.append(transition)
        if len(self.transition_history) > self.max_history_size:
            self.transition_history.pop(0)

        self.last_transition = transition

        # Log the transition
        logger.warning(
            f"DR MODE TRANSITION: {old_mode.value.upper()} -> "
            f"{new_mode.value.upper()} (health={health_percentage:.1%}, "
            f"triggered_by={triggered_by})"
        )

        # Notify on-call if degrading
        if new_mode.value < old_mode.value:  # Getting worse
            await self._notify_on_call(transition)

        return transition

    def _generate_transition_reason(self, mode: DRMode, health: float) -> str:
        """Generate human-readable transition reason."""
        reasons = {
            DRMode.EMERGENCY: f"Critical systems unavailable (health: {health:.1%})",
            DRMode.DEGRADED: f"Some systems unavailable (health: {health:.1%})",
            DRMode.NORMAL: f"All systems operational (health: {health:.1%})"
        }
        return reasons.get(mode, f"Health at {health:.1%}")

    async def _notify_on_call(self, transition: ModeTransition):
        """Notify on-call about mode transition."""
        if self.on_call_integration:
            try:
                await self.on_call_integration(transition)
                logger.info(f"On-call notified for transition to {transition.to_mode}")
            except Exception as e:
                logger.error(f"Failed to notify on-call: {e}")
        else:
            logger.warning("No on-call integration configured")

    async def manual_transition(
        self,
        new_mode: DRMode,
        reason: str,
        triggered_by: str = "manual"
    ) -> ModeTransition:
        """
        Manually trigger a mode transition.

        Args:
            new_mode: Target mode
            reason: Reason for transition
            triggered_by: Who triggered this

        Returns:
            ModeTransition record
        """
        old_mode = self.current_mode
        self.current_mode = new_mode

        available_count = sum(
            1 for h in self.source_health.values() if h.available
        )
        total_count = len(self.source_health)

        transition = ModeTransition(
            from_mode=old_mode.value,
            to_mode=new_mode.value,
            timestamp=datetime.now().isoformat(),
            reason=reason,
            available_sources=available_count,
            total_sources=total_count,
            health_percentage=self._calculate_health_percentage(),
            triggered_by=triggered_by
        )

        self.transition_history.append(transition)
        self.last_transition = transition

        logger.warning(
            f"MANUAL DR MODE TRANSITION: {old_mode.value.upper()} -> "
            f"{new_mode.value.upper()} (reason: {reason})"
        )

        # Notify on-call if degrading
        if new_mode.value < old_mode.value:
            await self._notify_on_call(transition)

        return transition

    def get_current_mode(self) -> DRMode:
        """Get current operating mode."""
        return self.current_mode

    def get_mode_status(self) -> Dict[str, Any]:
        """Get detailed mode status."""
        return {
            "current_mode": self.current_mode.value,
            "health_percentage": self._calculate_health_percentage(),
            "last_check": self.last_mode_check.isoformat() if self.last_mode_check else None,
            "last_transition": self.last_transition.to_dict() if self.last_transition else None,
            "source_health": {
                name: h.to_dict() for name, h in self.source_health.items()
            },
            "hysteresis": self.hysteresis,
            "running": self._running
        }

    def get_transition_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transition history."""
        return [
            t.to_dict()
            for t in self.transition_history[-limit:]
        ]

    def get_source_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health status of all sources."""
        return {
            name: h.to_dict()
            for name, h in self.source_health.items()
        }

    async def reset_to_normal(self, reason: str = "Manual reset"):
        """Reset mode to NORMAL."""
        return await self.manual_transition(
            DRMode.NORMAL,
            reason,
            "manual_reset"
        )

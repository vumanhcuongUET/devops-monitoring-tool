"""Chain monitoring and alerting for action chaining prevention."""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


@dataclass
class ChainEvent:
    """Event representing a chain monitoring alert."""
    event_type: str  # "approaching", "exceeded", "reset"
    project: str
    action_type: str
    chain_count: int
    chain_limit: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainMonitorConfig:
    """Configuration for chain monitoring."""
    enabled: bool = True  # Enable chain monitoring
    warning_threshold_ratio: float = 0.67  # Warn when chain is at 67% of limit (2/3)
    alert_on_exceed: bool = True  # Alert when limit is exceeded
    alert_on_reset: bool = False  # Alert when chain resets
    include_chain_in_audit: bool = True  # Include chain events in audit log


class ChainMonitor:
    """Monitor action chains and trigger alerts.

    This class monitors action chains and can trigger alerts when:
    - Chain is approaching the limit (warning threshold)
    - Chain limit is exceeded
    - Chain resets (optional)

    Alerts can be sent via callbacks (e.g., Slack, Email, WebSocket).
    """

    def __init__(
        self,
        config: Optional[ChainMonitorConfig] = None,
        alert_callback: Optional[Callable[[ChainEvent], None]] = None,
    ):
        """Initialize the chain monitor.

        Args:
            config: Chain monitor configuration
            alert_callback: Optional callback function to handle alerts
        """
        self.config = config or ChainMonitorConfig()
        self._alert_callback = alert_callback
        self._last_warning: Dict[tuple, datetime] = {}  # Track last warning per (project, action_type)

    def update_config(self, config: ChainMonitorConfig) -> None:
        """Update chain monitor configuration.

        Args:
            config: New configuration to apply
        """
        self.config = config

    def set_alert_callback(self, callback: Callable[[ChainEvent], None]) -> None:
        """Set the alert callback function.

        Args:
            callback: Function to call when chain events occur
        """
        self._alert_callback = callback

    def check_chain(
        self,
        project: str,
        action_type: str,
        chain_count: int,
        chain_limit: int,
        user: Optional[str] = None,
    ) -> Optional[ChainEvent]:
        """Check chain status and trigger alerts if needed.

        Args:
            project: Project name
            action_type: Type of action
            chain_count: Current chain count
            chain_limit: Maximum allowed chain length
            user: Optional user identifier

        Returns:
            ChainEvent if an alert was triggered, None otherwise
        """
        if not self.config.enabled:
            return None

        key = (project, action_type)
        event = None

        # Check if chain is approaching limit (use floor to get integer threshold)
        import math
        warning_threshold = math.floor(self.config.warning_threshold_ratio * chain_limit)
        if chain_count >= warning_threshold and chain_count < chain_limit:
            # Check if we haven't warned recently (avoid spam)
            last_warned = self._last_warning.get(key)
            now = datetime.now(timezone.utc)

            # Don't warn more than once per 5 minutes for same chain
            if last_warned is None or (now - last_warned).total_seconds() > 300:
                event = ChainEvent(
                    event_type="approaching",
                    project=project,
                    action_type=action_type,
                    chain_count=chain_count,
                    chain_limit=chain_limit,
                    user=user,
                    metadata={
                        "warning_threshold": warning_threshold,
                        "message": f"Action chain approaching limit: {chain_count}/{chain_limit}",
                    },
                )
                self._last_warning[key] = now

        # Check if chain limit is exceeded
        elif chain_count >= chain_limit:
            event = ChainEvent(
                event_type="exceeded",
                project=project,
                action_type=action_type,
                chain_count=chain_count,
                chain_limit=chain_limit,
                user=user,
                metadata={
                    "message": f"Action chain limit exceeded: {chain_count}/{chain_limit}",
                },
            )
            # Clear warning timestamp since we've now exceeded
            if key in self._last_warning:
                del self._last_warning[key]

        # Trigger alert via callback if configured
        if event and self._alert_callback:
            try:
                self._alert_callback(event)
            except Exception as e:
                logger.error(f"Failed to trigger chain alert callback: {e}")

        return event

    def reset_tracking(self, project: Optional[str] = None, action_type: Optional[str] = None) -> None:
        """Reset chain tracking for specific project/action type or all.

        Args:
            project: Optional project filter. If None, resets all projects.
            action_type: Optional action type filter. If None, resets all types.
        """
        keys_to_remove = []

        for key in self._last_warning.keys():
            key_project, key_action = key

            if project and key_project != project:
                continue

            if action_type and key_action != action_type:
                continue

            keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._last_warning[key]

        if self.config.alert_on_reset and self._alert_callback:
            event = ChainEvent(
                event_type="reset",
                project=project or "all",
                action_type=action_type or "all",
                chain_count=0,
                chain_limit=0,
                metadata={
                    "message": f"Chain tracking reset for {project or 'all projects'}",
                },
            )
            try:
                self._alert_callback(event)
            except Exception as e:
                logger.error(f"Failed to trigger chain reset alert: {e}")


# Default alert handlers

def log_chain_event(event: ChainEvent) -> None:
    """Default handler: Log chain events.

    Args:
        event: Chain event to log
    """
    log_level = logger.warning if event.event_type == "exceeded" else logger.info
    log_level(
        f"Chain Event: {event.event_type.upper()} - "
        f"Project: {event.project}, Action: {event.action_type}, "
        f"Chain: {event.chain_count}/{event.chain_limit}, "
        f"User: {event.user or 'N/A'}"
    )


def audit_chain_event(event: ChainEvent) -> None:
    """Handler: Log chain events to audit trail.

    Args:
        event: Chain event to audit
    """
    from app.audit.logger import get_audit_logger
    from app.models.audit import AuditEventType

    audit_logger = get_audit_logger()

    if event.event_type == "exceeded":
        audit_logger.log_chain_limit_exceeded(
            action_id=f"chain-{event.project}-{event.action_type}",
            project=event.project,
            action_type=event.action_type,
            chain_count=event.chain_count,
            chain_limit=event.chain_limit,
            user=event.user,
        )
    elif event.event_type == "approaching":
        # Log as a generic event for approaching limit
        audit_logger.log_event(
            event_type=AuditEventType.VALIDATION_CHECK,
            project=event.project,
            details={
                "type": "chain_warning",
                "action_type": event.action_type,
                "chain_count": event.chain_count,
                "chain_limit": event.chain_limit,
                "message": event.metadata.get("message", ""),
            },
        )


# Global singleton instance
_chain_monitor: Optional[ChainMonitor] = None


def get_chain_monitor(
    config: Optional[ChainMonitorConfig] = None,
    alert_callback: Optional[Callable[[ChainEvent], None]] = None,
) -> ChainMonitor:
    """Get or create the global ChainMonitor instance.

    Args:
        config: Optional configuration to use on first creation
        alert_callback: Optional alert callback to use on first creation

    Returns:
        The ChainMonitor singleton instance
    """
    global _chain_monitor
    if _chain_monitor is None:
        _chain_monitor = ChainMonitor(config, alert_callback)
        # Set up default handlers ONLY if both config and callback are None
        if alert_callback is None and config is None:
            # Use both log and audit as handlers
            def combined_handler(event: ChainEvent):
                log_chain_event(event)
                if _chain_monitor.config.include_chain_in_audit:
                    audit_chain_event(event)
            _chain_monitor.set_alert_callback(combined_handler)
    else:
        # Update existing monitor
        if config is not None:
            _chain_monitor.update_config(config)
        if alert_callback is not None:
            _chain_monitor.set_alert_callback(alert_callback)
    return _chain_monitor

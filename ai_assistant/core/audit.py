"""
Audit logging for AI Assistant.

Provides persistent, tamper-evident audit logging for security and compliance.
"""

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from core.logging_config import get_logger


class AuditLogEntry:
    """Single audit log entry."""

    def __init__(
        self,
        event_type: str,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
    ):
        """
        Create audit log entry.

        Args:
            event_type: Type of event (e.g., 'query', 'action', 'auth')
            actor: User or system identifier performing the action
            action: Action performed (e.g., 'run_query', 'scale_deployment')
            resource: Resource affected (e.g., 'meinvoice', 'production/pod-123')
            status: Status of the action ('success', 'failure', 'blocked')
            details: Additional event details
            timestamp: Unix timestamp (defaults to now)
        """
        self.event_type = event_type
        self.actor = actor or "system"
        self.action = action
        self.resource = resource
        self.status = status
        self.details = details or {}
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "status": self.status,
            "details": self.details,
            "timestamp": self.timestamp,
            "iso_timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditLogEntry":
        """Create entry from dictionary."""
        return cls(
            event_type=data.get("event_type"),
            actor=data.get("actor"),
            action=data.get("action"),
            resource=data.get("resource"),
            status=data.get("status", "success"),
            details=data.get("details"),
            timestamp=data.get("timestamp"),
        )


class AuditLogger:
    """
    Thread-safe audit logger with tamper-evident storage.

    Each log entry is hashed, and a chain hash is maintained to detect
    tampering. Logs are appended to a rotating file.
    """

    def __init__(self, log_dir: Optional[Path] = None, max_file_size: int = 10 * 1024 * 1024):
        """
        Initialize audit logger.

        Args:
            log_dir: Directory for audit logs (defaults to data/audit)
            max_file_size: Maximum file size before rotation (bytes)
        """
        self._lock = Lock()
        self._log_dir = log_dir or Path.cwd() / "data" / "audit"
        self._max_file_size = max_file_size
        self._current_file: Optional[Path] = None
        self._last_hash: Optional[str] = None

        # Create log directory FIRST before accessing secret file
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._secret = self._get_or_create_secret()

        # Initialize current file
        self._init_current_file()

    def _get_or_create_secret(self) -> str:
        """
        Get or create HMAC secret for chain hashing.

        Secret is stored in data/audit/.secret
        """
        secret_file = self._log_dir / ".secret"
        if secret_file.exists():
            return secret_file.read_text()

        # Generate new secret
        import secrets
        new_secret = secrets.token_hex(32)
        secret_file.write_text(new_secret)
        secret_file.chmod(0o600)  # Owner read/write only
        return new_secret

    def _init_current_file(self):
        """Initialize current log file and load last hash."""
        # Find most recent log file
        log_files = sorted(self._log_dir.glob("audit_*.jsonl"), reverse=True)

        if log_files:
            self._current_file = log_files[0]
            # Check if file needs rotation
            if self._current_file.stat().st_size >= self._max_file_size:
                self._rotate_log()
            else:
                # Load last hash from file
                self._last_hash = self._get_last_hash()
        else:
            # Create new file
            self._rotate_log()

    def _rotate_log(self):
        """Rotate to new log file."""
        # Ensure directory exists (in case it was deleted)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Use microseconds for uniqueness when rotating rapidly
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._current_file = self._log_dir / f"audit_{timestamp}.jsonl"
        self._last_hash = None  # Reset chain for new file

    def _get_last_hash(self) -> Optional[str]:
        """Get last chain hash from current file."""
        if not self._current_file or not self._current_file.exists():
            return None

        try:
            with open(self._current_file, "r") as f:
                lines = f.readlines()
                if lines:
                    last_line = json.loads(lines[-1])
                    return last_line.get("_chain_hash")
        except (json.JSONDecodeError, IOError):
            pass

        return None

    def _compute_chain_hash(self, entry: AuditLogEntry) -> str:
        """
        Compute HMAC chain hash for entry.

        Chain hash includes previous hash, entry data, and secret.
        """
        entry_data = json.dumps(entry.to_dict(), sort_keys=True)
        hash_input = f"{self._last_hash or ''}:{entry_data}:{self._secret}"

        return hashlib.sha256(hash_input.encode()).hexdigest()

    def log(self, entry: AuditLogEntry) -> bool:
        """
        Write audit log entry.

        Args:
            entry: Audit log entry to write

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Check for rotation (only if file exists)
                if self._current_file.exists() and self._current_file.stat().st_size >= self._max_file_size:
                    self._rotate_log()

                # Compute chain hash
                chain_hash = self._compute_chain_hash(entry)

                # Add chain hash to entry data
                entry_data = entry.to_dict()
                entry_data["_chain_hash"] = chain_hash

                # Write to file
                with open(self._current_file, "a") as f:
                    f.write(json.dumps(entry_data) + "\n")

                # Update last hash
                self._last_hash = chain_hash

                # Also log to standard logger for immediate visibility
                get_logger().info(
                    "Audit log entry written",
                    extra={
                        "event_type": entry.event_type,
                        "actor": entry.actor,
                        "action": entry.action,
                        "resource": entry.resource,
                        "status": entry.status,
                    },
                )

                return True

            except Exception as e:
                get_logger().error(f"Failed to write audit log: {e}")
                return False


# Global audit logger instance
_global_audit_logger: Optional[AuditLogger] = None


def reset_audit_logger():
    """Reset global audit logger instance (useful for testing)."""
    global _global_audit_logger
    _global_audit_logger = None


def set_global_audit_logger(logger: AuditLogger):
    """
    Set a specific audit logger instance as global.

    Useful for testing or custom configurations.

    Args:
        logger: The audit logger instance to use as global
    """
    global _global_audit_logger
    _global_audit_logger = logger


def get_audit_logger() -> AuditLogger:
    """Get or create global audit logger instance."""
    global _global_audit_logger
    if _global_audit_logger is None:
        _global_audit_logger = AuditLogger()
    return _global_audit_logger


def log_event(
    event_type: str,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    status: str = "success",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Convenience function to log audit event.

    Args:
        event_type: Type of event
        actor: User or system identifier
        action: Action performed
        resource: Resource affected
        status: Status of the action
        details: Additional event details

    Returns:
        True if logged successfully, False otherwise
    """
    entry = AuditLogEntry(
        event_type=event_type,
        actor=actor,
        action=action,
        resource=resource,
        status=status,
        details=details,
    )
    return get_audit_logger().log(entry)

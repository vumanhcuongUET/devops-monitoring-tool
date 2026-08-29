"""Audit logger for tracking all actions and Chain of Thought."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.audit import (
    AuditEntry,
    AuditEventType,
    AuditLogQuery,
    AuditLogResponse,
    ChainOfThoughtEntry,
)

AUDIT_LOG_FILE = "data/audit_log.json"
MAX_ENTRIES = 1000


class AuditLogger:
    """Audit logger for tracking all actions with Chain of Thought."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._max_entries = max_entries
        self._ensure_log_dir()

    def log_event(
        self,
        event_type: AuditEventType,
        user: str | None = None,
        action_id: str | None = None,
        triage_card_id: str | None = None,
        project: str | None = None,
        details: dict[str, Any] | None = None,
        chain_of_thought: list[ChainOfThoughtEntry] | None = None,
        execution_duration_seconds: float | None = None,
        success: bool | None = None,
        **kwargs
    ) -> AuditEntry:
        """Log an audit event."""
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            user=user,
            action_id=action_id,
            triage_card_id=triage_card_id,
            project=project,
            details=details or {},
            chain_of_thought=chain_of_thought,
            execution_duration_seconds=execution_duration_seconds,
            success=success,
            **kwargs
        )
        self._append_entry(entry)
        return entry

    def log_action_created(
        self,
        action_id: str,
        triage_card_id: str | None,
        project: str,
        command: str,
        user: str | None = None,
        chain_of_thought: list[ChainOfThoughtEntry] | None = None,
    ) -> AuditEntry:
        """Log action creation event."""
        return self.log_event(
            event_type=AuditEventType.ACTION_CREATED,
            user=user,
            action_id=action_id,
            triage_card_id=triage_card_id,
            project=project,
            details={"command": command},
            chain_of_thought=chain_of_thought,
        )

    def log_action_approved(
        self,
        action_id: str,
        approved_by: str,
        comment: str | None = None,
    ) -> AuditEntry:
        """Log action approval event."""
        return self.log_event(
            event_type=AuditEventType.ACTION_APPROVED,
            user=approved_by,
            action_id=action_id,
            details={"comment": comment} if comment else {},
        )

    def log_action_rejected(
        self,
        action_id: str,
        rejected_by: str,
        reason: str,
    ) -> AuditEntry:
        """Log action rejection event."""
        return self.log_event(
            event_type=AuditEventType.ACTION_REJECTED,
            user=rejected_by,
            action_id=action_id,
            details={"reason": reason},
        )

    def log_action_executed(
        self,
        action_id: str,
        executed_by: str,
        success: bool,
        duration_seconds: float,
        output: str | None = None,
    ) -> AuditEntry:
        """Log action execution event."""
        return self.log_event(
            event_type=AuditEventType.ACTION_EXECUTED if success else AuditEventType.ACTION_FAILED,
            user=executed_by,
            action_id=action_id,
            execution_duration_seconds=duration_seconds,
            success=success,
            details={"output": output} if output else {},
        )

    def log_chain_of_thought(
        self,
        action_id: str,
        chain_of_thought: list[ChainOfThoughtEntry],
    ) -> AuditEntry:
        """Log Chain of Thought for AI-generated actions."""
        return self.log_event(
            event_type=AuditEventType.CHAIN_OF_THOUGHT,
            action_id=action_id,
            chain_of_thought=chain_of_thought,
        )

    def log_chain_limit_exceeded(
        self,
        action_id: str,
        project: str,
        action_type: str,
        chain_count: int,
        chain_limit: int,
        user: str | None = None,
    ) -> AuditEntry:
        """Log when action chain limit is exceeded."""
        return self.log_event(
            event_type=AuditEventType.CHAIN_LIMIT_EXCEEDED,
            user=user,
            action_id=action_id,
            project=project,
            details={
                "action_type": action_type,
                "chain_count": chain_count,
                "chain_limit": chain_limit,
                "message": f"Action chain limit reached: {chain_count}/{chain_limit} consecutive actions",
            },
        )

    def log_rate_limit_exceeded(
        self,
        action_id: str,
        project: str,
        action_type: str,
        rate_limit: int,
        user: str | None = None,
    ) -> AuditEntry:
        """Log when rate limit is exceeded."""
        return self.log_event(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            user=user,
            action_id=action_id,
            project=project,
            details={
                "action_type": action_type,
                "rate_limit": rate_limit,
                "message": f"Rate limit exceeded: maximum {rate_limit} actions per hour",
            },
        )

    def log_cooldown_active(
        self,
        action_id: str,
        project: str,
        action_type: str,
        cooldown_remaining: int,
        user: str | None = None,
    ) -> AuditEntry:
        """Log when cooldown period is active."""
        return self.log_event(
            event_type=AuditEventType.COOLDOWN_ACTIVE,
            user=user,
            action_id=action_id,
            project=project,
            details={
                "action_type": action_type,
                "cooldown_remaining_seconds": cooldown_remaining,
                "message": f"Cooldown active: wait {cooldown_remaining}s before next action",
            },
        )

    def query(self, query: AuditLogQuery) -> AuditLogResponse:
        """Query audit logs with filters."""
        all_entries = self._load_entries()

        # Filter by event type
        if query.event_types:
            all_entries = [e for e in all_entries if e.event_type in query.event_types]

        # Filter by action_id
        if query.action_id:
            all_entries = [e for e in all_entries if e.action_id == query.action_id]

        # Filter by triage_card_id
        if query.triage_card_id:
            all_entries = [e for e in all_entries if e.triage_card_id == query.triage_card_id]

        # Filter by project
        if query.project:
            all_entries = [e for e in all_entries if e.project == query.project]

        # Filter by user
        if query.user:
            all_entries = [e for e in all_entries if e.user == query.user]

        # Filter by time range
        if query.start_time:
            all_entries = [e for e in all_entries if e.timestamp >= query.start_time]
        if query.end_time:
            all_entries = [e for e in all_entries if e.timestamp <= query.end_time]

        # Sort by timestamp descending
        all_entries.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        total = len(all_entries)
        entries = all_entries[query.offset : query.offset + query.limit]
        has_more = query.offset + query.limit < total

        return AuditLogResponse(
            total=total,
            entries=entries,
            has_more=has_more,
        )

    def get_action_history(self, action_id: str) -> list[AuditEntry]:
        """Get all audit entries for a specific action."""
        all_entries = self._load_entries()
        return [e for e in all_entries if e.action_id == action_id]

    def _ensure_log_dir(self):
        """Ensure the audit log directory exists."""
        os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)

    def _load_entries(self) -> list[AuditEntry]:
        """Load all audit entries from the log file."""
        if not os.path.exists(AUDIT_LOG_FILE):
            return []

        try:
            with open(AUDIT_LOG_FILE) as f:
                data = json.load(f)
                return [AuditEntry(**entry) for entry in data]
        except (json.JSONDecodeError, ValueError):
            # Corrupt log file, start fresh
            return []

    def _append_entry(self, entry: AuditEntry):
        """Append an entry to the log file with rotation."""
        entries = self._load_entries()

        # Add new entry at the beginning
        entries.insert(0, entry)

        # Trim to max entries
        if len(entries) > self._max_entries:
            entries = entries[: self._max_entries]

        # Write back to file
        self._ensure_log_dir()
        with open(AUDIT_LOG_FILE, "w") as f:
            json.dump([e.model_dump() for e in entries], f, indent=2, default=str)


# Singleton instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the singleton AuditLogger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger

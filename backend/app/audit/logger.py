"""Audit logger for tracking all actions and Chain of Thought."""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
import pathlib

from app.models.audit import (
    AuditEntry,
    AuditEventType,
    AuditLogQuery,
    AuditLogResponse,
    ChainOfThoughtEntry,
)

from app.settings import settings as _settings
AUDIT_LOG_FILE = str(pathlib.Path(_settings.DATA_DIR) / "audit_log.jsonl")
# Pre-Phase-14 format (whole-file JSON list, rewritten on every event)
LEGACY_AUDIT_LOG_FILE = str(pathlib.Path(_settings.DATA_DIR) / "audit_log.json")
# Rotate the append-only log once it exceeds this size; retention is no
# longer a silent trim to the last N entries.
ROTATION_SIZE_BYTES = 50 * 1024 * 1024
# In-memory tail cap for query()/history reads (does not delete anything).
MAX_ENTRIES = 10000


class AuditLogger:
    """Audit logger for tracking all actions with Chain of Thought.

    Phase 14: the log is append-only JSON-lines with size-based rotation.
    The old format rewrote the entire file on every event (corrupt-on-crash,
    O(file) per append) and silently truncated history to 1000 entries.
    """

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._max_entries = max_entries
        self._ensure_log_dir()
        self._migrate_legacy_log()

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
        # Best-effort PostgreSQL mirror (review F2); file stays primary
        from app.database.mirror import schedule_mirror, mirror_audit_entry
        schedule_mirror(mirror_audit_entry(entry))
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

    def _migrate_legacy_log(self):
        """One-time conversion of the old whole-file JSON list to JSONL.

        Only when both files live in the same directory — a patched/test
        AUDIT_LOG_FILE must never ingest the real legacy log.
        """
        if os.path.exists(AUDIT_LOG_FILE) or not os.path.exists(LEGACY_AUDIT_LOG_FILE):
            return
        if os.path.dirname(os.path.abspath(AUDIT_LOG_FILE)) != os.path.dirname(
            os.path.abspath(LEGACY_AUDIT_LOG_FILE)
        ):
            return
        try:
            with open(LEGACY_AUDIT_LOG_FILE) as f:
                data = json.load(f)
            with open(AUDIT_LOG_FILE, "a") as f:
                for entry in reversed(data):  # legacy list was newest-first
                    f.write(json.dumps(entry, default=str) + "\n")
        except (json.JSONDecodeError, OSError) as e:
            # Never block startup on a bad legacy file; it stays untouched.
            import logging

            logging.getLogger(__name__).warning(
                "Legacy audit log migration skipped: %s", e
            )

    def _load_entries(self) -> list[AuditEntry]:
        """Load the most recent audit entries (oldest first) from the JSONL log.

        Reads are bounded to the last `max_entries` lines for memory; the
        file itself is never trimmed (retention is size-based rotation).
        """
        if not os.path.exists(AUDIT_LOG_FILE):
            return []

        entries: list[AuditEntry] = []
        try:
            with open(AUDIT_LOG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(AuditEntry(**json.loads(line)))
                    except (json.JSONDecodeError, ValueError):
                        continue  # skip corrupt line, keep the rest
        except OSError:
            return []
        return entries[-self._max_entries:]

    def _append_entry(self, entry: AuditEntry):
        """Append one entry as a JSONL line; rotate on size threshold."""
        self._ensure_log_dir()
        line = json.dumps(entry.model_dump(mode="json"), default=str)
        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(line + "\n")

        if os.path.getsize(AUDIT_LOG_FILE) > ROTATION_SIZE_BYTES:
            rotated = AUDIT_LOG_FILE + ".1"
            try:
                os.replace(AUDIT_LOG_FILE, rotated)
            except OSError:
                pass  # rotation is best-effort; appends continue


# Singleton instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the singleton AuditLogger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger

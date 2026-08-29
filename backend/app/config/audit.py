"""
Audit Logging Module

Provides comprehensive audit logging for configuration changes
with rotation, compression, and query capabilities.
"""

import gzip
import json
import logging
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Types of auditable actions."""
    CONFIG_READ = "config_read"
    CONFIG_CREATE = "config_create"
    CONFIG_UPDATE = "config_update"
    CONFIG_DELETE = "config_delete"
    CONFIG_ROLLBACK = "config_rollback"
    CONFIG_VALIDATE = "config_validate"
    CONFIG_DEPLOY = "config_deploy"
    VERSION_CREATE = "version_create"
    VERSION_ROLLBACK = "version_rollback"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_PULL = "git_pull"
    SECURITY_ENCRYPT = "security_encrypt"
    SECURITY_DECRYPT = "security_decrypt"


class AuditLogger:
    """Audit logger for configuration changes."""

    def __init__(self, storage_path: str, rotation_size_mb: int = 10):
        """Initialize audit logger.

        Args:
            storage_path: Base path for audit logs
            rotation_size_mb: Size limit for log rotation (MB)
        """
        self.storage_path = Path(storage_path)
        self.audit_dir = self.storage_path / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self.rotation_size = rotation_size_mb * 1024 * 1024
        self.current_log_file = self._get_current_log_file()

        # Import security module for sanitization
        from .security import ConfigSecurity
        self.security = ConfigSecurity()

    def _get_current_log_file(self) -> Path:
        """Get current audit log file."""
        today = date.today().isoformat()
        return self.audit_dir / f"audit-{today}.jsonl.gz"

    async def log(
        self,
        action: AuditAction,
        project: str,
        user: str,
        details: dict[str, Any] | None = None,
        result: str = "success",
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None
    ):
        """Log configuration action.

        Args:
            action: Type of action performed
            project: Project name
            user: User who performed action
            details: Additional details about the action
            result: Result of action (success, failure, partial)
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request ID for correlation
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action.value,
            "project": project,
            "user": user,
            "details": self._sanitize_details(details or {}),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "request_id": request_id,
            "result": result
        }

        # Append to log file
        self._append_to_log(entry)

        # Check rotation
        self._check_rotation()

        logger.debug(f"Logged {action.value} for {project} by {user}")

    def _sanitize_details(self, details: dict[str, Any]) -> dict[str, Any]:
        """Sanitize sensitive details."""
        try:
            return self.security.sanitize_config(details)
        except Exception:
            return {"sanitized": True}

    def _append_to_log(self, entry: dict[str, Any]):
        """Append entry to compressed log file."""
        try:
            # Ensure parent directory exists
            self.current_log_file.parent.mkdir(parents=True, exist_ok=True)

            with gzip.open(self.current_log_file, 'at', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def _check_rotation(self):
        """Check if log rotation is needed."""
        if not self.current_log_file.exists():
            return

        size = self.current_log_file.stat().st_size
        if size >= self.rotation_size:
            self._rotate_log()

    def _rotate_log(self):
        """Rotate audit log file."""
        try:
            # Archive current log
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            archive_name = self.current_log_file.stem + f"-{timestamp}.jsonl.gz"

            # Rename with timestamp
            archived = self.current_log_file.parent / archive_name
            if self.current_log_file.exists():
                self.current_log_file.rename(archived)

            # Create new log file
            self.current_log_file = self._get_current_log_file()

            logger.info(f"Rotated audit log to {archive_name}")

        except Exception as e:
            logger.error(f"Failed to rotate audit log: {e}")

    async def get_audit_trail(
        self,
        project: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        action: AuditAction | None = None,
        user: str | None = None,
        limit: int = 1000,
        offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get audit trail with filtering options.

        Args:
            project: Filter by project
            start_date: Start of date range
            end_date: End of date range
            action: Filter by action type
            user: Filter by user
            limit: Maximum number of entries
            offset: Pagination offset

        Returns:
            List of audit entries
        """
        results = []
        skipped = 0

        # Determine which files to read
        files = self._get_files_in_range(start_date, end_date)

        for file_path in sorted(files, reverse=True):
            if not file_path.exists():
                continue

            try:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            entry = json.loads(line)

                            # Apply filters
                            if project and entry.get("project") != project:
                                continue
                            if action and entry.get("action") != action.value:
                                continue
                            if user and entry.get("user") != user:
                                continue

                            # Pagination
                            if skipped < offset:
                                skipped += 1
                                continue

                            results.append(entry)

                            if len(results) >= limit:
                                return results

                        except json.JSONDecodeError:
                            continue

            except Exception as e:
                logger.error(f"Failed to read audit file {file_path}: {e}")

        return results

    async def get_audit_summary(
        self,
        project: str | None = None,
        days: int = 7
    ) -> dict[str, Any]:
        """Get audit summary for a project.

        Args:
            project: Project name (None = all projects)
            days: Number of days to summarize

        Returns:
            Summary statistics
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        entries = await self.get_audit_trail(
            project=project,
            start_date=start_date,
            end_date=end_date,
            limit=100000
        )

        # Calculate statistics
        action_counts: dict[str, int] = {}
        user_counts: dict[str, int] = {}
        project_counts: dict[str, int] = {}
        result_counts: dict[str, int] = {}

        for entry in entries:
            # Count actions
            action = entry.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1

            # Count users
            user = entry.get("user", "unknown")
            user_counts[user] = user_counts.get(user, 0) + 1

            # Count projects
            proj = entry.get("project", "unknown")
            project_counts[proj] = project_counts.get(proj, 0) + 1

            # Count results
            result = entry.get("result", "unknown")
            result_counts[result] = result_counts.get(result, 0) + 1

        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "total_entries": len(entries),
            "action_counts": action_counts,
            "top_users": dict(sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "project_counts": project_counts,
            "result_counts": result_counts,
            "success_rate": (
                result_counts.get("success", 0) / len(entries) * 100
                if entries else 0
            )
        }

    async def get_user_activity(
        self,
        user: str,
        days: int = 30
    ) -> list[dict[str, Any]]:
        """Get activity for a specific user.

        Args:
            user: Username
            days: Number of days to look back

        Returns:
            List of user's actions
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        return await self.get_audit_trail(
            user=user,
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )

    async def get_project_history(
        self,
        project: str,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get configuration change history for a project.

        Args:
            project: Project name
            limit: Maximum entries

        Returns:
            List of project changes
        """
        return await self.get_audit_trail(
            project=project,
            action=None,  # All actions
            limit=limit
        )

    def _get_files_in_range(
        self,
        start_date: date | None,
        end_date: date | None
    ) -> list[Path]:
        """Get audit log files in date range."""
        files = []

        if start_date and end_date:
            # Get files for specific range
            current = start_date
            while current <= end_date:
                file_path = self.audit_dir / f"audit-{current.isoformat()}.jsonl.gz"
                if file_path.exists():
                    files.append(file_path)
                current += timedelta(days=1)
        else:
            # Get all recent files (last 90 days)
            cutoff = date.today() - timedelta(days=90)
            current = cutoff
            while current <= date.today():
                file_path = self.audit_dir / f"audit-{current.isoformat()}.jsonl.gz"
                if file_path.exists():
                    files.append(file_path)
                current += timedelta(days=1)

        return files

    async def cleanup_old_logs(
        self,
        retention_days: int = 90,
        archive_old: bool = True
    ) -> int:
        """Clean up old audit logs.

        Args:
            retention_days: Days to keep logs
            archive_old: Whether to archive before deletion

        Returns:
            Number of files cleaned up
        """
        cutoff = date.today() - timedelta(days=retention_days)
        cleaned = 0

        for file_path in self.audit_dir.glob("audit-*.jsonl.gz*"):
            # Extract date from filename
            try:
                parts = file_path.stem.split("-")
                if len(parts) >= 3:
                    file_date = date.fromisoformat(f"{parts[1]}-{parts[2]}-{parts[3]}")
                    if file_date < cutoff:
                        if archive_old:
                            # Move to archive
                            archive_dir = self.audit_dir / "archive"
                            archive_dir.mkdir(exist_ok=True)
                            file_path.rename(archive_dir / file_path.name)
                        else:
                            file_path.unlink()
                        cleaned += 1
            except (ValueError, IndexError):
                continue

        logger.info(f"Cleaned up {cleaned} old audit log files")
        return cleaned

    async def search_audit_trail(
        self,
        query: str,
        project: str | None = None,
        days: int = 7
    ) -> list[dict[str, Any]]:
        """Search audit trail for specific query.

        Args:
            query: Search query (searches in messages, details)
            project: Optional project filter
            days: Number of days to search

        Returns:
            Matching audit entries
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        entries = await self.get_audit_trail(
            project=project,
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )

        query_lower = query.lower()
        matches = []

        for entry in entries:
            # Search in various fields
            searchable_text = " ".join([
                entry.get("action", ""),
                entry.get("user", ""),
                json.dumps(entry.get("details", {})),
                entry.get("result", "")
            ]).lower()

            if query_lower in searchable_text:
                matches.append(entry)

        return matches

    async def get_config_change_history(
        self,
        project: str,
        config_type: str | None = None,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get detailed configuration change history.

        Args:
            project: Project name
            config_type: Type of configuration
            limit: Maximum entries

        Returns:
            Configuration changes with version info
        """
        changes = []

        # Get update and create actions
        for action in [AuditAction.CONFIG_CREATE, AuditAction.CONFIG_UPDATE]:
            entries = await self.get_audit_trail(
                project=project,
                action=action,
                limit=limit
            )
            changes.extend(entries)

        # Sort by timestamp descending
        changes.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return changes[:limit]

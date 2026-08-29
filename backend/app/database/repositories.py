"""
Database Repositories

Phase 10 - Sprint 1 - Day 3
Purpose: Repository pattern for database operations

Features:
- Audit log repository with indexing
- Approval history repository
- Session repository with cleanup
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ApprovalHistory, AuditLog, Session


class AuditLogRepository:
    """Repository for audit log operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        environment: str = "production",
        details: dict | None = None,
        status: str = "success",
    ) -> AuditLog:
        """
        Create a new audit log entry.

        Args:
            actor: User or service performing the action
            action: Action performed
            resource_type: Type of resource affected
            resource_id: ID of the resource
            environment: Environment (dev/staging/prod)
            details: Additional details as JSON
            status: Status of the action (success/failure)

        Returns:
            Created AuditLog entry
        """
        audit_log = AuditLog(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            environment=environment,
            details=details,
            status=status,
        )
        self.session.add(audit_log)
        await self.session.flush()
        return audit_log

    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """
        Get audit logs for a specific resource.

        Args:
            resource_type: Type of resource
            resource_id: ID of the resource
            limit: Maximum number of entries to return

        Returns:
            List of audit logs, newest first
        """
        stmt = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.resource_type == resource_type,
                    AuditLog.resource_id == resource_id,
                )
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_actor(
        self,
        actor: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """
        Get audit logs for a specific actor.

        Args:
            actor: User or service
            limit: Maximum number of entries to return

        Returns:
            List of audit logs, newest first
        """
        stmt = (
            select(AuditLog)
            .where(AuditLog.actor == actor)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(
        self,
        environment: str | None = None,
        hours: int = 24,
        limit: int = 1000,
    ) -> list[AuditLog]:
        """
        Get recent audit logs.

        Args:
            environment: Filter by environment (optional)
            hours: Number of hours to look back
            limit: Maximum number of entries to return

        Returns:
            List of audit logs, newest first
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        stmt = select(AuditLog).where(AuditLog.timestamp >= since)

        if environment:
            stmt = stmt.where(AuditLog.environment == environment)

        stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ApprovalHistoryRepository:
    """Repository for approval history operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        action_id: str,
        project: str,
        action_type: str,
        proposed_by: str,
        command: str | None = None,
    ) -> ApprovalHistory:
        """
        Create a new approval history entry.

        Args:
            action_id: Unique action ID
            project: Project name
            action_type: Type of action
            proposed_by: User proposing the action
            command: Command to execute

        Returns:
            Created ApprovalHistory entry
        """
        history = ApprovalHistory(
            action_id=action_id,
            project=project,
            action_type=action_type,
            proposed_by=proposed_by,
            command=command,
            status="pending",
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def update_approval(
        self,
        action_id: str,
        approved_by: str,
        status: str = "approved",
    ) -> ApprovalHistory | None:
        """
        Update approval history with approval information.

        Args:
            action_id: Action ID to update
            approved_by: User who approved/rejected
            status: New status (approved/rejected)

        Returns:
            Updated ApprovalHistory or None if not found
        """
        stmt = select(ApprovalHistory).where(ApprovalHistory.action_id == action_id)
        result = await self.session.execute(stmt)
        history = result.scalar_one_or_none()

        if history:
            history.approved_by = approved_by
            history.approved_at = datetime.now(timezone.utc)
            history.status = status
            await self.session.flush()
            return history
        return None

    async def get_by_project(
        self,
        project: str,
        limit: int = 100,
    ) -> list[ApprovalHistory]:
        """
        Get approval history for a project.

        Args:
            project: Project name
            limit: Maximum number of entries to return

        Returns:
            List of approval history, newest first
        """
        stmt = (
            select(ApprovalHistory)
            .where(ApprovalHistory.project == project)
            .order_by(ApprovalHistory.proposed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending(self, limit: int = 100) -> list[ApprovalHistory]:
        """
        Get pending approvals.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of pending approvals, oldest first
        """
        stmt = (
            select(ApprovalHistory)
            .where(ApprovalHistory.status == "pending")
            .order_by(ApprovalHistory.proposed_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SessionRepository:
    """Repository for session operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        session_id: str,
        user_id: str,
        expires_hours: int = 24,
    ) -> Session:
        """
        Create a new session.

        Args:
            session_id: Unique session ID (token)
            user_id: User ID
            expires_hours: Hours until session expires

        Returns:
            Created Session
        """
        now = datetime.now(timezone.utc)
        session = Session(
            id=session_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(hours=expires_hours),
            last_used=now,
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get(self, session_id: str) -> Session | None:
        """
        Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None if not found/expired
        """
        stmt = select(Session).where(Session.id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_last_used(self, session_id: str) -> bool:
        """
        Update the last_used timestamp for a session.

        Args:
            session_id: Session ID

        Returns:
            True if updated, False if not found
        """
        session = await self.get(session_id)
        if session:
            session.last_used = datetime.now(timezone.utc)
            await self.session.flush()
            return True
        return False

    async def delete(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        stmt = delete(Session).where(Session.id == session_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def cleanup_expired(self) -> int:
        """
        Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        stmt = delete(Session).where(Session.expires_at < datetime.now(timezone.utc))
        result = await self.session.execute(stmt)
        return result.rowcount

    async def cleanup_old_sessions(self, days: int = 30) -> int:
        """
        Delete sessions older than specified days.

        Args:
            days: Number of days to retain

        Returns:
            Number of sessions deleted
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = delete(Session).where(Session.created_at < cutoff)
        result = await self.session.execute(stmt)
        return result.rowcount

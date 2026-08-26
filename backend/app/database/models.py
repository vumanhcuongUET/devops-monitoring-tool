"""
PostgreSQL Database Models

Phase 10 - Sprint 1 - Day 3
Purpose: Define database schema for persistent storage

Features:
- Audit log table (queryable, indexed)
- Approval history table (complex queries)
- Sessions table (for authentication)
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database.base import Base


class AuditLog(Base):
    """
    Audit log for tracking all system actions.

    Stores comprehensive audit trail with:
    - Actor (user/service)
    - Action performed
    - Resource affected
    - Environment (dev/staging/prod)
    - Status (success/failure)
    - Detailed JSON payload

    Indexes for efficient querying by timestamp, actor, and resource.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    actor = Column(String(255), nullable=False, index=True)
    action = Column(String(255), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(255), nullable=True)
    environment = Column(String(50), nullable=False)
    details = Column(JSON, nullable=True)
    status = Column(String(50), nullable=True)

    # Composite index for resource queries
    __table_args__ = (
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )


class ApprovalHistory(Base):
    """
    Approval history for tracking action approvals.

    Stores complete approval workflow history:
    - Action metadata (ID, type, project)
    - Proposer information
    - Approver information
    - Status tracking
    - Command execution details

    Indexes for project-based and status-based queries.
    """

    __tablename__ = "approval_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(String(255), unique=True, nullable=False, index=True)
    project = Column(String(100), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    proposed_by = Column(String(255), nullable=False)
    proposed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=False, index=True)
    command = Column(Text, nullable=True)

    # Index for timestamp queries
    __table_args__ = (
        Index("idx_approval_timestamp", "proposed_at"),
    )


class Session(Base):
    """
    User sessions for authentication.

    Stores active user sessions with:
    - Session ID (token)
    - User ID reference
    - Creation and expiration timestamps
    - Last used timestamp (for sliding expiration)

    Indexes for user-based and cleanup queries.
    """

    __tablename__ = "sessions"

    id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    last_used = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

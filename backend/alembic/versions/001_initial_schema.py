"""Initial schema - audit_log, approval_history, sessions

Phase 10 - Sprint 1 - Day 3
Revision ID: 001_initial
Revises:
Create Date: 2026-08-25

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("phase10",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - create initial tables and indexes."""

    # Create audit_log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_actor"), "audit_log", ["actor"])
    op.create_index(op.f("ix_audit_log_timestamp"), "audit_log", ["timestamp"])
    op.create_index("idx_audit_resource", "audit_log", ["resource_type", "resource_id"])

    # Create approval_history table
    op.create_table(
        "approval_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action_id", sa.String(length=255), nullable=False),
        sa.Column("project", sa.String(length=100), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("proposed_by", sa.String(length=255), nullable=False),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("command", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_id"),
    )
    op.create_index(op.f("ix_approval_history_action_id"), "approval_history", ["action_id"])
    op.create_index(op.f("ix_approval_history_project"), "approval_history", ["project"])
    op.create_index(op.f("ix_approval_history_status"), "approval_history", ["status"])
    op.create_index("idx_approval_timestamp", "approval_history", ["proposed_at"])

    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])


def downgrade() -> None:
    """Reverse migration - drop all tables."""

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("idx_approval_timestamp", table_name="approval_history")
    op.drop_index(op.f("ix_approval_history_status"), table_name="approval_history")
    op.drop_index(op.f("ix_approval_history_project"), table_name="approval_history")
    op.drop_index(op.f("ix_approval_history_action_id"), table_name="approval_history")
    op.drop_table("approval_history")

    op.drop_index("idx_audit_resource", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_timestamp"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor"), table_name="audit_log")
    op.drop_table("audit_log")

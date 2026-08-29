"""approval_events table (review F2: durable approval event log)

Revision ID: 003_approval_events
Revises: 002_timescaledb_metrics
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "003_approval_events"
down_revision = "002_timescaledb_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approval_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("action_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index("ix_approval_events_timestamp", "approval_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("approval_events")

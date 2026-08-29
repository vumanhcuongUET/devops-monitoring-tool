"""TimescaleDB metrics hypertable and continuous aggregates

Phase 10 - Sprint 1 - Day 4
Revision ID: 002_timescaledb
Revises: 001_initial
Create Date: 2026-08-25

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_timescaledb"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = ("timescaledb",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - create TimescaleDB hypertable and views."""

    # Create metrics hypertable
    op.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            time TIMESTAMPTZ NOT NULL,
            project VARCHAR(100) NOT NULL,
            metric_name VARCHAR(255) NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL,
            labels TEXT,
            PRIMARY KEY (time, project, metric_name)
        );
    """)

    # Create indexes
    op.execute('CREATE INDEX IF NOT EXISTS idx_metrics_project ON metrics (project);')
    op.execute('CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics (metric_name);')

    # Convert to hypertable (partition by time)
    op.execute("""
        SELECT create_hypertable('metrics', 'time',
            if_not_exists => TRUE);
    """)

    # Create compression policy (compress data older than 7 days)
    op.execute("""
        SELECT add_compression_policy('metrics',
            INTERVAL '7 days');
    """)

    # Create retention policy (drop data older than 30 days)
    op.execute("""
        SELECT add_retention_policy('metrics',
            INTERVAL '30 days');
    """)

    # Create hourly continuous aggregate
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_hourly
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', time) AS bucket,
            project,
            metric_name,
            AVG(metric_value) AS avg_value,
            MAX(metric_value) AS max_value,
            MIN(metric_value) AS min_value,
            COUNT(*) AS count
        FROM metrics
        GROUP BY bucket, project, metric_name
        WITH NO DATA;
    """)

    # Create daily continuous aggregate
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', time) AS bucket,
            project,
            metric_name,
            AVG(metric_value) AS avg_value,
            MAX(metric_value) AS max_value,
            MIN(metric_value) AS min_value,
            COUNT(*) AS count,
            STDDEV(metric_value) AS std_dev_value
        FROM metrics
        GROUP BY bucket, project, metric_name
        WITH NO DATA;
    """)

    # Create refresh policy for hourly view
    op.execute("""
        SELECT add_continuous_aggregate_policy('metrics_hourly',
            start_offset => INTERVAL '1 hour',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour');
    """)

    # Create refresh policy for daily view
    op.execute("""
        SELECT add_continuous_aggregate_policy('metrics_daily',
            start_offset => INTERVAL '1 day',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day');
    """)


def downgrade() -> None:
    """Reverse migration - drop TimescaleDB objects."""

    # Drop continuous aggregates
    op.execute('DROP MATERIALIZED VIEW IF EXISTS metrics_daily CASCADE;')
    op.execute('DROP MATERIALIZED VIEW IF EXISTS metrics_hourly CASCADE;')

    # Drop retention and compression policies
    op.execute("SELECT remove_retention_policy('metrics');")
    op.execute("SELECT remove_compression_policy('metrics');")

    # Drop hypertable
    op.execute('DROP TABLE IF EXISTS metrics CASCADE;')

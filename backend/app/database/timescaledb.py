"""
TimescaleDB Models for Time-Series Metrics

Phase 10 - Sprint 1 - Day 4
Purpose: Time-series data storage for metrics and SLO calculations

Features:
- Metrics hypertable for time-series data
- Continuous aggregates for hourly/daily summaries
- Automatic partitioning by time
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, String, Text

from app.database.base import Base


class Metric(Base):
    """
    Time-series metric data stored in TimescaleDB hypertable.

    Stores metrics with:
    - Timestamp (time partitioning)
    - Project/service identification
    - Metric name and value
    - Labels (JSON) for dimensions

    Automatic partitioning by time ( hypertable).
    """

    __tablename__ = "metrics"

    # Time is the partition key
    time = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        primary_key=True,
    )

    # Dimensions
    project = Column(String(100), nullable=False, primary_key=True)
    metric_name = Column(String(255), nullable=False, primary_key=True)

    # Value
    metric_value = Column(Float, nullable=False)

    # Additional labels as JSON
    labels = Column(Text, nullable=True)

    # Index for querying by project
    __table_args__ = (
        Index("idx_metrics_project", "project"),
        Index("idx_metrics_name", "metric_name"),
    )


# Continuous Aggregate views (created via SQL, not ORM)
# These will be created via migration script

HOURLY_METRICS_VIEW = """
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
"""

DAILY_METRICS_VIEW = """
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
"""

# Refresh policies for continuous aggregates
HOURLY_REFRESH_POLICY = """
SELECT add_continuous_aggregate_policy('metrics_hourly',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
"""

DAILY_REFRESH_POLICY = """
SELECT add_continuous_aggregate_policy('metrics_daily',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
"""


class MetricRepository:
    """Repository for metric operations."""

    def __init__(self, session):
        self.session = session

    async def create(
        self,
        project: str,
        metric_name: str,
        metric_value: float,
        timestamp: datetime = None,
        labels: dict = None,
    ) -> Metric:
        """
        Create a new metric entry.

        Args:
            project: Project/service name
            metric_name: Name of the metric
            metric_value: Numeric value
            timestamp: Timestamp (defaults to now)
            labels: Additional labels as dict

        Returns:
            Created Metric
        """
        import json

        metric = Metric(
            time=timestamp or datetime.now(timezone.utc),
            project=project,
            metric_name=metric_name,
            metric_value=metric_value,
            labels=json.dumps(labels) if labels else None,
        )
        self.session.add(metric)
        await self.session.flush()
        return metric

    async def query(
        self,
        project: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        aggregate: str = None,
    ) -> list[dict]:
        """
        Query metrics with optional aggregation.

        Args:
            project: Project name
            metric_name: Metric name
            start_time: Start of time range
            end_time: End of time range
            aggregate: Aggregation function (avg, max, min, etc.) or None for raw

        Returns:
            List of {time, value} dicts
        """
        from sqlalchemy import and_, select

        stmt = select(Metric).where(
            and_(
                Metric.project == project,
                Metric.metric_name == metric_name,
                Metric.time >= start_time,
                Metric.time <= end_time,
            )
        ).order_by(Metric.time)

        result = await self.session.execute(stmt)
        metrics = result.scalars().all()

        if aggregate == "raw" or aggregate is None:
            return [{"time": m.time, "value": m.metric_value} for m in metrics]

        # Simple aggregation in Python (for production, use SQL aggregation)
        values = [m.metric_value for m in metrics]
        if not values:
            return []

        if aggregate == "avg":
            value = sum(values) / len(values)
        elif aggregate == "max":
            value = max(values)
        elif aggregate == "min":
            value = min(values)
        elif aggregate == "sum":
            value = sum(values)
        else:
            value = sum(values) / len(values)

        return [{"time": end_time, "value": value}]

    async def query_aggregated(
        self,
        project: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        bucket: str = "1 hour",
    ) -> list[dict]:
        """
        Query metrics using TimescaleDB time_bucket.

        Args:
            project: Project name
            metric_name: Metric name
            start_time: Start of time range
            end_time: End of time range
            bucket: Bucket size (1 hour, 1 day, etc.)

        Returns:
            List of aggregated metrics
        """
        from sqlalchemy import text

        sql = text("""
            SELECT
                time_bucket(:bucket, time) AS bucket,
                AVG(metric_value) AS avg_value,
                MAX(metric_value) AS max_value,
                MIN(metric_value) AS min_value,
                COUNT(*) AS count
            FROM metrics
            WHERE project = :project
                AND metric_name = :metric_name
                AND time >= :start_time
                AND time <= :end_time
            GROUP BY bucket
            ORDER BY bucket
        """)

        result = await self.session.execute(
            sql,
            {
                "bucket": bucket,
                "project": project,
                "metric_name": metric_name,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        return [
            {
                "time": row.bucket,
                "avg": float(row.avg_value),
                "max": float(row.max_value),
                "min": float(row.min_value),
                "count": row.count,
            }
            for row in result
        ]

    async def cleanup_old_metrics(self, days: int = 30) -> int:
        """
        Delete metrics older than specified days.

        Args:
            days: Number of days to retain

        Returns:
            Number of metrics deleted
        """
        from datetime import timedelta

        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = delete(Metric).where(Metric.time < cutoff)
        result = await self.session.execute(stmt)
        return result.rowcount

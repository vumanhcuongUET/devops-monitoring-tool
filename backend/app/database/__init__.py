"""
Database Module

Phase 10 - Sprint 1 - Day 3/4
Purpose: PostgreSQL integration with SQLAlchemy + TimescaleDB
"""

from app.database.base import Base
from app.database.models import ApprovalHistory, AuditLog, Session
from app.database.session import (
    check_connection,
    close_engine,
    get_database_url,
    get_engine,
    get_session,
    init_engine,
)

__all__ = [
    # Base
    "Base",
    # Models
    "AuditLog",
    "ApprovalHistory",
    "Session",
    # Session management
    "init_engine",
    "get_session",
    "close_engine",
    "get_engine",
    "check_connection",
    "get_database_url",
]

# TimescaleDB (optional import - requires TimescaleDB extension)
try:
    from app.database.timescaledb import (  # noqa: F401
        DAILY_METRICS_VIEW,
        DAILY_REFRESH_POLICY,
        HOURLY_METRICS_VIEW,
        HOURLY_REFRESH_POLICY,
        Metric,
        MetricRepository,
    )

    __all__.extend([
        "DAILY_METRICS_VIEW",
        "DAILY_REFRESH_POLICY",
        "HOURLY_METRICS_VIEW",
        "HOURLY_REFRESH_POLICY",
        "Metric",
        "MetricRepository",
    ])
except ImportError:
    pass

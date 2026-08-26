"""
Database Session Management

Phase 10 - Sprint 1 - Day 3
Purpose: SQLAlchemy session management with connection pooling

Features:
- Async engine with connection pooling
- Session factory for scoped sessions
- Proper cleanup on shutdown
- Support for PostgreSQL with asyncpg driver
"""

import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# Global engine and session maker
_engine: Optional["AsyncEngine"] = None
_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_database_url() -> str:
    """
    Build PostgreSQL database URL from settings.

    Returns:
        Async PostgreSQL URL for SQLAlchemy
    """
    if hasattr(settings, "DATABASE_URL") and settings.DATABASE_URL:
        # Use provided DATABASE_URL
        db_url = settings.DATABASE_URL
        # Convert to async if needed
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return db_url

    # Build from components
    password_part = f":{settings.DATABASE_PASSWORD}@" if settings.DATABASE_PASSWORD else "@"
    return (
        f"postgresql+asyncpg://{settings.DATABASE_USER}{password_part}"
        f"{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
    )


def init_engine(
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
) -> None:
    """
    Initialize the database engine with connection pooling.

    Args:
        pool_size: Number of connections to maintain
        max_overflow: Max additional connections beyond pool_size
        pool_timeout: Seconds to wait before giving up on getting a connection
        pool_recycle: Seconds before recycling connections (prevent stale connections)
    """
    global _engine, _async_session_maker

    if _engine is not None:
        logger.warning("Database engine already initialized, skipping")
        return

    database_url = get_database_url()

    _engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,  # Verify connections before using
        echo=False,  # Set True for SQL query logging
    )

    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info(f"Database engine initialized: {settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session for use in dependency injection.

    Yields:
        AsyncSession: SQLAlchemy async session

    Example:
        async with get_session() as session:
            result = await session.execute(select(AuditLog))
            audits = result.scalars().all()
    """
    if _async_session_maker is None:
        init_engine()

    async with _async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


def get_engine() -> Optional["AsyncEngine"]:
    """
    Get the current database engine.

    Returns:
        AsyncEngine or None if not initialized
    """
    return _engine


async def close_engine() -> None:
    """Close the database engine and all connections."""
    global _engine, _async_session_maker

    if _engine is None:
        logger.warning("Database engine not initialized, nothing to close")
        return

    try:
        await _engine.dispose()
        logger.info("Database engine closed successfully")
    except Exception as e:
        logger.error(f"Error closing database engine: {e}")
    finally:
        _engine = None
        _async_session_maker = None


async def check_connection() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        if _engine is None:
            return False

        async with _engine.connect() as conn:
            await conn.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False

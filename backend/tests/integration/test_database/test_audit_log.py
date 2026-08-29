"""
Integration tests for AuditLog repository.

Phase 10 - Sprint 1 - Day 5
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.repositories import AuditLogRepository


@pytest.fixture
async def db_session():
    """Create a test database session."""
    # Use SQLite for testing (or use test PostgreSQL)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_audit_log(db_session: AsyncSession):
    """Test creating an audit log entry."""
    repo = AuditLogRepository(db_session)

    audit_log = await repo.create(
        actor="test-user",
        action="deploy",
        resource_type="deployment",
        resource_id="nginx-deployment",
        environment="staging",
        details={"namespace": "default", "image": "nginx:1.25"},
        status="success",
    )

    assert audit_log.id is not None
    assert audit_log.actor == "test-user"
    assert audit_log.action == "deploy"
    assert audit_log.resource_type == "deployment"
    assert audit_log.resource_id == "nginx-deployment"
    assert audit_log.environment == "staging"
    assert audit_log.status == "success"
    assert audit_log.details["namespace"] == "default"


@pytest.mark.asyncio
async def test_get_by_resource(db_session: AsyncSession):
    """Test querying audit logs by resource."""
    repo = AuditLogRepository(db_session)

    # Create multiple audit logs
    await repo.create(
        actor="user1",
        action="update",
        resource_type="deployment",
        resource_id="test-deployment",
        environment="production",
    )
    await repo.create(
        actor="user2",
        action="scale",
        resource_type="deployment",
        resource_id="test-deployment",
        environment="production",
    )
    await repo.create(
        actor="user1",
        action="delete",
        resource_type="service",
        resource_id="other-service",
        environment="production",
    )

    await db_session.commit()

    # Query by resource
    logs = await repo.get_by_resource("deployment", "test-deployment")

    assert len(logs) == 2
    assert all(log.resource_id == "test-deployment" for log in logs)
    assert all(log.resource_type == "deployment" for log in logs)


@pytest.mark.asyncio
async def test_get_by_actor(db_session: AsyncSession):
    """Test querying audit logs by actor."""
    repo = AuditLogRepository(db_session)

    # Create audit logs
    await repo.create(
        actor="user1",
        action="create",
        resource_type="pod",
        resource_id="pod-1",
        environment="production",
    )
    await repo.create(
        actor="user1",
        action="delete",
        resource_type="pod",
        resource_id="pod-2",
        environment="production",
    )
    await repo.create(
        actor="user2",
        action="create",
        resource_type="pod",
        resource_id="pod-3",
        environment="production",
    )

    await db_session.commit()

    # Query by actor
    logs = await repo.get_by_actor("user1")

    assert len(logs) == 2
    assert all(log.actor == "user1" for log in logs)


@pytest.mark.asyncio
async def test_get_recent(db_session: AsyncSession):
    """Test querying recent audit logs."""
    repo = AuditLogRepository(db_session)

    # Create audit log
    await repo.create(
        actor="test-user",
        action="test-action",
        resource_type="test",
        resource_id="test-1",
        environment="production",
    )

    await db_session.commit()

    # Query recent logs
    logs = await repo.get_recent(
        environment="production",
        hours=1,
        limit=10,
    )

    assert len(logs) >= 1
    assert all(log.environment == "production" for log in logs)


@pytest.mark.asyncio
async def test_audit_log_timestamps(db_session: AsyncSession):
    """Test that timestamps are correctly set."""
    repo = AuditLogRepository(db_session)

    before = datetime.now(timezone.utc)
    audit_log = await repo.create(
        actor="test-user",
        action="test",
        resource_type="test",
        environment="production",
    )
    after = datetime.now(timezone.utc)

    assert audit_log.timestamp is not None
    assert before <= audit_log.timestamp <= after

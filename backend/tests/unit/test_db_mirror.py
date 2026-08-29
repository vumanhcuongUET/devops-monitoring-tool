"""DB mirror tests (review F2): audit/approval events persist when DB enabled.

Runs against SQLite (aiosqlite) — validates the write path without Postgres.
"""
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def db_enabled(tmp_path, monkeypatch):
    """Initialize the engine against a temp SQLite DB and enable mirroring."""
    from app.config import settings
    from app.database.session import close_engine, init_engine

    url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    monkeypatch.setattr(settings, "DATABASE_ENABLED", True)
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    init_engine()

    from app.database import models  # noqa: F401  (register tables)
    from app.database.base import Base
    from app.database.session import _engine

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await close_engine()
    monkeypatch.setattr(settings, "DATABASE_ENABLED", False)


async def test_audit_entry_mirrors_to_db(db_enabled):
    from app.audit.logger import AuditLogger
    from app.models.audit import AuditEventType
    from app.database.mirror import mirror_audit_entry
    from app.database.models import AuditLog
    from app.database.session import _async_session_maker
    from sqlalchemy import select

    entry = AuditLogger().log_event(
        event_type=AuditEventType.ACTION_CREATED,
        user="tester",
        action_id="act-123",
        project="meinvoice",
        success=True,
    )
    await mirror_audit_entry(entry)  # bypass scheduler; await directly

    async with _async_session_maker() as session:
        row = (await session.execute(select(AuditLog))).scalars().first()

    assert row is not None
    assert row.actor == "tester"
    assert row.resource_id == "act-123"


async def test_approval_event_mirrors_to_db(db_enabled):
    from app.database.mirror import mirror_approval_event
    from app.database.models import ApprovalEvent
    from app.database.session import _async_session_maker
    from sqlalchemy import select

    await mirror_approval_event({
        "id": "evt-1",
        "action_id": "act-123",
        "event": "approved",
        "user": "approver1",
        "details": {"comment": "lgtm"},
    })

    async with _async_session_maker() as session:
        row = (await session.execute(select(ApprovalEvent))).scalars().first()

    assert row is not None
    assert row.action_id == "act-123"
    assert row.actor == "approver1"
    assert row.details == {"comment": "lgtm"}


async def test_mirror_skipped_when_db_disabled(monkeypatch):
    """With DATABASE_ENABLED=false (default) no write is attempted."""
    from app.config import settings

    monkeypatch.setattr(settings, "DATABASE_ENABLED", False)
    from app.database.mirror import db_mirroring_enabled

    assert db_mirroring_enabled() is False

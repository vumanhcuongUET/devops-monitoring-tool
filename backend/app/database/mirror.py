"""Best-effort PostgreSQL mirrors for audit and approval events (review F2).

Before this module the database layer initialized but nothing wrote to it
("/health said database: enabled while zero bytes flowed"). Mirrors are
best-effort by design: the file/Redis stores remain the primary record and a
database failure must never break the action path (Phase 11 E2E lesson).
"""
import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def db_mirroring_enabled() -> bool:
    """True when the mirror should attempt writes."""
    if not settings.DATABASE_ENABLED:
        return False
    try:
        from app.database.session import _async_session_maker

        return _async_session_maker is not None
    except Exception:
        return False


async def mirror_audit_entry(entry) -> None:
    """Persist one AuditEntry to PostgreSQL (best effort)."""
    from app.database.repositories import AuditLogRepository
    from app.database.session import _async_session_maker

    try:
        async with _async_session_maker() as session:
            repo = AuditLogRepository(session)
            await repo.create(
                actor=entry.user or "system",
                action=str(getattr(entry.event_type, "value", entry.event_type)),
                resource_type="audit",
                resource_id=entry.action_id,
                environment=settings.ENVIRONMENT,
                details={
                    "project": entry.project,
                    "triage_card_id": entry.triage_card_id,
                    "chain_of_thought": [
                        c.model_dump(mode="json") for c in (entry.chain_of_thought or [])
                    ],
                    **(entry.details or {}),
                },
                status=(
                    ("success" if entry.success else "failure")
                    if entry.success is not None
                    else "unknown"
                ),
            )
            await session.commit()
    except Exception as e:
        logger.warning("Audit DB mirror failed (file record unaffected): %s", e)


async def mirror_approval_event(event: dict) -> None:
    """Persist one approval-lifecycle event dict to PostgreSQL (best effort)."""
    from sqlalchemy import insert

    from app.database.models import ApprovalEvent
    from app.database.session import _async_session_maker

    try:
        async with _async_session_maker() as session:
            await session.execute(
                insert(ApprovalEvent).values(
                    id=event.get("id"),
                    action_id=event.get("action_id"),
                    event=event.get("event"),
                    actor=event.get("user"),
                    details=event.get("details") or {},
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Approval DB mirror failed (file record unaffected): %s", e)


def schedule_mirror(coro) -> None:
    """Fire-and-forget a mirror coroutine when an event loop is running.

    Log_event and ApprovalHistory.add are called from both sync and async
    contexts; with no running loop the file store already holds the record,
    so skipping is correct.
    """
    if not db_mirroring_enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(coro)
    task.add_done_callback(_swallow_task_errors)


def _swallow_task_errors(task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("Audit DB mirror task failed: %s", exc)


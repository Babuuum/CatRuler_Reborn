from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import ActionEnum, UsageLog


async def create(db: AsyncSession, user_id: UUID, action: ActionEnum) -> UsageLog:
    usage_log = UsageLog(user_id=user_id, action=action)
    db.add(usage_log)
    await db.commit()
    await db.refresh(usage_log)
    return usage_log


async def create_bulk(
    db: AsyncSession,
    user_id: UUID,
    actions: list[ActionEnum],
) -> list[UsageLog]:
    """Create multiple usage log entries in a single transaction."""
    logs = [UsageLog(user_id=user_id, action=action) for action in actions]
    db.add_all(logs)
    await db.flush()
    return logs


async def count_today(db: AsyncSession, user_id: UUID, action: ActionEnum) -> int:
    now = datetime.now(UTC)
    day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    stmt = select(func.count(UsageLog.id)).where(
        UsageLog.user_id == user_id,
        UsageLog.action == action,
        UsageLog.created_at >= day_start,
        UsageLog.created_at < day_end,
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import ActionEnum, UsageLog


async def create(db: AsyncSession, user_id: UUID, action: ActionEnum) -> UsageLog:
    """Stage one usage row; the service owns the surrounding transaction."""
    usage_log = UsageLog(user_id=user_id, action=action)
    db.add(usage_log)
    await db.flush()
    return usage_log


async def create_bulk(
    db: AsyncSession,
    user_id: UUID,
    actions: list[ActionEnum],
) -> list[UsageLog]:
    """Stage multiple usage rows; the service owns commit or rollback."""
    logs = [UsageLog(user_id=user_id, action=action) for action in actions]
    db.add_all(logs)
    await db.flush()
    return logs


async def count_today(db: AsyncSession, user_id: UUID, action: ActionEnum) -> int:
    day_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    day_end = day_start + timedelta(days=1)

    stmt = select(func.count(UsageLog.id)).where(
        UsageLog.user_id == user_id,
        UsageLog.action == action,
        UsageLog.created_at >= day_start,
        UsageLog.created_at < day_end,
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)

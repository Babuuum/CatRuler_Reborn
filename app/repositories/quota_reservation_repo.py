from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import (
    ActionEnum,
    QuotaReservation,
    QuotaReservationStatusEnum,
    UsageLog,
    User,
)


class QuotaExceededError(Exception):
    """Raised when a generation reservation cannot fit into the daily quota."""


async def reserve_generation(
    db: AsyncSession,
    *,
    user_id: UUID,
    operation_id: UUID,
    day_utc: date,
    limit: int,
    text_units: int,
    image_units: int,
    expires_at: datetime,
    now: datetime,
) -> QuotaReservation:
    if text_units < 0 or image_units < 0 or text_units + image_units <= 0:
        raise ValueError("At least one generation unit is required")

    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None:
        raise LookupError("User not found")

    await db.execute(
        update(QuotaReservation)
        .where(
            QuotaReservation.user_id == user_id,
            QuotaReservation.status == QuotaReservationStatusEnum.reserved,
            QuotaReservation.expires_at <= now,
        )
        .values(
            status=QuotaReservationStatusEnum.released,
            finalized_at=now,
        )
    )

    used = (
        await db.execute(
            select(func.count(UsageLog.id)).where(
                UsageLog.user_id == user_id,
                UsageLog.created_at >= datetime.combine(day_utc, datetime.min.time()),
                UsageLog.created_at
                < datetime.combine(day_utc + timedelta(days=1), datetime.min.time()),
                UsageLog.action.in_(
                    [ActionEnum.post_generated, ActionEnum.image_generated]
                ),
            )
        )
    ).scalar_one()

    active_reserved = (
        await db.execute(
            select(func.coalesce(func.sum(QuotaReservation.units), 0)).where(
                QuotaReservation.user_id == user_id,
                QuotaReservation.day_utc == day_utc,
                QuotaReservation.status == QuotaReservationStatusEnum.reserved,
                QuotaReservation.expires_at > now,
            )
        )
    ).scalar_one()

    units = text_units + image_units
    if int(used) + int(active_reserved) + units > limit:
        raise QuotaExceededError

    reservation = QuotaReservation(
        id=uuid4(),
        operation_id=operation_id,
        user_id=user_id,
        day_utc=day_utc,
        text_units=text_units,
        image_units=image_units,
        units=units,
        status=QuotaReservationStatusEnum.reserved,
        expires_at=expires_at,
    )
    db.add(reservation)
    await db.flush()
    return reservation


async def get_for_update(
    db: AsyncSession, operation_id: UUID
) -> QuotaReservation | None:
    result = await db.execute(
        select(QuotaReservation)
        .where(QuotaReservation.operation_id == operation_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def finalize_consumed(
    db: AsyncSession, operation_id: UUID, now: datetime
) -> bool:
    reservation = await get_for_update(db, operation_id)
    if reservation is None:
        raise LookupError("Quota reservation not found")
    if reservation.status == QuotaReservationStatusEnum.consumed:
        return False
    if reservation.status == QuotaReservationStatusEnum.released:
        raise ValueError("Quota reservation is already released")

    logs = []
    if reservation.text_units:
        logs.append(
            UsageLog(user_id=reservation.user_id, action=ActionEnum.post_generated)
        )
    if reservation.image_units:
        logs.append(
            UsageLog(user_id=reservation.user_id, action=ActionEnum.image_generated)
        )
    db.add_all(logs)
    reservation.status = QuotaReservationStatusEnum.consumed
    reservation.finalized_at = now
    await db.flush()
    return True


async def finalize_released(
    db: AsyncSession, operation_id: UUID, now: datetime
) -> bool:
    reservation = await get_for_update(db, operation_id)
    if reservation is None:
        raise LookupError("Quota reservation not found")
    if reservation.status == QuotaReservationStatusEnum.released:
        return False
    if reservation.status == QuotaReservationStatusEnum.consumed:
        raise ValueError("Quota reservation is already consumed")

    reservation.status = QuotaReservationStatusEnum.released
    reservation.finalized_at = now
    await db.flush()
    return True

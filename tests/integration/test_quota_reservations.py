import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.db.models.models import (
    ActionEnum,
    Channel,
    ContentTypeEnum,
    PlanEnum,
    QuotaReservation,
    QuotaReservationStatusEnum,
    UsageLog,
    User,
)
from app.repositories.quota_reservation_repo import (
    QuotaExceededError,
    finalize_consumed,
    finalize_released,
    reserve_generation,
)
from app.schemas.post import PostCreate
from app.services.post_service import create_post


async def _new_user(session_maker, telegram_id: int) -> User:
    async with session_maker() as session:
        user = User(
            telegram_id=telegram_id,
            plan=PlanEnum.free,
            extended_free=False,
        )
        session.add(user)
        await session.commit()
        return user


@pytest.mark.asyncio
async def test_parallel_reservations_never_exceed_daily_limit(session_maker):
    user = await _new_user(session_maker, 94001)
    now = datetime.now(UTC).replace(tzinfo=None)

    async def reserve_one(_index: int) -> bool:
        async with session_maker() as session:
            try:
                await reserve_generation(
                    session,
                    user_id=user.id,
                    operation_id=uuid4(),
                    day_utc=now.date(),
                    limit=5,
                    text_units=1,
                    image_units=0,
                    expires_at=now + timedelta(minutes=15),
                    now=now,
                )
                await session.commit()
                return True
            except QuotaExceededError:
                await session.rollback()
                return False

    results = await asyncio.gather(*(reserve_one(index) for index in range(10)))
    assert sum(results) == 5

    async with session_maker() as session:
        count = await session.scalar(
            select(func.count(QuotaReservation.id)).where(
                QuotaReservation.user_id == user.id,
                QuotaReservation.status == QuotaReservationStatusEnum.reserved,
            )
        )
        assert count == 5


@pytest.mark.asyncio
async def test_failed_generation_releases_reservation_without_usage(session_maker):
    user = await _new_user(session_maker, 94002)
    operation_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_maker() as session:
        await reserve_generation(
            session,
            user_id=user.id,
            operation_id=operation_id,
            day_utc=now.date(),
            limit=5,
            text_units=1,
            image_units=1,
            expires_at=now + timedelta(minutes=15),
            now=now,
        )
        await session.commit()

    async with session_maker() as session:
        assert await finalize_released(session, operation_id, now)
        await session.commit()

    async with session_maker() as session:
        reservation = await session.scalar(
            select(QuotaReservation).where(
                QuotaReservation.operation_id == operation_id
            )
        )
        usage_count = await session.scalar(
            select(func.count(UsageLog.id)).where(UsageLog.user_id == user.id)
        )
        assert reservation.status == QuotaReservationStatusEnum.released
        assert usage_count == 0


@pytest.mark.asyncio
async def test_successful_text_image_consumes_exactly_two_units(session_maker):
    user = await _new_user(session_maker, 94003)
    operation_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_maker() as session:
        await reserve_generation(
            session,
            user_id=user.id,
            operation_id=operation_id,
            day_utc=now.date(),
            limit=5,
            text_units=1,
            image_units=1,
            expires_at=now + timedelta(minutes=15),
            now=now,
        )
        await session.commit()

    async with session_maker() as session:
        assert await finalize_consumed(session, operation_id, now)
        await session.commit()
        assert not await finalize_consumed(session, operation_id, now)

    async with session_maker() as session:
        count = await session.scalar(
            select(func.count(UsageLog.id)).where(UsageLog.user_id == user.id)
        )
        actions = (
            await session.scalars(
                select(UsageLog.action).where(UsageLog.user_id == user.id)
            )
        ).all()
        assert count == 2
        assert sorted(actions) == sorted(
            [ActionEnum.post_generated, ActionEnum.image_generated]
        )


@pytest.mark.asyncio
async def test_expired_reservation_is_released_before_new_reservation(session_maker):
    user = await _new_user(session_maker, 94004)
    old_operation = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_maker() as session:
        await reserve_generation(
            session,
            user_id=user.id,
            operation_id=old_operation,
            day_utc=now.date(),
            limit=1,
            text_units=1,
            image_units=0,
            expires_at=now - timedelta(seconds=1),
            now=now - timedelta(minutes=1),
        )
        await session.commit()

    async with session_maker() as session:
        await reserve_generation(
            session,
            user_id=user.id,
            operation_id=uuid4(),
            day_utc=now.date(),
            limit=1,
            text_units=1,
            image_units=0,
            expires_at=now + timedelta(minutes=15),
            now=now,
        )
        await session.commit()
        old = await session.scalar(
            select(QuotaReservation).where(
                QuotaReservation.operation_id == old_operation
            )
        )
        assert old.status == QuotaReservationStatusEnum.released


@pytest.mark.asyncio
async def test_parallel_post_creates_never_exceed_daily_limit(session_maker):
    user = await _new_user(session_maker, 94005)
    async with session_maker() as session:
        channel = Channel(
            user_id=user.id,
            platform="telegram",
            name="test",
            is_active=True,
        )
        session.add(channel)
        await session.commit()
        channel_id = channel.id

    async def create_one(_index: int) -> bool:
        async with session_maker() as session:
            data = PostCreate(
                channel_id=channel_id,
                scheduled_at=datetime.now(UTC).replace(tzinfo=None),
                content_type=ContentTypeEnum.text,
                text_prompt="text",
            )
            try:
                await create_post(session, user.id, data)
                return True
            except Exception:
                await session.rollback()
                return False

    results = await asyncio.gather(*(create_one(index) for index in range(10)))
    assert sum(results) == 3

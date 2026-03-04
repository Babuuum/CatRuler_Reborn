from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import User


async def get_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    return await db.get(User, user_id)


async def get_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create(db: AsyncSession, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update(db: AsyncSession, user_id: UUID, data: dict) -> User:
    user = await get_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")

    for key, value in data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return user


async def get_or_create(db: AsyncSession, telegram_id: int) -> tuple[User, bool]:
    user = await get_by_telegram_id(db, telegram_id)
    if user is not None:
        return user, False

    user = await create(db, telegram_id)
    return user, True

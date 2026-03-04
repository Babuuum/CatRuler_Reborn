from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.repositories import user_repo


async def get_or_create_user(
    x_telegram_id: int = Header(),
    db: AsyncSession = Depends(get_db),
) -> User:
    user, _ = await user_repo.get_or_create(db, x_telegram_id)
    return user

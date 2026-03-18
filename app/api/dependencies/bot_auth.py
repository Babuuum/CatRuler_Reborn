import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.core.settings import get_settings
from app.repositories import user_repo


async def get_or_create_user(
    x_telegram_id: int = Header(),
    x_internal_api_secret: str = Header(),
    db: AsyncSession = Depends(get_db),
) -> User:
    expected_secret = get_settings().INTERNAL_API_SHARED_SECRET
    if not expected_secret:
        raise HTTPException(
            status_code=503,
            detail="Internal bot authentication is not configured",
        )
    if not secrets.compare_digest(x_internal_api_secret, expected_secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    user, _ = await user_repo.get_or_create(db, x_telegram_id)
    return user

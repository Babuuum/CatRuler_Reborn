import bcrypt
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token
from app.repositories import user_repo


async def login(db: AsyncSession, telegram_id: int, password: str) -> str:
    """Verify credentials and return JWT token."""
    user = await user_repo.get_by_telegram_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.api_password_hash:
        raise HTTPException(
            status_code=401,
            detail="API password not set. Use /users/me/api-password via bot first.",
        )
    if not bcrypt.checkpw(password.encode(), user.api_password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_access_token(str(user.id))

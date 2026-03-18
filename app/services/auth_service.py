import anyio
import bcrypt
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token
from app.repositories import user_repo


def _check_password_sync(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


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
    password_matches = await anyio.to_thread.run_sync(
        _check_password_sync,
        password,
        user.api_password_hash,
    )
    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_access_token(str(user.id))

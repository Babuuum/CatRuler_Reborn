from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.core.jwt import decode_access_token
from app.repositories import user_repo

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        parsed_user_id = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = await user_repo.get_by_id(db, parsed_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

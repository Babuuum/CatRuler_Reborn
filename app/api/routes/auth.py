from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.db import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import auth_service

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    token = await auth_service.login(db, data.telegram_id, data.password)
    return TokenResponse(access_token=token)

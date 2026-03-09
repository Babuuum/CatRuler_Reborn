from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.bot_auth import get_or_create_user
from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.schemas.user import UserResponse, UserStats, UserUpdate
from app.services import user_service


class ApiPasswordResponse(BaseModel):
    password: str


router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        return await user_service.get_me(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        return await user_service.update_me(db, current_user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/me/api-password", response_model=ApiPasswordResponse)
async def create_api_password(
    current_user: User = Depends(get_or_create_user),
    db: AsyncSession = Depends(get_db),
) -> ApiPasswordResponse:
    try:
        password = await user_service.generate_api_password(db, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiPasswordResponse(password=password)


@router.get("/me/stats", response_model=UserStats)
async def get_me_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserStats:
    return await user_service.get_stats(db, current_user.id)

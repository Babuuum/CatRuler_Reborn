from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.db import get_db
from app.core.db.models.models import PostStatusEnum, User
from app.schemas.post import PostCreate, PostResponse, PostUpdate
from app.services import post_service

router = APIRouter(tags=["posts"])


@router.get("", response_model=list[PostResponse])
async def get_posts(
    status: PostStatusEnum | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PostResponse]:
    return await post_service.get_posts(db, current_user.id, status)


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    data: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    return await post_service.create_post(db, current_user.id, data)


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    return await post_service.get_post(db, current_user.id, post_id)


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: UUID,
    data: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    return await post_service.update_post(db, current_user.id, post_id, data)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await post_service.delete_post(db, current_user.id, post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/retry", response_model=PostResponse)
async def retry_post(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostResponse:
    return await post_service.retry_post(db, current_user.id, post_id)

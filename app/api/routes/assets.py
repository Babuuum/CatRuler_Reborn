from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.services import asset_service

router = APIRouter(tags=["assets"])


@router.get("/{asset_id}")
async def get_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await asset_service.download_owned_image(db, current_user.id, asset_id)
    return Response(content=data, media_type="image/jpeg")

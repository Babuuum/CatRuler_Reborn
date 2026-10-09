from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services import storage
from app.repositories import asset_repo


async def download_owned_image(
    db: AsyncSession, user_id: UUID, asset_id: UUID
) -> bytes:
    asset = await asset_repo.get_owned(db, asset_id, user_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Image asset not found")
    try:
        return await storage.download_file(asset.object_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Image asset unavailable") from exc

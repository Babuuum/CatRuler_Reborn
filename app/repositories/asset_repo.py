from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import GeneratedAsset


async def create(db: AsyncSession, user_id: UUID, object_key: str) -> GeneratedAsset:
    asset = GeneratedAsset(user_id=user_id, object_key=object_key)
    db.add(asset)
    await db.flush()
    return asset


async def get_owned(
    db: AsyncSession, asset_id: UUID, user_id: UUID
) -> GeneratedAsset | None:
    result = await db.execute(
        select(GeneratedAsset).where(
            GeneratedAsset.id == asset_id,
            GeneratedAsset.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()

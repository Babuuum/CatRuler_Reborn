from fastapi import APIRouter

from app.core.generation_models import get_available_model_keys
from app.schemas.model_catalog import AvailableModelsResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=AvailableModelsResponse)
async def get_models() -> AvailableModelsResponse:
    return AvailableModelsResponse(**get_available_model_keys())

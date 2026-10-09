from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Minimal liveness endpoint; never exposes settings or dependency details."""
    return {"status": "ok"}

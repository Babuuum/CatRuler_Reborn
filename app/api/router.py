from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.channels import router as channels_router
from app.api.routes.generate import router as generate_router
from app.api.routes.posts import router as posts_router
from app.api.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(channels_router, prefix="/channels", tags=["channels"])
api_router.include_router(posts_router, prefix="/posts", tags=["posts"])
api_router.include_router(generate_router, prefix="/generate", tags=["generate"])

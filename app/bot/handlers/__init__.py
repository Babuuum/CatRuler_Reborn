from app.bot.handlers.channels import router as channels_router
from app.bot.handlers.generate import router as generate_router
from app.bot.handlers.password import router as password_router
from app.bot.handlers.profile import router as profile_router
from app.bot.handlers.start import router as start_router

__all__ = [
    "channels_router",
    "generate_router",
    "password_router",
    "profile_router",
    "start_router",
]

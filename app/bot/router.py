from aiogram import Router

from app.bot.handlers import (
    channels_router,
    generate_router,
    password_router,
    profile_router,
    start_router,
)

router = Router()
router.include_router(start_router)
router.include_router(profile_router)
router.include_router(channels_router)
router.include_router(generate_router)
router.include_router(password_router)

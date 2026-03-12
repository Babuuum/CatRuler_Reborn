import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web

from app.bot.router import router
from app.core.settings import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured")

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=RedisStorage.from_url(settings.REDIS_URL))
    dp.include_router(router)

    if settings.BOT_MODE == "webhook":
        await start_webhook(bot, dp, settings)
        return

    await start_polling(bot, dp)


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def start_webhook(bot: Bot, dp: Dispatcher, settings) -> None:
    from aiogram.webhook.aiohttp_server import (
        SimpleRequestHandler,
        setup_application,
    )

    if not settings.WEBHOOK_BASE_URL:
        raise ValueError("WEBHOOK_BASE_URL is required when BOT_MODE=webhook")
    if not settings.WEBHOOK_SECRET:
        raise ValueError("WEBHOOK_SECRET is required when BOT_MODE=webhook")

    webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}{settings.WEBHOOK_PATH}"

    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.WEBHOOK_SECRET,
        drop_pending_updates=True,
    )

    app = web.Application()
    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET,
    )
    handler.register(app, path=settings.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8080)
    await site.start()

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

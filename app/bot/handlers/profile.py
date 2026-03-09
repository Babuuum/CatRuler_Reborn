from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    get_or_refresh_token,
    get_stats,
)

router = Router()


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def profile_handler(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_id = message.from_user.id

    try:
        token = await get_or_refresh_token(telegram_id)
        stats = await get_stats(token)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await message.answer(f"Не удалось получить профиль: {exc}")
        return

    await message.answer(
        "\n".join(
            [
                "👤 Профиль",
                "",
                f"📦 План: {stats['plan']}",
                f"📋 Каналов: {stats['channels_count']} / {stats['channels_limit']}",
                f"✉️ Постов сегодня: {stats['posts_today']} / {stats['posts_limit']}",
                "🔄 Генераций сегодня: "
                f"{stats['generations_today']} / {stats['generations_limit']}",
            ]
        )
    )

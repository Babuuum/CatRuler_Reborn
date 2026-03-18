from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    get_channels,
    get_or_refresh_token,
    humanize_api_error,
)

router = Router()

PLATFORM_LABELS = {
    "vk": "VK",
    "telegram": "Telegram",
}


@router.message(Command("mychannels"))
@router.message(F.text == "📋 Мои каналы")
async def channels_handler(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_id = message.from_user.id

    try:
        token = await get_or_refresh_token(telegram_id)
        channels = await get_channels(token)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await message.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось загрузить каналы. Попробуйте чуть позже.",
            )
        )
        return

    if not channels:
        await message.answer(
            "У вас пока нет подключённых каналов.\n"
            "Сейчас канал можно добавить через веб-интерфейс CatRuler. "
            "После подключения он появится здесь."
        )
        return

    lines = ["📋 Ваши каналы:", ""]
    for index, channel in enumerate(channels, start=1):
        platform = PLATFORM_LABELS.get(channel.get("platform", ""), "Unknown")
        lines.append(f"{index}. {channel['name']} ({platform})")

    await message.answer("\n".join(lines))

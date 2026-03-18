from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.api_client import BotAPIError, get_or_refresh_token, humanize_api_error
from app.bot.keyboards import main_keyboard

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if message.from_user is None:
        return

    try:
        await get_or_refresh_token(message.from_user.id)
    except BotAPIError as exc:
        await message.answer(
            humanize_api_error(
                exc,
                fallback="Сейчас не удаётся подключиться к сервису. Попробуйте позже.",
            )
        )
        return

    await message.answer(
        "Привет! Я CatRuler — помогу автоматизировать постинг. Выбери действие:",
        reply_markup=main_keyboard,
    )

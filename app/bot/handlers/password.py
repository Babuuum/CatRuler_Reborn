from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.api_client import BotAPIError, get_api_password

router = Router()


async def _delete_message_later(message: Message, delay_seconds: int = 30) -> None:
    await asyncio.sleep(delay_seconds)
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        return


@router.message(Command("setpassword"))
@router.message(F.text == "🔑 Получить пароль")
async def password_handler(message: Message) -> None:
    if message.from_user is None:
        return

    try:
        password = await get_api_password(message.from_user.id)
    except BotAPIError as exc:
        await message.answer(f"Не удалось получить пароль: {exc}")
        return

    try:
        sent_message = await message.bot.send_message(
            chat_id=message.from_user.id,
            text=(
                "🔐 Ваш API пароль (не передавайте никому):\n"
                f"<code>{password}</code>"
            ),
            parse_mode="HTML",
        )
    except TelegramForbiddenError:
        await message.answer(
            "Не удалось отправить пароль в личные сообщения. Напишите боту в личку."
        )
        return

    if message.chat.id != message.from_user.id:
        await message.answer("Пароль отправлен вам в личные сообщения на 30 секунд.")

    asyncio.create_task(_delete_message_later(sent_message))

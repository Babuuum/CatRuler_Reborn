from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    generate_text_image,
    get_or_refresh_token,
)

router = Router()

GENERATE_RESULT_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Создать пост",
                callback_data="generate:create_post",
            ),
            InlineKeyboardButton(
                text="🔄 Перегенерировать",
                callback_data="generate:retry",
            ),
        ]
    ]
)


class GenerateStates(StatesGroup):
    waiting_for_prompt = State()


async def _send_generation_result(
    message: Message,
    state: FSMContext,
    prompt: str,
) -> None:
    if message.from_user is None:
        return

    telegram_id = message.from_user.id
    progress_message = await message.answer("⏳ Генерирую...")

    try:
        token = await get_or_refresh_token(telegram_id)
        result = await generate_text_image(
            token,
            text_prompt=prompt,
            image_prompt=prompt,
        )
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await progress_message.edit_text(f"Не удалось сгенерировать пост: {exc}")
        return

    await state.update_data(last_prompt=prompt, last_result=result)

    text = result.get("text", "")
    image_key = result.get("image_key")

    note = ""
    if image_key:
        note = f"\n\n(изображение недоступно)\nimage_key: {image_key}"

    await progress_message.edit_text(
        f"{text}{note}",
        reply_markup=GENERATE_RESULT_KB,
    )


@router.message(Command("generate"))
@router.message(F.text == "🚀 Сгенерировать пост")
async def generate_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(GenerateStates.waiting_for_prompt)
    await message.answer("Опишите тему поста (например: советы по уходу за котом)")


@router.message(GenerateStates.waiting_for_prompt, F.text)
async def generate_from_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Нужен текстовый запрос для генерации.")
        return

    await state.clear()
    await _send_generation_result(message, state, prompt)


@router.callback_query(F.data == "generate:retry")
async def regenerate_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    prompt = data.get("last_prompt")
    if not prompt:
        await callback.answer("Сначала задайте тему поста", show_alert=True)
        return

    await callback.answer("Перегенерирую...")
    await _send_generation_result(callback.message, state, str(prompt))


@router.callback_query(F.data == "generate:create_post")
async def create_post_placeholder(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Создание поста из бота пока не реализовано. Используйте веб-интерфейс."
        )

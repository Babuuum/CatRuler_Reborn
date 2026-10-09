from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    create_post,
    download_asset,
    generate_text_image,
    get_channels,
    get_or_refresh_token,
    humanize_api_error,
)
from app.bot.keyboards.generate import (
    generation_channels_keyboard,
    result_keyboard,
    schedule_keyboard,
)
from app.bot.keyboards.main_kb import main_keyboard

router = Router()


class GenerateStates(StatesGroup):
    choosing_channel = State()
    waiting_for_prompt = State()
    waiting_for_schedule = State()
    waiting_for_time = State()


async def _start_generation(message: Message, state: FSMContext) -> None:
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
                exc, fallback="Не удалось загрузить каналы. Попробуйте позже."
            )
        )
        return

    active = [channel for channel in channels if channel.get("is_active", False)]
    if not active:
        await state.clear()
        await message.answer(
            "Сначала подключите активный канал в разделе «Мои каналы»."
        )
        return
    await state.set_state(GenerateStates.choosing_channel)
    await message.answer(
        "Выберите канал для этого материала. Выбор сохранится при перегенерации.",
        reply_markup=generation_channels_keyboard(active),
    )


async def _send_generation_result(
    message: Message,
    state: FSMContext,
    prompt: str,
    telegram_id: int,
) -> None:
    data = await state.get_data()
    channel_id = data.get("channel_id")
    if not channel_id:
        await message.answer("Канал не выбран. Начните генерацию заново.")
        await state.clear()
        return

    progress_message = await message.answer("⏳ Генерирую текст и изображение...")
    try:
        token = await get_or_refresh_token(telegram_id)
        result = await generate_text_image(
            token,
            text_prompt=prompt,
            image_prompt=prompt,
            channel_id=str(channel_id),
        )
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await progress_message.edit_text(
            humanize_api_error(
                exc,
                fallback="Не удалось сгенерировать пост. Повторите действие вручную.",
            )
        )
        return

    asset_id = result.get("asset_id")
    if not result.get("text") or not asset_id:
        await progress_message.edit_text(
            "Генерация вернула неполный результат. Пост не создан."
        )
        return

    await state.update_data(
        last_prompt=prompt,
        last_result=result,
        idempotency_key=str(uuid4()),
    )
    channel_name = str(data.get("channel_name", "выбранный канал"))
    await state.set_state(GenerateStates.waiting_for_schedule)
    caption = f"Канал: {channel_name}\n\n{result['text']}"
    try:
        image = await download_asset(token, str(asset_id))
    except BotAPIError:
        await progress_message.edit_text(
            f"{caption}\n\nИзображение не удалось загрузить. Пост не создан.",
            reply_markup=result_keyboard(),
        )
    else:
        await progress_message.delete()
        await message.answer_photo(
            BufferedInputFile(image, filename="generated.jpg"),
            caption=caption,
            reply_markup=result_keyboard(),
        )


@router.message(Command("generate"))
@router.message(F.text == "🚀 Сгенерировать пост")
async def generate_entry(message: Message, state: FSMContext) -> None:
    await _start_generation(message, state)


@router.callback_query(F.data.startswith("generate:channel:"))
async def choose_channel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    channel_id = callback.data.rsplit(":", 1)[1]
    try:
        token = await get_or_refresh_token(callback.from_user.id)
        channels = await get_channels(token)
    except BotAPIError as exc:
        await callback.answer(
            humanize_api_error(exc, fallback="Не удалось обновить список каналов."),
            show_alert=True,
        )
        return
    channel = next(
        (item for item in channels if str(item.get("id")) == channel_id), None
    )
    if channel is None or not channel.get("is_active", False):
        await callback.answer(
            "Канал удалён или отключён. Откройте список заново.", show_alert=True
        )
        return
    await state.update_data(
        channel_id=channel_id, channel_name=channel.get("name", "канал")
    )
    await state.set_state(GenerateStates.waiting_for_prompt)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Введите тему поста или /cancel.")


@router.message(GenerateStates.waiting_for_prompt, F.text)
async def generate_from_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if prompt == "/cancel":
        await state.clear()
        await message.answer("Генерация отменена.")
        return
    if not prompt:
        await message.answer("Нужен текстовый запрос для генерации.")
        return
    await _send_generation_result(message, state, prompt, message.from_user.id)


@router.callback_query(F.data == "generate:retry")
async def regenerate_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt = data.get("last_prompt")
    if not prompt or not data.get("channel_id"):
        await callback.answer(
            "Состояние устарело. Начните генерацию заново.", show_alert=True
        )
        await state.clear()
        return
    await callback.answer("Перегенерирую...")
    if callback.message is not None:
        await _send_generation_result(
            callback.message,
            state,
            str(prompt),
            callback.from_user.id,
        )


@router.callback_query(F.data == "generate:create_post")
async def create_post_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != GenerateStates.waiting_for_schedule.state:
        await callback.answer(
            "Результат устарел. Сгенерируйте материал заново.", show_alert=True
        )
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Когда поставить пост? Время указывается в UTC.",
            reply_markup=schedule_keyboard(),
        )


async def _save_generated_post(
    target: CallbackQuery | Message,
    state: FSMContext,
    scheduled_at: datetime,
    actor_id: int,
) -> None:
    data = await state.get_data()
    result = data.get("last_result") or {}
    channel_id = data.get("channel_id")
    asset_id = result.get("asset_id")
    text = result.get("text")
    if not channel_id or not asset_id or not text:
        if isinstance(target, CallbackQuery):
            await target.answer("Результат устарел. Начните заново.", show_alert=True)
        else:
            await target.answer("Результат устарел. Начните заново.")
        await state.clear()
        return
    try:
        token = await get_or_refresh_token(actor_id)
        await create_post(
            token,
            {
                "channel_id": channel_id,
                "scheduled_at": scheduled_at.isoformat(),
                "content_type": "text_image",
                "text_prompt": data.get("last_prompt", ""),
                "image_prompt": data.get("last_prompt", ""),
                "generated_text": text,
                "asset_id": asset_id,
                "idempotency_key": str(data.get("idempotency_key") or uuid4()),
            },
        )
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(actor_id)
        text = humanize_api_error(exc, fallback="Не удалось сохранить пост.")
        if isinstance(target, CallbackQuery):
            await target.answer(text, show_alert=True)
        else:
            await target.answer(text)
        return
    await state.clear()
    if isinstance(target, CallbackQuery):
        await target.answer("Пост сохранён в очередь")
        if target.message is not None:
            await target.message.answer(
                "✅ Пост сохранён. Повторное нажатие не создаст дубль."
            )
    else:
        await target.answer("✅ Пост сохранён. Повторное нажатие не создаст дубль.")


@router.callback_query(F.data == "generate:now")
async def create_post_now_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await _save_generated_post(
        callback,
        state,
        datetime.now(UTC).replace(tzinfo=None),
        callback.from_user.id,
    )


@router.callback_query(F.data == "generate:time")
async def create_post_time_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GenerateStates.waiting_for_time)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Введите дату и время UTC: YYYY-MM-DD HH:MM")


@router.message(GenerateStates.waiting_for_time, F.text)
async def create_post_at_time_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    try:
        value = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M").replace(
            tzinfo=UTC
        )
    except ValueError:
        await message.answer("Неверный формат. Используйте YYYY-MM-DD HH:MM UTC.")
        return
    await _save_generated_post(
        message, state, value.replace(tzinfo=None), message.from_user.id
    )


@router.callback_query(F.data == "generate:cancel")
async def generate_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await callback.message.answer("Действие отменено.")


@router.callback_query(F.data == "generate:menu")
async def generate_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Главное меню", reply_markup=main_keyboard)


@router.message(Command("cancel"))
async def cancel_generation_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")

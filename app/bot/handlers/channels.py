from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    create_tg_channel,
    create_vk_channel,
    disable_channel,
    get_channels,
    get_or_refresh_token,
    humanize_api_error,
)
from app.bot.keyboards.channels import (
    channel_card_keyboard,
    channels_keyboard,
    delete_confirmation_keyboard,
    platform_keyboard,
)
from app.bot.keyboards.main_kb import main_keyboard

router = Router()
PAGE_SIZE = 5

PLATFORM_LABELS = {"vk": "VK", "telegram": "Telegram"}


class ChannelStates(StatesGroup):
    choosing_platform = State()
    vk_name = State()
    vk_group = State()
    vk_token = State()
    tg_name = State()
    tg_chat_id = State()


async def _load_channels(telegram_id: int) -> tuple[str, list[dict]]:
    token = await get_or_refresh_token(telegram_id)
    return token, await get_channels(token)


async def _show_channels(message: Message, telegram_id: int, page: int = 0) -> None:
    token, channels = await _load_channels(telegram_id)
    del token
    total_pages = max(1, (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), total_pages - 1)
    current = channels[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    if not channels:
        await message.answer(
            "📋 Каналов пока нет. Подключите VK или Telegram канал.",
            reply_markup=channels_keyboard(0, False, False),
        )
        return

    await message.answer(
        f"📋 Мои каналы · страница {page + 1}/{total_pages}",
        reply_markup=channels_keyboard(page, page > 0, page < total_pages - 1),
    )
    for channel in current:
        platform = PLATFORM_LABELS.get(channel.get("platform", ""), "Канал")
        state = "активен" if channel.get("is_active", False) else "отключён"
        await message.answer(
            f"{channel.get('name', 'Без названия')}\n"
            f"Платформа: {platform}\nСостояние: {state}",
            reply_markup=channel_card_keyboard(str(channel["id"])),
        )


async def _handle_api_error(target, exc: BotAPIError, telegram_id: int) -> None:
    if exc.status_code == 401:
        clear_cached_token(telegram_id)
    text = humanize_api_error(exc, fallback="Не удалось выполнить действие.")
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await target.answer(text)


@router.message(Command("mychannels"))
@router.message(F.text == "📋 Мои каналы")
async def channels_handler(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    try:
        await _show_channels(message, message.from_user.id)
    except BotAPIError as exc:
        await _handle_api_error(message, exc, message.from_user.id)


@router.callback_query(F.data.startswith("channels:page:"))
async def channels_page_handler(callback: CallbackQuery) -> None:
    try:
        page = int(callback.data.rsplit(":", 1)[1])
        if callback.message is not None:
            await _show_channels(callback.message, callback.from_user.id, page)
        await callback.answer()
    except (BotAPIError, ValueError) as exc:
        if isinstance(exc, BotAPIError):
            await _handle_api_error(callback, exc, callback.from_user.id)
        else:
            await callback.answer(
                "Эта кнопка устарела. Откройте список каналов заново.", show_alert=True
            )


@router.callback_query(F.data == "channels:add")
async def add_channel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelStates.choosing_platform)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Выберите платформу. Секрет VK вводите только в личном чате с ботом.",
            reply_markup=platform_keyboard(),
        )


@router.callback_query(F.data.startswith("channels:platform:"))
async def platform_handler(callback: CallbackQuery, state: FSMContext) -> None:
    platform = callback.data.rsplit(":", 1)[1]
    if platform == "vk":
        await state.set_state(ChannelStates.vk_name)
        text = "Введите название VK канала или /cancel."
    elif platform == "telegram":
        await state.set_state(ChannelStates.tg_name)
        text = "Введите название Telegram канала или /cancel."
    else:
        await callback.answer("Эта кнопка устарела.", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(text)


@router.message(ChannelStates.vk_name, F.text)
async def vk_name_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(vk_name=message.text.strip())
    await state.set_state(ChannelStates.vk_group)
    await message.answer(
        "Отправьте ссылку на сообщество или его ID. Пароль VK не нужен."
    )


@router.message(ChannelStates.vk_group, F.text)
async def vk_group_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(vk_group=message.text.strip())
    await state.set_state(ChannelStates.vk_token)
    await message.answer(
        "Отправьте токен сообщества VK последним сообщением. "
        "Он не сохраняется в состоянии бота и будет удалён из чата, если Telegram позволит."
    )


@router.message(ChannelStates.vk_token, F.text)
async def vk_token_handler(message: Message, state: FSMContext) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Токен можно вводить только в личном чате с ботом.")
        return
    data = await state.get_data()
    token_value = message.text.strip()
    await state.clear()
    try:
        token = await get_or_refresh_token(message.from_user.id)
        channel = await create_vk_channel(
            token,
            name=str(data.get("vk_name", "VK канал")),
            group_id=str(data.get("vk_group", "")),
            community_token=token_value,
        )
        await message.answer(f"VK канал «{channel.get('name', 'канал')}» подключён.")
    except BotAPIError as exc:
        await _handle_api_error(message, exc, message.from_user.id)
    finally:
        try:
            await message.delete()
        except Exception:
            pass


@router.message(ChannelStates.tg_name, F.text)
async def tg_name_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(tg_name=message.text.strip())
    await state.set_state(ChannelStates.tg_chat_id)
    await message.answer("Введите @username или chat_id Telegram канала.")


@router.message(ChannelStates.tg_chat_id, F.text)
async def tg_chat_id_handler(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        token = await get_or_refresh_token(message.from_user.id)
        channel = await create_tg_channel(
            token,
            name=str(data.get("tg_name", "Telegram канал")),
            chat_id=message.text.strip(),
        )
        await message.answer(
            f"Telegram канал «{channel.get('name', 'канал')}» подключён."
        )
    except BotAPIError as exc:
        await _handle_api_error(message, exc, message.from_user.id)


@router.callback_query(F.data.startswith("channels:delete:"))
async def delete_channel_handler(callback: CallbackQuery) -> None:
    channel_id = callback.data.rsplit(":", 1)[1]
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Канал будет отключён. История сохранится, очередь не будет отправляться "
            "в этот канал. Внешнее сообщество и уже опубликованные записи не удаляются.",
            reply_markup=delete_confirmation_keyboard(channel_id),
        )


@router.callback_query(F.data.startswith("channels:delete_yes:"))
async def delete_channel_confirm_handler(callback: CallbackQuery) -> None:
    channel_id = callback.data.rsplit(":", 1)[1]
    try:
        token = await get_or_refresh_token(callback.from_user.id)
        await disable_channel(token, channel_id)
        await callback.answer("Канал отключён")
        if callback.message is not None:
            await callback.message.edit_text("Канал отключён. История сохранена.")
    except BotAPIError as exc:
        await _handle_api_error(callback, exc, callback.from_user.id)


@router.callback_query(F.data == "channels:cancel")
async def channels_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await callback.message.edit_text("Действие отменено.")


@router.callback_query(F.data == "channels:menu")
async def channels_menu_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Главное меню", reply_markup=main_keyboard)


@router.message(Command("cancel"))
async def cancel_channel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")

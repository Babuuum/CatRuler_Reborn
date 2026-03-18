from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.api_client import (
    BotAPIError,
    clear_cached_token,
    get_models,
    get_or_refresh_token,
    get_profile,
    get_stats,
    humanize_api_error,
    update_profile,
)
from app.core.generation_models import IMAGE_MODEL_LABELS, TEXT_MODEL_LABELS

router = Router()


def _profile_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Текстовая модель",
                    callback_data="profile:text_models",
                ),
                InlineKeyboardButton(
                    text="🖼 Image модель",
                    callback_data="profile:image_models",
                ),
            ]
        ]
    )


def _model_keyboard(
    *,
    model_keys: list[str],
    current_key: str,
    labels: dict[str, str],
    callback_prefix: str,
) -> InlineKeyboardMarkup:
    rows = []
    for key in model_keys:
        marker = "✅ " if key == current_key else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{labels.get(key, key)}",
                    callback_data=f"{callback_prefix}:{key}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="profile:back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render_profile_text(profile: dict, stats: dict) -> str:
    text_model_key = profile.get("text_model_key", "")
    image_model_key = profile.get("image_model_key", "")
    return "\n".join(
        [
            "👤 Профиль",
            "",
            f"📦 План: {stats['plan']}",
            f"📋 Каналов: {stats['channels_count']} / {stats['channels_limit']}",
            f"✉️ Постов сегодня: {stats['posts_today']} / {stats['posts_limit']}",
            "🔄 Генераций сегодня: "
            f"{stats['generations_today']} / {stats['generations_limit']}",
            "",
            "🧠 Модели генерации",
            f"Текст: {TEXT_MODEL_LABELS.get(text_model_key, text_model_key)}",
            f"Изображение: {IMAGE_MODEL_LABELS.get(image_model_key, image_model_key)}",
        ]
    )


async def _load_profile_data(telegram_id: int) -> tuple[dict, dict]:
    token = await get_or_refresh_token(telegram_id)
    profile = await get_profile(token)
    stats = await get_stats(token)
    return profile, stats


async def _send_profile(message: Message, telegram_id: int) -> None:
    profile, stats = await _load_profile_data(telegram_id)
    await message.answer(
        _render_profile_text(profile, stats),
        reply_markup=_profile_actions_keyboard(),
    )


async def _edit_profile(callback: CallbackQuery, telegram_id: int) -> None:
    profile, stats = await _load_profile_data(telegram_id)
    if callback.message is not None:
        await callback.message.edit_text(
            _render_profile_text(profile, stats),
            reply_markup=_profile_actions_keyboard(),
        )


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def profile_handler(message: Message) -> None:
    if message.from_user is None:
        return

    telegram_id = message.from_user.id

    try:
        await _send_profile(message, telegram_id)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await message.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось загрузить профиль. Попробуйте чуть позже.",
            )
        )


@router.callback_query(F.data == "profile:back")
async def profile_back_handler(callback: CallbackQuery) -> None:
    telegram_id = callback.from_user.id
    try:
        await _edit_profile(callback, telegram_id)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await callback.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось загрузить профиль. Попробуйте чуть позже.",
            ),
            show_alert=True,
        )
        return
    await callback.answer()


@router.callback_query(F.data == "profile:text_models")
async def profile_text_models_handler(callback: CallbackQuery) -> None:
    try:
        token = await get_or_refresh_token(callback.from_user.id)
        profile = await get_profile(token)
        models = await get_models()
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(callback.from_user.id)
        await callback.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось загрузить список моделей. Попробуйте позже.",
            ),
            show_alert=True,
        )
        return

    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите текстовую модель:",
            reply_markup=_model_keyboard(
                model_keys=models["text_model_keys"],
                current_key=str(profile["text_model_key"]),
                labels=TEXT_MODEL_LABELS,
                callback_prefix="profile:set_text",
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "profile:image_models")
async def profile_image_models_handler(callback: CallbackQuery) -> None:
    try:
        token = await get_or_refresh_token(callback.from_user.id)
        profile = await get_profile(token)
        models = await get_models()
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(callback.from_user.id)
        await callback.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось загрузить список моделей. Попробуйте позже.",
            ),
            show_alert=True,
        )
        return

    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите image модель:",
            reply_markup=_model_keyboard(
                model_keys=models["image_model_keys"],
                current_key=str(profile["image_model_key"]),
                labels=IMAGE_MODEL_LABELS,
                callback_prefix="profile:set_image",
            ),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:set_text:"))
async def profile_set_text_model_handler(callback: CallbackQuery) -> None:
    model_key = callback.data.split(":", 2)[2]
    telegram_id = callback.from_user.id

    try:
        token = await get_or_refresh_token(telegram_id)
        await update_profile(token, {"text_model_key": model_key})
        await _edit_profile(callback, telegram_id)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await callback.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось обновить профиль. Попробуйте позже.",
            ),
            show_alert=True,
        )
        return

    await callback.answer("Текстовая модель обновлена")


@router.callback_query(F.data.startswith("profile:set_image:"))
async def profile_set_image_model_handler(callback: CallbackQuery) -> None:
    model_key = callback.data.split(":", 2)[2]
    telegram_id = callback.from_user.id

    try:
        token = await get_or_refresh_token(telegram_id)
        await update_profile(token, {"image_model_key": model_key})
        await _edit_profile(callback, telegram_id)
    except BotAPIError as exc:
        if exc.status_code == 401:
            clear_cached_token(telegram_id)
        await callback.answer(
            humanize_api_error(
                exc,
                fallback="Не удалось обновить профиль. Попробуйте позже.",
            ),
            show_alert=True,
        )
        return

    await callback.answer("Image модель обновлена")

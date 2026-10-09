from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def generation_channels_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.get('name', 'Канал')} ({item.get('platform', '')})",
                callback_data=f"generate:channel:{item['id']}",
            )
        ]
        for item in channels
        if item.get("is_active", True)
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="Отмена", callback_data="generate:cancel")],
            [InlineKeyboardButton(text="Главное меню", callback_data="generate:menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Создать пост", callback_data="generate:create_post"
                ),
                InlineKeyboardButton(
                    text="🔄 Перегенерировать", callback_data="generate:retry"
                ),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="generate:cancel")],
            [InlineKeyboardButton(text="Главное меню", callback_data="generate:menu")],
        ]
    )


def schedule_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сейчас", callback_data="generate:now")],
            [
                InlineKeyboardButton(
                    text="Указать время UTC", callback_data="generate:time"
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="generate:cancel")],
            [InlineKeyboardButton(text="Главное меню", callback_data="generate:menu")],
        ]
    )

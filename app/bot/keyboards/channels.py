from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def channels_keyboard(
    page: int, has_previous: bool, has_next: bool
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="channels:add")]
    ]
    navigation = []
    if has_previous:
        navigation.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"channels:page:{page - 1}")
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(text="➡️", callback_data=f"channels:page:{page + 1}")
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [InlineKeyboardButton(text="Главное меню", callback_data="channels:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_card_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"channels:delete:{channel_id}"
                )
            ]
        ]
    )


def delete_confirmation_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Удалить", callback_data=f"channels:delete_yes:{channel_id}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="channels:cancel"),
            ]
        ]
    )


def platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="VK", callback_data="channels:platform:vk"),
                InlineKeyboardButton(
                    text="Telegram", callback_data="channels:platform:telegram"
                ),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="channels:cancel")],
        ]
    )

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🚀 Сгенерировать пост"),
            KeyboardButton(text="📋 Мои каналы"),
        ],
        [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="🔑 Получить пароль"),
        ],
    ],
    resize_keyboard=True,
)

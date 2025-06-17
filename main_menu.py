from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import MAIN_MENU_PHOTO

MAIN_MENU_TEXT = "<b>👋 Оуу</b>"

def get_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Мой профиль", callback_data="profile")],
        [
            InlineKeyboardButton(text="🤖 Боты", callback_data="bots"),
            InlineKeyboardButton(text="📋 Шаблоны", callback_data="templates")
        ],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info")],
        [InlineKeyboardButton(text="☘️ Отстук", url="https://t.me/offdarnonotsbot")]  
    ])

async def send_main_menu(message: Message):
    await message.answer_photo(
        photo=MAIN_MENU_PHOTO,
        caption=MAIN_MENU_TEXT,
        reply_markup=get_main_menu(),
        parse_mode="HTML"  
    )
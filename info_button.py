from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from main_menu import send_main_menu
from config import INFO_PHOTO_URL

router = Router()

INFO_LINKS = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="💬 Чат", url="https://t.me/example_chat"),
        InlineKeyboardButton(text="👤 Админ", url="https://t.me/example_admin")
    ],
    [
        InlineKeyboardButton(text="📚 Мануалы", url="https://t.me/example_manuals"),
        InlineKeyboardButton(text="💰 Депозиты", url="https://t.me/example_deposits")
    ],
    [
        InlineKeyboardButton(text="📢 Канал", url="https://t.me/example_channel")
    ],
    [
        InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")
    ]
])

@router.callback_query(F.data == "info")
async def open_info(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer_photo(
        photo=INFO_PHOTO_URL,
        caption="<b>🔗 Полезные ссылки:</b>",
        reply_markup=INFO_LINKS,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "go_back_main")
async def go_back_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await send_main_menu(callback.message)
    await callback.answer()
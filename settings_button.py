from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import SETTINGS_MENU_PHOTO
from models import MainUser, ConnectedID
from main_menu import send_main_menu

router = Router()

SETTINGS_TEXT = "<b>⚙️ Настройки.</b>"

class TransferFSM(StatesGroup):
    waiting_for_id = State()


def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить передачу", callback_data="connect_transfer")],
        [InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")]
    ])

# 📋 Отправка меню настроек с привязанными ID
async def send_settings_menu(target: types.Message | types.CallbackQuery, page: int = 0):
    user_id = target.from_user.id
    user, _ = await MainUser.get_or_create(telegram_id=user_id)
    connected_ids = await ConnectedID.filter(owner=user).order_by("-added_at")

    per_page = 10
    start = page * per_page
    end = start + per_page
    page_items = connected_ids[start:end]

    id_buttons = []
    row = []

    for i, conn in enumerate(page_items):
        row.append(InlineKeyboardButton(
            text=str(conn.telegram_id),
            callback_data=f"confirm_delete_id:{conn.telegram_id}"
        ))
        if len(row) == 2 or i == len(page_items) - 1:
            id_buttons.append(row)
            row = []

    pagination = []
    if start > 0:
        pagination.append(InlineKeyboardButton(text="⬅️", callback_data=f"settings:{page - 1}"))
    if end < len(connected_ids):
        pagination.append(InlineKeyboardButton(text="➡️", callback_data=f"settings:{page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подключить передачу", callback_data="connect_transfer"),
            InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")
        ],
        *id_buttons,
        pagination if pagination else []
    ])

    send_photo = (
        target.message.answer_photo if isinstance(target, types.CallbackQuery)
        else target.answer_photo
    )

    await send_photo(
        photo=SETTINGS_MENU_PHOTO,
        caption=SETTINGS_TEXT,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "settings")
@router.callback_query(F.data.startswith("settings:"))
async def open_settings(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    page = 0
    if ":" in callback.data:
        try:
            page = int(callback.data.split(":")[1])
        except:
            pass

    await send_settings_menu(callback, page)
    await callback.answer()



# 🔗 Кнопка подключения передачи
@router.callback_query(F.data == "connect_transfer")
async def handle_connect_transfer(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    await state.set_state(TransferFSM.waiting_for_id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data="settings")]
    ])

    caption = (
        "<blockquote>"
        "<b>📥 Пришлите Telegram ID аккаунта, которому вы хотите передавать подарки.</b>\n\n"
        "<b>🔎 Узнать его можно в боте: @getmyid_bot</b>\n"
        "<b>👆 Просто откройте бот, нажмите Start и скопируйте ID.</b>\n\n"
        "<b>⚠️ Не используйте свой основной аккаунт.</b>\n"
        "<b>Рекомендуем создать отдельный аккаунт для получения подарков.</b>"
        "</blockquote>"
    )

    await callback.message.answer_photo(
        photo=SETTINGS_MENU_PHOTO,
        caption=caption,
        reply_markup=markup,
        parse_mode="HTML"
    )
    await callback.answer()


# 💾 Обработка введённого Telegram ID
@router.message(TransferFSM.waiting_for_id)
async def process_transfer_id(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("<b>❌ Введите корректный Telegram ID (только цифры).</b>", parse_mode="HTML")
        return

    main_user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)

    obj, created = await ConnectedID.get_or_create(
        owner=main_user,
        telegram_id=target_id
    )

    if created:
        await message.answer("<b>✅ Аккаунт успешно привязан.</b>", parse_mode="HTML")
    else:
        await message.answer("<b>ℹ️ Этот Аккаунт уже привязан.</b>", parse_mode="HTML")

    await state.clear()
    await send_settings_menu(message)


@router.callback_query(F.data.startswith("confirm_delete_id:"))
async def confirm_delete_id(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    telegram_id = int(callback.data.split(":")[1])

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Удалить", callback_data=f"delete_id:{telegram_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="settings")
        ]
    ])

    await callback.message.answer_photo(
        photo=SETTINGS_MENU_PHOTO,
        caption=f"<b>Вы уверены, что хотите удалить аккаунт:</b> <code>{telegram_id}</code>?",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("delete_id:"))
async def delete_id(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    telegram_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    user, _ = await MainUser.get_or_create(telegram_id=user_id)

    await ConnectedID.filter(owner=user, telegram_id=telegram_id).delete()
    await callback.message.answer(
        "<b>✅ Аккаунт успешно удалён.</b>",
        parse_mode="HTML"
    )
    await send_settings_menu(callback)


# ⬅️ Назад в главное меню
@router.callback_query(F.data == "go_back_main")
async def go_back_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await send_main_menu(callback.message)
    await callback.answer()
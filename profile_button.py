from datetime import datetime
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from main_menu import send_main_menu
from config import PROFILE_PHOTO_URL
from models import MainUser, UserBot

router = Router()

class NickFSM(StatesGroup):
    waiting_for_nick = State()

def get_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить ник для топа", callback_data="change_nick")],
        [InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")]
    ])

async def send_profile_menu(message: types.Message, user: types.User):
    db_user, _ = await MainUser.get_or_create(telegram_id=user.id)
    bot_count = await UserBot.filter(owner=db_user).count()
    nickname = db_user.nickname or "не установлен"
    username = user.username or "без username"

    # Считаем сколько в команде
    now = datetime.utcnow()
    created = db_user.created_at.replace(tzinfo=None)  
    delta = now - created

    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    time_in_team = f"{days}д {hours}ч {minutes}м"

    text = (
        "<b>💎 Профиль</b>\n\n"
        f"🔹 <b>ID:</b> <code>{user.id}</code>\n"
        f"🔹 <b>Username:</b> @{username}\n"
        f"🔹 <b>Ник для топа:</b> <code>{nickname}</code>\n"
        f"🤖 <b>Количество ботов:</b> <b>{bot_count}</b>\n"
        f"⏳ <b>В команде:</b> <code>{time_in_team}</code>"
    )

    await message.answer_photo(
        photo=PROFILE_PHOTO_URL,
        caption=text,
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "profile")
async def open_profile(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await send_profile_menu(callback.message, callback.from_user)
    await callback.answer()

@router.callback_query(F.data == "change_nick")
async def change_nick(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data="profile")]
    ])

    sent = await callback.message.answer_photo(
        photo=PROFILE_PHOTO_URL,
        caption="<b>✏️ Введите новый ник для топа:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

    await state.set_state(NickFSM.waiting_for_nick)
    await state.update_data(prompt_message_id=sent.message_id)  # 💾 сохраняем ID
    await callback.answer()


@router.message(NickFSM.waiting_for_nick)
async def save_nick(message: types.Message, state: FSMContext):
    new_nick = message.text.strip()

    if len(new_nick) > 32:
        await message.answer("<b>❌ Ник слишком длинный. До 32 символов.</b>", parse_mode="HTML")
        return

    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)
    user.nickname = new_nick
    await user.save()

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_message_id")

    await state.clear()

    # Удаляем сообщение-вопрос (фото с кнопкой "назад")
    if prompt_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except:
            pass

    # Удаляем сообщение с ником
    try:
        await message.delete()
    except:
        pass

    await send_profile_menu(message, message.from_user)


@router.callback_query(F.data == "go_back_main")
async def go_back_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await send_main_menu(callback.message)
    await callback.answer()
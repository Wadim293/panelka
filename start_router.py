from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from models import MainUser, Application
from main_menu import send_main_menu
from config import ADMIN_TELEGRAM_ID  # Айди админа из конфига
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

class ApplicationState(StatesGroup):
    lzt = State()
    experience = State()
    source = State()

@router.message(F.text == "/start")
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    user, _ = await MainUser.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "username": message.from_user.username,
            "is_accepted": False
        }
    )
    # Если админ — сразу меню
    if message.from_user.id == ADMIN_TELEGRAM_ID:
        await message.answer("💎")
        await send_main_menu(message)
        return

    # Проверяем доступ пользователя
    if user.is_accepted:
        await message.answer("💎")
        await send_main_menu(message)
    else:
        # Проверяем есть ли pending заявка
        app = await Application.get_or_none(telegram_id=message.from_user.id, status="pending")
        if app:
            await message.answer("<b>⌛️ Ваша заявка в ожидании рассмотрения, подождите.</b>", parse_mode="HTML")
        else:
            await message.answer("<b>✨ Укажите свой LZT:</b>", parse_mode="HTML")
            await state.set_state(ApplicationState.lzt)

@router.message(ApplicationState.lzt)
async def process_lzt(message: types.Message, state: FSMContext):
    if "https://lolz.live" not in message.text.lower():
        await message.answer("<b>❌ Ошибка: ссылка должна содержать https://lolz.live</b>", parse_mode="HTML")
        return  

    await state.update_data(lzt=message.text)
    await message.answer("<b>⚡️ Какой у вас опыт?</b>", parse_mode="HTML")
    await state.set_state(ApplicationState.experience)

@router.message(ApplicationState.experience)
async def process_experience(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    await message.answer("<b>🌍 Откуда вы о нас узнали?</b>", parse_mode="HTML")
    await state.set_state(ApplicationState.source)

@router.message(ApplicationState.source)
async def process_source(message: types.Message, state: FSMContext):
    data = await state.get_data()

    app = await Application.create(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        lzt=data.get("lzt"),
        experience=data.get("experience"),
        source=message.text,
        status="pending"
    )

    await state.clear()
    await message.answer("<b>✅ Заявка отправлена!</b>", parse_mode="HTML")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_app:{app.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_app:{app.id}")
        ]
    ])

    admin_text = (
        f"<b>📥 Новая заявка #{app.id}</b>\n\n"
        f"<b>👤 ID: </b><code>{app.telegram_id}</code>\n"
        f"<b>👤 Юзернейм: </b><b>@{app.username or 'нет'}</b>\n"
        f"<b>👤 Имя: </b><b>{app.first_name or 'неизвестно'}</b>\n"
        f"<b>✨ LZT: </b><b>{app.lzt}</b>\n"
        f"<b>⚡ Опыт: </b><b>{app.experience}</b>\n"
        f"<b>🌍 Откуда узнал: </b><b>{app.source}</b>"
    )

    await message.bot.send_message(ADMIN_TELEGRAM_ID, admin_text, reply_markup=markup, parse_mode="HTML")
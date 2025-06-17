from aiogram import Router, F, types
from aiogram.filters import Command
from models import Application, MainUser
from main_menu import send_main_menu
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

async def get_status_markup(status: str, app_id: int) -> InlineKeyboardMarkup:
    if status == "accepted":
        btn = InlineKeyboardButton(text="✅ Принята", callback_data="none")
    elif status == "rejected":
        btn = InlineKeyboardButton(text="❌ Отклонена", callback_data="none")
    else:
        btn = InlineKeyboardButton(text="⚠️ Статус неизвестен", callback_data="none")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])

@router.callback_query(F.data.startswith("accept_app:"))
async def accept_application(callback: types.CallbackQuery):
    app_id = int(callback.data.split(":")[1])
    app = await Application.get_or_none(id=app_id)
    if not app:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return

    if app.status != "pending":
        await callback.answer(f"⚠️ Эта заявка уже обработана ({app.status}).", show_alert=True)
        return

    app.status = "accepted"
    await app.save()

    user = await MainUser.get_or_none(telegram_id=app.telegram_id)
    if user:
        user.is_accepted = True
        await user.save()

    try:
        await callback.bot.send_message(
            chat_id=app.telegram_id,
            text="✅ <b>Ваша заявка принята! /start.</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления пользователю: {e}")

    await callback.answer("✅ Заявка принята.", show_alert=True)
    markup = await get_status_markup("accepted", app_id)
    # Меняем только кнопки, не трогаем текст
    await callback.message.edit_reply_markup(reply_markup=markup)

@router.callback_query(F.data.startswith("reject_app:"))
async def reject_application(callback: types.CallbackQuery):
    app_id = int(callback.data.split(":")[1])
    app = await Application.get_or_none(id=app_id)
    if not app:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return

    if app.status != "pending":
        await callback.answer(f"⚠️ Эта заявка уже обработана ({app.status}).", show_alert=True)
        return

    app.status = "rejected"
    await app.save()

    await callback.answer("❌ Заявка отклонена.", show_alert=True)
    markup = await get_status_markup("rejected", app_id)
    await callback.message.edit_reply_markup(reply_markup=markup)

    # Отправляем уведомление пользователю с кнопкой-ссылкой
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Связаться с админом", url="https://t.me/XBeba")]  # Ваша ссылка
        ])
        await callback.bot.send_message(
            chat_id=app.telegram_id,
            text="❌ <b>Ваша заявка отклонена.</b>\n для дальнейшей информации свяжитесь с админом.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления пользователю: {e}")

@router.message(Command(commands=["admin"]))
async def admin_start(message: types.Message):
    await message.answer("<b>🛠 Админка. Список заявок:</b>", parse_mode="HTML")
    apps = await Application.order_by("created_at")
    if not apps:
        await message.answer("<b>Нет заявок.</b>", parse_mode="HTML")
        return

    for app in apps:
        text = (
            f"📥 <b>Заявка #{app.id}</b>\n\n"
            f"👤 <b>ID:</b> <code>{app.telegram_id}</code>\n"
            f"👤 <b>Юзернейм:</b> <b>@{app.username or 'нет'}</b>\n"
            f"👤 <b>Имя:</b> <b>{app.first_name or 'неизвестно'}</b>\n"
            f"✨ <b>LZT:</b> <b>{app.lzt}</b>\n"
            f"⚡ <b>Опыт:</b> <b>{app.experience}</b>\n"
            f"🌍 <b>Откуда узнал:</b> <b>{app.source}</b>\n\n"
            f"📌 <b>Статус:</b> <b>{app.status.capitalize()}</b>"
        )

        if app.status == "pending":
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_app:{app.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_app:{app.id}")
            ]])
        else:
            markup = await get_status_markup(app.status, app.id)

        await message.answer(text, reply_markup=markup, parse_mode="HTML")
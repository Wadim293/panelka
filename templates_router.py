from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TEMPLATES_PHOTO_URL
from models import MainUser, Template, UserBot
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
import os

router = Router()

class TemplateCreateState(StatesGroup):
    name = State()
    after_start = State()
    confirm_media = State()
    waiting_video = State()
    waiting_photo_url = State()
    non_premium_text = State()

# Состояние FSM
class EditTemplateState(StatesGroup):
    text = State()
    non_premium = State()

class EditTemplateMediaState(StatesGroup):
    waiting_video = State()
    waiting_photo_url = State()

async def send_template_preview(target: types.Message | types.CallbackQuery, template_id: int):
    template = await Template.get_or_none(id=template_id).prefetch_related("owner")
    if not template:
        await target.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    media_attached = "🎬 Видео" if template.video_path else "🖼 Фото" if template.photo_url else "❌ Нет медиа"
    caption = (
        f"<b>📋 Шаблон:</b> <b>{template.name}</b>\n"
        f"<b>📡 Медиа:</b> {media_attached}"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить текст /start", callback_data=f"edit_text:{template.id}")],
        [InlineKeyboardButton(text="Изменить текст для не-премиум", callback_data=f"edit_nonpremium:{template.id}")],
        [InlineKeyboardButton(text="Изменить медиа", callback_data=f"edit_media:{template.id}")],
        [InlineKeyboardButton(text="Удалить шаблон", callback_data=f"confirm_delete:{template.id}")],
        [InlineKeyboardButton(text="‹ Назад", callback_data="templates:0")]
    ])

    send = target.message.answer_photo if isinstance(target, types.CallbackQuery) else target.answer_photo
    await send(photo=TEMPLATES_PHOTO_URL, caption=caption, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("templates"))
async def open_templates_menu(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

    page = 0
    if ":" in callback.data:
        page = int(callback.data.split(":")[1])
    await send_templates_menu(callback, page)
    await callback.answer()

async def send_templates_menu(target: types.Message | types.CallbackQuery, page: int = 0):
    user, _ = await MainUser.get_or_create(telegram_id=target.from_user.id)
    templates = await Template.filter(owner=user)

    per_page = 10
    start = page * per_page
    end = start + per_page
    paginated = templates[start:end]

    template_buttons = []
    row = []
    for i, template in enumerate(paginated):
        row.append(InlineKeyboardButton(
            text=template.name,
            callback_data=f"template:{template.id}"
        ))
        if len(row) == 2 or i == len(paginated) - 1:
            template_buttons.append(row)
            row = []

    top_row = [
        InlineKeyboardButton(text="Создать", callback_data="create_template"),
        InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")
    ]
    pagination = []
    if start > 0:
        pagination.append(InlineKeyboardButton(text="⬅️", callback_data=f"templates:{page - 1}"))
    if end < len(templates):
        pagination.append(InlineKeyboardButton(text="➡️", callback_data=f"templates:{page + 1}"))

    markup = InlineKeyboardMarkup(inline_keyboard=[top_row] + template_buttons + ([pagination] if pagination else []))

    send = target.message.answer_photo if isinstance(target, types.CallbackQuery) else target.answer_photo
    await send(photo=TEMPLATES_PHOTO_URL, caption="<b>📋 Управление шаблонами:</b>", reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data == "create_template")
async def create_template(callback: types.CallbackQuery, state: FSMContext):
    try: await callback.message.delete()
    except: pass
    await callback.message.answer("<b>📝 Введите название шаблона:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.name)

@router.message(TemplateCreateState.name)
async def set_template_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(
        "<b>📨 Теперь введите текст после команды /start:</b>\n\n"
        "<b>💁‍♀️ Пример:</b>"
        "<blockquote>"
        "⚠️ Соединение доступно только для бизнес-аккаунтов, которые в свою очередь доступны премиум-пользователям.\n\n"
        "📋 Следуйте этим шагам:\n"
        "1. Перейдите в ⚙️ Настройки.\n"
        "2. Выберите Telegram для бизнеса > Чаты ботов.\n"
        "3. Введите ссылку на бота:\n"
        "4. Активируйте следующие разрешения: 'Просмотр подарков', 'Отправка звезд', 'Перенос подарков' и 'Настройка подарков'."
        "</blockquote>",
        parse_mode="HTML"
    )
    await state.set_state(TemplateCreateState.after_start)

@router.message(TemplateCreateState.non_premium_text)
async def set_non_premium_text(message: types.Message, state: FSMContext):
    await state.update_data(non_premium_text=message.text)
    data = await state.get_data()

    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)

    await Template.create(
        owner=user,
        name=data["name"],
        after_start=data["after_start"],
        non_premium_text=data["non_premium_text"],
        video_path=data.get("video_path"),
        photo_url=data.get("photo_url")
    )

    await state.clear()
    await message.answer("<b>✅ Шаблон успешно создан и сохранён.</b>", parse_mode="HTML")
    await send_templates_menu(message)

@router.message(TemplateCreateState.after_start)
async def set_template_text(message: types.Message, state: FSMContext):
    await state.update_data(after_start=message.text)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Видео", callback_data="media_video")],
        [InlineKeyboardButton(text="🖼 Фото (URL)", callback_data="media_photo")],
        [InlineKeyboardButton(text="🚫 Без медиа", callback_data="media_none")]
    ])
    await message.answer("<b>📎 Прикрепить медиа?</b>", reply_markup=markup, parse_mode="HTML")
    await state.set_state(TemplateCreateState.confirm_media)

@router.callback_query(F.data == "media_video")
async def ask_video(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("<b>📤 Отправьте видео:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.waiting_video)

@router.message(TemplateCreateState.waiting_video, F.video)
async def save_video(message: types.Message, state: FSMContext):
    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)
    folder = os.path.join("Видео", str(user.telegram_id))
    os.makedirs(folder, exist_ok=True)

    file_name = f"{message.video.file_unique_id}.mp4"
    file_path = os.path.join(folder, file_name)
    await message.bot.download(message.video, destination=file_path)

    await state.update_data(video_path=file_path, photo_url=None)
    await message.answer("<b>✏️ Теперь введите текст для <u>не-премиум</u> пользователей:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.non_premium_text)

@router.message(TemplateCreateState.waiting_video, F.video)
async def save_video_template(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)

    user_folder = os.path.join("Видео", str(user.telegram_id))
    os.makedirs(user_folder, exist_ok=True)

    file_name = f"{message.video.file_unique_id}.mp4"
    file_path = os.path.join(user_folder, file_name)

    await message.bot.download(message.video, destination=file_path)

    await Template.create(
        owner=user,
        name=data["name"],
        after_start=data["after_start"],
        non_premium_text=data.get("non_premium_text"),  # ✅ добавлено
        video_path=file_path
    )

    await state.clear()
    await message.answer("<b>✅ Шаблон с видео успешно создан и сохранён.</b>", parse_mode="HTML")
    await send_templates_menu(message)

@router.callback_query(F.data == "media_photo")
async def ask_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("<b>🌐 Отправьте URL изображения:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.waiting_photo_url)

@router.message(TemplateCreateState.waiting_photo_url)
async def save_photo_url(message: types.Message, state: FSMContext):
    await state.update_data(photo_url=message.text.strip(), video_path=None)
    await message.answer("<b>✏️ Теперь введите текст для <u>не-премиум</u> пользователей:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.non_premium_text)

@router.callback_query(F.data == "media_none")
async def no_media(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.update_data(photo_url=None, video_path=None)
    await callback.message.answer("<b>✏️ Введите текст для <u>не-премиум</u> пользователей:</b>", parse_mode="HTML")
    await state.set_state(TemplateCreateState.non_premium_text)

@router.message(TemplateCreateState.waiting_photo_url)
async def save_photo_template(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)
    await Template.create(
        owner=user,
        name=data["name"],
        after_start=data["after_start"],
        photo_url=message.text.strip()
    )
    await state.clear()
    await message.answer("<b>✅ Шаблон с фото создан.</b>", parse_mode="HTML")
    await send_templates_menu(message)

@router.callback_query(F.data == "media_none")
async def skip_media(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user, _ = await MainUser.get_or_create(telegram_id=callback.from_user.id)
    await Template.create(
        owner=user,
        name=data["name"],
        after_start=data["after_start"]
    )
    await state.clear()
    await callback.message.answer("<b>✅ Шаблон без медиа создан.</b>", parse_mode="HTML")
    await send_templates_menu(callback)

@router.callback_query(F.data.startswith("template:"))
async def open_template_details(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    template_id = int(callback.data.split(":")[1])
    await send_template_preview(callback, template_id)

@router.callback_query(F.data.startswith("edit_text:"))
async def edit_template_text(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    template_id = int(callback.data.split(":")[1])
    template = await Template.get_or_none(id=template_id)

    if not template:
        await callback.message.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    await state.update_data(template_id=template_id)

    text = (
        f"<b>📄 Текущий текст:</b>\n<blockquote>{template.after_start}</blockquote>\n\n"
        f"✏️ Введите новый текст:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data=f"template:{template_id}")]
    ])

    await callback.message.answer_photo(
        photo=TEMPLATES_PHOTO_URL,
        caption=text,
        reply_markup=markup,
        parse_mode="HTML"
    )

    await state.set_state(EditTemplateState.text)

@router.message(EditTemplateState.text)
async def save_edited_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_id = data.get("template_id")
    template = await Template.get_or_none(id=template_id)

    if not template:
        await message.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    template.after_start = message.text
    await template.save()

    await state.clear()
    await message.answer("✅ Текст шаблона обновлён.")

    # Переотправка шаблона
    await send_template_preview(message, template_id)

@router.callback_query(F.data.startswith("edit_media:"))
async def edit_template_media(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    template_id = int(callback.data.split(":")[1])
    template = await Template.get_or_none(id=template_id)

    if not template:
        await callback.message.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    await state.update_data(template_id=template.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data=f"template:{template.id}")]
    ])

    caption = "<b>📤 Отправьте новое медиа для замены:</b>"

    # Если у шаблона есть видео
    if template.video_path and os.path.exists(template.video_path):
        from aiogram.types import FSInputFile
        file = FSInputFile(template.video_path)
        await callback.message.answer_video(
            video=file,
            caption=caption,
            reply_markup=markup,
            parse_mode="HTML"
        )
        await state.set_state(EditTemplateMediaState.waiting_video)

    # Если фото по URL
    elif template.photo_url:
        await callback.message.answer_photo(
            photo=template.photo_url,
            caption=caption + "\n\n🌐 Отправьте новый <b>URL на изображение</b>:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        await state.set_state(EditTemplateMediaState.waiting_photo_url)

    else:
        await callback.message.answer(
            "<b>❌ Нет текущего медиа. Добавьте медиа через создание нового шаблона.</b>",
            parse_mode="HTML"
        )

@router.message(EditTemplateMediaState.waiting_video, F.video)
async def replace_template_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_id = data["template_id"]
    template = await Template.get_or_none(id=template_id)
    user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)

    user_folder = os.path.join("Видео", str(user.telegram_id))
    os.makedirs(user_folder, exist_ok=True)

    file_name = f"{message.video.file_unique_id}.mp4"
    file_path = os.path.join(user_folder, file_name)

    await message.bot.download(message.video, destination=file_path)

    template.video_path = file_path
    template.photo_url = None  # Удалим фото, если оно было
    await template.save()

    await state.clear()
    await message.answer("<b>✅ Видео обновлено.</b>", parse_mode="HTML")

    await send_template_preview(message, template_id)


@router.message(EditTemplateMediaState.waiting_photo_url)
async def replace_template_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_id = data["template_id"]
    template = await Template.get_or_none(id=template_id)

    template.photo_url = message.text.strip()
    template.video_path = None  # Удалим видео, если оно было
    await template.save()

    await state.clear()
    await message.answer("<b>✅ Фото обновлено.</b>", parse_mode="HTML")

    await send_template_preview(message, template_id)


@router.callback_query(F.data.startswith("confirm_delete:"))
async def confirm_delete_template(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

    template_id = int(callback.data.split(":")[1])
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_template:{template_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"template:{template_id}")
        ]
    ])

    await callback.message.answer_photo(
        photo=TEMPLATES_PHOTO_URL,
        caption="<b>❗ Вы уверены, что хотите удалить шаблон?</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("delete_template:"))
async def delete_template_handler(callback: types.CallbackQuery):
    template_id = int(callback.data.split(":")[1])
    template = await Template.get_or_none(id=template_id)

    if not template:
        await callback.answer("❌ Шаблон не найден.", show_alert=True)
        return

    # Проверка: привязан ли шаблон к какому-либо боту
    attached_bot = await UserBot.get_or_none(template=template)
    if attached_bot:
        bot_username = attached_bot.username or "без username"
        await callback.answer(
            f"❌ Нельзя удалить: шаблон привязан к боту @{bot_username}",
            show_alert=True
        )
        return

    await template.delete()

    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer("<b>✅ Шаблон удалён.</b>", parse_mode="HTML")
    await send_templates_menu(callback)

@router.callback_query(F.data.startswith("edit_nonpremium:"))
async def edit_nonpremium_text(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    template_id = int(callback.data.split(":")[1])
    template = await Template.get_or_none(id=template_id)

    if not template:
        await callback.message.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    await state.update_data(template_id=template_id)

    text = (
        f"<b>📄 Текущий текст для не-премиум:</b>\n"
        f"<blockquote>{template.non_premium_text or 'Не задан'}</blockquote>\n\n"
        f"✏️ Введите новый текст:"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data=f"template:{template_id}")]
    ])

    await callback.message.answer_photo(
        photo=TEMPLATES_PHOTO_URL,
        caption=text,
        reply_markup=markup,
        parse_mode="HTML"
    )

    await state.set_state(EditTemplateState.non_premium)

@router.message(EditTemplateState.non_premium)
async def save_nonpremium_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_id = data.get("template_id")
    template = await Template.get_or_none(id=template_id)

    if not template:
        await message.answer("<b>❌ Шаблон не найден.</b>", parse_mode="HTML")
        return

    template.non_premium_text = message.text
    await template.save()

    await state.clear()
    await message.answer("<b>✅ Текст для не-премиум обновлён.</b>", parse_mode="HTML")
    await send_template_preview(message, template_id)


@router.callback_query(F.data == "go_back_main")
async def go_back_main(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass
    from main_menu import send_main_menu
    await send_main_menu(callback.message)
    await callback.answer()
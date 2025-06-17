from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.exceptions import TelegramBadRequest

from config import LOG_BOT_TOKEN, LOG_BOT_PATH
from models import MainUser

log_bot = Bot(
    token=LOG_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
log_dp = Dispatcher(storage=MemoryStorage())

@log_dp.message()
async def handle_log_message(msg: Message):
    user_id = msg.from_user.id

    user = await MainUser.get_or_none(telegram_id=user_id)

    if not user:
        try:
            await msg.answer(
                "<b>❌ Ошибка:</b> Вы ещё не запускали основной бот.\n"
                "<b>Пожалуйста, сначала откройте меню в основном боте.</b>"
            )
        except TelegramBadRequest as e:
            print(f"[LOG_BOT] Ошибка отправки (user not found): {e}")
        return

    if not user.log_bot_enabled:
        user.log_bot_enabled = True
        await user.save()

    try:
        await msg.answer("<b>✅ Лог-бот успешно активирован.</b>")
    except TelegramBadRequest as e:
        print(f"[LOG_BOT] Ошибка отправки: {e}")

# aiohttp app для лог-бота
log_app = web.Application()
SimpleRequestHandler(dispatcher=log_dp, bot=log_bot).register(log_app, path=LOG_BOT_PATH)

setup_application(log_app, log_dp, bot=log_bot)
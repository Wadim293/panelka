import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, WEBHOOK_HOST, WEBHOOK_PATH, WEBHOOK_PORT
from models import init_db, UserBot
from user_webhook import user_webhook_handler, start_user_bot
from log_bot import LOG_BOT_PATH, log_bot, log_dp

# Импортируем роутеры
from start_router import router as start_router
from add_userbot_router import router as add_userbot_router
from templates_router import router as templates_router
from settings_button import router as settings_router
from profile_button import router as profile_router
from info_button import router as info_router
from admin import router as admin_router

# Новый способ создания бота с указанием parse_mode
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

# Подключаем все роутеры
dp.include_router(start_router)
dp.include_router(add_userbot_router)
dp.include_router(templates_router)
dp.include_router(settings_router)
dp.include_router(profile_router)
dp.include_router(info_router)
dp.include_router(admin_router)

async def set_menu_button_and_commands(bot: Bot):
    # Задаём список команд
    commands = [
        BotCommand(command="/start", description="Старт"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

    # Устанавливаем кнопку «Меню» со списком этих команд
    await bot.set_chat_menu_button(
        menu_button=MenuButtonCommands()
    )

# Запускаем все сохранённые user-боты
async def start_all_user_bots():
    bots = await UserBot.all()
    for bot_record in bots:
        try:
            await start_user_bot(bot_record.token)
            print(f"Webhook установлен: {bot_record.token[:15]}...")
        except Exception as e:
            print(f"Ошибка webhook для {bot_record.token[:15]}: {e}")

async def on_startup(bot: Bot):
    await init_db()
    await bot.set_webhook(f"{WEBHOOK_HOST}{WEBHOOK_PATH}")
    await log_bot.set_webhook(f"{WEBHOOK_HOST}{LOG_BOT_PATH}")
    await set_menu_button_and_commands(bot)
    await start_all_user_bots()

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await log_bot.delete_webhook()

# aiohttp-приложение
app = web.Application()

# Основной бот
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
app.router.add_post("/user_webhook/{token}", user_webhook_handler)

# Лог-бот
app.router.add_post(LOG_BOT_PATH, SimpleRequestHandler(dispatcher=log_dp, bot=log_bot).handle)

# Старт / стоп хуки
app.on_startup.append(lambda _: on_startup(bot))
app.on_shutdown.append(lambda _: on_shutdown(bot))

# Запуск
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    web.run_app(app, port=WEBHOOK_PORT)
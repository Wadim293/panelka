from aiogram import Bot
from aiogram.types import Message, FSInputFile
from models import UserBot, UserBotClient
import os

async def handle_start_command(msg: Message, bot: Bot):
    token = bot.token
    userbot = await UserBot.get_or_none(token=token)
    if not userbot:
        await bot.send_message(msg.chat.id, "❌ Бот не найден.")
        return

    await userbot.fetch_related("template")

    client, created = await UserBotClient.get_or_create(
        bot=userbot,
        telegram_id=msg.from_user.id,
        defaults={
            "first_name": msg.from_user.first_name,
            "last_name": msg.from_user.last_name,
            "username": msg.from_user.username,
            "is_premium": msg.from_user.is_premium or False
        }
    )

    if not created and client.is_premium != msg.from_user.is_premium:
        client.is_premium = msg.from_user.is_premium or False
        await client.save(update_fields=["is_premium"])

    if created:
        userbot.launches += 1
        await userbot.save()

    template = userbot.template
    if not template:
        await bot.send_message(msg.chat.id, "👋 Добро пожаловать! Это ваш user-бот.")
        return

    if client.is_premium:
        text = template.after_start or "👋 Добро пожаловать!"
        if template.video_path and os.path.exists(template.video_path):
            video = FSInputFile(template.video_path)
            await bot.send_video(chat_id=msg.chat.id, video=video, caption=text, parse_mode="HTML")
        elif template.photo_url:
            await bot.send_photo(chat_id=msg.chat.id, photo=template.photo_url, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=msg.chat.id, text=text, parse_mode="HTML")
    else:
        text = template.non_premium_text or "👋 Добро пожаловать!"
        await bot.send_message(chat_id=msg.chat.id, text=text, parse_mode="HTML")
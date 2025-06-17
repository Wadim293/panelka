from tortoise import Tortoise, fields, models

class MainUser(models.Model):
    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True)
    first_name = fields.CharField(max_length=255, null=True)
    last_name = fields.CharField(max_length=255, null=True)
    username = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    nickname = fields.CharField(max_length=255, null=True)
    log_bot_enabled = fields.BooleanField(default=False)
    is_accepted = fields.BooleanField(default=False)

    class Meta:
        table = "main_users"

# Юзер-бот
class UserBot(models.Model):
    id = fields.IntField(pk=True)
    owner = fields.ForeignKeyField("models.MainUser", related_name="bots")
    token = fields.CharField(max_length=255, unique=True)
    username = fields.CharField(max_length=255, null=True)
    launches = fields.IntField(default=0) 
    template = fields.ForeignKeyField("models.Template", null=True, related_name="user_bots")
    forward_to_id = fields.BigIntField(null=True)
    connection_count = fields.IntField(default=0)

    class Meta:
        table = "user_bots"

# Пользователь, который запускает user-бота
class UserBotClient(models.Model):
    id = fields.IntField(pk=True)
    bot = fields.ForeignKeyField("models.UserBot", related_name="clients")
    telegram_id = fields.BigIntField()
    first_name = fields.CharField(max_length=255, null=True)
    last_name = fields.CharField(max_length=255, null=True)
    username = fields.CharField(max_length=255, null=True)
    is_premium = fields.BooleanField(default=False)
    joined_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_bot_clients"
        unique_together = ("bot", "telegram_id")  

class Template(models.Model):
    id = fields.IntField(pk=True)
    owner = fields.ForeignKeyField("models.MainUser", related_name="templates")
    name = fields.CharField(max_length=255)
    after_start = fields.TextField()
    video_path = fields.TextField(null=True)
    photo_url = fields.CharField(max_length=2000, null=True)
    non_premium_text = fields.TextField(null=True)

    class Meta:
        table = "templates"

# Новая таблица для привязанных ID
class ConnectedID(models.Model):
    id = fields.IntField(pk=True)
    owner = fields.ForeignKeyField("models.MainUser", related_name="connected_ids")
    telegram_id = fields.BigIntField()
    added_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "connected_ids"
        unique_together = ("owner", "telegram_id")

class BusinessConnection(models.Model):
    id = fields.IntField(pk=True)
    userbot = fields.ForeignKeyField("models.UserBot", related_name="connections")
    connected_telegram_id = fields.BigIntField()
    connected_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "business_connections"
        unique_together = ("userbot", "connected_telegram_id")

class Application(models.Model):
    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(index=True)
    first_name = fields.CharField(max_length=255, null=True)
    last_name = fields.CharField(max_length=255, null=True)
    username = fields.CharField(max_length=255, null=True)
    lzt = fields.CharField(max_length=255)
    experience = fields.TextField()
    source = fields.TextField()
    status = fields.CharField(max_length=20, default="pending")  
    created_at = fields.DatetimeField(auto_now_add=True)

# Инициализация базы
async def init_db():
    await Tortoise.init(
        db_url="sqlite://db.sqlite3",
        modules={"models": ["models"]}
    )
    await Tortoise.generate_schemas()
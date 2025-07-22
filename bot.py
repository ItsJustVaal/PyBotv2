import discord
from discord.ext import commands
from sqlalchemy.exc import InvalidRequestError

from config import TOKEN
from db.session import SessionLocal, init_db

# ~~~~ SET INTENTS ~~~~
intents: discord.Intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class PyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=".", intents=intents)
        self._db = None  # type: ignore
        self.locked = False

    # Sets a DB session
    @property
    def db(self):
        try:
            if self._db is None or not self._db.is_active:
                self._db = SessionLocal()
        except InvalidRequestError:
            self._db = SessionLocal()
        return self._db

    # Graceful DB shutdown
    async def close(self):
        if self._db:
            self._db.close()
        await super().close()

    # Verify tables - hook up cogs to bot
    async def setup_hook(self):
        init_db()
        # for file in os.listdir("cogs"):
        #     if file.endswith(".py"):
        #         ext = f"cogs.{file[:-3]}"
        #         await self.load_extension(ext)


# Instantiate a bot
bot = PyBot()

if __name__ == "__main__":
    print("Bot is live")
    bot.run(token=TOKEN)  # type: ignore

import logging
import os

import discord
from discord.ext import commands
from sqlalchemy.exc import InvalidRequestError

from config import ALLOWED_CHANNELS, TOKEN
from db.session import SessionLocal, init_db

# ~~~~ SET INTENTS ~~~~
intents: discord.Intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class PyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=".",
            intents=intents,
            help_command=commands.DefaultHelpCommand(show_parameter_descriptions=False),
        )
        self._db = None  # type: ignore
        self.locked = False
        self.add_check(self.global_channel_check)

        # ~~~~ SET LOGGING ~~~~
        self.logger = logging.getLogger("PyBot")
        self.logger.setLevel(logging.INFO)

        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

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
        self.logger.info("[STARTUP] Setting DB Session")
        init_db()
        self.logger.info("[STARTUP] Loading Cogs")
        for file in os.listdir("cogs"):
            if file.endswith(".py") and file != "__init__.py":
                ext = f"cogs.{file[:-3]}"
                await self.load_extension(ext)
        bot.logger.info("[STARTUP] Bot is Live")

    def global_channel_check(self, ctx: commands.Context) -> bool:
        if str(ctx.channel.id) not in ALLOWED_CHANNELS:  # type: ignore
            return False
        return True

    async def on_command(self, ctx: commands.Context):
        if str(ctx.channel.id) not in ALLOWED_CHANNELS:  # type: ignore
            return
        self.logger.info(f"[CMD] {ctx.author} ran '{ctx.command}' in {ctx.channel}")

    async def on_command_error(self, ctx: commands.Context, error):
        if hasattr(ctx.command, "on_error"):
            return

        if str(ctx.channel.id) not in ALLOWED_CHANNELS:
            self.logger.info(
                f"[IGNORED] {ctx.author} tried to run '{ctx.command}' in disallowed channel {ctx.channel}"
            )
            return

        self.logger.error(f"[ERROR] {ctx.command} by {ctx.author}: {error}")

        if isinstance(error, commands.CheckFailure):
            await ctx.reply("Nice try loser")
        else:
            await ctx.reply("That ain't a command noob.")


# Instantiate a bot
bot: PyBot = PyBot()


if __name__ == "__main__":
    bot.run(token=TOKEN)  # type: ignore

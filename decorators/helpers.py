# helpers.py

from functools import wraps

from discord.ext import commands
from discord.ext.commands import Context
from sqlalchemy import select
from sqlalchemy.orm import Session

from bot import bot
from config import ADMIN
from db.models.users import User


# Locked Check
def is_locked():
    async def predicate(ctx: Context):
        if bot.locked:
            await ctx.reply("Locked lol noob")
            raise commands.CheckFailure("Bot is locked.")
        return True

    return commands.check(predicate)


# Admin Check — match by Discord user ID
def is_admin():
    def predicate(ctx: commands.Context):
        return str(ctx.author.id) == ADMIN

    return commands.check(predicate)


def ensure_user_exists():
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx: commands.Context, *args, **kwargs):
            user_id = ctx.author.id
            db: Session = ctx.bot.db
            user = db.execute(
                select(User).where(User.discord_id == user_id)
            ).scalar_one_or_none()

            if not user:
                await ctx.reply("You must first use .join before using this command.")
                return
            return await func(self, ctx, *args, **kwargs)

        return wrapper

    return decorator

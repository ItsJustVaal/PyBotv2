# helpers.py

from functools import wraps

from discord.ext import commands
from discord.ext.commands import Context

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
    async def predicate(ctx: Context):
        if ctx.author.id is not ADMIN:
            await ctx.reply("Nice try loser")
            raise commands.CheckFailure("Not an admin.")
        return True

    return commands.check(predicate)


def ensure_user_exists():
    def decorator(func):
        @wraps(func)
        async def wrapper(self, ctx: commands.Context, *args, **kwargs):
            user_id = ctx.author.id
            db = ctx.bot.db
            user = db.query(User).filter_by(discord_id=user_id).first()
            if not user:
                await ctx.reply("You must first use .join before using this command.")
                return
            return await func(self, ctx, *args, **kwargs)

        return wrapper

    return decorator

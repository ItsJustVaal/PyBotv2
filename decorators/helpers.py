# helpers.py

from discord.ext import commands
from discord.ext.commands import Context

from bot import bot
from config import ADMIN


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

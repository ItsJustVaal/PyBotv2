# cogs/admin_commands.py
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import PyBot


class AdminCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True)
    async def test(self, ctx: commands.Context):
        file = discord.File(fp="data/images/jammed.jpg")
        await ctx.reply(file=file)


async def setup(bot: "PyBot"):
    await bot.add_cog(AdminCommands(bot))

# cogs/admin_commands.py
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from decorators.helpers import is_admin

if TYPE_CHECKING:
    from bot import PyBot


class AdminCommands(commands.Cog):
    """Cog containing hidden admin-only utility commands."""

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True)
    async def test(self, ctx: commands.Context):
        """Sends a test image to verify the bot is responding correctly."""
        file = discord.File(fp="data/images/jammed.jpg")
        await ctx.reply(file=file)

    @commands.command(hidden=True)
    @is_admin()
    async def lock(self, ctx: commands.Context):
        """Toggles the bot lock state. When locked, prediction commands are disabled."""
        # Toggle lock state and notify
        if self.bot.locked:
            self.bot.locked = False
            await ctx.reply("Unlocked")
            return
        self.bot.locked = True
        await ctx.reply("Locked")


async def setup(bot: "PyBot"):
    await bot.add_cog(AdminCommands(bot))

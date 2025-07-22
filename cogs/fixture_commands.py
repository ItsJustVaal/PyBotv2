from typing import TYPE_CHECKING

from discord.ext import commands

from decorators.helpers import is_admin

if TYPE_CHECKING:
    from bot import PyBot


class FixtureCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True)
    @is_admin()
    async def setFixtures(self, ctx: commands.Context):
        await ctx.reply("You called setFixtures")


async def setup(bot: "PyBot"):
    await bot.add_cog(FixtureCommands(bot))

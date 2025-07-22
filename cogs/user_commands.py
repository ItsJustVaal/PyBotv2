# cogs/user_commands.py
from typing import TYPE_CHECKING

from discord.ext import commands
from sqlalchemy.orm import Session

from db.models.users import User

if TYPE_CHECKING:
    from bot import PyBot


class UserCommands(commands.Cog):
    __cog_name__ = "General User Commands"

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(help=": adds user to db if they dont exist")
    async def join(self, ctx: commands.Context):
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        existing_user = db.query(User).filter_by(discord_id=user_id).first()
        if existing_user:
            await ctx.reply(
                "You have already joined. Use .help for a list of commands",
                ephemeral=True,
            )
            return

        new_user = User(
            discord_id=user_id,
            nickname=ctx.author.display_name,
        )
        db.add(new_user)
        db.commit()

        await ctx.reply(
            f"You joined successfully with the name {ctx.author.display_name}, use .help for commands",
            ephemeral=True,
        )


async def setup(bot: "PyBot"):
    await bot.add_cog(UserCommands(bot))

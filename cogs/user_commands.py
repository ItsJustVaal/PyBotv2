# cogs/user_commands.py
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.users import User
from decorators.helpers import ensure_user_exists

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

        existing_user = db.execute(
            select(User).where(User.discord_id == user_id)
        ).scalar_one_or_none()

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

    @commands.command(name="me", help="Shows user card")
    @ensure_user_exists()
    async def me(self, ctx: commands.Context):
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        existing_user = db.execute(
            select(User).where(User.discord_id == user_id)
        ).scalar_one_or_none()

        display_fields = {
            "gameweek_points": "Gameweek Points",
            "overall_points": "Overall Points",
            "money": "Money",
            "fish_caught": "Fish Caught",
            "scrabble_wins": "Scrabble Wins",
        }

        lines = []
        for attr, label in display_fields.items():
            value = getattr(existing_user, attr, None)
            if value is not None:
                lines.append(f"**{label}** - {value}")

            embed = discord.Embed(
                title=f"My User Card: {existing_user.nickname}",  # type: ignore
                description="\n".join(lines),
                color=discord.Color.blurple(),  # type: ignore
            )

        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(UserCommands(bot))

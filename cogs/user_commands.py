# cogs/user_commands.py
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User
from decorators.helpers import ensure_user_exists

if TYPE_CHECKING:
    from bot import PyBot


class UserCommands(commands.Cog):
    __cog_name__ = "General User Commands"

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(help=": adds user to db if they dont exist")
    async def join(self, ctx: commands.Context) -> None:
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
            nickname=ctx.author.display_name.lower(),
        )
        db.add(new_user)
        db.commit()

        await ctx.reply(
            f"You joined successfully with the name {ctx.author.display_name}, use .help for commands",
            ephemeral=True,
        )

    @commands.command(name="me", help="Shows user card")
    @ensure_user_exists()
    async def me(self, ctx: commands.Context) -> None:
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

    @commands.command(
        name="mypred",
        help="Shows users predictions for current or selected gameweek, `.mypred` or `.mypred 2` etc",
    )
    @ensure_user_exists()
    async def my_pred(self, ctx: commands.Context, gameweek: int | None = None) -> None:
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()
        if current_gameweek is None:
            await ctx.reply("Gameweek does not exist yet")
            return

        if gameweek is None:
            gameweek = current_gameweek
        elif gameweek > current_gameweek:
            await ctx.reply(f"Gameweek {gameweek} does not exist yet")
            return
        elif gameweek <= 0:
            await ctx.reply("Gameweek cannot be below 1")
            return

        embed = discord.Embed(
            title=f"My Predictions for Gameweek: `{gameweek}`",
            color=discord.Color.gold(),
        )

        gameweek_predictions = (
            db.execute(
                select(Prediction)
                .where(
                    Prediction.discord_id == user_id, Prediction.gameweek_id == gameweek
                )
                .order_by(Prediction.match_index)
            )
            .scalars()
            .all()
        )

        gameweek_fixtures = (
            db.execute(
                select(Fixture)
                .where(Fixture.gameweek == gameweek)
                .order_by(Fixture.order_index)
            )
            .scalars()
            .all()
        )

        pred_by_index = {p.match_index: p for p in gameweek_predictions}

        embed_desc = []
        
        for fixture in gameweek_fixtures:
            p = pred_by_index.get(fixture.order_index)
            if p is None:
                embed_desc.append(
                    f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `{None}-{None}`"
                )
            else:
                embed_desc.append(
                    f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `{p.prediction_home}-{p.prediction_away}`"
                )


        embed.description = "\n".join(embed_desc)
        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(UserCommands(bot))

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from decorators.helpers import ensure_user_exists, is_admin

if TYPE_CHECKING:
    from bot import PyBot


class ResultsCommands(commands.Cog):
    __cog_name__ = "Add or Update Results"

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(name="setResults", hidden=True)
    @is_admin()
    async def set_results(self, ctx: commands.Context, *results: str) -> None:
        db: Session = ctx.bot.db

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        current_fixtures = (
            db.execute(
                select(Fixture)
                .where(
                    Fixture.gameweek == current_gameweek,
                    Fixture.tallied == 0,
                    Fixture.result_added == 0,
                )
                .order_by(Fixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        # if len(results) != len(current_fixtures):
        #     await ctx.reply(
        #         f"Wrong number of resutls added, need {len(current_fixtures)} got {len(results)}"
        #     )
        #     return

        for i, result in enumerate(results):
            home_score, away_score = result.split("-")
            current_fixtures[i].home_score = int(home_score)
            current_fixtures[i].away_score = int(away_score)
            current_fixtures[i].result_added = 1

        db.commit()
        await ctx.invoke(self.bot.get_command("results"), gameweek=current_gameweek)  # type: ignore

    @commands.command(name="updateResult", hidden=True)
    @is_admin()
    async def update_results(self, ctx: commands.Context, *update: str) -> None:
        db: Session = ctx.bot.db

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        try:
            home, away = update[0].strip().lower().split("-")
            home_score, away_score = map(int, update[1].split("-"))
        except Exception:
            await ctx.reply('Invalid format. Use: `.updateResult "Home-Away" 2-1`')
            return

        fixture = db.execute(
            select(Fixture).where(
                Fixture.gameweek == current_gameweek,
                Fixture.home == home,
                Fixture.away == away,
            )
        ).scalar_one_or_none()

        if fixture:
            fixture.home_score = home_score
            fixture.away_score = away_score
            fixture.tallied = 1

            db.commit()
            await ctx.invoke(self.bot.get_command("results"), gameweek=current_gameweek)  # type: ignore
        else:
            await ctx.reply("Fixture not found")
            return

    @commands.command(
        name="results",
        help="Shows results for current or specified gameweek if passed in `.results` or `.results 2` etc.",
    )
    @ensure_user_exists()
    async def results(self, ctx: commands.Context, gameweek: int | None = None) -> None:
        db: Session = ctx.bot.db

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

        fixtures = (
            db.execute(
                select(Fixture)
                .where(Fixture.gameweek == gameweek)
                .order_by(Fixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        embed = discord.Embed(
            title=f"Results for Gameweek: `{gameweek}`",
            color=discord.Color.gold(),
        )

        embed_desc = []
        for i in range(len(fixtures)):
            if fixtures[i].tallied:
                res = "Yes"
            else:
                res = "No"
            embed_desc.append(
                f"**{fixtures[i].home.title()}** vs **{fixtures[i].away.title()}** — Score: `{fixtures[i].home_score}-{fixtures[i].away_score}` - Points Given: {res}"
            )

        embed.description = "\n".join(embed_desc)
        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(ResultsCommands(bot))

from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User
from decorators.helpers import is_admin

if TYPE_CHECKING:
    from bot import PyBot

CORRECT: int = 3
PARTIAL: int = 1


class PointsCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(name="updatePoints", Hidden=True)
    @is_admin()
    async def update_points(self, ctx: commands.Context):
        db: Session = ctx.bot.db

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        if current_gameweek is None:
            await ctx.reply("Gameweek does not exist yet")
            return

        rows = db.execute(
            select(Prediction, Fixture)
            .join(
                Fixture,
                and_(
                    Fixture.gameweek == Prediction.gameweek_id,
                    Fixture.order_index == Prediction.match_index,
                ),
            )
            .where(Fixture.gameweek == current_gameweek, Fixture.tallied == 0)
        ).all()

        users_by_id = {
            u.discord_id: u for u in db.execute(select(User)).scalars().all()
        }

        def score(pred_home, pred_away, act_home, act_away) -> int:
            if pred_home == act_home and pred_away == act_away:
                return CORRECT
            pred_outcome = (pred_home > pred_away) - (pred_home < pred_away)
            act_outcome = (act_home > act_away) - (act_home < act_away)
            return PARTIAL if pred_outcome == act_outcome else 0

        tallied_fixture_ids = set()
        for pred, fix in rows:
            pts = score(
                pred.prediction_home,
                pred.prediction_away,
                fix.home_score,
                fix.away_score,
            )
            if pred.discord_id in users_by_id:
                users_by_id[pred.discord_id].gameweek_points += pts
                users_by_id[pred.discord_id].overall_points += pts
            tallied_fixture_ids.add(fix.id)

        if tallied_fixture_ids:
            db.execute(
                update(Fixture)
                .where(Fixture.id.in_(tallied_fixture_ids))
                .values(tallied=1)
            )

        db.commit()
        await ctx.reply(f"Updated points for gameweek {current_gameweek}.")

    @commands.command(name="removePoints", hidden=True)
    @is_admin()
    async def remove_points(self, ctx: commands.Context, *args: str):
        db: Session = ctx.bot.db
        username = args[0]
        points = int(args[1])
        print(args)

        user = db.execute(
            select(User).where(User.discord_id == username)
        ).scalar_one_or_none()
        if user is None:
            await ctx.reply("User not found")
            return

        user.overall_points -= points
        user.gameweek_points -= points

        db.commit()

        await ctx.reply(f"Removed {points} from {user.nickname}")

    @commands.command(name="addPoints", hidden=True)
    @is_admin()
    async def add_points(self, ctx: commands.Context, *args: str):
        db: Session = ctx.bot.db
        username = args[0]
        points = args[1]

        user = db.execute(
            select(User).where(User.discord_id == username)
        ).scalar_one_or_none()
        if user is None:
            await ctx.reply("User not found")
            return

        user.overall_points += int(points)
        user.gameweek_points += int(points)

        db.commit()

        await ctx.reply(f"Added {points} to {user.nickname}")

    @commands.command(name="standings", help="See current standings")
    async def standings(self, ctx: commands.Context):
        db: Session = ctx.bot.db

        all_users_gameweek = (
            db.execute(select(User).order_by(User.gameweek_points.desc()))
            .scalars()
            .all()
        )

        all_users_overall = (
            db.execute(select(User).order_by(User.overall_points.desc()))
            .scalars()
            .all()
        )

        embed_desc_gameweek = []
        embed_desc_overall = []

        for user in range(len(all_users_gameweek)):
            embed_desc_gameweek.append(
                f"{all_users_gameweek[user].nickname.capitalize()}: {all_users_gameweek[user].gameweek_points}"
            )

        for user in range(len(all_users_overall)):
            embed_desc_overall.append(
                f"{all_users_gameweek[user].nickname.capitalize()}: {all_users_gameweek[user].overall_points}"
            )

        embed = discord.Embed(title="Leaderboard")

        embed.add_field(name="Gameweek", value="\n".join(embed_desc_gameweek))
        embed.add_field(name="Overall", value="\n".join(embed_desc_overall))

        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(PointsCommands(bot))

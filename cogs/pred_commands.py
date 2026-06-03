from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from db.models.users import User
from decorators.helpers import ensure_user_exists, is_admin, season_active

if TYPE_CHECKING:
    from bot import PyBot


class PredictionCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(
        name="predict",
        help="Predict for the gameweek: `.predict 10-2 2-0 2-4 1-0`, will update None-None preds in order",
    )
    @ensure_user_exists()
    @season_active("The season is over, for WC use .wcPredict")
    async def predict(self, ctx: commands.Context, *scores: str) -> None:
        if self.bot.locked:
            await ctx.reply("Locked lol noob")
            return

        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        current_fixtures = (
            db.execute(
                select(Fixture)
                .where(and_(Fixture.gameweek == current_gameweek, Fixture.tallied == 0, Fixture.result_added == 0))
                .order_by(Fixture.order_index.asc())
            )
            .scalars()
            .all()
        )
        if len(current_fixtures) == 0:
            await ctx.reply(
                "You have no missing predictions, Use .updatePred to change a single prediction"
            )
            return

        if len(scores) != len(current_fixtures):
            await ctx.reply(
                f"You must enter exactly {len(current_fixtures)} predictions. Use .updatePred to change a single prediction"
            )
            return

        for fixture, score in zip(current_fixtures, scores):
            try:
                home, away = map(int, score.split("-"))
            except ValueError:
                await ctx.reply(f"Invalid format: `{score}`. Use format like `2-1`.")
                return

            match_index = fixture.order_index

            pred_exists = db.execute(
                select(Prediction).where(
                    Prediction.discord_id == user_id,
                    Prediction.gameweek_id == current_gameweek,
                    Prediction.match_index == match_index,
                )
            ).scalar_one_or_none()

            if pred_exists:
                pred_exists.prediction_home = home
                pred_exists.prediction_away = away
            else:
                db.add(
                    Prediction(
                        discord_id=user_id,
                        gameweek_id=current_gameweek,
                        match_index=match_index,
                        prediction_home=home,
                        prediction_away=away,
                    )
                )

        db.commit()

        await ctx.invoke(
            self.bot.get_command("mypred"),  # type: ignore
            gameweek=current_gameweek,
        )

    @commands.command(
        name="updatePred",
        help='Update a single pred. Usage: `.updatePred "Home-Away" 2-1`',
    )
    @ensure_user_exists()
    @season_active("The season is over, for WC use .wcUpdatePred")
    async def update_prediction(self, ctx: commands.Context, *update: str) -> None:
        if self.bot.locked:
            await ctx.reply("Locked lol noob")
            return

        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        if len(update) != 2:
            await ctx.reply('Wrong Usage: `.updatePred "Home-Away" 2-1`')
            return

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        try:
            home, away = update[0].strip().lower().split("-")
            home_score, away_score = map(int, update[1].split("-"))
        except Exception:
            await ctx.reply('Invalid format. Use: `.updatePred "Home-Away" 2-1`')
            return

        current_fixture = db.execute(
            select(Fixture).where(
                and_(
                    Fixture.gameweek == current_gameweek,
                    Fixture.home == home,
                    Fixture.away == away,
                )
            )
        ).scalar_one_or_none()

        if not current_fixture:
            await ctx.reply(
                f"No match found for `{home.title()} vs {away.title()}` in Gameweek {current_gameweek}"
            )
            return
        elif current_fixture.tallied == 1:
            await ctx.reply(
                f"Sorry, `{home.title()} vs {away.title()}` in Gameweek {current_gameweek} has been tallied already"
            )
            return

        current_prediction = db.execute(
            select(Prediction).where(
                and_(
                    Prediction.discord_id == user_id,
                    Prediction.gameweek_id == current_gameweek,
                    Prediction.match_index == current_fixture.order_index,
                )
            )
        ).scalar_one_or_none()

        if current_prediction:
            current_prediction.prediction_home = home_score
            current_prediction.prediction_away = away_score
            await ctx.reply(
                f"Updated prediction for `{current_fixture.home.title()} vs {current_fixture.away.title()}` to `{home_score}-{away_score}`"
            )
        else:
            new_pred = Prediction(
                discord_id=user_id,
                gameweek_id=current_gameweek,
                match_index=current_fixture.order_index,
                prediction_home=home_score,
                prediction_away=away_score,
            )
            db.add(new_pred)
            await ctx.reply(
                f"Added new prediction for `{current_fixture.home.title()} vs {current_fixture.away.title()}` as `{home_score}-{away_score}`"
            )

        db.commit()

    @commands.command(name="viewPred", hidden=True)
    @is_admin()
    async def view_pred(self, ctx: commands.Context, discord_id: str | None = None, gameweek: int | None = None) -> None:
        if discord_id is None:
            await ctx.reply("You must provide a Discord ID. Usage: `.viewPred <discord_id> <gameweek>`")
            return
        if gameweek is None:
            await ctx.reply("You must provide a gameweek. Usage: `.viewPred <discord_id> <gameweek>`")
            return

        db: Session = ctx.bot.db

        user = db.execute(
            select(User).where(User.discord_id == discord_id)
        ).scalar_one_or_none()
        if user is None:
            await ctx.reply(f"No user found with Discord ID `{discord_id}`")
            return

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()
        if current_gameweek is None:
            await ctx.reply("Gameweek does not exist yet")
            return

        if gameweek > current_gameweek:
            await ctx.reply(f"Gameweek {gameweek} does not exist yet")
            return
        elif gameweek <= 0:
            await ctx.reply("Gameweek cannot be below 1")
            return

        embed = discord.Embed(
            title=f"{user.nickname.capitalize()}'s Predictions for Gameweek: `{gameweek}`",
            color=discord.Color.gold(),
        )

        gameweek_predictions = (
            db.execute(
                select(Prediction)
                .where(
                    Prediction.discord_id == discord_id, Prediction.gameweek_id == gameweek
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
    await bot.add_cog(PredictionCommands(bot))

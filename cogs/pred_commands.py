from typing import TYPE_CHECKING

from discord.ext import commands
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from db.models.fixtures import Fixture
from db.models.predictions import Prediction
from decorators.helpers import ensure_user_exists

if TYPE_CHECKING:
    from bot import PyBot


class PredictionCommands(commands.Cog):
    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(
        name="predict", help="Predict for the gameweek: .predict GW 10-2 2-0 2-4 1-0"
    )
    @ensure_user_exists()
    async def predict(self, ctx: commands.Context, *scores: str) -> None:
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        current_gameweek = db.execute(
            select(func.max(Fixture.gameweek))
        ).scalar_one_or_none()

        current_fixtures = (
            db.execute(
                select(Fixture)
                .where(Fixture.gameweek == current_gameweek)
                .order_by(Fixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        if len(scores) != len(current_fixtures):
            await ctx.reply(
                f"You must enter exactly {len(current_fixtures)} predictions. Use .updatePred to change a single prediction"
            )
            return

        for i, score in enumerate(scores):
            try:
                home, away = map(int, score.split("-"))
            except ValueError:
                await ctx.reply(f"Invalid format: `{score}`. Use format like `2-1`.")
                return

            pred_exists = db.execute(
                select(Prediction).where(
                    Prediction.discord_id == user_id,
                    Prediction.gameweek_id == current_gameweek,
                    Prediction.match_index == i,
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
                        match_index=i,
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
    async def update_prediction(self, ctx: commands.Context, *update: str) -> None:
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


async def setup(bot: "PyBot"):
    await bot.add_cog(PredictionCommands(bot))

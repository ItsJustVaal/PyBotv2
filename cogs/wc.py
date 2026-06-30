# cogs/wc.py
import os
import shlex
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.orm import Session

from db.models.users import User
from db.models.wc_fixtures import WCFixture
from db.models.wc_predictions import WCPrediction
from decorators.helpers import ensure_user_exists, is_admin

if TYPE_CHECKING:
    from bot import PyBot

API_BASE = "https://api.football-data.org/v4"

STAGE_MAP = {
    "32":    ("LAST_32",        4, "Round of 32"),
    "16":    ("LAST_16",        5, "Round of 16"),
    "8":     ("QUARTER_FINALS", 6, "Quarter Finals"),
    "4":     ("SEMI_FINALS",    7, "Semi Finals"),
    "final": (None,             8, "Third Place & Final"),
}

_GW_DISPLAY = {gw: name for _, gw, name in STAGE_MAP.values()}
_GW_TO_ROUND = {gw: r for r, (_, gw, _) in STAGE_MAP.items()}


class WorldCupCommands(commands.Cog):
    """Cog for World Cup 2026 commands."""

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    def _get_current_gameweek(self, db: Session) -> int | None:
        resulted_gameweeks = (
            select(WCFixture.gameweek)
            .where(WCFixture.result_added == 1)
            .distinct()
        )
        active_gameweek = db.execute(
            select(func.max(WCFixture.gameweek)).where(
                WCFixture.result_added == 0,
                WCFixture.gameweek.in_(resulted_gameweeks),
            )
        ).scalar_one_or_none()
        if active_gameweek is not None:
            return active_gameweek

        next_open_gameweek = db.execute(
            select(func.min(WCFixture.gameweek)).where(WCFixture.result_added == 0)
        ).scalar_one_or_none()
        if next_open_gameweek is not None:
            return next_open_gameweek

        return self._get_latest_gameweek(db)

    def _get_current_result_gameweek(self, db: Session) -> int | None:
        untallied_results_gameweek = db.execute(
            select(func.max(WCFixture.gameweek)).where(
                WCFixture.result_added == 1,
                WCFixture.tallied == 0,
            )
        ).scalar_one_or_none()
        if untallied_results_gameweek is not None:
            return untallied_results_gameweek
        return self._get_current_gameweek(db)

    def _select_prediction_gameweek(
        self,
        db: Session,
        scores: tuple[str, ...],
    ) -> tuple[int | None, str | None, tuple[str, ...], str | None]:
        round_arg = scores[0] if scores else None
        if round_arg in ("2", "3"):
            current_gameweek = int(round_arg)
            display = f"Gameweek: `{current_gameweek}`"
            return current_gameweek, display, scores[1:], None

        if round_arg is not None and round_arg.isdecimal():
            return (
                None,
                None,
                scores,
                "Only gameweeks 2 or 3 can be selected directly. "
                "Omit the round to predict the current gameweek.",
            )

        selected_gameweek = self._get_current_gameweek(db)
        if selected_gameweek is None:
            return None, None, scores, "No WC fixtures have been set up yet."

        display = _GW_DISPLAY.get(selected_gameweek, f"Gameweek: `{selected_gameweek}`")
        return selected_gameweek, display, scores, None

    def _get_latest_gameweek(self, db: Session) -> int | None:
        return db.execute(select(func.max(WCFixture.gameweek))).scalar_one_or_none()

    def _parse_round(self, round: str) -> tuple[int, str] | None:
        if round in ("1", "2", "3"):
            gameweek = int(round)
            return gameweek, f"Gameweek: `{gameweek}`"
        if round in STAGE_MAP:
            _, gameweek, display = STAGE_MAP[round]
            return gameweek, display
        return None

    def _normalize_team_name(self, name: str | None) -> str:
        return " ".join((name or "").strip().lower().split())

    def _score_prediction(
        self,
        pred_home: int,
        pred_away: int,
        act_home: int,
        act_away: int,
    ) -> int:
        if pred_home == act_home and pred_away == act_away:
            return 3
        pred_outcome = (pred_home > pred_away) - (pred_home < pred_away)
        act_outcome = (act_home > act_away) - (act_home < act_away)
        return 1 if pred_outcome == act_outcome else 0

    def _get_full_time_score(self, match: dict[str, Any]) -> tuple[int, int] | None:
        score = match.get("score") or {}
        regular_time = score.get("regularTime") or {}
        full_time = score.get("fullTime") or {}
        score_to_use = regular_time if (
            regular_time.get("home") is not None and regular_time.get("away") is not None
        ) else full_time

        home_score = score_to_use.get("home")
        away_score = score_to_use.get("away")
        if home_score is None or away_score is None:
            return None
        return int(home_score), int(away_score)

    def _get_gameweek_standings(
        self,
        db: Session,
        current_gameweek: int | None,
    ) -> list[tuple[User, int]]:
        if current_gameweek is None:
            return []

        rows = db.execute(
            select(User, WCPrediction, WCFixture)
            .join(WCPrediction, User.discord_id == WCPrediction.discord_id)
            .join(
                WCFixture,
                and_(
                    WCFixture.gameweek == WCPrediction.gameweek_id,
                    WCFixture.order_index == WCPrediction.match_index,
                ),
            )
            .where(WCPrediction.gameweek_id == current_gameweek)
        ).all()

        standings: dict[str, dict[str, Any]] = {}
        for user, pred, fixture in rows:
            row = standings.setdefault(
                user.discord_id,
                {"user": user, "points": 0, "first_pred": pred.updated_at},
            )
            if pred.updated_at is not None and (
                row["first_pred"] is None or pred.updated_at > row["first_pred"]
            ):
                row["first_pred"] = pred.updated_at

            if fixture.result_added == 1:
                row["points"] += self._score_prediction(
                    pred.prediction_home,
                    pred.prediction_away,
                    fixture.home_score,
                    fixture.away_score,
                )

        return [
            (row["user"], row["points"])
            for row in sorted(
                standings.values(),
                key=lambda row: (
                    -row["points"],
                    row["first_pred"] is not None,
                    row["first_pred"],
                ),
            )
        ]

    async def _fetch_api_json(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        headers: dict[str, str],
        **kwargs: Any,
    ) -> tuple[dict[str, Any] | None, str | None]:
        async with session.get(f"{API_BASE}{endpoint}", headers=headers, **kwargs) as resp:
            try:
                data = await resp.json(content_type=None)
            except ValueError:
                return None, f"API returned a non-JSON response ({resp.status}: {resp.reason})."
            if resp.status >= 400:
                message = data.get("message", resp.reason) if isinstance(data, dict) else resp.reason
                return None, f"API request failed ({resp.status}): {message}"
            if not isinstance(data, dict):
                return None, "API returned an unexpected response."
            return data, None

    def _build_grouped_embed(self, embed: discord.Embed, groups: dict) -> None:
        for i, group_name in enumerate(sorted(groups.keys())):
            formatted = group_name.replace("_", " ").title()
            fixtures_str = "\n".join(
                f"{f.home.title()} vs {f.away.title()}" for f in groups[group_name]
            )
            embed.add_field(name=formatted, value=fixtures_str, inline=True)
            if (i + 1) % 2 == 0:
                embed.add_field(name="​", value="​", inline=True)

    @commands.command(hidden=True, name="wcSetFixtures")
    @is_admin()
    async def wc_set_fixtures(self, ctx: commands.Context, round: str | None = None) -> None:
        """Fetch WC fixtures from the API and store them. Usage: `.wcSetFixtures <1|2|3|32|16|8|4|final>`"""
        if round is None:
            await ctx.reply("You must provide a round. Usage: `.wcSetFixtures <1|2|3|32|16|8|4|final>`")
            return

        db: Session = ctx.bot.db
        api_key = os.getenv("API_KEY_FOOTBALL")
        if api_key is None:
            await ctx.reply("There was an error with the api key")
            return

        headers = {"X-Auth-Token": api_key}

        if round in ("1", "2", "3"):
            gameweek = int(round)
            existing = db.execute(
                select(WCFixture).where(WCFixture.gameweek == gameweek)
            ).scalars().first()
            if existing:
                await ctx.reply(f"Fixtures already exist for gameweek {gameweek}.")
                return

            async with aiohttp.ClientSession() as session:
                match_data, error = await self._fetch_api_json(
                    session,
                    "/competitions/WC/matches",
                    headers=headers,
                    params={"matchday": gameweek},
                )
                if error:
                    await ctx.reply(error)
                    return
            if match_data:
                matches = match_data.get("matches", [])
            if not matches:
                await ctx.reply(f"No fixtures found for matchday {gameweek}.")
                return

            embed = discord.Embed(
                title=f"World Cup Fixtures for Gameweek {gameweek} — Matchday {gameweek}",
                color=discord.Color.blue(),
            )
            groups: dict = defaultdict(list)
            for match in matches:
                group_key = match.get("group") or "Knockout Stage"
                groups[group_key].append(match)

            order_index = 0
            for i, group_name in enumerate(sorted(groups.keys())):
                formatted = group_name.replace("_", " ").title()
                fixtures_str = []
                for match in groups[group_name]:
                    db.add(WCFixture(
                        api_match_id=match.get("id"),
                        order_index=order_index,
                        gameweek=gameweek,
                        group=group_name,
                        home=self._normalize_team_name(match["homeTeam"]["name"]),
                        away=self._normalize_team_name(match["awayTeam"]["name"]),
                    ))
                    fixtures_str.append(f"{match['homeTeam']['name']} vs {match['awayTeam']['name']}")
                    order_index += 1
                embed.add_field(name=formatted, value="\n".join(fixtures_str), inline=True)
                if (i + 1) % 2 == 0:
                    embed.add_field(name="​", value="​", inline=True)

        elif round in STAGE_MAP:
            stage, gameweek, display_name = STAGE_MAP[round]

            existing = db.execute(
                select(WCFixture).where(WCFixture.gameweek == gameweek)
            ).scalars().first()
            if existing:
                await ctx.reply(f"Fixtures already exist for {display_name}.")
                return

            if round == "final":
                stages_to_fetch = ["THIRD_PLACE", "FINAL"]
            else:
                assert stage is not None
                stages_to_fetch = [stage]
            matches = []
            async with aiohttp.ClientSession() as session:
                for s in stages_to_fetch:
                    data, error = await self._fetch_api_json(
                        session,
                        "/competitions/WC/matches",
                        headers=headers,
                        params={"stage": s},
                    )
                    if error:
                        await ctx.reply(error)
                        return
                    if data:
                        matches.extend(data.get("matches", []))

            if not matches:
                await ctx.reply(f"No fixtures found for {display_name}.")
                return

            embed = discord.Embed(
                title=f"World Cup Fixtures — {display_name}",
                color=discord.Color.blue(),
            )
            embed_desc = []
            for i, match in enumerate(matches):
                home = match["homeTeam"]["name"] or "TBD"
                away = match["awayTeam"]["name"] or "TBD"
                db.add(WCFixture(
                    api_match_id=match.get("id"),
                    order_index=i,
                    gameweek=gameweek,
                    group=display_name,
                    home=self._normalize_team_name(home),
                    away=self._normalize_team_name(away),
                ))
                embed_desc.append(f"{home} vs {away}")
            embed.description = "\n".join(embed_desc)

        else:
            await ctx.reply("Invalid round. Use: `.wcSetFixtures <1|2|3|32|16|8|4|final>`")
            return

        db.commit()
        await ctx.reply(embed=embed)

    @commands.command(
        name="wcFixtures",
        help="Show WC fixtures: `.wcFixtures` or `.wcFixtures 32` etc.",
    )
    @ensure_user_exists()
    async def wc_get_fixtures(self, ctx: commands.Context, round: str | None = None) -> None:
        """Display all WC fixtures for the current or specified round."""
        db: Session = ctx.bot.db

        if round is None:
            current_gameweek = self._get_current_gameweek(db)
            if current_gameweek is None or current_gameweek <= 0:
                await ctx.reply("No WC gameweeks have been set yet.")
                return
            display = _GW_DISPLAY.get(current_gameweek, f"Gameweek {current_gameweek}")
        elif round in ("1", "2", "3"):
            current_gameweek = int(round)
            display = f"Gameweek {current_gameweek}"
        elif round in STAGE_MAP:
            _, current_gameweek, display = STAGE_MAP[round]
        else:
            await ctx.reply("Invalid round. Use: `.wcFixtures <1|2|3|32|16|8|4|final>`")
            return

        check = db.execute(
            select(WCFixture).where(WCFixture.gameweek == current_gameweek)
        ).scalars().first()
        if check is None:
            await ctx.reply("No fixtures found for that round.")
            return

        embed = discord.Embed(
            title=f"WC Fixtures — {display}",
            color=discord.Color.blue(),
        )

        fixture_list = (
            db.execute(
                select(WCFixture)
                .where(WCFixture.gameweek == current_gameweek)
                .order_by(WCFixture.group, WCFixture.order_index)
            )
            .scalars()
            .all()
        )

        groups: dict = defaultdict(list)
        for fixture in fixture_list:
            groups[fixture.group or "Knockout Stage"].append(fixture)

        self._build_grouped_embed(embed, groups)
        await ctx.reply(embed=embed)

    @commands.command(
        name="wcPredict",
        help="Predict WC scores: `.wcPredict 2-1 0-0` or `.wcPredict 2 1-1 1-1`, only 2 or 3 can select a future gameweek",
    )
    @ensure_user_exists()
    async def wc_predict(self, ctx: commands.Context, *scores: str) -> None:
        """Submit predictions for all open WC fixtures in the current or selected group gameweek."""
        if self.bot.locked:
            await ctx.reply("Locked lol noob")
            return

        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        current_gameweek, display, scores, error = self._select_prediction_gameweek(db, scores)
        if error is not None:
            await ctx.reply(error)
            return
        assert current_gameweek is not None
        assert display is not None

        current_fixtures = (
            db.execute(
                select(WCFixture)
                .where(
                    and_(
                        WCFixture.gameweek == current_gameweek,
                        WCFixture.tallied == 0,
                        WCFixture.result_added == 0,
                    )
                )
                .order_by(WCFixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        if len(current_fixtures) == 0:
            await ctx.reply(
                f"No open WC fixtures to predict for {display} — this round may already be tallied. "
                "Use .wcUpdatePred to change an existing prediction."
            )
            return

        if len(scores) != len(current_fixtures):
            await ctx.reply(
                f"You must enter exactly {len(current_fixtures)} predictions for {display}. "
                "Use .wcUpdatePred to change a single prediction"
            )
            return

        existing_preds = (
            db.execute(
                select(WCPrediction).where(
                    WCPrediction.discord_id == user_id,
                    WCPrediction.gameweek_id == current_gameweek,
                )
            )
            .scalars()
            .all()
        )
        pred_by_index = {p.match_index: p for p in existing_preds}

        for fixture, score in zip(current_fixtures, scores):
            try:
                home, away = map(int, score.split("-"))
            except ValueError:
                await ctx.reply(f"Invalid format: `{score}`. Use format like `2-1`.")
                return

            match_index = fixture.order_index
            pred_exists = pred_by_index.get(match_index)

            if pred_exists:
                pred_exists.prediction_home = home
                pred_exists.prediction_away = away
            else:
                db.add(
                    WCPrediction(
                        discord_id=user_id,
                        gameweek_id=current_gameweek,
                        match_index=match_index,
                        prediction_home=home,
                        prediction_away=away,
                    )
                )

        db.commit()

        round_str = _GW_TO_ROUND.get(current_gameweek, str(current_gameweek))
        await ctx.invoke(
            self.bot.get_command("wcmypred"),  # type: ignore
            round=round_str,
        )

    @commands.command(
        name="wcmypred",
        help="Shows your WC predictions: `.wcmypred` or `.wcmypred 32` etc.",
    )
    @ensure_user_exists()
    async def wc_my_pred(self, ctx: commands.Context, round: str | None = None) -> None:
        """Display the user's WC predictions for the current or specified round."""
        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        latest_gameweek = self._get_latest_gameweek(db)
        if latest_gameweek is None:
            await ctx.reply("No WC gameweeks have been set yet.")
            return

        if round is None:
            gameweek = self._get_current_gameweek(db)
            if gameweek is None:
                await ctx.reply("No WC gameweeks have been set yet.")
                return
            display = _GW_DISPLAY.get(gameweek, f"Gameweek: `{gameweek}`")
        else:
            selected_round = self._parse_round(round)
            if selected_round is None:
                await ctx.reply("Invalid round. Use: `.wcmypred <1|2|3|32|16|8|4|final>`")
                return
            gameweek, display = selected_round

        if gameweek > latest_gameweek:
            await ctx.reply(f"{display} does not exist yet")
            return

        embed = discord.Embed(
            title=f"My WC Predictions — {display}",
            color=discord.Color.gold(),
        )

        gameweek_predictions = (
            db.execute(
                select(WCPrediction)
                .where(WCPrediction.discord_id == user_id, WCPrediction.gameweek_id == gameweek)
                .order_by(WCPrediction.match_index)
            )
            .scalars()
            .all()
        )

        gameweek_fixtures = (
            db.execute(
                select(WCFixture)
                .where(WCFixture.gameweek == gameweek)
                .order_by(WCFixture.order_index)
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
                    f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `None-None`"
                )
            else:
                embed_desc.append(
                    f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `{p.prediction_home}-{p.prediction_away}`"
                )

        embed.description = "\n".join(embed_desc) if embed_desc else "No fixtures found for this round."
        await ctx.reply(embed=embed)

    @commands.command(
        name="wcUpdatePred",
        help='Update a single WC pred. Usage: `.wcUpdatePred "Home" "Away" 2-1`',
    )
    @ensure_user_exists()
    async def wc_update_prediction(self, ctx: commands.Context, *args: str) -> None:
        """Update a single WC prediction by match name."""
        if self.bot.locked:
            await ctx.reply("Locked lol noob")
            return

        db: Session = ctx.bot.db
        user_id = str(ctx.author.id)

        if len(args) != 3:
            await ctx.reply('Wrong Usage: `.wcUpdatePred "Home" "Away" 2-1`')
            return

        current_gameweek = self._get_current_gameweek(db)
        if current_gameweek is None:
            await ctx.reply("No WC fixtures have been set up yet.")
            return

        try:
            home = args[0].strip().lower()
            away = args[1].strip().lower()
            home_score, away_score = map(int, args[2].split("-"))
        except Exception:
            await ctx.reply('Invalid format. Use: `.wcUpdatePred "Home" "Away" 2-1`')
            return

        current_fixture = db.execute(
            select(WCFixture).where(
                and_(
                    WCFixture.gameweek == current_gameweek,
                    WCFixture.home == home,
                    WCFixture.away == away,
                )
            )
        ).scalar_one_or_none()

        round_display = _GW_DISPLAY.get(current_gameweek, f"Gameweek {current_gameweek}")
        if not current_fixture:
            await ctx.reply(
                f"No match found for `{home.title()} vs {away.title()}` in {round_display}"
            )
            return
        elif current_fixture.result_added == 1:
            await ctx.reply(
                f"Sorry, `{home.title()} vs {away.title()}` in {round_display} already has a result"
            )
            return
        elif current_fixture.tallied == 1:
            await ctx.reply(
                f"Sorry, `{home.title()} vs {away.title()}` in {round_display} has been tallied already"
            )
            return

        current_prediction = db.execute(
            select(WCPrediction).where(
                and_(
                    WCPrediction.discord_id == user_id,
                    WCPrediction.gameweek_id == current_gameweek,
                    WCPrediction.match_index == current_fixture.order_index,
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
            db.add(WCPrediction(
                discord_id=user_id,
                gameweek_id=current_gameweek,
                match_index=current_fixture.order_index,
                prediction_home=home_score,
                prediction_away=away_score,
            ))
            await ctx.reply(
                f"Added new prediction for `{current_fixture.home.title()} vs {current_fixture.away.title()}` as `{home_score}-{away_score}`"
            )

        db.commit()

    @commands.command(
        hidden=True,
        name="wcUpdateUserPred",
        help=(
            'Admin: update a user WC pred. Usage: '
            '`.wcUpdateUserPred <discord_id> <round> "Home" "Away" 2-1`'
        ),
    )
    @is_admin()
    async def wc_update_user_prediction(
        self,
        ctx: commands.Context,
        discord_id: str | None = None,
        round: str | None = None,
        home: str | None = None,
        away: str | None = None,
        score: str | None = None,
    ) -> None:
        """Admin: update a user's WC prediction by Discord ID, round, and match name."""
        usage = (
            'Usage: `.wcUpdateUserPred <discord_id> <1|2|3|32|16|8|4|final> '
            '"Home" "Away" 2-1`'
        )
        if None in (discord_id, round, home, away, score):
            await ctx.reply(usage)
            return

        assert discord_id is not None
        assert round is not None
        assert home is not None
        assert away is not None
        assert score is not None

        db: Session = ctx.bot.db
        discord_id = discord_id.strip("<@!>")

        user = db.execute(
            select(User).where(User.discord_id == discord_id)
        ).scalar_one_or_none()
        if user is None:
            await ctx.reply(f"No user found with Discord ID `{discord_id}`")
            return

        selected_round = self._parse_round(round)
        if selected_round is None:
            await ctx.reply(
                "Invalid round. Use: `.wcUpdateUserPred <discord_id> "
                '<1|2|3|32|16|8|4|final> "Home" "Away" 2-1`'
            )
            return
        gameweek, display = selected_round

        latest_gameweek = self._get_latest_gameweek(db)
        if latest_gameweek is None:
            await ctx.reply("No WC fixtures have been set up yet.")
            return
        if gameweek > latest_gameweek:
            await ctx.reply(f"{display} does not exist yet")
            return

        try:
            home_score, away_score = map(int, score.split("-"))
        except ValueError:
            await ctx.reply(
                'Invalid score format. Use: `.wcUpdateUserPred <discord_id> '
                '<round> "Home" "Away" 2-1`'
            )
            return

        normalized_home = self._normalize_team_name(home)
        normalized_away = self._normalize_team_name(away)

        current_fixture = db.execute(
            select(WCFixture).where(
                and_(
                    WCFixture.gameweek == gameweek,
                    WCFixture.home == normalized_home,
                    WCFixture.away == normalized_away,
                )
            )
        ).scalar_one_or_none()

        if not current_fixture:
            await ctx.reply(
                f"No match found for `{normalized_home.title()} vs {normalized_away.title()}` in {display}"
            )
            return
        elif current_fixture.result_added == 1:
            await ctx.reply(
                f"Sorry, `{current_fixture.home.title()} vs {current_fixture.away.title()}` in {display} already has a result"
            )
            return
        elif current_fixture.tallied == 1:
            await ctx.reply(
                f"Sorry, `{current_fixture.home.title()} vs {current_fixture.away.title()}` in {display} has been tallied already"
            )
            return

        current_prediction = db.execute(
            select(WCPrediction).where(
                and_(
                    WCPrediction.discord_id == discord_id,
                    WCPrediction.gameweek_id == gameweek,
                    WCPrediction.match_index == current_fixture.order_index,
                )
            )
        ).scalar_one_or_none()

        if current_prediction:
            current_prediction.prediction_home = home_score
            current_prediction.prediction_away = away_score
            action = "Updated"
        else:
            db.add(WCPrediction(
                discord_id=discord_id,
                gameweek_id=gameweek,
                match_index=current_fixture.order_index,
                prediction_home=home_score,
                prediction_away=away_score,
            ))
            action = "Added"

        db.commit()
        await ctx.reply(
            f"{action} {user.nickname.capitalize()}'s prediction for "
            f"`{current_fixture.home.title()} vs {current_fixture.away.title()}` "
            f"in {display} to `{home_score}-{away_score}`"
        )

    @commands.command(hidden=True, name="wcUpdatePoints")
    @is_admin()
    async def wc_update_points(self, ctx: commands.Context) -> None:
        """Tally WC predictions for all result_added fixtures and update user WC points."""
        db: Session = ctx.bot.db

        rows = db.execute(
            select(WCPrediction, WCFixture)
            .join(
                WCFixture,
                and_(
                    WCFixture.gameweek == WCPrediction.gameweek_id,
                    WCFixture.order_index == WCPrediction.match_index,
                ),
            )
            .where(
                WCFixture.tallied == 0,
                WCFixture.result_added == 1,
            )
        ).all()

        if not rows:
            await ctx.reply("No untallied WC results to process.")
            return

        users_by_id = {
            u.discord_id: u
            for u in db.execute(select(User)).scalars().all()
        }

        processed_gameweeks = {fix.gameweek for _, fix in rows}
        tallied_fixture_ids = set()
        for pred, fix in rows:
            pts = self._score_prediction(
                pred.prediction_home,
                pred.prediction_away,
                fix.home_score,
                fix.away_score,
            )
            if pred.discord_id in users_by_id:
                users_by_id[pred.discord_id].wc_gameweek_points += pts
                users_by_id[pred.discord_id].wc_overall_points += pts
            tallied_fixture_ids.add(fix.id)

        db.execute(
            update(WCFixture)
            .where(WCFixture.id.in_(tallied_fixture_ids))
            .values(tallied=1)
        )

        db.commit()

        displays = [
            _GW_DISPLAY.get(gameweek, f"gameweek {gameweek}")
            for gameweek in sorted(processed_gameweeks)
        ]
        display = ", ".join(displays)
        await ctx.reply(f"WC points updated for {display}.")

    @commands.command(name="wcReset", hidden=True)
    @is_admin()
    async def wc_reset(self, ctx: commands.Context) -> None:
        """Reset all users' WC gameweek points to 0."""
        db: Session = ctx.bot.db

        all_users = db.execute(select(User)).scalars().all()

        for user in all_users:
            user.wc_gameweek_points = 0

        db.commit()
        await ctx.reply("WC Gameweek Points Reset")

    @commands.command(name="wcStandings", help="See current WC prediction standings")
    async def wc_standings(self, ctx: commands.Context) -> None:
        """Display WC prediction leaderboard, only for users who have made predictions."""
        db: Session = ctx.bot.db

        current_gameweek = self._get_current_gameweek(db)

        # Overall: tiebreak by latest update across all preds ever
        overall_pred_subq = (
            select(WCPrediction.discord_id, func.max(WCPrediction.updated_at).label("first_pred"))
            .group_by(WCPrediction.discord_id)
            .subquery()
        )

        overall_ids = {
            row[0] for row in db.execute(select(WCPrediction.discord_id).distinct()).all()
        }

        if not overall_ids:
            await ctx.reply("No WC predictions have been made yet.")
            return

        users_gameweek = self._get_gameweek_standings(db, current_gameweek)

        users_overall = (
            db.execute(
                select(User)
                .join(overall_pred_subq, User.discord_id == overall_pred_subq.c.discord_id)
                .where(User.discord_id.in_(overall_ids))
                .order_by(User.wc_overall_points.desc(), overall_pred_subq.c.first_pred.asc())
            )
            .scalars()
            .all()
        )

        embed = discord.Embed(title="WC Prediction Standings", color=discord.Color.gold())
        gw_value = "\n".join(f"{u.nickname.capitalize()}: {points}" for u, points in users_gameweek)
        embed.add_field(name="Gameweek", value=gw_value if gw_value else "No predictions for this round yet")
        embed.add_field(
            name="Overall",
            value="\n".join(f"{u.nickname.capitalize()}: {u.wc_overall_points}" for u in users_overall)
        )
        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="wcSetResults")
    @is_admin()
    async def wc_set_results(self, ctx: commands.Context) -> None:
        """Fetch finished WC match results from the API and update fixtures. Usage: `.wcSetResults`"""
        db: Session = ctx.bot.db
        api_key = os.getenv("API_KEY_FOOTBALL")
        if api_key is None:
            await ctx.reply("There was an error with the api key")
            return

        headers = {"X-Auth-Token": api_key}

        async with aiohttp.ClientSession() as session:
            match_data, error = await self._fetch_api_json(
                session,
                "/competitions/WC/matches",
                headers=headers,
                params={"status": "FINISHED"},
            )
            if error:
                await ctx.reply(error)
                return
        matches = match_data.get("matches", []) if match_data else []
        if not matches:
            await ctx.reply("No finished WC matches found.")
            return

        # Build lookup of unresulted fixtures by (home, away)
        pending_fixtures = (
            db.execute(
                select(WCFixture).where(WCFixture.result_added == 0)
            )
            .scalars()
            .all()
        )
        fixture_lookup = {(f.home, f.away): f for f in pending_fixtures}
        fixture_lookup_by_api_id = {
            f.api_match_id: f for f in pending_fixtures if f.api_match_id is not None
        }

        updated = []
        for match in matches:
            home = self._normalize_team_name(match["homeTeam"]["name"])
            away = self._normalize_team_name(match["awayTeam"]["name"])
            full_time_score = self._get_full_time_score(match)
            if full_time_score is None:
                continue
            home_score, away_score = full_time_score

            fixture = fixture_lookup_by_api_id.get(match.get("id")) or fixture_lookup.get((home, away))
            if fixture is None:
                continue

            fixture.home_score = home_score
            fixture.away_score = away_score
            fixture.result_added = 1
            updated.append(f"{match['homeTeam']['name']} {home_score}–{away_score} {match['awayTeam']['name']}")

        if not updated:
            await ctx.reply("No new results to update.")
            return

        db.commit()

        embed = discord.Embed(
            title=f"WC Results Updated — {len(updated)} match(es)",
            color=discord.Color.green(),
        )
        embed.description = "\n".join(updated)
        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="wcUpdateResult")
    @is_admin()
    async def wc_update_result(self, ctx: commands.Context, *args: str) -> None:
        """Admin: update one WC result in the current gameweek. Usage: `.wcUpdateResult "Home" "Away" 2-1`"""
        usage = 'Usage: `.wcUpdateResult "Home" "Away" 2-1` or `.wcUpdateResult "Home-Away" 2-1`'
        if len(args) == 2:
            try:
                home, away = args[0].split("-", 1)
                score = args[1]
            except ValueError:
                await ctx.reply(usage)
                return
        elif len(args) == 3:
            home, away, score = args
        else:
            await ctx.reply(usage)
            return

        try:
            home_score, away_score = map(int, score.split("-"))
        except ValueError:
            await ctx.reply(usage)
            return

        db: Session = ctx.bot.db
        current_gameweek = self._get_current_result_gameweek(db)
        if current_gameweek is None:
            await ctx.reply("No WC fixtures have been set up yet.")
            return

        normalized_home = self._normalize_team_name(home)
        normalized_away = self._normalize_team_name(away)
        fixture = db.execute(
            select(WCFixture).where(
                and_(
                    WCFixture.gameweek == current_gameweek,
                    WCFixture.home == normalized_home,
                    WCFixture.away == normalized_away,
                )
            )
        ).scalar_one_or_none()

        round_display = _GW_DISPLAY.get(current_gameweek, f"Gameweek {current_gameweek}")
        if fixture is None:
            await ctx.reply(
                f"No match found for `{normalized_home.title()} vs {normalized_away.title()}` in {round_display}"
            )
            return

        fixture.home_score = home_score
        fixture.away_score = away_score
        fixture.result_added = 1
        db.commit()

        await ctx.reply(
            f"Updated `{fixture.home.title()} vs {fixture.away.title()}` in "
            f"{round_display} to `{home_score}-{away_score}`"
        )
        await ctx.invoke(
            self.bot.get_command("wcResults"),  # type: ignore
            round=_GW_TO_ROUND.get(current_gameweek, str(current_gameweek)),
        )

    @commands.command(name="wcViewPred", hidden=True)
    @is_admin()
    async def wc_view_pred(self, ctx: commands.Context, discord_id: str | None = None, round: str | None = None) -> None:
        """Admin: view a user's WC predictions. Usage: `.wcViewPred <discord_id> <round>`"""
        if discord_id is None:
            await ctx.reply("You must provide a Discord ID. Usage: `.wcViewPred <discord_id> <round>`")
            return
        if round is None:
            await ctx.reply("You must provide a round. Usage: `.wcViewPred <discord_id> <1|2|3|32|16|8|4|final>`")
            return

        db: Session = ctx.bot.db

        user = db.execute(select(User).where(User.discord_id == discord_id)).scalar_one_or_none()
        if user is None:
            await ctx.reply(f"No user found with Discord ID `{discord_id}`")
            return

        latest_gameweek = self._get_latest_gameweek(db)
        if latest_gameweek is None:
            await ctx.reply("No WC gameweeks exist yet")
            return

        selected_round = self._parse_round(round)
        if selected_round is None:
            await ctx.reply("Invalid round. Use: `.wcViewPred <discord_id> <1|2|3|32|16|8|4|final>`")
            return
        gameweek, display = selected_round

        if gameweek > latest_gameweek:
            await ctx.reply(f"{display} does not exist yet")
            return

        embed = discord.Embed(
            title=f"{user.nickname.capitalize()}'s WC Predictions — {display}",
            color=discord.Color.gold(),
        )

        gameweek_predictions = (
            db.execute(
                select(WCPrediction)
                .where(WCPrediction.discord_id == discord_id, WCPrediction.gameweek_id == gameweek)
                .order_by(WCPrediction.match_index)
            )
            .scalars()
            .all()
        )

        gameweek_fixtures = (
            db.execute(
                select(WCFixture)
                .where(WCFixture.gameweek == gameweek)
                .order_by(WCFixture.order_index)
            )
            .scalars()
            .all()
        )

        pred_by_index = {p.match_index: p for p in gameweek_predictions}
        embed_desc = []
        for fixture in gameweek_fixtures:
            p = pred_by_index.get(fixture.order_index)
            if p is None:
                embed_desc.append(f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `None-None`")
            else:
                embed_desc.append(f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `{p.prediction_home}-{p.prediction_away}`")

        embed.description = "\n".join(embed_desc) if embed_desc else "No fixtures found for this round."
        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="wcAddPoints")
    @is_admin()
    async def wc_add_points(self, ctx: commands.Context, discord_id: str | None = None, points: int | None = None) -> None:
        """Admin: manually add WC points to a user. Usage: `.wcAddPoints <discord_id> <points>`"""
        if discord_id is None or points is None:
            await ctx.reply("Usage: `.wcAddPoints <discord_id> <points>`")
            return

        db: Session = ctx.bot.db
        user = db.execute(select(User).where(User.discord_id == discord_id)).scalar_one_or_none()
        if user is None:
            await ctx.reply("User not found")
            return

        user.wc_overall_points += points
        user.wc_gameweek_points += points
        db.commit()
        await ctx.reply(f"Added {points} WC points to {user.nickname.capitalize()}")

    @commands.command(hidden=True, name="wcRemovePoints")
    @is_admin()
    async def wc_remove_points(self, ctx: commands.Context, discord_id: str | None = None, points: int | None = None) -> None:
        """Admin: manually remove WC points from a user. Usage: `.wcRemovePoints <discord_id> <points>`"""
        if discord_id is None or points is None:
            await ctx.reply("Usage: `.wcRemovePoints <discord_id> <points>`")
            return

        db: Session = ctx.bot.db
        user = db.execute(select(User).where(User.discord_id == discord_id)).scalar_one_or_none()
        if user is None:
            await ctx.reply("User not found")
            return

        user.wc_overall_points -= points
        user.wc_gameweek_points -= points
        db.commit()
        await ctx.reply(f"Removed {points} WC points from {user.nickname.capitalize()}")

    @commands.command(
        name="wcResults",
        help="Shows WC results: `.wcResults 1` or `.wcResults 32` etc.",
    )
    @ensure_user_exists()
    async def wc_results(self, ctx: commands.Context, round: str | None = None) -> None:
        """Display WC fixture results for the given round."""
        db: Session = ctx.bot.db

        if round is None:
            gameweek = self._get_current_gameweek(db)
            if gameweek is None:
                await ctx.reply("No WC gameweeks exist yet")
                return
            display = _GW_DISPLAY.get(gameweek, f"Gameweek: `{gameweek}`")
        elif round in ("1", "2", "3"):
            gameweek = int(round)
            display = f"Gameweek: `{gameweek}`"
        elif round in STAGE_MAP:
            _, gameweek, display = STAGE_MAP[round]
        else:
            await ctx.reply("Invalid round. Use: `.wcResults <1|2|3|32|16|8|4|final>`")
            return

        fixtures = (
            db.execute(
                select(WCFixture)
                .where(WCFixture.gameweek == gameweek)
                .order_by(WCFixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        if not fixtures:
            await ctx.reply("No fixtures found for that round.")
            return

        embed = discord.Embed(
            title=f"WC Results — {display}",
            color=discord.Color.gold(),
        )

        embed_desc = []
        for fixture in fixtures:
            if fixture.result_added:
                points_given = "Yes" if fixture.tallied else "No"
                score_str = f"`{fixture.home_score}-{fixture.away_score}` - Points Given: {points_given}"
            else:
                score_str = "`TBD`"
            embed_desc.append(
                f"**{fixture.home.title()}** vs **{fixture.away.title()}** — Score: {score_str}"
            )

        embed.description = "\n".join(embed_desc)
        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="wcUpdateFixture")
    @is_admin()
    async def wc_update_fixture(self, ctx: commands.Context) -> None:
        """Update a WC fixture's teams. Usage: `.wcUpdateFixture <round> "Old Home" "Old Away" "New Home" "New Away"`"""
        args = shlex.split(ctx.message.content)
        if len(args) != 6:
            await ctx.reply('Usage: `.wcUpdateFixture <round> "Old Home" "Old Away" "New Home" "New Away"`')
            return

        round = args[1]
        old_home, old_away, new_home, new_away = args[2], args[3], args[4], args[5]

        if round in ("1", "2", "3"):
            gameweek = int(round)
        elif round in STAGE_MAP:
            _, gameweek, _ = STAGE_MAP[round]
        else:
            await ctx.reply("Invalid round. Use: `.wcUpdateFixture <1|2|3|32|16|8|4|final> ...`")
            return

        db: Session = ctx.bot.db

        fixture = db.execute(
            select(WCFixture).where(
                WCFixture.gameweek == gameweek,
                WCFixture.home == old_home.strip().lower(),
                WCFixture.away == old_away.strip().lower(),
            )
        ).scalar_one_or_none()

        if fixture is None:
            await ctx.reply("Fixture not found.")
            return

        fixture.home = self._normalize_team_name(new_home)
        fixture.away = self._normalize_team_name(new_away)
        db.commit()
        await ctx.reply(f"Updated: `{old_home.title()} vs {old_away.title()}` → `{new_home.title()} vs {new_away.title()}`")

    @commands.command(hidden=True, name="wcDeleteFixture")
    @is_admin()
    async def wc_delete_fixture(self, ctx: commands.Context, round: str | None = None, home: str | None = None, away: str | None = None) -> None:
        """Delete a WC fixture and reindex. Usage: `.wcDeleteFixture <round> "Home" "Away"`"""
        if round is None or home is None or away is None:
            await ctx.reply('Usage: `.wcDeleteFixture <round> "Home" "Away"`')
            return

        if round in ("1", "2", "3"):
            gameweek = int(round)
        elif round in STAGE_MAP:
            _, gameweek, _ = STAGE_MAP[round]
        else:
            await ctx.reply("Invalid round. Use: `.wcDeleteFixture <1|2|3|32|16|8|4|final> ...`")
            return

        db: Session = ctx.bot.db

        fixture = db.execute(
            select(WCFixture).where(
                WCFixture.gameweek == gameweek,
                WCFixture.home == home.lower(),
                WCFixture.away == away.lower(),
            )
        ).scalar_one_or_none()

        if fixture is None:
            await ctx.reply("Fixture not found.")
            return

        deleted_index = fixture.order_index
        deleted_predictions = db.execute(
            delete(WCPrediction).where(
                WCPrediction.gameweek_id == gameweek,
                WCPrediction.match_index == deleted_index,
            )
        )
        db.execute(
            update(WCPrediction)
            .where(WCPrediction.gameweek_id == gameweek, WCPrediction.match_index > deleted_index)
            .values(match_index=WCPrediction.match_index + 1000)
        )
        db.execute(
            update(WCPrediction)
            .where(WCPrediction.gameweek_id == gameweek, WCPrediction.match_index >= deleted_index + 1001)
            .values(match_index=WCPrediction.match_index - 1001)
        )

        db.delete(fixture)

        remaining = (
            db.execute(
                select(WCFixture).where(WCFixture.gameweek == gameweek).order_by(WCFixture.order_index)
            )
            .scalars()
            .all()
        )
        for i, f in enumerate(remaining):
            f.order_index = i
        db.commit()

        await ctx.reply(
            f"Deleted `{home.title()} vs {away.title()}`, removed "
            f"{deleted_predictions.rowcount or 0} prediction(s), and reindexed."
        )


async def setup(bot: "PyBot"):
    await bot.add_cog(WorldCupCommands(bot))

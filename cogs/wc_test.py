# cogs/wc_test.py
import os
from collections import defaultdict
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord.ext import commands
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from db.models.wc_fixtures import WCFixture
from decorators.helpers import is_admin

if TYPE_CHECKING:
    from bot import PyBot

API_BASE = "https://api.football-data.org/v4"


class WorldCupTestCommands(commands.Cog):
    """Cog for World Cup 2026 test/debug commands."""

    def __init__(self, bot: "PyBot"):
        self.bot = bot

    @commands.command(hidden=True, name="wcTestFixtures")
    @is_admin()
    async def wc_test_fixtures(self, ctx: commands.Context) -> None:
        """Fetch current WC round fixtures from the API and display them without saving. Usage: `.wcTestFixtures`"""
        api_key = os.getenv("API_KEY_FOOTBALL")
        if api_key is None:
            await ctx.reply("There was an error with the api key")
            return

        headers = {"X-Auth-Token": api_key}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE}/competitions/WC",
                headers=headers,
            ) as resp:
                comp_data = await resp.json()

            current_matchday = comp_data.get("currentSeason", {}).get("currentMatchday")
            if current_matchday is None:
                await ctx.reply("Could not determine the current matchday from the API.")
                return

            async with session.get(
                f"{API_BASE}/competitions/WC/matches",
                headers=headers,
                params={"matchday": current_matchday},
            ) as resp:
                match_data = await resp.json()

        matches = match_data.get("matches", [])
        if not matches:
            await ctx.reply(f"No fixtures found for matchday {current_matchday}.")
            return

        embed = discord.Embed(
            title=f"[TEST] World Cup Fixtures — Matchday {current_matchday}",
            color=discord.Color.blue(),
        )

        groups: dict = defaultdict(list)
        for match in matches:
            group_key = match.get("group") or "Knockout Stage"
            groups[group_key].append(match)

        for i, group_name in enumerate(sorted(groups.keys())):
            formatted = group_name.replace("_", " ").title()
            fixtures_str = "\n".join(
                f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}"
                for m in groups[group_name]
            )
            embed.add_field(name=formatted, value=fixtures_str, inline=True)
            if (i + 1) % 2 == 0:
                embed.add_field(name="​", value="​", inline=True)

        await ctx.reply(embed=embed)

    @commands.command(hidden=True, name="wcTestPred")
    @is_admin()
    async def wc_test_pred(self, ctx: commands.Context, *scores: str) -> None:
        """Dry run of wcPredict — shows output without saving. Usage: `.wcTestPred 2-1 0-0 ...`"""
        db: Session = ctx.bot.db

        current_gameweek = db.execute(
            select(func.max(WCFixture.gameweek))
        ).scalar_one_or_none()

        current_fixtures = (
            db.execute(
                select(WCFixture)
                .where(and_(WCFixture.gameweek == current_gameweek, WCFixture.tallied == 0, WCFixture.result_added == 0))
                .order_by(WCFixture.order_index.asc())
            )
            .scalars()
            .all()
        )

        if len(current_fixtures) == 0:
            await ctx.reply("No active WC fixtures found.")
            return

        if len(scores) != len(current_fixtures):
            await ctx.reply(f"You must enter exactly {len(current_fixtures)} predictions.")
            return

        embed = discord.Embed(
            title=f"[TEST] WC Predictions for Gameweek: `{current_gameweek}`",
            color=discord.Color.gold(),
        )
        embed_desc = []
        for fixture, score in zip(current_fixtures, scores):
            try:
                home, away = map(int, score.split("-"))
            except ValueError:
                await ctx.reply(f"Invalid format: `{score}`. Use format like `2-1`.")
                return
            embed_desc.append(
                f"**{fixture.home.title()}** vs **{fixture.away.title()}** – Predicted: `{home}-{away}`"
            )

        embed.description = "\n".join(embed_desc)
        await ctx.reply(embed=embed)


async def setup(bot: "PyBot"):
    await bot.add_cog(WorldCupTestCommands(bot))
